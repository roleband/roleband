"""Private discovery and request-bound authentication for an account's HTTP engine."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tracker.platform import filelock
from tracker.platform.paths import PACKAGED

SCHEME = "RoleBand"
PROOF_HEADER = "X-RoleBand-Proof"
TICKET_PATH = "/api/local-auth/browser-ticket"
SESSION_PATH = "/api/local-auth/browser-session"
MAX_BODY = 16 * 1024 * 1024
WINDOW_SECONDS = 45
_HEX = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[0-9a-f]{32}$")


class AuthenticationError(ValueError):
    """The endpoint or request cannot prove possession of this account's key."""


def required() -> bool:
    return (sys.platform == "win32" and PACKAGED) or os.environ.get("ROLEBAND_LOCAL_AUTH") == "1"


def origin(host: str, port: int) -> str:
    if host != "127.0.0.1" or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Authenticated engine HTTP requires 127.0.0.1 and a valid port")
    return f"http://127.0.0.1:{port}"


def _endpoint(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    host, port = parsed.hostname or "", parsed.port or 0
    if (not host.endswith(".localhost") or not _NONCE.fullmatch(host.removesuffix(".localhost"))
            or not 1 <= port <= 65535 or value != f"http://{host}:{port}"):
        raise AuthenticationError("Invalid engine discovery origin")
    return host, port


def _private(path: Path, *, directory: bool = False) -> None:
    if sys.platform == "win32":
        from tracker.platform.windows_private import private_directory, require_private

        if directory:
            private_directory(path)
        else:
            require_private(path)
        return
    if directory:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    wanted = stat.S_ISDIR if directory else stat.S_ISREG
    if not wanted(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("HTTP discovery must be private to this account")


def record_path(data: Path) -> Path:
    return data / "launcher" / "http-engine.json"


def _mac(secret: str, message: str) -> str:
    return hmac.new(bytes.fromhex(secret), message.encode("utf-8"), hashlib.sha256).hexdigest()


def signature(secret: str, key_id: str, stamp: str, nonce: str, method: str,
              target: str, endpoint: str, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    return _mac(secret, "\n".join(("request-v1", key_id, stamp, nonce, method, endpoint, target, digest)))


def authorization(secret: str, key_id: str, method: str, target: str, endpoint: str,
                  body: bytes = b"") -> str:
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    signed = signature(secret, key_id, stamp, nonce, method, target, endpoint, body)
    return f"{SCHEME} {key_id}:{stamp}:{nonce}:{signed}"


def response_proof(secret: str, authorization_header: str, status: int, body: bytes = b"") -> str:
    return _mac(secret, f"response-v1\n{authorization_header}\n{status}\n{hashlib.sha256(body).hexdigest()}")


@dataclass(frozen=True)
class Credential:
    secret: str
    expires: float


class Authority:
    """One process owns discovery, ephemeral browser keys and replay memory."""

    def __init__(self, data: Path, endpoint: str) -> None:
        parsed = urlsplit(endpoint)
        if endpoint != origin(parsed.hostname or "", parsed.port or 0):
            raise ValueError("Invalid authenticated engine origin")
        self.secret = secrets.token_hex(32)
        self.instance = secrets.token_hex(16)
        self.endpoint = f"http://{self.instance}.localhost:{parsed.port}"
        self._guard = threading.RLock()
        self._keys = {"control": Credential(self.secret, float("inf"))}
        self._used: dict[tuple[str, str], float] = {}
        self._tickets: dict[str, float] = {}
        self._highest_wall = time.time()
        self._clock_invalid = False
        self.path = record_path(data)
        self._lock: int | None = None
        for folder in (data, self.path.parent):
            _private(folder, directory=True)
        lock = self.path.with_suffix(".lock")
        if lock.exists() or lock.is_symlink():
            _private(lock)
        flags = os.O_CREAT | os.O_RDWR
        if sys.platform != "win32":
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock, flags, 0o600)
        try:
            filelock.lock(descriptor, blocking=False)
            self._lock = descriptor
            if self.path.exists() or self.path.is_symlink():
                _private(self.path)
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".http-engine-")
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(json.dumps({"format": 1, "origin": self.endpoint, "instance": self.instance,
                                             "secret": self.secret, "pid": os.getpid()}).encode())
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        except BaseException:
            self._lock = None
            os.close(descriptor)
            raise

    def close(self) -> None:
        with self._guard:
            if self._lock is not None:
                try:
                    self.path.unlink(missing_ok=True)
                finally:
                    os.close(self._lock)
                    self._lock = None
            self._keys.clear()
            self._tickets.clear()
            self._used.clear()

    def authenticate(self, header: str, method: str, target: str, body: bytes) -> Credential:
        with self._guard:
            try:
                scheme, value = header.split(" ", 1)
                key_id, stamp, nonce, signed = value.split(":")
                now = self._now()
                key = self._keys[key_id]
                if (scheme != SCHEME or not stamp.isascii() or not stamp.isdecimal()
                        or abs(now - int(stamp)) > WINDOW_SECONDS or key.expires <= now
                        or not _NONCE.fullmatch(nonce) or not _HEX.fullmatch(signed)
                        or len(body) > MAX_BODY):
                    raise AuthenticationError("Invalid authentication")
                expected = signature(key.secret, key_id, stamp, nonce, method, target, self.endpoint, body)
                if not hmac.compare_digest(expected, signed):
                    raise AuthenticationError("Invalid authentication")
                if key_id != "control" and unquote(target.partition("?")[0]).startswith("/api/local-auth/"):
                    raise AuthenticationError("Browser sessions cannot issue handoffs")
                self._used = {item: expiry for item, expiry in self._used.items() if expiry > now}
                token = (key_id, nonce)
                if token in self._used or len(self._used) >= 8192:
                    raise AuthenticationError("Replayed authentication or replay memory full")
                self._used[token] = int(stamp) + WINDOW_SECONDS + 1
                return key
            except (KeyError, ValueError, OverflowError) as error:
                raise AuthenticationError("Invalid authentication") from error

    def issue_ticket(self) -> dict[str, str | int]:
        with self._guard:
            now = self._now()
            self._tickets = {ticket: until for ticket, until in self._tickets.items() if until > now}
            if len(self._tickets) >= 16:
                raise AuthenticationError("Too many pending browser handoffs")
            ticket = secrets.token_hex(32)
            self._tickets[ticket] = now + 60
            return {"url": f"{self.endpoint}/#roleband={ticket}", "expires_in": 60}

    def redeem(self, ticket: str) -> dict[str, str]:
        with self._guard:
            now = self._now()
            if not _HEX.fullmatch(ticket) or self._tickets.pop(ticket, 0) <= now:
                raise AuthenticationError("Invalid browser handoff")
            self._keys = {name: key for name, key in self._keys.items() if key.expires > now}
            if len(self._keys) >= 33:
                raise AuthenticationError("Too many browser sessions")
            key_id, secret = secrets.token_hex(16), secrets.token_hex(32)
            self._keys[key_id] = Credential(secret, now + 8 * 60 * 60)
            return {"key_id": key_id, "secret": secret, "origin": self.endpoint}

    def _now(self) -> float:
        now = time.time()
        # A clock rollback must not make an expired signature valid again after
        # its nonce is pruned. Health refusal lets the supervisor rotate keys.
        if self._clock_invalid or now < self._highest_wall:
            self._clock_invalid = True
            self._keys.clear()
            self._tickets.clear()
            raise AuthenticationError("The engine authentication clock moved backwards")
        self._highest_wall = now
        return now


class Client:
    """A native client sends signatures, never the private discovery key."""

    def __init__(self, data: Path) -> None:
        path = record_path(data)
        for folder in (data, path.parent):
            # Reading discovery must not create directories or alter their ACLs.
            if not folder.is_dir():
                raise AuthenticationError("Engine discovery is unavailable")
            if sys.platform == "win32":
                from tracker.platform.windows_private import require_private

                require_private(folder)
            else:
                info = folder.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise PermissionError("HTTP discovery must be private to this account")
        _private(path)
        if path.stat().st_size > 8192:
            raise AuthenticationError("Engine discovery is too large")
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise AuthenticationError("Invalid engine discovery")
        endpoint, secret = value.get("origin", ""), value.get("secret", "")
        if not isinstance(endpoint, str):
            raise AuthenticationError("Invalid engine discovery")
        host, port = _endpoint(endpoint)
        if (type(value.get("format")) is not int or value["format"] != 1
                or not isinstance(secret, str) or not _HEX.fullmatch(secret)
                or value.get("instance") != host.removesuffix(".localhost")):
            raise AuthenticationError("Invalid engine discovery")
        self.endpoint, self.secret, self.port = endpoint, secret, port

    def request(self, method: str, target: str, body: bytes = b"") -> tuple[int, bytes]:
        if not target.startswith("/") or target.startswith("//") or "\r" in target or "\n" in target:
            raise ValueError("Engine requests require an origin-relative target")
        signed = authorization(self.secret, "control", method, target, self.endpoint, body)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, target, body=body,
                               headers={"Authorization": signed, "Content-Type": "application/json",
                                        "Host": self.endpoint.removeprefix("http://")})
            response = connection.getresponse()
            content = response.read(MAX_BODY + 1)
            if len(content) > MAX_BODY:
                raise AuthenticationError("Engine response is too large")
            proof = response.getheader(PROOF_HEADER, "")
            if not hmac.compare_digest(proof, response_proof(self.secret, signed, response.status, content)):
                raise AuthenticationError("The listener did not authenticate as this engine")
            return response.status, content
        finally:
            connection.close()

    def browser_url(self) -> str:
        status, content = self.request("POST", TICKET_PATH, b"{}")
        if status != 200:
            raise AuthenticationError("Browser handoff refused")
        value = json.loads(content)
        url = value.get("url", "")
        prefix = f"{self.endpoint}/#roleband="
        if not isinstance(url, str) or not url.startswith(prefix) or not _HEX.fullmatch(url[len(prefix):]):
            raise AuthenticationError("Invalid browser handoff response")
        return url
