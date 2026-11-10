"""Pure-logic tests for skill overlap aggregation (no DB).

Pins the pairing and ordering math behind the Overlap view.
"""

from __future__ import annotations

from tracker.skills.analytics import compute_overlap, seriate


def test_overlap_weighs_a_skill_by_how_few_companies_name_it():
    """A skill every compared company names says nothing about a pair."""
    skill_sets = {
        "a": {"python": 5, "rust": 2, "go": 1},
        "b": {"python": 4, "rust": 6},
        "c": {"scala": 3, "python": 1},
        "d": {"scala": 2},
    }
    pairs = {(p["a"], p["b"]): p for p in compute_overlap(skill_sets, ["a", "b", "c", "d"])}
    # Python is named by three of four: weighed little. Rust, by two: what a and b share.
    ab, ac = pairs[("a", "b")], pairs[("a", "c")]
    assert (ab["shared"], ab["union"]) == (2, 3)
    assert ab["top_shared_terms"][0] == "rust"
    assert ab["similarity"] > ac["similarity"] > 0
    assert pairs[("c", "d")]["top_shared_terms"] == ["scala"]
    assert ("a", "d") not in pairs  # nothing shared, no pair


def test_a_skill_every_company_names_scores_nothing():
    pairs = compute_overlap({"a": {"python": 5}, "b": {"python": 1}}, ["a", "b"])
    assert pairs[0]["similarity"] == 0.0


def test_seriation_puts_similar_companies_side_by_side():
    pairs = [
        {"a": "x1", "b": "x2", "similarity": 0.9}, {"a": "y1", "b": "y2", "similarity": 0.8},
        {"a": "x1", "b": "y1", "similarity": 0.1}, {"a": "x2", "b": "y2", "similarity": 0.05},
        {"a": "x1", "b": "y2", "similarity": 0.0}, {"a": "x2", "b": "y1", "similarity": 0.0},
    ]
    order = seriate(["x1", "y1", "x2", "y2"], pairs)
    assert {frozenset(order[:2]), frozenset(order[2:])} == {frozenset({"x1", "x2"}), frozenset({"y1", "y2"})}
    assert seriate(["a", "b"], []) == ["a", "b"]
