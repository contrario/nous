"""Lock test for the release-VSA bundle alias.  __s236_p1_alias_lock_test_v1__

THE DEFECT THIS REPRODUCES. The offline verifier a stranger downloads reads
exactly one filename: build-vsa.intoto.json. For nineteen releases the mint
wrote only the version-named VSA into the publish directory and copied the
alias into a TEMPORARY DIRECTORY to self-verify -- so the producer's check
passed against an input the producer had constructed, and every published
bundle failed a bare run of its own verifier (rc 2). S234 backfilled the alias
into the 19 published bundles as new files; it did NOT touch the producer.
This test is the forcing function that keeps the producer honest, and it fails
at 6343689.

A verification whose input is constructed by the verifier is not a verification
of anything a stranger will ever hold.

Every predicate carries its control: the published bundles (which DO ship the
alias, since S234) must stay green, and the producer paths that do not emit it
must go red. A guard that passes either way proves nothing.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import shutil
from pathlib import Path

import pytest

import mint_release_vsa as M

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_VSA_DIR = REPO_ROOT / "website" / ".well-known" / "nous" / "release-vsa"
REF_VERSION = "5.60.1"
REF_DIR = RELEASE_VSA_DIR / REF_VERSION

ALIAS = "build-vsa.intoto.json"
VERIFIER = "verify_build_vsa_offline.py"
VERIFIER_KEY = "release-verifier-key.json"


def _versioned(version: str) -> str:
    return "nous_lang-" + version + "." + ALIAS


def _posix_line(data: bytes, name: str) -> bytes:
    return (hashlib.sha256(data).hexdigest() + "  " + name + "\n").encode("ascii")


def _mint_dir(tmp_path: Path, *, with_alias: bool) -> Path:
    d = tmp_path / "mintdir"
    d.mkdir()
    for name in (_versioned(REF_VERSION), VERIFIER, VERIFIER_KEY):
        shutil.copy2(REF_DIR / name, d / name)
    if with_alias:
        shutil.copy2(REF_DIR / ALIAS, d / ALIAS)
    return d


def _pins(tmp_path: Path) -> Path:
    p = tmp_path / "pins"
    p.mkdir()
    (p / "trusted_root.json").write_text("{}", encoding="utf-8")
    (p / "tsa_chain.pem").write_text("x", encoding="utf-8")
    return p


def _never_anchor(*args, **kwargs):
    raise AssertionError(
        "anchor() reached the IRREVERSIBLE Rekor write with a bundle that "
        "does not ship " + ALIAS + " under the name its own offline verifier "
        "reads. A stranger running the published procedure gets rc 2."
    )


def test_verifier_template_reads_only_the_alias_name() -> None:
    """POSITIVE CONTROL, and the premise of every other test in this file.
    The verifier shipped in every bundle hardcodes this one filename; no
    argument an auditor can type reaches the version-named file."""
    import build_vsa

    src = build_vsa.BUILD_VSA_VERIFY_OFFLINE_PY
    assert 'ROOT / "' + ALIAS + '"' in src
    assert 'Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent' in src


def test_mint_emits_the_alias_into_the_publish_dir() -> None:
    """The producer must write the file the verifier reads, into the directory
    that gets published -- not into a temp dir it then verifies."""
    src = Path(M.__file__).read_text(encoding="utf-8")
    assert "__s236_p1_alias_const_v1__" in src
    assert "__s236_p1_alias_emit_v1__" in src
    assert M.VERIFIER_VSA_FILENAME == ALIAS
    assert "_write_with_sidecar(out_dir / VERIFIER_VSA_FILENAME" in src


def test_root1_self_verify_constructs_no_input() -> None:
    """FG-S234-A, at its root. The self-check must run the command the
    document tells a stranger to run: the verifier, bare, in the publish
    directory. If it builds its own input, it verifies nothing anyone holds."""
    src = inspect.getsource(M._root1_self_verify)
    assert "__s236_p1_root1_no_construct_v1__" in src
    assert "TemporaryDirectory" not in src, (
        "the ROOT-1 self-verify still constructs its own input directory"
    )
    tree = ast.parse(src.lstrip())
    argvs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.List)
        and any(
            isinstance(e, ast.Attribute) and e.attr == "executable"
            for e in node.elts
        )
    ]
    assert len(argvs) == 1, "expected exactly one subprocess argv list"
    assert len(argvs[0].elts) == 2, (
        "the verifier must be invoked BARE (no directory argument); an argv "
        "the auditor never types is not the auditor's command"
    )


@pytest.mark.skipif(not REF_DIR.is_dir(), reason="5.60.1 reference dir absent")
def test_anchor_refuses_a_bundle_with_no_alias(tmp_path: Path) -> None:
    """NEGATIVE CONTROL. The alias must be structurally required BEFORE the
    irreversible Rekor write, not discovered by an auditor afterwards."""
    d = _mint_dir(tmp_path, with_alias=False)
    with pytest.raises(M.MintError, match=ALIAS):
        M.anchor(
            REF_VERSION,
            d,
            pins_dir=_pins(tmp_path),
            anchor_fn=_never_anchor,
            timestamp_fn=lambda **k: b"",
            verify_fn=lambda a, b: {},
        )


@pytest.mark.skipif(not REF_DIR.is_dir(), reason="5.60.1 reference dir absent")
def test_anchor_refuses_a_divergent_alias(tmp_path: Path) -> None:
    """A bundle whose alias and version-named VSA differ would verify bytes
    other than the ones it names. Refuse before the anchor."""
    d = _mint_dir(tmp_path, with_alias=True)
    (d / ALIAS).write_bytes(b'{"payloadType":"tampered"}\n')
    with pytest.raises(M.MintError, match="differ"):
        M.anchor(
            REF_VERSION,
            d,
            pins_dir=_pins(tmp_path),
            anchor_fn=_never_anchor,
            timestamp_fn=lambda **k: b"",
            verify_fn=lambda a, b: {},
        )


@pytest.mark.skipif(
    not RELEASE_VSA_DIR.is_dir(), reason="no release-vsa mirror in this checkout"
)
def test_every_published_bundle_ships_a_verifiable_alias() -> None:
    """POSITIVE CONTROL over the real committed mirror. Green since S234's
    backfill; this is the assertion that would have failed for nineteen
    consecutive releases before it."""
    bundles = sorted(p for p in RELEASE_VSA_DIR.iterdir() if p.is_dir())
    assert bundles, "the mirror ships bundles; scanning zero means the walk "\
                    "is broken and this gate is vacuous"
    problems: list[str] = []
    for bundle in bundles:
        version = bundle.name
        alias = bundle / ALIAS
        sidecar = bundle / (ALIAS + ".sha256")
        versioned = bundle / _versioned(version)
        if not versioned.is_file():
            problems.append(version + ": no version-named VSA")
            continue
        if not alias.is_file():
            problems.append(version + ": no " + ALIAS + " (bare verifier run -> rc 2)")
            continue
        if not sidecar.is_file():
            problems.append(version + ": alias has no .sha256 sidecar")
            continue
        alias_bytes = alias.read_bytes()
        if alias_bytes != versioned.read_bytes():
            problems.append(version + ": alias bytes differ from the version-named VSA")
            continue
        if sidecar.read_bytes() != _posix_line(alias_bytes, ALIAS):
            problems.append(version + ": alias sidecar is not the POSIX line for its own bytes")
    assert not problems, "\n".join(problems)


@pytest.mark.skipif(
    not RELEASE_VSA_DIR.is_dir(), reason="no release-vsa mirror in this checkout"
)
def test_published_alias_is_a_signed_dsse_envelope() -> None:
    """The alias is not a placeholder: it is the same signed envelope, so the
    bare verifier run reaches the signature check on real bytes."""
    for bundle in sorted(p for p in RELEASE_VSA_DIR.iterdir() if p.is_dir()):
        alias = bundle / ALIAS
        if not alias.is_file():
            continue
        envelope = json.loads(alias.read_text(encoding="utf-8"))
        assert envelope["payloadType"] == "application/vnd.in-toto+json"
        assert envelope["signatures"], bundle.name + ": alias carries no signature"


def test_the_published_procedure_names_the_alias() -> None:
    """docs/VERIFYING_A_RELEASE.md (S235) tells every auditor to fetch this
    exact filename. The producer emitting it is what keeps that document
    true at the NEXT release, not only for the backfilled ones."""
    doc = REPO_ROOT / "docs" / "VERIFYING_A_RELEASE.md"
    if not doc.is_file():
        pytest.skip("docs/VERIFYING_A_RELEASE.md not in this checkout")
    text = doc.read_text(encoding="utf-8")
    assert ALIAS in text
    assert "python3 " + VERIFIER in text
