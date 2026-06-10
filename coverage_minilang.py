"""NOUS coverage minilang: independent text-level re-derivation of
the coverage gap disjunct set, for issuance-time cross-derivation
gating and for the offline bundle verifier (which embeds the same
core verbatim). Pure stdlib parsing; no Lark, no solver."""
from __future__ import annotations


# --- minilang core (shared text; do not edit one copy without the other) ---
# Tokenizer + recursive-descent parser for the NOUS signal-expression
# fragment, plus a string-aware structural scanner for policy blocks.
# Mirrors nous.lark precedence exactly on the supported subset:
#   or_expr < and_expr < compare_expr < add_expr < mul_expr < unary(!)
# with left-folding at every binary level. Anything outside the subset
# raises MinilangError (typed refuse) -- never a silent fallback.
# __s124_minilang_core_v1__


class MinilangError(ValueError):
    """Signal text outside the minilang fragment, or malformed source
    structure; the disjunct set cannot be independently re-derived."""


_ML_TWO_CHAR = ("&&", "||", ">=", "<=", "==", "!=")
_ML_ONE_CHAR = "()!<>+-*/%:"
_ML_CLAUSE_KEYWORDS = (
    "kind", "signal", "window", "weight", "action",
    "description", "inject_as", "message",
)
_ML_BLOCKING_ACTIONS = ("block", "abort_cycle")


def ml_tokenize(text):
    toks = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        two = text[i:i + 2]
        if two in _ML_TWO_CHAR:
            toks.append(two)
            i += 2
            continue
        if c in _ML_ONE_CHAR:
            toks.append(c)
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            seen_dot = False
            while j < n and (
                text[j].isdigit() or (text[j] == "." and not seen_dot)
            ):
                if text[j] == ".":
                    seen_dot = True
                j += 1
            lit = text[i:j]
            toks.append(("num", float(lit) if "." in lit else int(lit)))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            toks.append(("name", text[i:j]))
            i = j
            continue
        raise MinilangError(
            "unsupported character " + repr(c) + " in signal text"
        )
    return toks


class _MlParser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek()
        self.i += 1
        return t


def _ml_or(p):
    node = _ml_and(p)
    while p.peek() == "||":
        p.take()
        node = {"kind": "binop", "op": "||",
                "left": node, "right": _ml_and(p)}
    return node


def _ml_and(p):
    node = _ml_cmp(p)
    while p.peek() == "&&":
        p.take()
        node = {"kind": "binop", "op": "&&",
                "left": node, "right": _ml_cmp(p)}
    return node


def _ml_cmp(p):
    node = _ml_add(p)
    while p.peek() in (">", ">=", "<", "<=", "==", "!="):
        op = p.take()
        node = {"kind": "binop", "op": op,
                "left": node, "right": _ml_add(p)}
    return node


def _ml_add(p):
    node = _ml_mul(p)
    while p.peek() in ("+", "-"):
        op = p.take()
        node = {"kind": "binop", "op": op,
                "left": node, "right": _ml_mul(p)}
    return node


def _ml_mul(p):
    node = _ml_unary(p)
    while p.peek() in ("*", "/", "%"):
        op = p.take()
        node = {"kind": "binop", "op": op,
                "left": node, "right": _ml_unary(p)}
    return node


def _ml_unary(p):
    if p.peek() == "!":
        p.take()
        return {"kind": "not", "operand": _ml_unary(p)}
    return _ml_atom(p)


def _ml_atom(p):
    t = p.take()
    if t == "(":
        node = _ml_or(p)
        if p.take() != ")":
            raise MinilangError("unbalanced parenthesis in signal text")
        return node
    if isinstance(t, tuple) and t[0] == "num":
        return t[1]
    if isinstance(t, tuple) and t[0] == "name":
        if t[1] == "true":
            return True
        if t[1] == "false":
            return False
        return t[1]
    raise MinilangError("unexpected token " + repr(t) + " in signal text")


def ml_parse(text):
    """Parse a complete expression; trailing tokens are refused."""
    p = _MlParser(ml_tokenize(text))
    node = _ml_or(p)
    if p.peek() is not None:
        raise MinilangError(
            "trailing tokens after expression: " + repr(p.peek())
        )
    return node


def _ml_parse_prefix(toks):
    """Maximal-munch parse of a token prefix. Returns (node, stop_index).
    The token at stop_index must be a clause keyword or absent."""
    p = _MlParser(toks)
    node = _ml_or(p)
    stop = p.peek()
    if stop is not None and not (
        isinstance(stop, tuple)
        and stop[0] == "name"
        and stop[1] in _ML_CLAUSE_KEYWORDS
    ):
        raise MinilangError(
            "signal expression does not end at a clause boundary: "
            + repr(stop)
        )
    return node, p.i


def _ml_shadow(text):
    """Comments stripped, string interiors blanked (positions preserved).
    All structural scanning happens on the shadow so 'policy', braces,
    and '#' inside string literals can never mislead the scanner."""
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == '"':
                in_str = False
                out.append(c)
                i += 1
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "#":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _ml_is_ident_char(c):
    return c.isalnum() or c == "_"


def _ml_find_keyword(shadow, word, start):
    i = start
    n = len(shadow)
    w = len(word)
    while True:
        j = shadow.find(word, i)
        if j < 0:
            return -1
        before_ok = j == 0 or not _ml_is_ident_char(shadow[j - 1])
        after_ok = j + w >= n or not _ml_is_ident_char(shadow[j + w])
        if before_ok and after_ok:
            return j
        i = j + 1


def _ml_match_brace(shadow, open_idx):
    depth = 0
    for i in range(open_idx, len(shadow)):
        if shadow[i] == "{":
            depth += 1
        elif shadow[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise MinilangError("unbalanced braces in source")


def _ml_clause_text(block, keyword):
    j = _ml_find_keyword(block, keyword, 0)
    if j < 0:
        return None
    k = block.find(":", j)
    if k < 0:
        raise MinilangError(
            "clause " + repr(keyword) + " without ':' in policy block"
        )
    return block[k + 1:]


def ml_scan_blocking_signals(source_text):
    """Return the parsed signal ASTs of every policy whose action is a
    blocking action, derived purely from the source TEXT (string-aware,
    comment-aware). Refuses (typed) on structure it cannot certify."""
    shadow = _ml_shadow(source_text)
    sigs = []
    i = 0
    while True:
        j = _ml_find_keyword(shadow, "policy", i)
        if j < 0:
            break
        k = shadow.find("{", j)
        if k < 0:
            raise MinilangError("policy header without '{'")
        end = _ml_match_brace(shadow, k)
        block = shadow[k + 1:end]
        action_text = _ml_clause_text(block, "action")
        if action_text is not None:
            action_toks = ml_tokenize(action_text)
            action = (
                action_toks[0][1]
                if action_toks
                and isinstance(action_toks[0], tuple)
                and action_toks[0][0] == "name"
                else None
            )
            if action in _ML_BLOCKING_ACTIONS:
                signal_text = _ml_clause_text(block, "signal")
                if signal_text is None:
                    raise MinilangError(
                        "blocking policy without a signal clause"
                    )
                node, _stop = _ml_parse_prefix(ml_tokenize(signal_text))
                sigs.append(node)
        i = end + 1
    return sigs
# --- end minilang core ---


# --- derive layer (repo-side; the offline template embeds its own copy
#     of the same logic from coverage_farkas) ---  __s124_minilang_derive_v1__

from coverage_farkas import (
    DISJUNCT_BOUND as _F_BOUND,
    FarkasError,
    _canon_json as _f_canon_json,
    _canon_system as _f_canon_system,
    _gap_disjuncts as _f_gap_disjuncts,
)


def derive_disjunct_constraints(source_text: str, threshold_expr: str) -> dict:
    """Source TEXT + threshold expression -> {canonical key: canonical
    constraints}, one entry per derived gap disjunct (deduplicated).
    The independent reconstruction of what a Farkas bundle must prove,
    built from the minilang parse rather than the Lark AST. Raises
    MinilangError or FarkasError (typed) outside the fragment."""
    threshold_ast = ml_parse(threshold_expr)
    blocking = ml_scan_blocking_signals(source_text)
    disjuncts = _f_gap_disjuncts(threshold_ast, blocking, _F_BOUND)
    derived: dict = {}
    for comps in disjuncts:
        constraints, _system = _f_canon_system(comps)
        derived[_f_canon_json(constraints)] = constraints
    return derived


def bundle_cert_keys(doc: dict) -> set:
    """Canonical keys of the certs carried by a bundle dict."""
    keys = set()
    for cert in doc.get("certs", []):
        keys.add(_f_canon_json(cert.get("constraints")))
    return keys
