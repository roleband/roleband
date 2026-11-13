/* Browser credentials stay in this tab. Only request-bound signatures leave it. */
type Session = { key_id: string; secret: string; origin: string };
const STORAGE = "roleband.local-session";
const encoder = new TextEncoder();
const hex64 = /^[0-9a-f]{64}$/;
const hex32 = /^[0-9a-f]{32}$/;
let ticket: string | null = null;
let current: Session | null = null;
let exchange: Promise<Session> | null = null;

export class LocalAuthenticationError extends Error {}

export function captureBrowserHandoff(): void {
  if (!window.location.hash.startsWith("#roleband=")) return;
  ticket = window.location.hash.slice("#roleband=".length);
  current = null;
  exchange = null;
  forgetStored();
  window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
}

function forgetStored(): void {
  try { window.sessionStorage.removeItem(STORAGE); } catch { /* Private browsing may refuse storage. */ }
}

function valid(value: unknown): value is Session {
  if (!value || typeof value !== "object") return false;
  const session = value as Partial<Session>;
  return typeof session.key_id === "string" && hex32.test(session.key_id)
    && typeof session.secret === "string" && hex64.test(session.secret)
    && session.origin === window.location.origin;
}

async function session(): Promise<Session | null> {
  captureBrowserHandoff();
  if (ticket !== null && exchange === null) {
    const handoff = ticket;
    ticket = null;
    exchange = (async () => {
      if (!hex64.test(handoff)) throw new LocalAuthenticationError("invalid-browser-handoff");
      const response = await fetch("/api/local-auth/browser-session", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket: handoff }),
        redirect: "error", cache: "no-store", credentials: "omit",
      });
      if (!response.ok) throw new LocalAuthenticationError("browser-handoff-refused");
      const received: unknown = await response.json();
      if (!valid(received)) throw new LocalAuthenticationError("invalid-browser-session");
      current = received;
      try { window.sessionStorage.setItem(STORAGE, JSON.stringify(received)); } catch { /* Keep the in-memory session. */ }
      return received;
    })();
  }
  if (exchange !== null) return exchange;
  if (current !== null) return current;
  try {
    const raw = window.sessionStorage.getItem(STORAGE);
    // Every request without a session reaches here, so storage is written only to drop a bad entry.
    if (raw === null) return null;
    const stored: unknown = JSON.parse(raw);
    if (valid(stored)) current = stored;
    else forgetStored();
  } catch { forgetStored(); }
  return current;
}

function hex(value: ArrayBuffer | Uint8Array): string {
  return [...new Uint8Array(value instanceof Uint8Array ? value.buffer : value)]
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function bytes(value: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(value.match(/../g) ?? [], (pair) => Number.parseInt(pair, 16));
}

async function digest(value: Uint8Array<ArrayBuffer>): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", value));
}

async function responseBytes(response: Response): Promise<Uint8Array<ArrayBuffer>> {
  const reader = response.clone().body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 16 * 1024 * 1024) {
        await reader.cancel();
        throw new LocalAuthenticationError("engine-response-too-large");
      }
      chunks.push(value);
    }
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  return body;
}

type Signed = { response: Response; authorization: string };

async function signedFetch(credential: Session, key: CryptoKey, url: string, target: URL, init?: RequestInit): Promise<Signed> {
  const method = init?.method ?? "GET";
  const stamp = String(Math.floor(Date.now() / 1000));
  const nonce = hex(crypto.getRandomValues(new Uint8Array(16)));
  const message = ["request-v1", credential.key_id, stamp, nonce, method, credential.origin,
    target.pathname + target.search, await digest(encoder.encode((init?.body as string | undefined) ?? ""))].join("\n");
  const signed = hex(await crypto.subtle.sign("HMAC", key, encoder.encode(message)));
  const authorization = /* not copy */ `RoleBand ${credential.key_id}:${stamp}:${nonce}:${signed}`;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", authorization);
  const response = await fetch(url, { ...init, headers, redirect: "error", cache: "no-store", credentials: "omit" });
  return { response, authorization };
}

/** Waits until the wall clock reads a later second than `than`, or reports that it did not within
 * two seconds, as when the clock is stepped back. */
async function laterSecond(than: number): Promise<boolean> {
  const deadline = performance.now() + 2000;
  while (Math.floor(Date.now() / 1000) <= than) {
    if (performance.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, Math.min(1000 - (Date.now() % 1000) + 1, 250)));
  }
  return true;
}

export async function localFetch(url: string, init?: RequestInit): Promise<Response> {
  const credential = await session();
  if (credential === null) return init === undefined ? fetch(url) : fetch(url, init);
  const target = new URL(url, window.location.origin);
  if (target.origin !== credential.origin || (init?.body !== undefined && typeof init.body !== "string")) {
    throw new LocalAuthenticationError("invalid-engine-request-target");
  }
  const key = await crypto.subtle.importKey("raw", bytes(credential.secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
  let { response, authorization } = await signedFetch(credential, key, url, target, init);
  // An API process refuses, with a 401 and no proof, a signature stamped in or before the second it
  // started, so a request that waited through an API restart comes back like this. The engine
  // accepts one signed in a later second than the refusal; a listener that is not the engine cannot
  // prove that one either. Other replies without a proof are not sent again: a route that fails
  // after a write answers 500 without one.
  if (response.status === 401 && !response.headers.has("X-RoleBand-Proof")
      && await laterSecond(Math.floor(Date.now() / 1000))) {
    void response.body?.cancel().catch(() => {});
    ({ response, authorization } = await signedFetch(credential, key, url, target, init));
  }
  const proof = response.headers.get("X-RoleBand-Proof") ?? "";
  const responseMessage = `response-v1\n${authorization}\n${response.status}\n${await digest(await responseBytes(response))}`;
  if (!hex64.test(proof) || !await crypto.subtle.verify("HMAC", key, bytes(proof), encoder.encode(responseMessage))) {
    current = null;
    forgetStored();
    // Hold the refusal until a fresh app handoff instead of falling back to an unsigned request.
    exchange = Promise.reject(new LocalAuthenticationError("engine-identity-unverified"));
    void exchange.catch(() => {});
    throw new LocalAuthenticationError("engine-identity-unverified");
  }
  return response;
}
