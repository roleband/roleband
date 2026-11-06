"""The engine reaches the same startup verdict as the native host on every shared record case.

Cases live in launcher/windows/contracts/retained-records.json, which the native
RecordContractTests read too: a rule changed on one side only fails one of them.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows recovery requires Windows")

CORPUS = json.loads(
    (Path(__file__).resolve().parents[2] / "launcher/windows/contracts/retained-records.json").read_text(encoding="utf-8")
)


def _materialize(case: dict, state: Path) -> bytes:
    places = {"{state}": str(state), "{pgdata}": str(state / "db"), "{checkpoint}": str(state.parent / "checkpoint")}
    if "raw" in case:
        text = case["raw"]
        for placeholder, value in places.items():
            text = text.replace(placeholder, json.dumps(value)[1:-1])
        return text.encode("utf-8")

    def substitute(value):
        if isinstance(value, dict):
            return {key: substitute(item) for key, item in value.items()}
        if isinstance(value, list):
            return [substitute(item) for item in value]
        return places.get(value, value) if isinstance(value, str) else value

    document = copy.deepcopy(CORPUS["bases"][case["file"]])
    document.update(copy.deepcopy(case.get("set", {})))
    for key in case.get("remove", []):
        del document[key]
    return json.dumps(substitute(document)).encode("utf-8")


def _verdict(message: str) -> str:
    for keyword, verdict in (("requires Windows reader contract", "newer-reader"),
                             ("unfinished", "unfinished"), ("damaged", "damaged")):
        if keyword in message:
            return verdict
    return f"unclassified: {message}"


@pytest.mark.parametrize("case", CORPUS["cases"], ids=[case["name"] for case in CORPUS["cases"]])
def test_engine_startup_verdict_matches_the_shared_case(case, tmp_path):
    from tracker.platform.windows_private import private_directory
    from tracker.platform.windows_recovery import RecoveryError, require_launchable
    from tracker.platform.windows_storage import StorageCompatibilityError

    state = tmp_path / "state"
    record = state / CORPUS["files"][case["file"]]
    private_directory(state)
    private_directory(record.parent)
    record.write_bytes(_materialize(case, state))
    try:
        require_launchable(state)
        verdict = "accepted"
    except (RecoveryError, StorageCompatibilityError) as error:
        verdict = _verdict(str(error))
    assert verdict == case["verdict"]
    assert not (state / "db").exists(), "a startup check never creates the database"


def test_the_corpus_covers_every_verdict_each_record_can_reach():
    reached = {(case["file"], case["verdict"]) for case in CORPUS["cases"]}
    assert reached >= {("storage", "accepted"), ("storage", "damaged"), ("storage", "newer-reader"),
                       ("drill", "accepted"), ("drill", "damaged"), ("drill", "unfinished"),
                       ("restore", "accepted"), ("restore", "damaged"), ("restore", "unfinished")}
    names = [case["name"] for case in CORPUS["cases"]]
    assert len(names) == len(set(names))
