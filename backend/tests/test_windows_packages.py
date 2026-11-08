"""An update package is kept only once it matches what the owner signed, and the way back stays."""

from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from tracker.platform import windows_packages
from tracker.platform.windows_packages import download, folder, retained
from tracker.platform.windows_release import Identity, ReleaseError, prepare, verify_offer

FEED = "roleband/roleband-trials"


@pytest.fixture
def key():
    return ed25519.Ed25519PrivateKey.generate()


@pytest.fixture
def identity(key):
    return Identity(FEED, key.public_key().public_bytes_raw(), "RoleBand.Windows.Trial", "CN=RoleBand Windows Trial")


class Server:
    def __init__(self, tmp_path, key, identity):
        self.tmp_path, self.key, self.identity = tmp_path, key, identity
        self.content: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.cut_after: int | None = None
        self.ignore_range = False
        self.content_range: str | None = None
        self.serve: bytes | None = None
        self.redirect_to = "https://release-assets.githubusercontent.com/objects/{name}"

    def release(self, version, size=200_000):
        package = self.tmp_path / f"{version}.msix"
        package.write_bytes(bytes((index * 7 + len(version)) % 251 for index in range(size)))
        files = prepare(package, self.tmp_path / f"r-{version}", self.identity, self.key,
                        version=version, revision=0, commit="d" * 40)
        for path in files:
            self.content[path.name] = path.read_bytes()
        signed = tuple(path.read_bytes() for path in files[1:])
        return verify_offer(self.identity, "0.0.0", *signed), signed

    def handler(self, request):
        self.requests.append(request)
        url = str(request.url)
        if url.startswith(f"https://github.com/{FEED}/releases/download/"):
            return httpx.Response(302, headers={"Location": self.redirect_to.format(name=url.rsplit("/", 1)[1])})
        if not url.startswith("https://release-assets.githubusercontent.com/objects/"):
            return httpx.Response(404)
        name = url.rsplit("/", 1)[1]
        if name not in self.content:
            return httpx.Response(404)
        body = self.serve if self.serve is not None and name.endswith(".msix") else self.content[name]
        start = 0
        if "Range" in request.headers and not self.ignore_range:
            start = int(request.headers["Range"].removeprefix("bytes=").rstrip("-"))
            headers = {"Content-Range": self.content_range or f"bytes {start}-{len(body) - 1}/{len(body)}"}
            status = 206
        else:
            headers, status = {}, 200
        payload = body[start:]
        if self.cut_after is not None:
            cut, self.cut_after = self.cut_after, None
            return httpx.Response(status, headers=headers, stream=Interrupted(payload[:cut]))
        return httpx.Response(status, headers=headers, content=payload)

    @property
    def transport(self):
        return httpx.MockTransport(self.handler)


class Interrupted(httpx.SyncByteStream):
    def __init__(self, sent):
        self.sent = sent

    def __iter__(self):
        yield self.sent
        raise httpx.ReadError("connection lost")


@pytest.fixture
def server(tmp_path, key, identity):
    return Server(tmp_path, key, identity)


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"


def test_a_verified_package_is_retained_with_its_signed_files(state, identity, server):
    offer, signed = server.release("0.1.3")
    path = download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert path.read_bytes() == server.content[offer.package]
    assert [found.version for found, _ in retained(state, identity)] == ["0.1.3"]


def test_an_interrupted_download_resumes_where_it_stopped(state, identity, server):
    offer, signed = server.release("0.1.3")
    server.cut_after = 70_000
    with pytest.raises(httpx.ReadError):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert (folder(state) / f".{offer.package}.partial").stat().st_size == 70_000
    path = download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert server.requests[-1].headers["Range"] == "bytes=70000-"
    assert path.read_bytes() == server.content[offer.package]


def test_a_complete_partial_file_is_verified_without_asking_past_its_end(state, identity, server):
    """A stop between the last byte and the rename leaves the whole package as the partial file."""
    offer, signed = server.release("0.1.3")
    download(state, identity, offer, signed, "0.1.2", transport=server.transport).rename(
        folder(state) / f".{offer.package}.partial")
    server.requests.clear()
    path = download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert server.requests == [], "the bytes are all here; a range past the end is refused for ever"
    assert path.read_bytes() == server.content[offer.package]


def test_a_server_that_ignores_the_range_restarts_the_file(state, identity, server):
    offer, signed = server.release("0.1.3")
    server.cut_after = 50_000
    with pytest.raises(httpx.ReadError):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    server.ignore_range = True
    assert download(state, identity, offer, signed, "0.1.2", transport=server.transport).read_bytes() == \
        server.content[offer.package]


def test_a_resume_at_the_wrong_place_is_refused(state, identity, server):
    offer, signed = server.release("0.1.3")
    server.cut_after = 50_000
    with pytest.raises(httpx.ReadError):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    server.content_range = f"bytes 0-{offer.bytes - 1}/{offer.bytes}"
    with pytest.raises(ReleaseError, match="wrong place"):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert retained(state, identity) == []


def test_a_package_that_differs_from_its_signed_digest_is_discarded(state, identity, server):
    offer, signed = server.release("0.1.3")
    tampered = bytearray(server.content[offer.package])
    tampered[1234] ^= 1
    server.serve = bytes(tampered)
    with pytest.raises(ReleaseError, match="signed checksum"):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert retained(state, identity) == []
    assert not (folder(state) / f".{offer.package}.partial").exists(), "a wrong complete file cannot be resumed"


def test_a_package_larger_than_signed_is_refused_while_downloading(state, identity, server):
    offer, signed = server.release("0.1.3")
    server.serve = server.content[offer.package] + b"\0" * 10
    with pytest.raises(ReleaseError, match="larger"):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)


def test_the_package_comes_only_from_the_feed_and_its_cdn(state, identity, server):
    offer, signed = server.release("0.1.3")
    server.redirect_to = "https://mirror.example/objects/{name}"
    with pytest.raises(ReleaseError, match="outside"):
        download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    assert not any("mirror.example" in str(request.url) for request in server.requests)


def test_signed_files_for_another_release_cannot_carry_this_offer(state, identity, server):
    offer, _signed = server.release("0.1.3")
    _other, other_signed = server.release("0.1.4")
    with pytest.raises(ReleaseError, match="do not describe"):
        download(state, identity, offer, other_signed, "0.1.2", transport=server.transport)


def test_a_retained_package_that_changed_is_no_longer_a_way_back(state, identity, server):
    offer, signed = server.release("0.1.3")
    path = download(state, identity, offer, signed, "0.1.2", transport=server.transport)
    path.write_bytes(path.read_bytes()[:-1] + b"\0")
    assert retained(state, identity) == []


def test_the_newest_two_and_the_running_version_are_kept(state, identity, server):
    versions = ("0.1.3", "0.1.4", "0.1.5", "0.1.6")
    for version in versions:
        offer, signed = server.release(version, size=4096)
        download(state, identity, offer, signed, "0.1.3", transport=server.transport)
    assert [offer.version for offer, _ in retained(state, identity)] == ["0.1.6", "0.1.5", "0.1.3"]
    assert windows_packages.KEEP == 2


def test_the_running_versions_own_release_is_kept_as_the_way_back(state, identity, server):
    from tracker.platform.windows_packages import retain_running

    server.release("0.1.2")
    path = retain_running(state, identity, "0.1.2", transport=server.transport)
    assert [offer.version for offer, _ in retained(state, identity)] == ["0.1.2"]
    asked = len(server.requests)
    assert retain_running(state, identity, "0.1.2", transport=server.transport) == path
    assert len(server.requests) == asked, "a kept package is not fetched again"


def test_release_files_for_another_version_cannot_stand_in_for_the_running_one(state, identity, server):
    from tracker.platform.windows_packages import retain_running
    from tracker.platform.windows_release import names

    server.release("0.1.3")
    for real, posing in zip(names("0.1.3")[1:], names("0.1.2")[1:], strict=True):
        server.content[posing] = server.content[real]
    with pytest.raises(ReleaseError, match="another version"):
        retain_running(state, identity, "0.1.2", transport=server.transport)
    assert retained(state, identity) == []


def test_an_unpublished_running_version_leaves_no_way_back(state, identity, server):
    from tracker.platform.windows_packages import retain_running

    with pytest.raises(ReleaseError):
        retain_running(state, identity, "0.1.2", transport=server.transport)
