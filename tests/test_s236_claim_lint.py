"""Lock test for scripts/claim_lint.py.  __s236_p3_claim_lint_lock_test_v1__

claim_lint.py has been a RELEASE GATE since S232 (phase_claim_lint, [5b/10])
and NOTHING GUARDED IT. Break a predicate and every future release silently
un-gates: the phase still runs, still prints "0 violations", and still passes.
A gate whose predicates are unguarded is a gate that can be disarmed by a typo.
Carried unwritten from S231, S232, S234 and S235. Written here.

Fixtures are EMBEDDED BYTES and the REAL claims.toml, never git history:
GitHub Actions checks out at fetch-depth 1, so a test that shells `git show`
passes on the server and FAILS IN CI.

Every predicate carries BOTH controls: the real defect it was built to catch
(must go red) and a conformant sibling (must stay green). A guard observed only
passing has not been observed.

This test EVIDENCES that the linter's declared predicates still fire. It PROVES
nothing about whether any claim in the tree is true -- the linter does not
determine that, and neither does this.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_PATH = REPO_ROOT / "scripts" / "claim_lint.py"
CLAIMS_TOML = REPO_ROOT / "claims.toml"
RELEASE_PATH = REPO_ROOT / "scripts" / "release.py"


def _load():
    spec = importlib.util.spec_from_file_location("claim_lint", LINT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["claim_lint"] = module
    spec.loader.exec_module(module)
    return module


def _run(module, root: Path, capsys, config: Path | None = None) -> tuple[int, dict]:
    rc = module.main([
        "--config", str(config or CLAIMS_TOML),
        "--root", str(root),
        "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    return rc, payload


def _tree(tmp_path: Path, name: str, body: str) -> Path:
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    return root


def _predicates(payload: dict) -> list[str]:
    return [v["predicate"] for v in payload["violations"]]


def test_lint_script_and_config_exist() -> None:
    assert LINT_PATH.is_file(), "scripts/claim_lint.py is the [5b/10] gate"
    assert CLAIMS_TOML.is_file(), "claims.toml IS the declared convention"


def test_declared_proof_legs_is_three() -> None:
    """The three genuine legs: cost-cap, policy-coverage, sequence-ordering.
    If this number moves, the whole boundary moved and it was not this test's
    decision to allow it."""
    module = _load()
    cfg = module.load_config(CLAIMS_TOML)
    assert cfg.declared_proof_legs == 3


def test_object_predicate_catches_the_f2c2409_defect(tmp_path, capsys) -> None:
    """NEGATIVE CONTROL, and the real reproducer. The pre-f2c2409 sentence was
    PASSIVE -- a backward-only binding would have missed it entirely. Identity
    is a forbidden object: NOUS runs no CA and the name-to-key binding is
    operator-asserted."""
    module = _load()
    root = _tree(
        tmp_path, "doc.md",
        "Author identity is proven by the Ed25519 signature.\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 1
    assert "object" in _predicates(payload)


def test_object_predicate_active_voice_also_caught(tmp_path, capsys) -> None:
    module = _load()
    root = _tree(tmp_path, "doc.md", "The dossier proves author identity.\n")
    rc, payload = _run(module, root, capsys)
    assert rc == 1
    assert "object" in _predicates(payload)


def test_negation_stays_green(tmp_path, capsys) -> None:
    """POSITIVE CONTROL. The honest sentence must not fire, or the linter is a
    predicate that always fires and is worthless as a gate."""
    module = _load()
    root = _tree(
        tmp_path, "doc.md",
        "Author identity is NOT proven by this signature; it is "
        "operator-asserted.\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_byte_identity_is_not_the_forbidden_object(tmp_path, capsys) -> None:
    """POSITIVE CONTROL for a real false positive from the first live scan:
    'byte identity' tokenises through the forbidden object 'identity'."""
    module = _load()
    root = _tree(
        tmp_path, "doc.md",
        "The regression harness proves byte identity held at 0 diffs.\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_axis_predicate_catches_the_s228_defect(tmp_path, capsys) -> None:
    """NEGATIVE CONTROL. VerificationResult.proven filters the SEVERITY axis,
    where prove() AND verify() AND estimate() all set severity='PROVEN'.
    Rendering a reserved word from it renders a count of STATIC CHECKS as a
    proof count. The property name is itself the trap."""
    module = _load()
    root = _tree(
        tmp_path, "mod.py",
        'def r(result):\n'
        '    return f"VERIFIED: {len(result.proven)} proven"\n',
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 1
    assert "axis" in _predicates(payload)


def test_axis_predicate_tier_axis_stays_green(tmp_path, capsys) -> None:
    """POSITIVE CONTROL. The honest axis (verifier.py:146) must stay clean."""
    module = _load()
    root = _tree(
        tmp_path, "mod.py",
        'def r(tproven, tverified):\n'
        '    return f"{tproven} proven, {tverified} verified"\n',
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_stat_card_predicate_catches_an_inflated_count(tmp_path, capsys) -> None:
    """NEGATIVE CONTROL. The stat card is the only shape in English that
    actually asserts how many Z3/Farkas legs exist."""
    module = _load()
    root = _tree(
        tmp_path, "page.html",
        "<div><div>31+</div><div>Formal Proofs</div></div>\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 1
    assert "stat" in _predicates(payload)


def test_stat_card_at_three_stays_green(tmp_path, capsys) -> None:
    """POSITIVE CONTROL. This is the card the live homepage ships."""
    module = _load()
    root = _tree(
        tmp_path, "page.html",
        "<div><div>3</div><div>Z3/Farkas Proofs</div></div>\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_stat_card_singular_is_an_ordinal_not_a_count(tmp_path, capsys) -> None:
    """POSITIVE CONTROL for a real false positive on index.html:596. A numbered
    card title ('1. Envelope proof') is an ORDINAL. Only the plural asserts a
    cardinality."""
    module = _load()
    root = _tree(
        tmp_path, "page.html",
        "<div><div>1</div><div>Envelope proof</div></div>\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_schema_literal_is_not_prose(tmp_path, capsys) -> None:
    """E5. A string whose ENTIRE value is one reserved token is SCHEMA:
    PROVEN = "PROVEN", {"verdict": "proven"}. Handled in code, not by an
    allowlist, so the enum and the JSON key need no entries."""
    module = _load()
    root = _tree(
        tmp_path, "mod.py",
        'PROVEN = "PROVEN"\n'
        'VERDICT = {"tier": "proven"}\n',
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_use_versus_mention(tmp_path, capsys) -> None:
    """E6. The fixture carries a forbidden object AND a reserved word, so it
    would fire without the mention rule -- which is what makes it a control and
    not decoration. Without E6 the linter flags the sentence that declares its
    own boundary."""
    module = _load()
    root = _tree(
        tmp_path, "doc.md",
        "Writing 'proven' about identity would overstate the boundary.\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_terms_of_art_are_not_claims(tmp_path, capsys) -> None:
    """E2. An RFC 6962 inclusion proof is a term of art, not a claim word. The
    fixture puts a forbidden object downstream of two of them, so without E2
    the nearest-claim-word binding fires and this goes red."""
    module = _load()
    root = _tree(
        tmp_path, "doc.md",
        "The consistency proof and the inclusion proof bound the topology of "
        "the log.\n",
    )
    rc, payload = _run(module, root, capsys)
    assert rc == 0, payload["violations"]


def test_a_stale_allowlist_entry_rots_loudly(tmp_path, capsys) -> None:
    """The allowlist pins the sha256 of its justifying line. If that line
    changes, the entry must ROT LOUDLY (exit non-zero) rather than silently
    protect text it was never reviewed against."""
    module = _load()
    root = _tree(tmp_path, "doc.md", "The dossier proves author identity.\n")
    config = tmp_path / "claims_stale.toml"
    config.write_text(
        CLAIMS_TOML.read_text(encoding="utf-8")
        + '\n[[allow]]\npath = "doc.md"\nline = 1\nword = "proves"\n'
        'reason = "fixture"\nregion_sha256 = "' + ("0" * 64) + '"\n',
        encoding="utf-8",
    )
    rc, payload = _run(module, root, capsys, config=config)
    assert rc == 1
    assert payload["allowlist_stale"], "a stale pin must be reported, not honoured"


def test_an_allowlist_entry_matching_nothing_rots(tmp_path, capsys) -> None:
    """A dead entry is a licence nobody is checking. Delete it or it reports."""
    module = _load()
    root = _tree(tmp_path, "doc.md", "The runtime records the trace.\n")
    config = tmp_path / "claims_dead.toml"
    config.write_text(
        CLAIMS_TOML.read_text(encoding="utf-8")
        + '\n[[allow]]\npath = "gone.md"\nline = 9\nword = "proves"\n'
        'reason = "fixture"\nregion_sha256 = "' + ("0" * 64) + '"\n',
        encoding="utf-8",
    )
    rc, payload = _run(module, root, capsys, config=config)
    assert rc == 1
    assert payload["allowlist_stale"]


def test_the_live_tree_is_clean() -> None:
    """THE GATE ITSELF, over the real tree. This is [5b/10]."""
    module = _load()
    rc = module.main([
        "--config", str(CLAIMS_TOML),
        "--root", str(REPO_ROOT),
        "--json",
    ])
    assert rc == 0


def test_gate_is_wired_into_release() -> None:
    """A mechanism nothing forces rots. The tool is only a gate if the release
    path calls it -- which is the S231 lesson and the reason S232 wired it."""
    release = RELEASE_PATH.read_text(encoding="utf-8")
    assert "__s232_p2_claim_lint_phase_v1__" in release
    assert "__s232_p2_claim_lint_call_v1__" in release
    assert "claim_lint.py" in release
