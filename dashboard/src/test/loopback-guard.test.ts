/* The dev and preview servers' /api proxy serves this computer only. A real Vite
   server with the real config's proxy runs in front of a stand-in API; a plugin
   placed ahead of the guard makes a request look as if another machine sent it,
   which is the one thing a test on loopback cannot do for real. */
import http from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import { createServer, type Plugin, type ProxyOptions, type ViteDevServer } from "vite";
import config from "../../vite.config";
import { isLoopbackPeer, loopbackApi } from "../../scripts/dev/loopback-guard.mjs";

describe("isLoopbackPeer", () => {
  it.each(["127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1", "0:0:0:0:0:0:0:1"])("%s is this computer", (peer) => {
    expect(isLoopbackPeer(peer)).toBe(true);
  });

  it.each(["192.168.1.5", "10.0.0.1", "::ffff:192.168.1.5", "fe80::1%en0", "127.evil", "1127.0.0.1", "", undefined])(
    "%s is not",
    (peer) => {
      expect(isLoopbackPeer(peer)).toBe(false);
    },
  );
});

describe("the real config", () => {
  const proxies = [config.server?.proxy?.["/api"], config.preview?.proxy?.["/api"]] as ProxyOptions[];

  it("puts the guard ahead of every other plugin", () => {
    const plugins = (config.plugins ?? []).flat() as Plugin[];
    expect(plugins[0]?.name).toBe("roleband-loopback-api");
  });

  it("forwards the browser's own Host to the API on both servers", () => {
    for (const proxy of proxies) {
      expect(proxy?.target).toBeTruthy();
      expect(proxy?.changeOrigin).not.toBe(true);
    }
  });
});

describe("a dev server with the guard", () => {
  const closers: Array<() => Promise<void>> = [];
  afterEach(async () => {
    await Promise.all(closers.splice(0).map((close) => close()));
  });

  async function stack(peer: string | null) {
    const seen: http.IncomingHttpHeaders[] = [];
    const api = http.createServer((req, res) => {
      seen.push(req.headers);
      res.end("api");
    });
    await new Promise<void>((resolve) => api.listen(0, "127.0.0.1", resolve));
    closers.push(() => new Promise((resolve) => api.close(() => resolve())));
    const disguise: Plugin = {
      name: "remote-peer",
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          if (peer) Object.defineProperty(req.socket, "remoteAddress", { value: peer, configurable: true });
          next();
        });
      },
    };
    const target = `http://127.0.0.1:${(api.address() as AddressInfo).port}`;
    const server: ViteDevServer = await createServer({
      configFile: false,
      logLevel: "silent",
      plugins: [disguise, loopbackApi()],
      server: { host: "127.0.0.1", port: 0, proxy: { "/api": { ...config.server?.proxy?.["/api"] as ProxyOptions, target } } },
    });
    await server.listen();
    closers.push(() => server.close());
    const port = (server.httpServer?.address() as AddressInfo).port;
    return { seen, url: `http://127.0.0.1:${port}/api/health` };
  }

  it("forwards a request from this computer with its Host", async () => {
    const { seen, url } = await stack(null);
    const response = await fetch(url);
    expect(await response.text()).toBe("api");
    expect(seen).toHaveLength(1);
    expect(seen[0].host).toBe(new URL(url).host);
  });

  it("refuses a request from another machine before the proxy forwards it", async () => {
    const { seen, url } = await stack("192.168.1.5");
    const response = await fetch(url);
    expect(response.status).toBe(403);
    expect(seen).toHaveLength(0);
  });
});
