import { createHash, createHmac, webcrypto } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";

const secret = "a7".repeat(32);
const keyId = "b4".repeat(16);
const ticket = "c5".repeat(32);
const storage = "roleband.local-session";
const digest = (value: string) => createHash("sha256").update(value).digest("hex");
const mac = (value: string) => createHmac("sha256", Buffer.from(secret, "hex")).update(value).digest("hex");

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("crypto", webcrypto);
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("local browser authentication", () => {
  it("removes a private handoff from the address before network access, then exchanges it once for concurrent reads", async () => {
    window.history.replaceState(null, "", `/?source=app#roleband=${ticket}`);
    let exchanges = 0;
    const nonces = new Set<string>();
    const network = vi.fn(async (url: string, init?: RequestInit) => {
      expect(window.location.hash).toBe("");
      if (url === "/api/local-auth/browser-session") {
        exchanges += 1;
        expect(JSON.parse(init!.body as string)).toEqual({ ticket });
        expect(init!.redirect).toBe("error");
        expect(init!.credentials).toBe("omit");
        return new Response(JSON.stringify({ key_id: keyId, secret, origin: window.location.origin }));
      }
      const authorization = new Headers(init?.headers).get("Authorization")!;
      expect(authorization).not.toContain(secret);
      const [id, stamp, nonce, signed] = authorization.slice("RoleBand ".length).split(":");
      expect(id).toBe(keyId);
      expect(nonces.has(nonce!)).toBe(false);
      nonces.add(nonce!);
      const canonical = ["request-v1", id, stamp, nonce, init?.method ?? "GET", window.location.origin, url, digest("")].join("\n");
      expect(signed).toBe(mac(canonical));
      const body = JSON.stringify({ sentinel: "account-private-history" });
      return new Response(body, { headers: { "X-RoleBand-Proof": mac(`response-v1\n${authorization}\n200\n${digest(body)}`) } });
    });
    vi.stubGlobal("fetch", network);
    const { captureBrowserHandoff, localFetch } = await import("./localAuthentication");
    captureBrowserHandoff();
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("?source=app");
    expect(network).not.toHaveBeenCalled();
    const [first, second] = await Promise.all([localFetch("/api/read?first=1"), localFetch("/api/read?second=2")]);
    expect(await first.json()).toEqual({ sentinel: "account-private-history" });
    expect(await second.json()).toEqual({ sentinel: "account-private-history" });
    expect(exchanges).toBe(1);
    expect(nonces.size).toBe(2);
    expect(window.sessionStorage.getItem(storage)).not.toContain(ticket);
  });

  it("signs the exact Unicode JSON body and forwards cancellation", async () => {
    window.sessionStorage.setItem(storage, JSON.stringify({ key_id: keyId, secret, origin: window.location.origin }));
    const body = JSON.stringify({ value: "你好, café" });
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      const authorization = new Headers(init.headers).get("Authorization")!;
      const [id, stamp, nonce, signed] = authorization.slice("RoleBand ".length).split(":");
      expect(signed).toBe(mac(["request-v1", id, stamp, nonce, "POST", window.location.origin, url, digest(body)].join("\n")));
      expect(init.signal).toBe(controller.signal);
      expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
      const response = '{"saved":true}';
      return new Response(response, { headers: { "X-RoleBand-Proof": mac(`response-v1\n${authorization}\n200\n${digest(response)}`) } });
    }));
    const { localFetch } = await import("./localAuthentication");
    const response = await localFetch("/api/write?save=1", { method: "POST", body, signal: controller.signal, headers: { "Content-Type": "application/json" } });
    expect(await response.json()).toEqual({ saved: true });
  });

  it.each(["missing", "altered-body", "redirect"])("refuses a %s response and holds the refusal without unsigned retries", async (failure) => {
    window.sessionStorage.setItem(storage, JSON.stringify({ key_id: keyId, secret, origin: window.location.origin }));
    const network = vi.fn(async (_url: string, init: RequestInit) => {
      const authorization = new Headers(init.headers).get("Authorization")!;
      if (failure === "redirect") throw new TypeError("Redirect refused");
      const headers: Record<string, string> = failure === "missing" ? {} : { "X-RoleBand-Proof": mac(`response-v1\n${authorization}\n200\n${digest('{"sentinel":"private"}')}`) };
      return new Response('{"sentinel":"foreign"}', { headers });
    });
    vi.stubGlobal("fetch", network);
    const { localFetch } = await import("./localAuthentication");
    await expect(localFetch("/api/read")).rejects.toThrow();
    if (failure !== "redirect") {
      expect(window.sessionStorage.getItem(storage)).toBeNull();
      await expect(localFetch("/api/read")).rejects.toThrow();
      // A reply with no proof at all is signed once more before the tab locks; a wrong proof is not.
      expect(network).toHaveBeenCalledTimes(failure === "missing" ? 2 : 1);
    }
    expect(network.mock.calls[0]?.[1]?.redirect).toBe("error");
  });

  it.each([
    ["read", "GET", undefined],
    ["write", "POST", '{"value":"café"}'],
  ])("signs a %s refused during an API restart again, in a later second, and keeps the session", async (_case, method, body) => {
    window.sessionStorage.setItem(storage, JSON.stringify({ key_id: keyId, secret, origin: window.location.origin }));
    let started: number | null = null;
    const seen: { stamp: number; nonce: string }[] = [];
    const network = vi.fn(async (url: string, init: RequestInit) => {
      const authorization = new Headers(init.headers).get("Authorization")!;
      const [id, stamp, nonce, signed] = authorization.slice("RoleBand ".length).split(":");
      expect(signed).toBe(mac(["request-v1", id, stamp, nonce, method, window.location.origin, url, digest(body ?? "")].join("\n")));
      expect(init.body).toBe(body);
      seen.push({ stamp: Number(stamp), nonce: nonce! });
      // The new API process started while this request waited; it accepts only later stamps.
      started ??= Math.floor(Date.now() / 1000);
      if (Number(stamp) <= started) return new Response('{"detail":"locked"}', { status: 401 });
      const reply = '{"sentinel":"account-private-history"}';
      return new Response(reply, { headers: { "X-RoleBand-Proof": mac(`response-v1\n${authorization}\n200\n${digest(reply)}`) } });
    });
    vi.stubGlobal("fetch", network);
    const { localFetch } = await import("./localAuthentication");
    const response = await localFetch("/api/read", { method, body });
    expect(await response.json()).toEqual({ sentinel: "account-private-history" });
    expect(network).toHaveBeenCalledTimes(2);
    expect(seen[1]!.stamp).toBeGreaterThan(started!);
    expect(seen[1]!.nonce).not.toBe(seen[0]!.nonce);
    expect(window.sessionStorage.getItem(storage)).not.toBeNull();
    await localFetch("/api/read", { method, body });
    expect(network).toHaveBeenCalledTimes(3);
  });

  it("locks the tab when the second signature also comes back without a proof", async () => {
    window.sessionStorage.setItem(storage, JSON.stringify({ key_id: keyId, secret, origin: window.location.origin }));
    const stamps: number[] = [];
    const network = vi.fn(async (_url: string, init: RequestInit) => {
      stamps.push(Number(new Headers(init.headers).get("Authorization")!.split(":")[1]));
      return new Response('{"sentinel":"foreign"}', { status: 401 });
    });
    vi.stubGlobal("fetch", network);
    const { localFetch, LocalAuthenticationError } = await import("./localAuthentication");
    await expect(localFetch("/api/read")).rejects.toBeInstanceOf(LocalAuthenticationError);
    expect(network).toHaveBeenCalledTimes(2);
    expect(stamps[1]).toBeGreaterThan(stamps[0]!);
    expect(window.sessionStorage.getItem(storage)).toBeNull();
    await expect(localFetch("/api/read")).rejects.toBeInstanceOf(LocalAuthenticationError);
    expect(network).toHaveBeenCalledTimes(2);
  });

  it("refuses to send credentials to another origin", async () => {
    window.sessionStorage.setItem(storage, JSON.stringify({ key_id: keyId, secret, origin: window.location.origin }));
    const network = vi.fn();
    vi.stubGlobal("fetch", network);
    const { localFetch } = await import("./localAuthentication");
    await expect(localFetch("http://outside.invalid/api/read")).rejects.toThrow();
    expect(network).not.toHaveBeenCalled();
  });

  it("preserves unsigned source development requests without a browser session", async () => {
    const response = new Response('{"source":true}');
    const network = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", network);
    const { localFetch } = await import("./localAuthentication");
    expect(await localFetch("/api/read")).toBe(response);
    expect(network).toHaveBeenCalledExactlyOnceWith("/api/read");
  });

  it("leaves storage alone on requests without a browser session", async () => {
    const network = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", network);
    const items = new Map<string, string>();
    const writes: string[] = [];
    const recording = {
      getItem: (key: string) => items.get(key) ?? null,
      setItem: (key: string, value: string) => { writes.push(`set ${key}`); items.set(key, value); },
      removeItem: (key: string) => { writes.push(`remove ${key}`); items.delete(key); },
    };
    const stored = vi.spyOn(window, "sessionStorage", "get").mockReturnValue(recording as unknown as Storage);
    try {
      const { localFetch } = await import("./localAuthentication");
      await localFetch("/api/read");
      await localFetch("/api/write", { method: "POST", body: "{}" });
      expect(network).toHaveBeenCalledTimes(2);
      expect(writes).toEqual([]);
    } finally {
      stored.mockRestore();
    }
  });

  it.each([
    ["another origin", JSON.stringify({ key_id: keyId, secret, origin: "http://outside.invalid" })],
    ["damaged", "{not json"],
  ])("drops a stored session from %s and sends unsigned", async (_case, stored) => {
    window.sessionStorage.setItem(storage, stored);
    const network = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", network);
    const { localFetch } = await import("./localAuthentication");
    await localFetch("/api/read");
    expect(window.sessionStorage.getItem(storage)).toBeNull();
    expect(network).toHaveBeenCalledExactlyOnceWith("/api/read");
  });
});
