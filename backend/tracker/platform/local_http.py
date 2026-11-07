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
#: Clock corrections up to this, backwards, keep the keys (see `Authority._wall`).
TOLERATED_STEP_SECONDS = WINDOW_SECONDS
_NONCE_RETENTION = 2 * WINDOW_SECONDS + TOLERATED_STEP_SECONDS
#: Browser sessions one engine keeps; opening another ends the oldest.
BROWSER_SESSIONS = 32
#: Set by the desktop supervisor for its API: adopt the engine's browser address and keys.
SESSION_ENV = "ROLEBAND_ENGINE_SESSION"
_SESSION_LIMIT = 64 * 1024
_HEX = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[0-9a-f]{32}$")


class AuthenticationError(ValueError):
    """The endpoint or request cannot prove possession of this account's key."""


def _elapsed() -> float:
    """Seconds on a clock that wall-clock changes cannot move: lifetimes and replay memory."""
    return time.monotonic()


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


def session_path(data: Path) -> Path:
    return data / "launcher" / "engine-session.json"


def _write(path: Path, payload: bytes) -> None:
    if sys.platform == "win32":
        from tracker.platform.windows_fs import publish

        publish(path, payload)
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def begin_engine_session(data: Path) -> None:
    """Give one engine a fresh browser address and no browser keys.

    Its API processes adopt both, so restarting the API keeps open tabs working;
    the next engine starts over.
    """
    path = session_path(data)
    for folder in (data, path.parent):
        _private(folder, directory=True)
    if path.exists() or path.is_symlink():
        _private(path)
    _write(path, json.dumps({"format": 1, "instance": secrets.token_hex(16), "browser": {}}).encode())


def end_engine_session(data: Path) -> None:
    session_path(data).unlink(missing_ok=True)


def _session(path: Path) -> tuple[str, dict[str, str]]:
    _private(path)
    if path.stat().st_size > _SESSION_LIMIT:
        raise ValueError("The engine session record exceeds its size limit")
    record = json.loads(path.read_bytes())
    browser = record.get("browser") if isinstance(record, dict) else None
    if (record.get("format") != 1 or not isinstance(record.get("instance"), str)
            or not _NONCE.fullmatch(record["instance"]) or not isinstance(browser, dict)
            or len(browser) > BROWSER_SESSIONS
            or not all(isinstance(key, str) and _NONCE.fullmatch(key) and isinstance(value, str)
                       and _HEX.fullmatch(value) for key, value in browser.items())):
        raise ValueError("The engine session record is damaged")
    return record["instance"], browser


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
    #: Signatures stamped earlier were made for another API process, whose replay
    #: memory this one does not have.
    not_before: int = 0


class Authority:
    """One process owns discovery, ephemeral browser keys and replay memory."""

    def __init__(self, data: Path, endpoint: str, *, engine_session: bool = False) -> None:
        parsed = urlsplit(endpoint)
        if endpoint != origin(parsed.hostname or "", parsed.port or 0):
            raise ValueError("Invalid authenticated engine origin")
        self.secret = secrets.token_hex(32)
        self._session_path = session_path(data) if engine_session else None
        adopted: dict[str, str] = {}
        if self._session_path is not None:
            self.instance, adopted = _session(self._session_path)
        else:
            self.instance = secrets.token_hex(16)
        self.endpoint = f"http://{self.instance}.localhost:{parsed.port}"
        self._guard = threading.RLock()
        born = int(time.time())
        self._keys = {"control": Credential(self.secret, float("inf")),
                      **{key: Credential(value, float("inf"), born) for key, value in adopted.items()}}
        self._used: dict[tuple[str, str], float] = {}
        self._tickets: dict[str, float] = {}
        self._highest_wall = time.time()
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
            self._publish(self.secret)
        except BaseException:
            self._lock = None
            os.close(descriptor)
            raise

    def _publish(self, secret: str) -> None:
        # The native host reads discovery before every request.
        _write(self.path, json.dumps({"format": 1, "origin": self.endpoint, "instance": self.instance,
                                      "secret": secret, "pid": os.getpid()}).encode())

    def _remember(self, keys: dict[str, Credential]) -> None:
        """Record the browser keys a later API process of this engine adopts, before using them."""
        if self._session_path is not None:
            browser = {name: key.secret for name, key in keys.items() if name != "control"}
            _write(self._session_path, json.dumps({"format": 1, "instance": self.instance,
                                                   "browser": browser}).encode())

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
                wall, elapsed = self._wall(), _elapsed()
                key = self._keys[key_id]
                if (scheme != SCHEME or not stamp.isascii() or not stamp.isdecimal()
                        or abs(wall - int(stamp)) > WINDOW_SECONDS or key.expires <= elapsed
                        or int(stamp) < key.not_before
                        or not _NONCE.fullmatch(nonce) or not _HEX.fullmatch(signed)
                        or len(body) > MAX_BODY):
                    raise AuthenticationError("Invalid authentication")
                expected = signature(key.secret, key_id, stamp, nonce, method, target, self.endpoint, body)
                if not hmac.compare_digest(expected, signed):
                    raise AuthenticationError("Invalid authentication")
                if key_id != "control" and unquote(target.partition("?")[0]).startswith("/api/local-auth/"):
                    raise AuthenticationError("Browser sessions cannot issue handoffs")
                self._used = {item: until for item, until in self._used.items() if until > elapsed}
                token = (key_id, nonce)
                if token in self._used or len(self._used) >= 8192:
                    raise AuthenticationError("Replayed authentication or replay memory full")
                self._used[token] = elapsed + _NONCE_RETENTION
                return key
            except (KeyError, ValueError, OverflowError) as error:
                raise AuthenticationError("Invalid authentication") from error

    def issue_ticket(self) -> dict[str, str | int]:
        with self._guard:
            self._wall()
            elapsed = _elapsed()
            self._tickets = {ticket: until for ticket, until in self._tickets.items() if until > elapsed}
            if len(self._tickets) >= 16:
                raise AuthenticationError("Too many pending browser handoffs")
            ticket = secrets.token_hex(32)
            self._tickets[ticket] = elapsed + 60
            return {"url": f"{self.endpoint}/#roleband={ticket}", "expires_in": 60}

    def redeem(self, ticket: str) -> dict[str, str]:
        with self._guard:
            self._wall()
            elapsed = _elapsed()
            if not _HEX.fullmatch(ticket) or self._tickets.pop(ticket, 0) <= elapsed:
                raise AuthenticationError("Invalid browser handoff")
            keys = dict(self._keys)
            browser = [name for name in keys if name != "control"]
            for name in browser[:max(0, len(browser) - BROWSER_SESSIONS + 1)]:
                del keys[name]
            key_id, secret = secrets.token_hex(16), secrets.token_hex(32)
            keys[key_id] = Credential(secret, float("inf"))
            self._remember(keys)
            self._keys = keys
            return {"key_id": key_id, "secret": secret, "origin": self.endpoint}

    def _wall(self) -> float:
        """The wall clock that signature stamps are checked against.

        Nonces are kept long enough that a backward step of up to
        `TOLERATED_STEP_SECONDS` in all cannot make a used signature fresh again.
        A larger step replaces the control key and ends browser sessions instead,
        so nothing signed before it verifies; clients read the new key from
        discovery on their next request."""
        now = time.time()
        if now < self._highest_wall - TOLERATED_STEP_SECONDS:
            if self._lock is None:
                raise AuthenticationError("The engine authority is closed")
            # Stored browser keys are dropped first, so no later API process adopts one from
            # before the step. Discovery is published before the swap: if it fails, the
            # advertised key is still the one in use.
            self._remember({})
            replacement = secrets.token_hex(32)
            self._publish(replacement)
            self.secret = replacement
            self._keys = {"control": Credential(replacement, float("inf"))}
            self._tickets.clear()
            self._used.clear()
            self._highest_wall = now
        self._highest_wall = max(self._highest_wall, now)
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
        if sys.platform == "win32":
            from tracker.platform.windows_fs import RecordTooLarge, read_private

            try:
                payload = read_private(path, 8192)
            except RecordTooLarge as error:
                raise AuthenticationError("Engine discovery is too large") from error
        else:
            _private(path)
            if path.stat().st_size > 8192:
                raise AuthenticationError("Engine discovery is too large")
            payload = path.read_bytes()
        value = json.loads(payload)
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
