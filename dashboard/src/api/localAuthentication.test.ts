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
      expect(network).toHaveBeenCalledTimes(1);
    }
    expect(network.mock.calls[0]?.[1]?.redirect).toBe("error");
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
});
