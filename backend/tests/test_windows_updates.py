"""The Windows app asks for updates only as allowed and offers only verified, newer releases."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import psutil
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from tracker.platform import windows_updates
from tracker.platform.windows_release import Identity, names, prepare
from tracker.platform.windows_updates import AUTOMATIC_INTERVAL, check, record_consent

FEED = "roleband/roleband-trials"
NOW = 1_800_000_000.0


class Feed:
    """A fake GitHub: the API listing, asset downloads through a CDN redirect, and a request log."""

    def __init__(self, tmp_path, key, identity):
        self.tmp_path, self.key, self.identity = tmp_path, key, identity
        self.releases: dict[str, dict[str, bytes]] = {}
        self.latest: str | None = None
        self.requests: list[str] = []
        self.listing_override: httpx.Response | None = None
        self.redirect_to = "https://release-assets.githubusercontent.com/assets/{name}"
        self.redirects = 1

    def publish(self, version, *, tamper=False):
        package = self.tmp_path / f"{version}.msix"
        package.write_bytes(f"package {version}".encode() * 32)
        files = prepare(package, self.tmp_path / f"release-{version}", self.identity, self.key,
                        version=version, revision=0, commit="b" * 40)
        content = {path.name: path.read_bytes() for path in files}
        if tamper:
            metadata = names(version)[2]
            content[metadata] = content[metadata].replace(b'"bytes": ', b'"bytes": 1')
        self.releases[version] = content
        self.latest = version

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        assert "Authorization" not in request.headers and "Cookie" not in request.headers
        url = str(request.url)
        if url == f"https://api.github.com/repos/{FEED}/releases/latest":
            if self.listing_override is not None:
                return self.listing_override
            tag = f"v{self.latest}"
            return httpx.Response(200, json={"tag_name": tag, "draft": False, "prerelease": False,
                                             "html_url": f"https://github.com/{FEED}/releases/tag/{tag}"})
        prefix = f"https://github.com/{FEED}/releases/download/v"
        if url.startswith(prefix) and "/hop" in url:
            hops = int(url.rsplit("/hop", 1)[1].split("/")[0])
            return self._redirect(url.rsplit("/", 1)[1], hops)
        if url.startswith(prefix):
            version, _, name = url.removeprefix(prefix).partition("/")
            if name not in self.releases.get(version, {}):
                return httpx.Response(404)
            return self._redirect(name, self.redirects)
        if url.startswith("https://release-assets.githubusercontent.com/assets/"):
            name = url.rsplit("/", 1)[1]
            for content in self.releases.values():
                if name in content:
                    return httpx.Response(200, content=content[name])
            return httpx.Response(404)
        return httpx.Response(404)

    def _redirect(self, name, remaining):
        if remaining > 1:
            target = f"https://github.com/{FEED}/releases/download/v{self.latest}/hop{remaining - 1}/{name}"
        else:
            target = self.redirect_to.format(name=name)
        return httpx.Response(302, headers={"Location": target})

    @property
    def transport(self):
        return httpx.MockTransport(self.handler)


@pytest.fixture
def key():
    return ed25519.Ed25519PrivateKey.generate()


@pytest.fixture
def identity(key):
    return Identity(FEED, key.public_key().public_bytes_raw(), "RoleBand.Windows.Trial", "CN=RoleBand Windows Trial")


@pytest.fixture
def feed(tmp_path, key, identity):
    return Feed(tmp_path, key, identity)


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"


def run(state, identity, feed, *, manual, now=NOW, installed="0.1.2"):
    return check(state, identity, installed, manual=manual, now=now, transport=feed.transport)


def allow(state, automatic):
    record_consent(state, automatic=automatic, text="Check for RoleBand updates once a day.", language="en", now=NOW)


def test_no_choice_means_no_automatic_request(state, identity, feed):
    feed.publish("0.1.3")
    assert run(state, identity, feed, manual=False).status == "not-allowed"
    assert feed.requests == []


def test_declined_automatic_checks_still_allow_one_manual_request(state, identity, feed):
    feed.publish("0.1.3")
    allow(state, False)
    assert run(state, identity, feed, manual=False).status == "not-allowed"
    assert feed.requests == []
    assert run(state, identity, feed, manual=True).status == "offered"
    assert feed.requests[0].startswith("https://api.github.com/")
    assert json.loads((state / windows_updates.CONSENT).read_text())["automatic"] is False


def test_automatic_checks_run_once_a_day_even_after_a_failure(state, identity, feed):
    feed.listing_override = httpx.Response(500)
    allow(state, True)
    assert run(state, identity, feed, manual=False).status == "failed"
    assert len(feed.requests) == 1
    assert run(state, identity, feed, manual=False, now=NOW + AUTOMATIC_INTERVAL - 1).status == "throttled"
    assert len(feed.requests) == 1
    feed.listing_override = None
    feed.publish("0.1.3")
    assert run(state, identity, feed, manual=False, now=NOW + AUTOMATIC_INTERVAL).status == "offered"


def test_a_verified_offer_survives_a_restart_and_a_later_failure(state, identity, feed):
    feed.publish("0.1.3")
    first = run(state, identity, feed, manual=True)
    assert (first.status, first.offer.version) == ("offered", "0.1.3")
    feed.listing_override = httpx.Response(500)
    later = run(state, identity, feed, manual=True, now=NOW + 1)
    assert (later.status, later.offer) == ("failed", first.offer)


def test_an_older_listing_never_replaces_a_verified_offer(state, identity, feed):
    feed.publish("0.1.4")
    assert run(state, identity, feed, manual=True).offer.version == "0.1.4"
    feed.latest = "0.1.3"
    feed.releases.pop("0.1.4")
    feed.publish("0.1.3")
    asked = len(feed.requests)
    result = run(state, identity, feed, manual=True, now=NOW + 1)
    assert (result.status, result.offer.version) == ("offered", "0.1.4")
    assert len(feed.requests) == asked + 1, "only the listing was read"


def test_installing_the_offered_version_retires_the_offer(state, identity, feed):
    feed.publish("0.1.3")
    run(state, identity, feed, manual=True)
    result = run(state, identity, feed, manual=True, now=NOW + 1, installed="0.1.3")
    assert (result.status, result.offer) == ("up-to-date", None)
    assert "offer" not in json.loads((state / windows_updates.CHECK).read_text())


def test_tampered_metadata_offers_nothing(state, identity, feed):
    feed.publish("0.1.3", tamper=True)
    assert run(state, identity, feed, manual=True) == windows_updates.Result("failed", None)


def test_a_release_whose_files_are_not_all_published_offers_nothing(state, identity, feed):
    feed.publish("0.1.3")
    del feed.releases["0.1.3"][names("0.1.3")[3]]
    assert run(state, identity, feed, manual=True).status == "failed"


@pytest.mark.parametrize("target", [
    "https://evil.example/assets/{name}", "http://release-assets.githubusercontent.com/assets/{name}",
    "https://release-assets.githubusercontent.com:8443/assets/{name}",
    "https://user:pw@release-assets.githubusercontent.com/assets/{name}",
    "https://github.com/someone/else/releases/download/v0.1.3/{name}",
])
def test_release_files_are_read_only_from_the_feed_and_its_cdn(state, identity, feed, target):
    feed.publish("0.1.3")
    feed.redirect_to = target
    assert run(state, identity, feed, manual=True).status == "failed"
    assert not any("evil" in url or "someone" in url or ":8443" in url for url in feed.requests[1:])


@pytest.mark.parametrize("redirects, status", [(5, "offered"), (6, "failed")])
def test_a_chain_of_redirects_is_bounded(state, identity, feed, redirects, status):
    feed.publish("0.1.3")
    feed.redirects = redirects
    assert run(state, identity, feed, manual=True).status == status


def test_a_rate_limit_delays_manual_checks_until_it_ends(state, identity, feed):
    feed.listing_override = httpx.Response(429, headers={"Retry-After": "120"})
    result = run(state, identity, feed, manual=True)
    assert (result.status, result.until) == ("rate-limited", NOW + 120)
    asked = len(feed.requests)
    assert run(state, identity, feed, manual=True, now=NOW + 119).status == "rate-limited"
    assert len(feed.requests) == asked
    feed.listing_override = None
    feed.publish("0.1.3")
    assert run(state, identity, feed, manual=True, now=NOW + 120).status == "offered"


def test_an_exhausted_api_quota_waits_for_its_reset(state, identity, feed):
    reset = int(NOW) + 3600
    feed.listing_override = httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)})
    assert run(state, identity, feed, manual=True).until == reset


@pytest.mark.parametrize("listing", [
    httpx.Response(301, headers={"Location": "https://evil.example/latest"}),
    httpx.Response(200, json={"tag_name": "v0.1.3", "draft": True, "prerelease": False,
                              "html_url": f"https://github.com/{FEED}/releases/tag/v0.1.3"}),
    httpx.Response(200, json={"tag_name": "v0.1.3", "draft": False, "prerelease": True,
                              "html_url": f"https://github.com/{FEED}/releases/tag/v0.1.3"}),
    httpx.Response(200, json={"tag_name": "v0.1.3", "draft": False, "prerelease": False,
                              "html_url": "https://github.com/someone/else/releases/tag/v0.1.3"}),
    httpx.Response(200, json={"tag_name": "v0.1.3-rc.1", "draft": False, "prerelease": False,
                              "html_url": f"https://github.com/{FEED}/releases/tag/v0.1.3-rc.1"}),
    httpx.Response(200, content=b"[" * (300 * 1024)),
    httpx.Response(200, content=b"not json"),
])
def test_a_listing_that_is_not_a_published_stable_release_offers_nothing(state, identity, feed, listing):
    feed.publish("0.1.3")
    feed.listing_override = listing
    assert run(state, identity, feed, manual=True).status == "failed"
    assert len(feed.requests) == 1, "no release file is read for a refused listing"


def test_a_consent_choice_needs_its_words(state):
    with pytest.raises(ValueError):
        record_consent(state, automatic=True, text=" ", language="en")
    with pytest.raises(ValueError):
        record_consent(state, automatic="yes", text="Check daily.", language="en")


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows update requires Windows")


def _desktop(state, *arguments):
    return subprocess.run([psutil.Process().exe(), "-I", "-B", str(Path(__file__).resolve().parents[1] / "desktop.py"),
                           "--source", "update", *arguments, "--state", str(state)],
                          env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


@windows_only
def test_the_desktop_command_records_the_choice_with_its_words(tmp_path):
    from tracker.platform.windows_private import private_directory

    state = tmp_path / "state"
    private_directory(state)
    result = _desktop(state, "consent", "--automatic", "on", "--text", "Buscar actualizaciones una vez al día.",
                      "--language", "es")
    assert result.returncode == 0, result.stderr
    record = json.loads((state / windows_updates.CONSENT).read_text(encoding="utf-8"))
    assert (record["automatic"], record["text"], record["language"]) == (
        True, "Buscar actualizaciones una vez al día.", "es")


@windows_only
def test_a_build_without_an_update_identity_never_asks_the_feed(tmp_path):
    from tracker.platform.windows_private import private_directory

    state = tmp_path / "state"
    private_directory(state)
    result = _desktop(state, "check", "--manual")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "unavailable"
    assert not (state / windows_updates.CHECK).exists(), "no attempt was recorded, so no request was made"
