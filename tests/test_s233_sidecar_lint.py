"""Lock test for scripts/sidecar_lint.py.  __s233_p3_sidecar_lock_test_v1__

Fixtures are EMBEDDED BYTES, never git history: GitHub Actions checks out at
fetch-depth 1, so a test that shells `git show` passes on the server and FAILS
IN CI.

The reproducer at the centre of this file is the REAL S233 defect: the
published verifier-registry.json.sha256 carried the digest of the registry
from eighteen releases earlier, in bare-hex form with no filename field. The
format defect made `sha256sum -c` refuse the file before it could report the
digest mismatch, so the integrity defect stayed invisible.

Every predicate carries a NEGATIVE CONTROL: a conformant fixture that must
stay green, paired with the defect that must go red. A guard that passes
either way proves nothing.
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_PATH = REPO_ROOT / "scripts" / "sidecar_lint.py"

CONTENT = b'{"registry_schema":"nous.verifier_registry.v1","entries":[]}\n'
GOOD_SHA = hashlib.sha256(CONTENT).hexdigest()

STALE_SHA = "b5af4d0532959be530ec2b89a0c86270dd185a7d919ff3d6c8eb43cb80212e7e"

TARGET_NAME = "verifier-registry.json"


def _load():
    spec = importlib.util.spec_from_file_location("sidecar_lint", LINT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sidecar_lint"] = module
    spec.loader.exec_module(module)
    return module


def _bundle(tmp_path: Path, sidecar_bytes: bytes,
            content: bytes = CONTENT) -> Path:
    root = tmp_path / "well-known"
    root.mkdir(parents=True, exist_ok=True)
    (root / TARGET_NAME).write_bytes(content)
    (root / (TARGET_NAME + ".sha256")).write_bytes(sidecar_bytes)
    return root


def _posix(digest: str, name: str = TARGET_NAME) -> bytes:
    return (digest + "  " + name + "\n").encode("ascii")


def test_lint_script_exists() -> None:
    assert LINT_PATH.is_file(), "scripts/sidecar_lint.py is the release gate"


def test_conformant_sidecar_passes(tmp_path: Path) -> None:
    """POSITIVE CONTROL. A correct sidecar must be green, or the tool is a
    predicate that always fires and is worthless as a gate."""
    module = _load()
    root = _bundle(tmp_path, _posix(GOOD_SHA))
    total, violations = module.scan(root)
    assert total == 1
    assert violations == []
    assert module.main(["--root", str(root)]) == 0


def test_the_real_s233_defect_is_caught(tmp_path: Path) -> None:
    """NEGATIVE CONTROL, and the reproducer. Bare hex, no filename field,
    carrying a digest from eighteen releases earlier. This is byte-for-byte
    the shape of the published sidecar before S233."""
    module = _load()
    root = _bundle(tmp_path, (STALE_SHA + "\n").encode("ascii"))
    total, violations = module.scan(root)
    assert total == 1
    assert len(violations) == 1
    assert violations[0].kind == "BAD-FORMAT"
    assert module.main(["--root", str(root)]) == 1


def test_digest_drift_is_caught(tmp_path: Path) -> None:
    """POSIX-formatted but naming a digest the file does not have. This is the
    defect the format bug was HIDING."""
    module = _load()
    root = _bundle(tmp_path, _posix(STALE_SHA))
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "DIGEST-DRIFT"
    assert module.main(["--root", str(root)]) == 1


def test_sidecar_naming_another_file_is_caught(tmp_path: Path) -> None:
    """A sidecar whose checksum line names a DIFFERENT file passes sha256sum
    -c against that other file while telling the auditor nothing about its
    own target."""
    module = _load()
    root = _bundle(tmp_path, _posix(GOOD_SHA, "some-other-file.json"))
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "WRONG-NAME"


def test_missing_target_is_caught(tmp_path: Path) -> None:
    module = _load()
    root = tmp_path / "wk"
    root.mkdir()
    (root / (TARGET_NAME + ".sha256")).write_bytes(_posix(GOOD_SHA))
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "NO-TARGET"


def test_non_ascii_sidecar_is_caught(tmp_path: Path) -> None:
    module = _load()
    root = _bundle(tmp_path, GOOD_SHA.encode("ascii") + b"  \xff\n")
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "NON-ASCII"


def test_single_space_is_rejected(tmp_path: Path) -> None:
    """GNU coreutils writes TWO spaces for binary mode. One space is the
    text-mode form and is not what the rest of the tree ships."""
    module = _load()
    root = _bundle(
        tmp_path, (GOOD_SHA + " " + TARGET_NAME + "\n").encode("ascii")
    )
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "BAD-FORMAT"


def test_uppercase_hex_is_rejected(tmp_path: Path) -> None:
    module = _load()
    root = _bundle(tmp_path, _posix(GOOD_SHA.upper()))
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "BAD-FORMAT"


def test_trailing_junk_is_rejected(tmp_path: Path) -> None:
    """A second line, or anything after the checksum line, is not the shape
    this convention declares."""
    module = _load()
    root = _bundle(tmp_path, _posix(GOOD_SHA) + b"extra\n")
    total, violations = module.scan(root)
    assert len(violations) == 1
    assert violations[0].kind == "BAD-FORMAT"


def test_live_website_mirror_is_clean() -> None:
    """THE GATE ITSELF, over the real committed mirror. This is the assertion
    that would have failed at 14f6655, the release that shipped the stale
    registry sidecar."""
    module = _load()
    website = REPO_ROOT / "website"
    if not website.is_dir():
        pytest.skip("no website/ mirror in this checkout")
    total, violations = module.scan(website)
    assert total > 0, "the mirror ships sidecars; scanning zero means the "\
                      "walk is broken and the gate is vacuous"
    assert violations == [], "\n".join(
        v.render(website) for v in violations
    )


def test_gate_is_wired_into_release() -> None:
    """A mechanism nothing forces rots. The tool is only a gate if the release
    path calls it."""
    release = (REPO_ROOT / "scripts" / "release.py").read_text(
        encoding="utf-8"
    )
    assert "__s233_p3_sidecar_phase_v1__" in release
    assert "__s233_p3_sidecar_call_v1__" in release
    assert "sidecar_lint.py" in release
