"""S120 unit (a): chain-carrying build_dossier tests.

Drives the REAL producer (cmd_verify --smt --supersedes) to mint
build-valid signed manifests carrying prior_digest, then exercises the
real build_dossier chain block across all six branches:

  1. genesis (prior_digest None, no supersedes) -> no chain/ dir
  2. prior_digest None + supersedes given       -> REFUSE
  3. prior_digest set + supersedes None          -> REFUSE
  4. re-bind depth-1                              -> chain/000 = genesis
  5. re-bind depth-2                              -> chain = [genesis, v1]
  6. self-consistency mismatch                    -> REFUSE

The non-no-op re-binding is produced by appending a NOUS comment
(# ...; %ignore COMMENT in nous.lark) to the child source: the AST and
thus smt_spec_sha256 are unchanged, only source_sha256 moves, which alone
satisfies the producer's sha-bearing-field-moved check.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import DossierError, build_dossier

TEMPLATE = Path(__file__).resolve().parent.parent / (
    "aml_transaction_governance.nous"
)


def _produce(
    tmp_path: Path,
    *,
    source_bytes: bytes,
    supersedes: str | None = None,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "source.nous"
    src.write_bytes(source_bytes)
    mout = tmp_path / "source.manifest.json"

    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(mout)
        key_path = str(tmp_path / "signing.key")
        smt_margin = 0
        coverage_threshold = "amount > 10000"
        no_lint = True
        lint_strict = False
        lint_error_on = None

    Args.supersedes = supersedes
    rc = cmd_verify(Args())
    assert rc == 0, "producer failed for " + str(tmp_path)
    assert mout.is_file()
    return src, mout


def _genesis(tmp_path: Path) -> tuple[Path, Path]:
    return _produce(tmp_path, source_bytes=TEMPLATE.read_bytes())


def _child(
    tmp_path: Path, predecessor_manifest: Path
) -> tuple[Path, Path]:
    rebind_source = TEMPLATE.read_bytes() + b"\n# rebind marker\n"
    return _produce(
        tmp_path,
        source_bytes=rebind_source,
        supersedes=str(predecessor_manifest),
    )


def _prior_digest(manifest_path: Path) -> str | None:
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    return doc.get("prior_digest")


def test_genesis_emits_no_chain_dir(tmp_path: Path) -> None:
    g = tmp_path / "g"
    g.mkdir()
    src, mout = _genesis(g)
    assert _prior_digest(mout) is None
    out = tmp_path / "d0"
    result = build_dossier(src, manifest=mout, output=out)
    assert not (out / "chain").exists()
    assert not any(f.startswith("chain/") for f in result.files)


def test_prior_none_with_supersedes_refused(tmp_path: Path) -> None:
    g = tmp_path / "g"
    g.mkdir()
    src, mout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(src, manifest=mout, output=out0)
    src2, mout2 = _genesis(tmp_path / "g2")
    out = tmp_path / "dX"
    with pytest.raises(DossierError, match="no prior_digest"):
        build_dossier(src2, manifest=mout2, output=out, supersedes=out0)


def test_prior_set_without_supersedes_refused(tmp_path: Path) -> None:
    g = tmp_path / "g"
    g.mkdir()
    src, mout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(src, manifest=mout, output=out0)
    c = tmp_path / "c"
    c.mkdir()
    csrc, cmout = _child(c, mout)
    assert _prior_digest(cmout) is not None
    out = tmp_path / "dY"
    with pytest.raises(DossierError, match="no --supersedes"):
        build_dossier(csrc, manifest=cmout, output=out)


def test_rebind_depth1_chain000_is_genesis(tmp_path: Path) -> None:
    g = tmp_path / "g"
    g.mkdir()
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)
    c = tmp_path / "c"
    c.mkdir()
    csrc, cmout = _child(c, gmout)
    out1 = tmp_path / "d1"
    result = build_dossier(
        csrc, manifest=cmout, output=out1, supersedes=out0
    )
    assert result.files.count("chain/000_manifest.json") == 1
    assert not (out1 / "chain" / "001_manifest.json").exists()
    assert (
        (out1 / "chain" / "000_manifest.json").read_bytes()
        == (out0 / "manifest.json").read_bytes()
    )


def test_rebind_depth2_chain_ordering(tmp_path: Path) -> None:
    g = tmp_path / "g"
    g.mkdir()
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    c1 = tmp_path / "c1"
    c1.mkdir()
    c1src, c1mout = _child(c1, gmout)
    out1 = tmp_path / "d1"
    build_dossier(c1src, manifest=c1mout, output=out1, supersedes=out0)

    c2 = tmp_path / "c2"
    c2.mkdir()
    c2src = c2 / "source.nous"
    c2src.write_bytes(TEMPLATE.read_bytes() + b"\n# rebind marker 2\n")
    c2mout = c2 / "source.manifest.json"

    class Args2:
        file = str(c2src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(c2mout)
        key_path = str(c2 / "signing.key")
        smt_margin = 0
        coverage_threshold = "amount > 10000"
        no_lint = True
        lint_strict = False
        lint_error_on = None
        supersedes = str(c1mout)

    assert cmd_verify(Args2()) == 0
    out2 = tmp_path / "d2"
    result = build_dossier(
        c2src, manifest=c2mout, output=out2, supersedes=out1
    )
    links = sorted(f for f in result.files if f.startswith("chain/"))
    assert links == [
        "chain/000_manifest.json",
        "chain/001_manifest.json",
    ]
    assert (
        (out2 / "chain" / "000_manifest.json").read_bytes()
        == (out0 / "manifest.json").read_bytes()
    )
    assert (
        (out2 / "chain" / "001_manifest.json").read_bytes()
        == (out1 / "manifest.json").read_bytes()
    )


def test_self_consistency_mismatch_refused(tmp_path: Path) -> None:
    g = tmp_path / "g"
    g.mkdir()
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    other = tmp_path / "other"
    other.mkdir()
    osrc, omout = _produce(
        other,
        source_bytes=TEMPLATE.read_bytes() + b"\n# distinct other envelope\n",
    )
    outo = tmp_path / "do"
    build_dossier(osrc, manifest=omout, output=outo)

    c = tmp_path / "c"
    c.mkdir()
    csrc, cmout = _child(c, gmout)
    out = tmp_path / "dZ"
    with pytest.raises(DossierError, match="self-consistency"):
        build_dossier(csrc, manifest=cmout, output=out, supersedes=outo)
