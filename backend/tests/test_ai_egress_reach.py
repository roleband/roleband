"""What the AI egress switch lets leave this computer, held to what the consent says.

The switch is the master switch for every AI provider the person adds. Settings
› AI asks before it turns on, and the consent it shows (`ai-egress-detail`,
pinned in `dashboard/src/copy/pinned.en.json`) states its scope (which
providers, whose key) and names no data, because no product task sends posting
text to a provider. These tests are the fact that silence rests on:

1. **Reach.** Only the routing ladder can hand job text to a cloud model, and
   no shipped module asks the ladder for a provider: the model bench
   (`scripts.bench_relevance_review`) is its only caller. A new caller fails
   here, and must change the consent (and its pin) in the same change.
2. **Behaviour.** With the switch on and a cloud provider turned on, the one
   model task the product runs, duplicate review, still answers from the local
   model or refuses; it never reaches the cloud provider. The provider's Test is
   the control that the cloud double sees a request when one is made.
3. **The sentence.** The pinned consent states the scope and still names no
   posting text: a task that starts sending it must say so there.

Search query parsing (`search/llm.py`) takes the same switch and sends the
person's own query, never posting text; `test_search_llm_egress.py` holds it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.api_errors import code_of
from tests.intelligence_contract_seed import pin_integration_machine, seed_cloud_connection
from tests.lineage_contract_seed import pin_lineage_environment, seed_lineage_contract
from tracker.settings_store import get_ai_egress_enabled

BACKEND = Path(__file__).resolve().parents[1]
TRACKER = BACKEND / "tracker"
PINNED = BACKEND.parent / "dashboard" / "src" / "copy" / "pinned.en.json"

#: The names through which a model generation can reach a cloud provider: the
#: ladder (`build_tiers`, `resolve_provider`), the cloud provider and its client,
#: and the tool-calling transport that drives a tier.
pytestmark = pytest.mark.usefixtures("no_escape")

CLOUD_DOORS = frozenset(
    {"build_tiers", "resolve_provider", "CloudLLMProvider", "CloudLLMClient", "transport_for_tier"}
)

#: Every shipped module that names a door, and which. Each is plumbing: it
#: defines a door or assembles the ladder. None runs a product task.
PLUMBING = {
    "tracker/cloud_llm/client.py": {"CloudLLMClient"},
    "tracker/intelligence/providers/cloud.py": {"CloudLLMProvider", "CloudLLMClient"},
    "tracker/intelligence/tool_calls/__init__.py": {"transport_for_tier"},
    "tracker/intelligence/tool_calls/transport.py": {"CloudLLMProvider", "transport_for_tier"},
    "tracker/intelligence_runtime/routing.py": {"build_tiers", "resolve_provider", "CloudLLMProvider"},
}


def doors_named(source: str) -> set[str]:
    """Every door a module's source names: imported, defined, called or read."""
    named: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            named.add(node.id)
        elif isinstance(node, ast.Attribute):
            named.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            named.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            named.update(alias.name for alias in node.names)
    return named & CLOUD_DOORS


def _shipped_reach() -> dict[str, set[str]]:
    reach = {}
    for path in sorted(TRACKER.rglob("*.py")):
        doors = doors_named(path.read_text(encoding="utf-8"))
        if doors:
            reach[path.relative_to(BACKEND).as_posix()] = doors
    return reach


def test_no_shipped_module_but_the_plumbing_can_reach_a_cloud_model():
    reach = _shipped_reach()
    assert reach == PLUMBING, (
        "A shipped module now names a door to a cloud model. If a product task can send "
        "job text to a cloud provider, the consent `ai-egress-detail` (pinned in "
        "dashboard/src/copy/pinned.en.json), docs/cli.md and SECURITY.md say it cannot: "
        "change them with it, then update PLUMBING here."
    )


def test_the_ladder_has_no_caller_in_the_product():
    callers = {
        path for path, doors in _shipped_reach().items() if "resolve_provider" in doors
    }
    assert callers == {"tracker/intelligence_runtime/routing.py"}
    bench = (BACKEND / "scripts" / "bench_relevance_review.py").read_text(encoding="utf-8")
    assert "resolve_provider" in doors_named(bench), "the bench is the control: it does call the ladder"


@pytest.mark.parametrize(
    "planted",
    [
        "from tracker.intelligence_runtime.routing import resolve_provider\n",
        "from tracker.intelligence_runtime import routing\nasync def f(s):\n    return await routing.build_tiers(s, task_type=None)\n",
        "import tracker.intelligence.providers.cloud as c\nprovider = c.CloudLLMProvider(None)\n",
    ],
    ids=["imported", "attribute_call", "module_alias"],
)
def test_the_scan_sees_a_planted_door(planted):
    assert doors_named(planted), "the reach scan missed a door, so its verdict means nothing"


@pytest.fixture
def machine(monkeypatch, tmp_path):
    pin_lineage_environment(monkeypatch)
    return pin_integration_machine(monkeypatch, tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("local_model", "status", "code"),
    [(True, 200, None), (False, 409, "no-local-model")],
    ids=["local_model_answers", "no_local_model_refuses"],
)
async def test_duplicate_review_never_reaches_a_cloud_provider_with_egress_on(
    api_client, db_session, machine, local_model, status, code
):
    seeded = await seed_lineage_contract(db_session, local_model=local_model)
    cloud = await seed_cloud_connection(db_session, egress=True, enabled=True)
    assert await get_ai_egress_enabled(db_session)

    response = await api_client.post(f"/api/lineage/links/{seeded.pending_link}/analyze")
    assert response.status_code == status, response.text
    if code is None:
        assert response.json()["provider"] == "omlx"
    else:
        assert code_of(response.json()) == code
    assert machine.cloud.requests == [], "duplicate review reached the cloud provider"

    # The control: the same cloud double does see a request when the Test makes one.
    tested = await api_client.post(f"/api/intelligence/cloud-models/{cloud.id}/test")
    assert tested.status_code == 200, tested.text
    assert len(machine.cloud.requests) == 1


def test_the_pinned_consent_states_the_scope_and_names_no_posting_text():
    consent = json.loads(PINNED.read_text(encoding="utf-8"))["ai-egress-detail"]
    assert "Only the AI providers you turn on are used" in consent
    assert "each with your own API key" in consent
    assert "ones you add or turn on later" in consent
    assert "posting" not in consent.lower(), (
        "the consent now speaks of postings; if a task sends posting text, "
        "update PLUMBING and the reach tests with it"
    )
