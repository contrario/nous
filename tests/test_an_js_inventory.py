"""AN-GATE-1 K-JS.6 (RULING 10:44Z, Q2.1): no JSON parse outside the
strict region, found by the AST, not by grep.

Scanned: the 21 verifier texts, every str constant of dossier.py that
parses as Python (the splices), tb_check.py and rekor_check.py, and the
modules on the input reads of the five named installed paths. Collected:
every name bound to the json module or to json.loads, json.load,
json.JSONDecoder (import json, import json as X, from json import ...,
__import__("json")), every call through such a name, and every call of
an attribute named raw_decode, model_validate_json or parse_raw. Lines
inside the strict region are not counted. A call found here and not in
ALLOW fails the test; an ALLOW entry that no longer matches fails it too.
Round 3 (RULING 11:58Z, 2): allow-only. Every reference to the json
module other than json.dumps and json.dump is a hit (aliases,
assignments, getattr, importlib, json.decoder, exception classes), and
so is every pydantic JSON parser (model_validate_json, parse_raw,
validate_json, TypeAdapter, pydantic_core.from_json).

# __an_js_inventory_v1__
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import test_an_js_strict as A

REPO = Path(__file__).resolve().parent.parent
SCOPE_R = ("tb_check.py", "rekor_check.py")
SCOPE_P = ("ndec.py", "cli_ndec.py", "cli_conformance.py", "attest_apr.py",
           "manifest.py", "nous_trace.py", "cli_continuity.py",
           "continuity_ledger.py", "cli_verify_release.py",
           "rekor_v2_offline.py", "cli_verify_cost.py", "rekor_verify_v2.py",
           "verifier_registry.py", "closure_witness.py")


def _region_lines(text: str) -> set:
    lines = text.splitlines()
    out, inside = set(), False
    for i, ln in enumerate(lines, 1):
        if ln == A.REGION_START:
            inside = True
        if inside:
            out.add(i)
        if ln == A.REGION_END:
            inside = False
    return out


ALLOWED_ATTRS = ("dumps", "dump")  # RULING 11:58Z, round 3, 2
PYDANTIC_ATTRS = ("model_validate_json", "parse_raw", "parse_file",
                  "validate_json", "raw_decode")
PYDANTIC_NAMES = ("TypeAdapter", "from_json", "pydantic_core")


def _is_json_import_call(node) -> bool:
    if not (isinstance(node, ast.Call) and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.split(".")[0] == "json"):
        return False
    f = node.func
    return ((isinstance(f, ast.Name) and f.id == "__import__")
            or (isinstance(f, ast.Attribute) and f.attr == "import_module"))


def _qualname(stack) -> str:
    return ".".join(stack) or "<module>"


def scan(src: str, where: str) -> list:
    """[(where, enclosing function, source)] of every reference to the
    json module other than json.dumps and json.dump, outside the region
    (allow-only, RULING 11:58Z round 3, 2), and of every reference to a
    pydantic JSON parser."""
    tree = ast.parse(src)
    skip = _region_lines(src)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "json":
                    mods.add(a.asname or "json")
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    hits = []

    def hit(node, stack):
        seg = ast.get_source_segment(src, node) or type(node).__name__
        hits.append((where, _qualname(stack), " ".join(seg.split())[:120]))

    def visit(node, stack):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            stack = stack + [node.name]
        line = getattr(node, "lineno", None)
        if line is not None and line not in skip:
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("json."):
                        hit(node, stack)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "json" or mod.startswith("json."):
                    if mod != "json" or any(
                            a.name not in ALLOWED_ATTRS for a in node.names):
                        hit(node, stack)
                if mod.split(".")[0] in ("pydantic", "pydantic_core") and any(
                        a.name in PYDANTIC_NAMES for a in node.names):
                    hit(node, stack)
            elif isinstance(node, ast.Name) and node.id in mods:
                par = parents.get(node)
                if not (isinstance(par, ast.Attribute) and par.value is node
                        and par.attr in ALLOWED_ATTRS):
                    hit(par if isinstance(par, ast.Attribute)
                        and par.value is node else node, stack)
            elif _is_json_import_call(node):
                hit(node, stack)
            elif isinstance(node, ast.Attribute) and (
                    node.attr in PYDANTIC_ATTRS
                    or node.attr in PYDANTIC_NAMES):
                hit(node, stack)
            elif isinstance(node, ast.Name) and node.id in PYDANTIC_NAMES:
                hit(node, stack)
        for child in ast.iter_child_nodes(node):
            visit(child, stack)
    visit(tree, [])
    return hits


def _dossier_constants():
    import dossier
    out, unparsed = {}, []
    src = (REPO / "dossier.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        tg = None
        if isinstance(node, ast.Assign) and isinstance(node.targets[0],
                                                       ast.Name):
            tg = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                            ast.Name):
            tg = node.target.id
        if tg is None:
            continue
        val = getattr(dossier, tg, None)
        if not isinstance(val, str) or "\n" not in val:
            continue
        for cand in (val, textwrap.dedent(val)):
            try:
                ast.parse(cand)
            except SyntaxError:
                continue
            out[tg] = cand
            break
        else:
            if "json" in val:
                unparsed.append(tg)
    return out, unparsed


def test_kjs6_every_dossier_constant_parses():
    # a dossier.py constant that carries json but does not parse would
    # escape the scan (REVIEW 2 item 5)
    assert _dossier_constants()[1] == []


def inventory() -> list:
    hits = []
    for name, text in sorted(A._texts21().items()):
        hits += scan(text, "T:" + name)
    consts, _unparsed = _dossier_constants()
    for name, text in sorted(consts.items()):
        hits += scan(text, "S:dossier." + name)
    for f in SCOPE_R + SCOPE_P:
        hits += scan((REPO / f).read_text(encoding="utf-8"), "F:" + f)
    return hits


_RC = ("the recompute region's own strict loader: it refuses a duplicate "
       "key and a non-finite number with the pinned phrase (K-JS.5)")
_TB = ("a second parse after the region's loads in _tb_jloads, for the "
       "float refusal FLOAT_IN_SIGNED; the region has already refused "
       "duplicates and non-finite numbers in the same text")
_JDE_T = ("the exception class in a handler for malformed JSON around a "
          "region call; it parses nothing (the region raises json's own "
          "error for malformed input)")
_JDE_C = ("the exception class in the installed path's handler for "
          "malformed JSON; it parses nothing (the read inside is the "
          "region's)")
_JDE_P = ("the exception class in a producer command's handler (continuity "
          "link or receipt); it parses nothing")
_JDE = "json.JSONDecodeError"
# (where, enclosing function, source) -> (count, reason). Allow-only
# (RULING 11:58Z, round 3, 2): every other reference to json than dumps
# and dump, and every pydantic JSON parser, must be here.
ALLOW = {
    ("T:builder.conformance_v2", "_conf_rc_load", "json.loads"): (1, _RC),
    ("T:conformance.standalone", "_conf_rc_load", "json.loads"): (1, _RC),
    ("T:vsa.template", "_conf_rc_load", "json.loads"): (1, _RC),
    ("S:dossier._TRACE_BUNDLE_CHECK_EMBED", "_tb_jloads", "_json.loads"):
        (1, _TB),
    ("F:tb_check.py", "_tb_jloads", "_json.loads"): (1, _TB),
    ("F:ndec.py", "build_ndec", "json.loads"):
        (1, "producer: build_ndec reads the dossier it packs; nous ndec "
            "verify does not call it"),
    ("F:cli_conformance.py", "_load_aprs",
     "AttestationPinningRecord.model_validate_json"):
        (1, "the region has accepted these same bytes on the line before"),
    ("F:manifest.py", "parse_manifest_json", "json.loads"):
        (1, "general loader; on the five paths only cli_conformance calls "
            "it, on bytes the region has accepted"),
    ("F:manifest.py", "parse_manifest_json_with_anchor", "json.loads"):
        (1, "general loader; not called on the five paths"),
    ("F:manifest.py", "parse_manifest_json_with_anchor_v2", "json.loads"):
        (1, "general loader; not called on the five paths"),
    ("F:nous_trace.py", "load_trace", "json.load"):
        (1, "general loader; conformance verify builds the trace from the "
            "region's parse and does not call it"),
    ("F:cli_continuity.py", "_read_json", "json.loads"):
        (1, "producers only (continuity link and receipt); continuity "
            "verify reads through _read_json_strict"),
    ("F:continuity_ledger.py", "verify_authorization_receipt", "json.loads"):
        (2, "outside D4 (RULING 10:44Z, Q2.4), named in 3.5"),
    ("T:annex_iv.built", "main", _JDE): (1, _JDE_T),
    ("T:build_vsa.template", "_load_json", _JDE): (1, _JDE_T),
    ("T:build_vsa.template", "_verify_dsse", _JDE): (1, _JDE_T),
    ("T:builder.conformance_v2", "main", _JDE): (2, _JDE_T),
    ("T:builder.dossier_v2", "main", _JDE): (1, _JDE_T),
    ("T:conformance.standalone", "main", _JDE): (2, _JDE_T),
    ("T:continuity.template", "_verify_checkpoint_leg", _JDE): (1, _JDE_T),
    ("T:continuity.template", "main", _JDE): (1, _JDE_T),
    ("T:provenance.template", "_verify_dsse", _JDE): (1, _JDE_T),
    ("T:provenance.template", "main", _JDE): (1, _JDE_T),
    ("T:vsa.template", "_load_json", _JDE): (1, _JDE_T),
    ("T:vsa.template", "_resolve_pin_from_registry", _JDE): (1, _JDE_T),
    ("T:vsa.template", "_verify_dsse", _JDE): (1, _JDE_T),
    ("T:vsa.template", "main", _JDE): (2, _JDE_T),
    ("F:cli_conformance.py", "_cmd_certify", _JDE): (1, _JDE_C),
    ("F:cli_conformance.py", "cmd_conformance", _JDE): (1, _JDE_C),
    ("F:cli_continuity.py", "_cmd_verify", _JDE): (1, _JDE_C),
    ("F:cli_verify_cost.py", "cmd_verify_cost", _JDE): (2, _JDE_C),
    ("F:cli_verify_release.py", "_extract_anchored_digest", _JDE):
        (1, _JDE_C),
    ("F:cli_verify_release.py", "_load_json", _JDE): (1, _JDE_C),
    ("F:cli_verify_release.py", "_verify_operator_root", _JDE): (1, _JDE_C),
    ("F:ndec.py", "verify_envelope", _JDE): (1, _JDE_C),
    ("F:cli_continuity.py", "_cmd_link", _JDE): (1, _JDE_P),
    ("F:cli_continuity.py", "_cmd_receipt", _JDE): (1, _JDE_P),
}


def test_kjs6_every_reason_is_written():
    for k, (n, why) in ALLOW.items():
        assert isinstance(n, int) and n >= 1, k
        assert isinstance(why, str) and len(why) > 20, k


def test_kjs6_no_parse_outside_the_region():
    import collections
    found = collections.Counter(inventory())
    unallowed = sorted((k, n) for k, n in found.items()
                       if k not in ALLOW or ALLOW[k][0] != n)
    stale = sorted(k for k in ALLOW if k not in found)
    assert not unallowed and not stale, {"not allowed or wrong count":
                                        unallowed, "stale allowlist": stale}


if __name__ == "__main__":
    for h in inventory():
        print(" | ".join(h))
    print("unparsed dossier constants with json:", _dossier_constants()[1])
