"""trace-bundle dossier wiring: embed parity + emitted-verifier + byte-identity.

Mirrors test_s190_pce_dossier. The dossier carries the NOUS-TRACE runtime-
evidence verifier as the _TRACE_BUNDLE_CHECK_EMBED string. These tests extract
that exact embed, import it, and assert:

  1. PARITY: the embed's _tb_verify_pack verdict (code + reason) equals the
     AUTHORITATIVE trace/reference/verifier.py verify_pack on shared real
     packs, incl. tamper variants (the dossier verdict can never drift from
     the committed reference verifier).
  2. EMITTED VERIFIER: dossier._splice_trace_bundle_check produces a verifier
     that, on a synthetic dossier, returns rc 0 on VALID and on INCOMPLETE
     (monitor, never gate) and rc 1 only on integrity failure (bundle-manifest
     sha swap, tampered event).
  3. NO-FIELD BYTE-IDENTITY: the splice is never applied without a bundle, so a
     verifier carrying no trace_bundle_sha256 is byte-identical to its template.

importorskip keeps this green-on-server and skipped where dossier / trace_bridge
/ the reference verifier are not importable.
"""
from __future__ import annotations

import sys as _sys  # __trace_bundle_test_syspath_v1__ _REPO_ROOT_ONPATH
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

dossier = pytest.importorskip("dossier")
trace_bridge = pytest.importorskip("trace_bridge")

_REPO = Path(__file__).resolve().parent.parent
_REF_PATH = _REPO / "trace" / "reference" / "verifier.py"
_TB_SOURCE_PATH = _REPO / "tb_check.py"


def _load_embed():
    src = getattr(dossier, "_TRACE_BUNDLE_CHECK_EMBED", None)
    assert isinstance(src, str) and "_check_trace_bundle" in src, \
        "dossier._TRACE_BUNDLE_CHECK_EMBED missing"
    d = Path(tempfile.mkdtemp())
    p = d / "_tb_embed_extracted.py"
    p.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_tb_embed_extracted", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load_reference():
    if not _REF_PATH.is_file():
        pytest.skip("reference verifier not present")
    spec = importlib.util.spec_from_file_location("_tb_reference", _REF_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _build_valid_pack(root: Path) -> Path:
    pack = root / "bundle"
    keys = root / "keys"
    pred = {"op": "or", "args": [
        {"op": "<=", "left": {"var": "amt"}, "right": {"int": 100}},
        {"var": "approved"}]}
    obls = [{"label": "cap", "predicate": pred,
             "variables": [{"name": "amt", "type": "int"},
                           {"name": "approved", "type": "bool"}],
             "assurance": "declared", "proof_artifact": None,
             "dossier_ref": None}]
    with trace_bridge.TraceBridge(str(pack), "actor", obls, str(keys)) as tb:
        tb.llm_call("m", "prov", "de" * 32, input_bytes=b"{}")
        tb.policy_check("cap", {"amt": 42, "approved": False})
        tb.checkpoint()
    return pack


def _build_incomplete_pack(root: Path) -> Path:
    pack = root / "bundle_inc"
    keys = root / "keys"
    child = (
        "import sys, time; sys.path.insert(0, %r)\n"
        "from trace_bridge import TraceBridge\n"
        "tb = TraceBridge(%r, 'a', [], %r)\n"
        "tb.tool_call('t', 'ad', input_bytes=b'{}')\n"
        "print('R', flush=True); time.sleep(30)\n"
        % (str(_REPO), str(pack), str(root / "keys"))
    )
    p = subprocess.Popen([sys.executable, "-c", child],
                         stdout=subprocess.PIPE, text=True)
    assert "R" in p.stdout.readline()
    p.kill()
    p.wait()
    return pack


def _assemble(dossier_dir: Path, pack: Path, template: str,
              with_field: bool = True) -> Path:
    dossier_dir.mkdir(parents=True, exist_ok=True)
    (dossier_dir / "source.nous").write_text("world W {}\n", encoding="utf-8")
    src_sha = hashlib.sha256(b"world W {}\n").hexdigest()
    man = {"source_sha256": src_sha}
    if with_field:
        import shutil
        shutil.copytree(pack, dossier_dir / "trace_bundle")
        tbm = (dossier_dir / "trace_bundle" / "manifest.json").read_bytes()
        man["trace_bundle_sha256"] = hashlib.sha256(tbm).hexdigest()
        vsrc = dossier._splice_trace_bundle_check(template)
    else:
        vsrc = template
    man = _sign_manifest(man)
    (dossier_dir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (dossier_dir / "verify_offline.py").write_text(vsrc, encoding="utf-8")
    return dossier_dir


def _run(dossier_dir: Path):
    r = subprocess.run([sys.executable, str(dossier_dir / "verify_offline.py")],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _sign_manifest(man: dict) -> dict:
    import base64 as _b64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.hazmat.primitives import serialization
    sk = Ed25519PrivateKey.generate()
    raw_pub = sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    body = {k: v for k, v in man.items() if k != "signature"}
    body_bytes = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sig = sk.sign(body_bytes)
    man["signature"] = {
        "public_key_b64": _b64.b64encode(raw_pub).decode("ascii"),
        "signature_b64": _b64.b64encode(sig).decode("ascii"),
    }
    return man


# ---------------------------------------------------------------- parity ----
def test_embed_parity_with_reference_verifier(tmp_path):
    embed = _load_embed()
    ref = _load_reference()
    pack = _build_valid_pack(tmp_path)

    # VALID pack: same code + verdict
    e_code, e_rep = embed._tb_verify_pack(str(pack))
    r_code, r_rep = ref.verify_pack(str(pack))
    assert e_code == r_code == 0
    assert e_rep["verdict"] == r_rep["verdict"] == "VALID"
    assert e_rep["recomputed"] == r_rep["recomputed"]

    # tampered event: both raise the same reason
    tf = pack / "trace.ndjson"
    ev = [json.loads(x) for x in tf.read_text().splitlines() if x.strip()]
    ev[1]["body"]["model"] = "x"
    tf.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                          for e in ev), encoding="utf-8")
    with pytest.raises(embed._TbVErr) as ei:
        embed._tb_verify_pack(str(pack))
    with pytest.raises(ref.VErr) as ri:
        ref.verify_pack(str(pack))
    assert ei.value.reason == ri.value.reason == "SIG_INVALID"


# -------------------------------------------------------- emitted verifier --
def test_emitted_verifier_valid_is_pass(tmp_path):
    pack = _build_valid_pack(tmp_path)
    d = _assemble(tmp_path / "d_ok", pack, dossier.VERIFY_OFFLINE_PY)
    rc, out, err = _run(d)
    assert rc == 0, (out, err)
    assert "NOUS-TRACE evidence bundle authenticated" in out
    assert "verdict: VALID" in out


def test_emitted_verifier_incomplete_is_monitor(tmp_path):
    pack = _build_incomplete_pack(tmp_path)
    d = _assemble(tmp_path / "d_inc", pack, dossier.VERIFY_OFFLINE_PY)
    rc, out, err = _run(d)
    assert rc == 0, (out, err)          # monitor: adverse finding, not failure
    assert "INCOMPLETE" in out


def test_emitted_verifier_tampered_event_fails(tmp_path):
    pack = _build_valid_pack(tmp_path)
    d = _assemble(tmp_path / "d_tamper", pack, dossier.VERIFY_OFFLINE_PY)
    tf = d / "trace_bundle" / "trace.ndjson"
    ev = [json.loads(x) for x in tf.read_text().splitlines() if x.strip()]
    ev[1]["body"]["model"] = "x"
    tf.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                          for e in ev), encoding="utf-8")
    rc, out, err = _run(d)
    assert rc == 1 and "SIG_INVALID" in err, (rc, out, err)


def test_emitted_verifier_bundle_root_swap_fails(tmp_path):
    pack = _build_valid_pack(tmp_path)
    d = _assemble(tmp_path / "d_swap", pack, dossier.VERIFY_OFFLINE_PY)
    bm = d / "trace_bundle" / "manifest.json"
    m = json.loads(bm.read_text())
    m["tolerance_s"] = 599
    bm.write_text(json.dumps(m), encoding="utf-8")
    rc, out, err = _run(d)
    assert rc == 1 and "does not match" in err, (rc, out, err)


# --------------------------------------------------------- byte-identity ----
def test_no_field_is_byte_identical(tmp_path):
    d = _assemble(tmp_path / "d_none", tmp_path / "unused",
                  dossier.VERIFY_OFFLINE_PY, with_field=False)
    emitted = (d / "verify_offline.py").read_text(encoding="utf-8")
    assert emitted == dossier.VERIFY_OFFLINE_PY
    rc, out, err = _run(d)
    assert rc == 0 and "VERDICT: PASS" in out, (rc, out, err)


def test_embed_matches_tracked_source():
    # The tracked tb_check.py is the embed source-of-truth; the shipped
    # dossier constant must equal it byte-for-byte (no silent drift).
    if not _TB_SOURCE_PATH.is_file():
        pytest.skip("tb_check.py source not tracked in repo root")
    src = _TB_SOURCE_PATH.read_text(encoding="utf-8")
    assert src == dossier._TRACE_BUNDLE_CHECK_EMBED, (
        "tb_check.py has drifted from dossier._TRACE_BUNDLE_CHECK_EMBED; "
        "re-run the dossier patch or reconcile the two"
    )
