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
from tracker.platform.windows_release import Identity, ReleaseError, names, prepare
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


def test_a_release_with_only_the_mac_files_is_no_update_yet_and_offered_once_windows_files_arrive(state, identity, feed):
    feed.publish("0.1.3")
    windows = feed.releases["0.1.3"]
    feed.releases["0.1.3"] = {"RoleBand-0.1.3.dmg": b"the macOS image"}
    waiting = run(state, identity, feed, manual=True)
    assert (waiting.status, waiting.offer) == ("up-to-date", None), "never 'couldn't check', never an offer"
    assert windows_updates.status(state, identity, "0.1.2")["checked_at"] == NOW
    feed.releases["0.1.3"] = {**feed.releases["0.1.3"], **windows}
    arrived = run(state, identity, feed, manual=True, now=NOW + 1)
    assert (arrived.status, arrived.offer.version) == ("offered", "0.1.3")


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


def test_only_a_check_the_feed_answered_counts_as_checked(state, identity, feed):
    feed.listing_override = httpx.Response(500)
    run(state, identity, feed, manual=True)
    assert windows_updates.status(state, identity, "0.1.2")["checked_at"] is None, "a failed check is not a check"
    feed.listing_override = None
    feed.publish("0.1.2")
    assert run(state, identity, feed, manual=True, now=NOW + 1).status == "up-to-date"
    assert windows_updates.status(state, identity, "0.1.2")["checked_at"] == NOW + 1
    feed.listing_override = httpx.Response(500)
    run(state, identity, feed, manual=True, now=NOW + 2)
    assert windows_updates.status(state, identity, "0.1.2")["checked_at"] == NOW + 1, "the last success stays"
    feed.listing_override = None
    feed.publish("0.1.3")
    assert run(state, identity, feed, manual=True, now=NOW + 3).status == "offered"
    assert run(state, identity, feed, manual=True, now=NOW + 4).status == "offered"
    assert windows_updates.status(state, identity, "0.1.2")["checked_at"] == NOW + 4


def test_a_version_just_installed_checks_once_whatever_the_one_before_did(state, identity, feed):
    allow(state, True)
    feed.publish("0.1.3")
    assert run(state, identity, feed, manual=False, installed="0.1.2").status == "offered"
    assert run(state, identity, feed, manual=False, now=NOW + 60, installed="0.1.2").status == "throttled"
    assert run(state, identity, feed, manual=False, now=NOW + 60, installed="0.1.3").status == "up-to-date", \
        "the updated version asks for itself"
    assert run(state, identity, feed, manual=False, now=NOW + 120, installed="0.1.3").status == "throttled"


def test_a_check_counts_only_for_the_version_that_made_it(state, identity, feed):
    feed.publish("0.1.3")
    run(state, identity, feed, manual=True, installed="0.1.3")
    assert windows_updates.status(state, identity, "0.1.3")["checked_at"] == NOW
    assert windows_updates.status(state, identity, "0.1.2")["checked_at"] is None, \
        "after an Undo, the newer version's 'up to date' says nothing about this one"


def test_a_version_this_installation_undid_is_not_offered_again(state, identity, feed):
    feed.publish("0.1.3")
    assert run(state, identity, feed, manual=True).offer.version == "0.1.3"
    assert windows_updates.status(state, identity, "0.1.2", held_back="0.1.3")["offer"] is None, "the kept offer is dropped"
    assert windows_updates.stored_offer(state, identity, "0.1.2", held_back="0.1.3") is None, "nothing to download"
    held = check(state, identity, "0.1.2", manual=True, now=NOW + 1, transport=feed.transport, held_back="0.1.3")
    assert (held.status, held.offer) == ("up-to-date", None)
    feed.publish("0.1.4")
    newer = check(state, identity, "0.1.2", manual=True, now=NOW + 2, transport=feed.transport, held_back="0.1.3")
    assert (newer.status, newer.offer.version) == ("offered", "0.1.4"), "a newer release is offered"


def test_status_reads_what_checks_kept_without_asking_the_feed(state, identity, feed):
    assert windows_updates.status(state, identity, "0.1.2") == {
        "automatic": False, "checked_at": None, "offer": None, "rate_limited_until": None}
    allow(state, True)
    feed.publish("0.1.3")
    run(state, identity, feed, manual=True)
    asked = len(feed.requests)
    kept = windows_updates.status(state, identity, "0.1.2")
    assert (kept["automatic"], kept["offer"], kept["checked_at"]) == (True, "0.1.3", NOW)
    assert windows_updates.status(state, identity, "0.1.3")["offer"] is None, "an installed offer is no offer"
    feed.listing_override = httpx.Response(429, headers={"Retry-After": "120"})
    run(state, identity, feed, manual=True, now=NOW + 1)
    assert windows_updates.status(state, identity, "0.1.2")["rate_limited_until"] == NOW + 121
    assert len(feed.requests) == asked + 1, "only the rate-limited check asked"


def _download_command(state, identity, feed, monkeypatch):
    import base64

    from scripts import windows_update
    from tracker.platform import releases
    from tracker.platform.windows_private import private_directory

    private_directory(state)
    feed.publish("0.1.3")
    run(state, identity, feed, manual=True)
    stamped = state.parent / "release-identity.json"
    stamped.write_text(json.dumps({"format": 1, "feed": identity.feed,
                                   "release_public_key": base64.b64encode(identity.release_key).decode(),
                                   "package_name": identity.package_name, "publisher": identity.publisher}), encoding="utf-8")
    monkeypatch.setattr(windows_update, "identity_path", lambda: stamped)
    monkeypatch.setattr(releases, "running_version", lambda *_: "0.1.2")
    monkeypatch.setenv("ROLEBAND_STATE_DIR", str(state))
    return windows_update


def _full_disk() -> OSError:
    error = OSError(28, "No space left on device")
    error.winerror = 112  # type: ignore[attr-defined]
    return error


@windows_only
@pytest.mark.parametrize(("failure", "step", "kind"), [
    (ReleaseError("The download is not the signed release"), "download", "check"),
    (OSError("The connection was reset"), "download", "download"),
    (httpx.ConnectError("offline"), "download", "offline"),
    (httpx.ReadTimeout("the network went quiet"), "download", "offline"),
    ("interrupted", "download", "offline"),
    ("not available", "download", "download"),
    ("missing", "download", "missing"),
    (_full_disk(), "download", "space"),
    (ReleaseError("The installed version's release is not signed by this key"), "retain", "download"),
    (httpx.ConnectError("offline"), "retain", "offline"),
])
def test_a_failed_download_says_what_stopped_it(state, identity, feed, monkeypatch, capsys, failure, step, kind):
    from tracker.platform import windows_packages

    windows_update = _download_command(state, identity, feed, monkeypatch)
    failure = {"interrupted": windows_packages.DownloadInterrupted("The package download was interrupted"),
               "not available": windows_packages.DownloadIncomplete("The package is not available"),
               "missing": windows_updates.ReleaseMissing("The package is not published")}.get(failure, failure)
    downloads = []

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(windows_packages, "retain_running", fail if step == "retain" else lambda *_args, **_kwargs: None)
    monkeypatch.setattr(windows_packages, "download", fail if step == "download" else lambda *args, **_kwargs: downloads.append(args))
    assert windows_update.main(["download", "--state", str(state)]) == 1
    answer = json.loads(capsys.readouterr().out)
    assert (answer["status"], answer["kind"]) == ("failed", kind)
    assert not downloads, "without the way back, the update is not downloaded"


@windows_only
@pytest.mark.parametrize(("kept", "packages"), [((), 2), (("0.1.2",), 1), (("0.1.2", "0.1.3"), 0)])
def test_a_download_without_room_for_itself_and_its_install_is_not_started(state, identity, feed, monkeypatch, capsys,
                                                                            kept, packages):
    import shutil

    from tracker.platform import windows_packages

    windows_update = _download_command(state, identity, feed, monkeypatch)
    offer = windows_updates.stored_offer(state, identity, "0.1.2")[0]
    windows_packages.folder(state).mkdir(exist_ok=True)
    for version in kept:
        (windows_packages.folder(state) / names(version)[0]).write_bytes(b"kept")
    needed = offer.bytes * (packages + 1) + windows_update._SPACE_MARGIN
    started = []
    monkeypatch.setattr(windows_packages, "retain_running", lambda *args, **_kwargs: started.append(args))
    monkeypatch.setattr(windows_packages, "download", lambda *args, **_kwargs: started.append(args) or Path("kept.msix"))
    usage = shutil.disk_usage(state)

    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage._replace(free=needed - 1))
    assert windows_update.main(["download", "--state", str(state)]) == 1
    answer = json.loads(capsys.readouterr().out)
    assert (answer["status"], answer["kind"], answer["needed"]) == ("failed", "space", needed)
    assert not started, "nothing is fetched, so a full disk is not filled further"

    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage._replace(free=needed))
    assert windows_update.main(["download", "--state", str(state)]) == 0, capsys.readouterr().out
    assert len(started) == 2, "with the room it needs, the way back is kept and the update downloaded"


@windows_only
def test_a_download_reports_its_progress_over_both_packages_on_stderr(state, identity, feed, monkeypatch, capsys):
    from tracker.platform import windows_packages

    windows_update = _download_command(state, identity, feed, monkeypatch)
    offer = windows_updates.stored_offer(state, identity, "0.1.2")[0]
    way_back = offer.bytes // 2

    def retain(*_args, progress, **_kwargs):
        progress(0, way_back)
        progress(way_back, way_back)

    def fetch(*_args, progress, **_kwargs):
        progress(offer.bytes // 4, offer.bytes)
        progress(offer.bytes, offer.bytes)
        return Path("update.msix")

    monkeypatch.setattr(windows_packages, "retain_running", retain)
    monkeypatch.setattr(windows_packages, "download", fetch)
    assert windows_update.main(["download", "--state", str(state)]) == 0
    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.err.splitlines()]
    assert json.loads(captured.out)["status"] == "downloaded", "stdout stays one answer"
    assert lines[0]["total"] == way_back + offer.bytes, "the update counts in the total while the way back arrives"
    assert lines[-1] == {"received": way_back + offer.bytes, "total": way_back + offer.bytes}
    assert all(line["received"] <= line["total"] for line in lines)


@windows_only
def test_a_kept_way_back_leaves_only_the_update_in_the_progress(state, identity, feed, monkeypatch, capsys):
    from tracker.platform import windows_packages

    windows_update = _download_command(state, identity, feed, monkeypatch)
    offer = windows_updates.stored_offer(state, identity, "0.1.2")[0]

    def fetch(*_args, progress, **_kwargs):
        progress(offer.bytes, offer.bytes)
        return Path("update.msix")

    monkeypatch.setattr(windows_packages, "retain_running", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(windows_packages, "download", fetch)
    assert windows_update.main(["download", "--state", str(state)]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert lines[-1] == {"received": offer.bytes, "total": offer.bytes}


@windows_only
def test_a_build_without_an_update_identity_reports_its_status_as_unavailable(tmp_path):
    from tracker.platform.windows_private import private_directory

    state = tmp_path / "state"
    private_directory(state)
    result = _desktop(state, "status")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "unavailable"
