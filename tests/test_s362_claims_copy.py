from __future__ import annotations

from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent

OVERCLAIMS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "no execution path can ever exceed it",
        "across every reachable path, that total cost cannot exceed",
    ),
    "docs/COST_VERIFICATION_GUIDE.md": (
        "first agentic programming language",
        "that your agent will not exceed a",
    ),
    "docs/SKILL_EXPORT.md": ("semantically equivalent at runtime",),
    "docs/ANNEX_IV_MAPPING.md": ("guarantees about every possible run",),
    "website/index.html": (
        "Each run is proven to stay inside",
        "proves the cost ceiling",
    ),
    "website/coverage.html": (
        "cannot exceed its declared spend",
        "proves the cost ceiling",
    ),
    "website/blog/index.html": (
        "Z3 proves every reachable execution path stays under the cap",
        "cannot exceed its declared spend",
        "we proved we will not exceed",
        "the proven bound matches the alarm",
        "Z3 proved it cannot",
        "that every reachable execution path stays under the cap",
        "formally verified against the world",
        "Every system is formally verified",
        "statically verifies they cannot occur",
    ),
    "website/docs/index.html": (
        "The clone is formally verified before deployment",
        "formal verification gate",
    ),
}

DISCLOSURES: dict[str, tuple[str, ...]] = {
    "README.md": (
        "it does not meter or stop spend at runtime",
        "it does not meter or cap what a run actually spends",
    ),
    "docs/COST_VERIFICATION_GUIDE.md": ("declared cost envelope",),
    "docs/SKILL_EXPORT.md": ("The two forms are not equivalent.",),
    "docs/ANNEX_IV_MAPPING.md": ("not what any run spends",),
    "website/index.html": (
        "resource (an estimate, not a proof)",
        "The proof covers the declarations, not metered spend",
        "proves the cost cap over the declared cost envelope",
    ),
    "website/coverage.html": (
        "declared cost envelope cannot exceed its declared cost cap",
        "proves the cost cap over the declared cost envelope",
    ),
    "website/blog/index.html": (
        "it does not meter what a run spends",
        "the runtime alarm still does its own job",
        "(a tier-price estimate)",
        "Cost overrun it only estimates here",
        "priced from its declared model in the pricing table",  # __s364_p2_s362_disclosure_v1__
    ),
    "website/docs/index.html": ("its cost check is an estimate",),
}


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_no_shipped_copy_states_the_cost_bound_as_spend() -> None:
    found = [
        (rel, phrase)
        for rel, phrases in OVERCLAIMS.items()
        for phrase in phrases
        if phrase in _text(rel)
    ]
    assert found == [], f"overclaim copy present: {found}"


def test_corrected_copy_says_what_the_proof_covers() -> None:
    missing = [
        (rel, phrase)
        for rel, phrases in DISCLOSURES.items()
        for phrase in phrases
        if phrase not in _text(rel)
    ]
    assert missing == [], f"corrected copy missing: {missing}"


def test_codegen_does_not_read_world_cost_cap() -> None:
    assert "cost_cap" not in _text("codegen.py"), (
        "codegen.py now reads cost_cap; docs/SKILL_EXPORT.md says the "
        "generated runtime reads only the cost law, so review that copy"
    )


def test_smt_emit_does_not_read_the_cost_law() -> None:
    assert "LawCost" not in _text("smt_emit.py"), (
        "smt_emit.py now reads the cost law; the homepage, coverage page "
        "and docs/SKILL_EXPORT.md say the bound reads only cost_cap, so "
        "review that copy"
    )


def test_vr001_prices_by_model_and_mitosis_by_tier() -> None:  # __s364_p2_s362_rebind_v1__
    text = _text("verifier.py")
    assert "TIER_COSTS" in text, (
        "verifier.py no longer prices from TIER_COSTS; the blog calls the "
        "clone admission check a tier-price estimate, so review that copy"
    )
    assert "self._pricing.resolve(" in text, (
        "VR001 no longer resolves the soul's model through the pricing table; "
        "the blog says the resource estimate is priced from the declared "
        "model, so review that copy"
    )
