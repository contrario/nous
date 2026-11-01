"""AN-GATE-1 K-JS.7 (RULING 11:58Z, round 3, 1): every call site of the
strict region that the K-JS.6 scan finds is reached by at least one
strict case, or is named below with a reason.

Each site carries one tag [js:<object>.<n>] in its label. A helper that
hands its own label parameter to the region (_load_json, _tb_jloads) is
tagged at its callers. The strict tests record every tag they see in a
refusal (test_an_js_strict.HITS); this file runs after them (its name
sorts last among the an_js files) and compares. Run alone it fails: the
strict tests must run in the same session.

# __an_js_sites_v1__
"""
from __future__ import annotations

import ast

import test_an_js_inventory as I
import test_an_js_strict as A

REGION_CALLS = ("loads", "_strict_loads")
HELPERS = ("_load_json", "_tb_jloads")

# tag -> reason it is reached by no strict case
UNREACHED: dict = {
    "cnt.2": ("shadowed: the continuity text parses the same receipt "
              "payload at cnt.6 (the iss peek) before _verify_receipt, "
              "and the script has no other entry; a re-signed planted "
              "payload is refused at cnt.6 (test_f_continuity_text_"
              "resigned_payload_shadow). Measured with a copy whose "
              "cnt.6 is lenient: refused at cnt.2 (R3B U1)"),
    "vrk.3": ("the Rekor leaf is parsed only after the Rekor "
              "SignedEntryTimestamp verifies over the same body bytes "
              "under a Sigstore key pinned in the text "
              "(KNOWN_REKOR_PUBLIC_KEYS); a test holds no such private "
              "key, and a planted byte breaks the SET first. Reaching it "
              "needs a text with a swapped pin, not the shipped text"),
}


def _objects():
    for name, text in sorted(A._texts21().items()):
        yield "T:" + name, text
    consts, _ = I._dossier_constants()
    for name, text in sorted(consts.items()):
        yield "S:dossier." + name, text
    for f in I.SCOPE_R + I.SCOPE_P:
        yield "F:" + f, (I.REPO / f).read_text(encoding="utf-8")


def _sites(src):
    """[(line, label source, tags)] of every region call and helper call
    outside the region; a region call inside a helper that passes the
    helper's own parameter is not a site."""
    tree = ast.parse(src)
    skip = I._region_lines(src)
    # a helper is a passthrough only where it hands its own `label` to the
    # region (cli_verify_release._load_json does not; its label is for
    # its own errors)
    passthrough = any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id in REGION_CALLS and len(c.args) > 1
        and isinstance(c.args[1], ast.Name) and c.args[1].id == "label"
        for c in ast.walk(tree))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func,
                                                         ast.Name)):
            continue
        if node.lineno in skip or len(node.args) < 2:
            continue
        lab = node.args[1]
        if node.func.id in REGION_CALLS:
            if isinstance(lab, ast.Name) and lab.id == "label":
                continue
        elif node.func.id not in HELPERS or not passthrough:
            continue
        tags = set()
        for sub in ast.walk(lab):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                tags |= set(A.TAG.findall(sub.value))
        out.append((node.lineno, ast.get_source_segment(src, lab), tags))
    return out


def scope_sites():
    return [(where, line, lab, tags) for where, src in _objects()
            for line, lab, tags in _sites(src)]


def test_kjs7_every_site_has_one_tag():
    bad = [(w, ln, lab) for w, ln, lab, tags in scope_sites()
           if len(tags) != 1]
    assert not bad, bad


def test_kjs7_every_reason_is_written():
    for tag, why in UNREACHED.items():
        assert isinstance(why, str) and len(why) > 20, tag


def test_kjs7_every_site_is_reached():
    assert A.HITS, ("no refusal was recorded: run the strict tests "
                    "(tests/test_an_js_strict*.py) in the same session")
    tags = set().union(*(t for _w, _l, _s, t in scope_sites()))
    missing = sorted(tags - A.HITS - set(UNREACHED))
    stale = sorted(set(UNREACHED) - tags)
    reached_anyway = sorted(set(UNREACHED) & A.HITS)
    assert not missing and not stale and not reached_anyway, {
        "reached by no case": missing, "stale": stale,
        "listed but reached": reached_anyway}
