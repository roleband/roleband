/* Keeps the dev and preview servers' /api proxy to this computer.

   `vite --host` listens on every interface, and the proxy then connects to the
   API from 127.0.0.1, so the API's own check of the peer sees only the proxy.
   This middleware refuses a request for /api whose peer is not a loopback
   address before the proxy forwards it. Vite runs a plugin's middleware ahead
   of its own, the proxy included. */

const IPV4_LOOPBACK = /^127(\.\d{1,3}){3}$/;
const API_PREFIX = "/api";

/** True for a peer address on this computer's loopback: 127.0.0.0/8, ::1, ::ffff:127.x. */
export function isLoopbackPeer(address) {
  if (typeof address !== "string") return false;
  const value = address.toLowerCase().split("%", 1)[0];
  if (value === "::1" || value === "0:0:0:0:0:0:0:1") return true;
  const mapped = value.startsWith("::ffff:") ? value.slice("::ffff:".length) : value;
  return IPV4_LOOPBACK.test(mapped);
}

/** Connect middleware: answers 403 to a request for /api from another machine,
 *  passes the rest on. It tests the raw URL as the proxy does (any URL that starts
 *  with /api), not Connect's mount path, which would let `/api%2Fhealth` past: the
 *  proxy forwards it and the API decodes it to /api/health. */
function refuseRemote(req, res, next) {
  if (!req.url?.startsWith(API_PREFIX) || isLoopbackPeer(req.socket?.remoteAddress)) {
    next();
    return;
  }
  res.statusCode = 403;
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.end("Only this computer may reach the API");
}

export function loopbackApi() {
  return {
    name: "roleband-loopback-api",
    configureServer(server) {
      server.middlewares.use(refuseRemote);
    },
    configurePreviewServer(server) {
      server.middlewares.use(refuseRemote);
    },
  };
}
