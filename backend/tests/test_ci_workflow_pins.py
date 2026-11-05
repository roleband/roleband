"""Every workflow runs code it names exactly, with the least it needs.

A tag such as `actions/checkout@v4` or `pgvector/pgvector:pg16` can be moved
to other code by whoever controls it, and the next run executes that code
with the workflow's token. So an action is referenced by its full commit SHA
(the version it is, in a trailing comment, for the reader and for Dependabot),
a container action and a service image by digest, and every workflow declares
its `permissions` instead of inheriting the repository default. Every job also
states its `timeout-minutes`, so a hung step fails within minutes instead of the
runner's six-hour default.

The machine is named the same way: a `-latest` runner label moves to a new
operating system on GitHub's schedule, so each job names its version and an
upgrade is a change of its own. A checkout leaves no token in `.git/config` for
a later step or an uploaded workspace to carry, and a download retries the
transient errors GitHub's release hosting answers with.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$", re.M)
SHA = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
DOCKER = re.compile(r"^docker://[\w./-]+@sha256:[0-9a-f]{64}$")
VERSION_NOTE = re.compile(r"^\s*#\s*v\d+(\.\d+){1,2}\s*$")


def _images(node) -> list[str]:
    if isinstance(node, dict):
        found = [node["image"]] if isinstance(node.get("image"), str) else []
        return found + [image for value in node.values() for image in _images(value)]
    if isinstance(node, list):
        return [image for value in node for image in _images(value)]
    return []


def _pinned(ref: str, rest: str) -> bool:
    return bool((SHA.match(ref) or DOCKER.match(ref)) and VERSION_NOTE.match(rest))


def _runner_labels(job: dict) -> list[str]:
    """The labels a job can run on, with a `matrix` runner read from its matrix."""
    runs_on = job.get("runs-on", [])
    if isinstance(runs_on, dict):
        runs_on = runs_on.get("labels", [])
    labels = [runs_on] if isinstance(runs_on, str) else list(runs_on)
    matrix = job.get("strategy", {}).get("matrix", {})
    out = []
    for label in labels:
        key = re.fullmatch(r"\$\{\{\s*matrix\.(\w+)\s*\}\}", label)
        if key is None:
            out.append(label)
            continue
        values = matrix.get(key[1], []) + [entry[key[1]] for entry in matrix.get("include", []) if key[1] in entry]
        out += values or [label]
    return out


def _floating_runners(workflow: dict) -> list[str]:
    return [
        f"{name}: {label}" for name, job in workflow.get("jobs", {}).items()
        for label in _runner_labels(job) if label.endswith("-latest") or "${{" in label
    ]


def _steps(workflow: dict) -> list[dict]:
    return [step for job in workflow.get("jobs", {}).values() for step in job.get("steps", [])]


def _checkouts_keeping_the_token(workflow: dict) -> list[str]:
    return [
        step["uses"] for step in _steps(workflow)
        if str(step.get("uses", "")).startswith("actions/checkout@")
        and (step.get("with") or {}).get("persist-credentials") is not False
    ]


DOWNLOAD = re.compile(r"(^|[\s;&|(])(curl|wget)\s")
RETRIES = re.compile(r"(--retry|--tries|(?<![\w-])-t)[=\s]+0*[1-9]")


def _downloads_without_retry(workflow: dict) -> list[str]:
    return [
        line.strip() for step in _steps(workflow) for line in str(step.get("run", "")).splitlines()
        if DOWNLOAD.search(line) and not RETRIES.search(line)
    ]


def _untimed_jobs(workflow: dict) -> list[str]:
    return [name for name, job in workflow.get("jobs", {}).items() if "timeout-minutes" not in job]


def test_the_scan_finds_the_workflows_and_their_actions():
    assert WORKFLOWS, "no workflows found"
    assert sum(len(USES.findall(w.read_text())) for w in WORKFLOWS) >= 10


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit_with_its_version_noted(workflow):
    loose = [
        f"{ref}{rest}" for ref, rest in USES.findall(workflow.read_text())
        if not ref.startswith("./") and not _pinned(ref, rest)
    ]
    assert loose == [], f"{workflow.name}: reference by full SHA with '# vX.Y.Z': {loose}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_service_image_is_pinned_by_digest(workflow):
    images = _images(yaml.safe_load(workflow.read_text()))
    assert [i for i in images if "@sha256:" not in i] == []


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_workflow_declares_its_permissions(workflow):
    assert "permissions" in yaml.safe_load(workflow.read_text()), f"{workflow.name} inherits the default token"


def _scan_upload_grants(workflow: dict) -> list[str]:
    """Where `security-events: write` is granted beyond a job that uploads a CodeQL analysis.

    The grant lets a token rewrite the repository's code scanning alerts, so it belongs on
    the job that uploads results and nowhere else, never on the whole workflow.
    """
    def grants(permissions) -> bool:
        return permissions == "write-all" or (
            isinstance(permissions, dict) and permissions.get("security-events") == "write"
        )

    found = ["workflow"] if grants(workflow.get("permissions")) else []
    for name, job in (workflow.get("jobs") or {}).items():
        uploads = any(
            str(step.get("uses", "")).startswith("github/codeql-action/analyze@") for step in job.get("steps") or []
        )
        if grants(job.get("permissions")) and not uploads:
            found.append(name)
    return found


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_only_a_job_that_uploads_a_scan_may_write_security_events(workflow):
    granted = _scan_upload_grants(yaml.safe_load(workflow.read_text()))
    assert granted == [], f"{workflow.name}: security-events: write outside a CodeQL upload: {granted}"


def test_the_security_events_rule_sees_a_grant_without_an_upload():
    """The negative controls for the rule above."""
    analyze = {"uses": "github/codeql-action/analyze@" + "a" * 40}
    workflow = {"permissions": {"contents": "read", "security-events": "write"}, "jobs": {
        "scan": {"permissions": {"security-events": "write"}, "steps": [analyze]},
        "decide": {"permissions": {"security-events": "write"}, "steps": [{"run": "true"}]},
        "everything": {"permissions": "write-all", "steps": []},
        "reads": {"permissions": {"security-events": "read"}, "steps": []},
    }}
    assert _scan_upload_grants(workflow) == ["workflow", "decide", "everything"]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_declares_a_timeout(workflow):
    doc = yaml.safe_load(workflow.read_text())
    assert doc["jobs"], f"{workflow.name} has no jobs"
    assert _untimed_jobs(doc) == [], f"{workflow.name}: add timeout-minutes to these jobs"


def test_the_timeout_rule_reads_the_job_not_its_steps():
    """A step's timeout does not bound the job: only the job-level key counts."""
    workflow = {"jobs": {
        "timed": {"timeout-minutes": 5, "steps": []},
        "step_only": {"steps": [{"run": "x", "timeout-minutes": 5}]},
    }}
    assert _untimed_jobs(workflow) == ["step_only"]


@pytest.mark.parametrize(("ref", "rest", "pinned"), [
    ("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", " # v4.4.0", True),
    ("actions/checkout@v4", "", False),
    ("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "", False),
    ("docker://rhysd/actionlint@sha256:" + "b" * 64, " # v1.7.12", True),
    ("docker://rhysd/actionlint:1.7.12", " # v1.7.12", False),
    ("docker://rhysd/actionlint:latest@sha256:" + "b" * 64, " # v1.7.12", False),
    ("docker://rhysd/actionlint@sha256:" + "b" * 64, "", False),
])
def test_the_pin_rule_tells_a_pinned_reference_from_a_tag(ref, rest, pinned):
    """The negative controls for the rule above."""
    assert _pinned(ref, rest) is pinned


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_names_its_runner_version(workflow):
    floating = _floating_runners(yaml.safe_load(workflow.read_text()))
    assert floating == [], f"{workflow.name}: name the version, e.g. ubuntu-24.04: {floating}"


def test_the_runner_rule_reads_a_matrix_and_refuses_latest():
    """The negative controls: a `-latest` label, directly or through the matrix, is reported."""
    workflow = {"jobs": {
        "named": {"runs-on": "ubuntu-24.04"},
        "latest": {"runs-on": "ubuntu-latest"},
        "listed": {"runs-on": ["self-hosted", "macos-latest"]},
        "matrix_named": {"runs-on": "${{ matrix.runner }}",
                         "strategy": {"matrix": {"include": [{"runner": "macos-15"}, {"runner": "ubuntu-24.04-arm"}]}}},
        "matrix_latest": {"runs-on": "${{ matrix.os }}",
                          "strategy": {"matrix": {"os": ["ubuntu-24.04", "windows-latest"]}}},
        "unresolved": {"runs-on": "${{ inputs.runner }}"},
        "group_named": {"runs-on": {"group": "larger", "labels": "ubuntu-24.04"}},
        "group_latest": {"runs-on": {"group": "larger", "labels": ["ubuntu-latest"]}},
    }}
    assert _floating_runners(workflow) == [
        "latest: ubuntu-latest", "listed: macos-latest",
        "matrix_latest: windows-latest", "unresolved: ${{ inputs.runner }}",
        "group_latest: ubuntu-latest",
    ]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_checkout_leaves_no_token_behind(workflow):
    kept = _checkouts_keeping_the_token(yaml.safe_load(workflow.read_text()))
    assert kept == [], f"{workflow.name}: give these checkouts `persist-credentials: false`"


def test_the_token_rule_needs_an_explicit_false():
    """The negative controls: no `with`, a `with` without the key and a true value all keep the token."""
    checkout = "actions/checkout@" + "a" * 40
    workflow = {"jobs": {"a": {"steps": [
        {"uses": checkout, "with": {"persist-credentials": False}},
        {"uses": checkout},
        {"uses": checkout, "with": {"fetch-depth": 0}},
        {"uses": checkout, "with": {"persist-credentials": True}},
        {"uses": "actions/setup-node@" + "a" * 40},
    ]}}}
    assert len(_checkouts_keeping_the_token(workflow)) == 3


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_download_retries(workflow):
    once = _downloads_without_retry(yaml.safe_load(workflow.read_text()))
    assert once == [], f"{workflow.name}: give these downloads --retry: {once}"


def test_the_download_rule_finds_a_curl_without_retry():
    """The negative controls: a download without a positive retry count is reported."""
    workflow = {"jobs": {"a": {"steps": [
        {"run": "curl -sSfL --retry 4 -o x https://example.test/x"},
        {"run": 'archive=x\ncurl -sSfL -o "$archive" https://example.test/x'},
        {"run": "curl -sSfL --retry-delay 5 https://example.test/x"},
        {"run": "curl -sSfL --retry 0 https://example.test/x"},
        {"run": "wget -q https://example.test/x"},
        {"run": "wget --tries=3 https://example.test/x"},
        {"run": "wget -t 3 https://example.test/x"},
        {"run": "pip install curl_cffi"},
    ]}}}
    assert _downloads_without_retry(workflow) == [
        'curl -sSfL -o "$archive" https://example.test/x',
        "curl -sSfL --retry-delay 5 https://example.test/x",
        "curl -sSfL --retry 0 https://example.test/x",
        "wget -q https://example.test/x",
    ]


def test_the_local_workflow_gate_runs_the_image_ci_runs():
    """docs/testing.md gives the actionlint command for a workflow change; it names CI's digest."""
    hygiene = yaml.safe_load((WORKFLOWS[0].parent / "hygiene.yml").read_text())
    refs = [step["uses"] for step in _steps(hygiene) if str(step.get("uses", "")).startswith("docker://rhysd/actionlint@")]
    assert len(refs) == 1
    testing = (WORKFLOWS[0].parents[2] / "docs" / "testing.md").read_text()
    assert refs[0].removeprefix("docker://") in testing
