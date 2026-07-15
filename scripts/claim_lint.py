#!/usr/bin/env python3
"""NOUS claim-boundary linter.

WHAT THIS CHECKS
  Conformance to a declared convention: a reserved claim word may appear at a
  site only if that site satisfies a declared, mechanically decidable
  justification predicate, or is explicitly allowlisted with a written reason.

WHAT THIS DOES NOT DO
  It does not determine whether any claim is TRUE. It performs no semantic
  understanding and calls no language model. Passing this linter EVIDENCES that
  no declared reserved word appears without its declared justification. It
  PROVES nothing about the correctness of the system it scans.

  It cannot detect a capability the config does not name. The forbidden-object
  set is a blocklist and blocklists are incomplete by construction.

DECLARED BLIND SPOTS (v1) -- named, not omitted:
  1. Attribution flaws. A string that points at ANOTHER command's real proof
     ("bind a dossier proving the new build still satisfies the same proven
     properties -- run `nous verify --smt`") has no forbidden object, no axis
     binding and no negation, so no predicate fires. Catching it needs
     semantics. That is the line this tool does not cross.
  2. Claim-class errors with no numeral and no forbidden object. A doc that
     says a decidable boolean check "PROVES" something is not caught: the
     wrongness is the CLASS of the claim, not a countable or a named object.
  3. Counts laundered through an intermediate variable. The axis predicate
     binds a rendered word to the nearest preceding f-string expression. A
     value copied into an unrelated local first is invisible.
  4. str.format() and %-formatting are not axis-checked. f-strings only.
  5. The false-fix-marker class -- a marker asserting a fix that was never
     applied. That needs a marker bound to a test with a proven negative
     control. Out of scope, named.

RUN
  python3 claim_lint.py --config claims.toml --root .
  python3 claim_lint.py --config claims.toml --root . --anchor $(git rev-parse HEAD)
  python3 claim_lint.py --config claims.toml --root . --sarif > out.sarif

EXIT
  0 = no violations. 1 = violations. 2 = usage/config error.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import sys
import tokenize
import tomllib
import warnings
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

TOOL_NAME = "nous-claim-lint"
TOOL_VERSION = "1.2.0"

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
SENT_SPLIT_RE = re.compile(r"(?<!\d)[.!?;](?!\d)|\n")
QUOTE_CHARS = "'\"`\u2018\u2019\u201c\u201d"
MD_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
MD_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    col: int
    word: str
    predicate: str
    reason: str
    symbol: str
    sentence: str
    high: bool
    alternatives: tuple[str, ...] = ()

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.path, self.line, self.col, self.predicate)


@dataclass
class TextUnit:
    text: str
    line: int
    col: int
    kind: str
    symbol: str = ""
    axis_ids: tuple[str, ...] = ()
    axis_expr: str = ""
    schema_literal: bool = False
    verbatim: bool = True
    line_map: tuple[tuple[int, int], ...] = ()


@dataclass
class Config:
    raw: dict[str, Any]
    declared_proof_legs: int
    reserved: frozenset[str]
    allowed: frozenset[str]
    alternatives: dict[str, tuple[str, ...]]
    forbidden_objects: tuple[tuple[str, ...], ...]
    terms_of_art: tuple[tuple[str, ...], ...]
    negators: frozenset[str]
    negation_window: int
    passive_window: int
    copulas: frozenset[str]
    reserved_participles: frozenset[str]
    proof_nouns: frozenset[str]
    exempt_object_phrases: tuple[tuple[str, ...], ...]
    axis_required: frozenset[str]
    axis_forbidden: frozenset[str]
    include_globs: tuple[str, ...]
    exclude_dirs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    high_severity_modules: frozenset[str]
    allowlist: tuple[dict[str, Any], ...]


def _phrases(items: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    out: list[tuple[str, ...]] = []
    for item in items:
        toks = tuple(m.group(0).lower() for m in TOKEN_RE.finditer(item))
        if toks:
            out.append(toks)
    return tuple(out)


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"config unreadable: {path}: {exc}") from exc

    try:
        res = raw["reserved"]
        exempt = raw["exempt"]
        obj = raw["object"]
        stat = raw["stat"]
        axis = raw["axis"]
        surf = raw["surfaces"]
    except KeyError as exc:
        raise ConfigError(f"config missing required table: {exc}") from exc

    legs = raw.get("declared_proof_legs")
    if not isinstance(legs, int):
        raise ConfigError("declared_proof_legs must be an integer")

    alts: dict[str, tuple[str, ...]] = {}
    for word, values in res.get("alternatives", {}).items():
        alts[word.lower()] = tuple(values)

    return Config(
        raw=raw,
        declared_proof_legs=legs,
        reserved=frozenset(w.lower() for w in res["words"]),
        allowed=frozenset(w.lower() for w in res["allowed_claim_words"]),
        alternatives=alts,
        forbidden_objects=_phrases(obj["forbidden_objects"]),
        terms_of_art=_phrases(exempt["terms_of_art"]),
        negators=frozenset(w.lower() for w in exempt["negators"]),
        negation_window=int(exempt["negation_window"]),
        passive_window=int(obj["passive_window"]),
        copulas=frozenset(w.lower() for w in obj["copulas"]),
        reserved_participles=frozenset(
            w.lower() for w in obj["reserved_participles"]
        ),
        proof_nouns=frozenset(w.lower() for w in stat["proof_nouns"]),
        exempt_object_phrases=_phrases(obj["exempt_object_phrases"]),
        axis_required=frozenset(w.lower() for w in axis["required_fields"]),
        axis_forbidden=frozenset(w.lower() for w in axis["forbidden_fields"]),
        include_globs=tuple(surf["include"]),
        exclude_dirs=tuple(surf["exclude_dirs"]),
        exclude_globs=tuple(surf["exclude_globs"]),
        high_severity_modules=frozenset(surf["high_severity_modules"]),
        allowlist=tuple(raw.get("allow", [])),
    )


def tokenize_text(text: str) -> list[tuple[str, int, int]]:
    return [
        (m.group(0).lower(), m.start(), m.end())
        for m in TOKEN_RE.finditer(text)
    ]


def sentences(text: str) -> Iterator[tuple[str, int]]:
    start = 0
    for m in SENT_SPLIT_RE.finditer(text):
        chunk = text[start:m.start()]
        if chunk.strip():
            yield chunk, start
        start = m.end()
    tail = text[start:]
    if tail.strip():
        yield tail, start


def find_phrase_spans(
    toks: list[tuple[str, int, int]],
    phrases: tuple[tuple[str, ...], ...],
) -> list[tuple[int, int, tuple[str, ...]]]:
    spans: list[tuple[int, int, tuple[str, ...]]] = []
    words = [t[0] for t in toks]
    for phrase in phrases:
        n = len(phrase)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == phrase:
                spans.append((i, i + n - 1, phrase))
    return spans


SPAN_QUOTES = '"`\u201c\u201d'


def quoted_spans(text: str) -> list[tuple[int, int]]:
    """Sentence-scoped double-quote / backtick spans.

    Single quotes are NOT span delimiters: an apostrophe ("the manifest's
    bytes") would open a span that swallowed the rest of the sentence and
    silently exempt a real claim. The word-adjacent rule below still covers
    the 'proves' single-quote form.
    """
    spans: list[tuple[int, int]] = []
    open_at: Optional[int] = None
    opener = ""
    for i, ch in enumerate(text):
        if ch not in SPAN_QUOTES:
            continue
        if open_at is None:
            open_at = i
            opener = ch
        else:
            if ch == opener or (opener == "\u201c" and ch == "\u201d"):
                spans.append((open_at, i))
                open_at = None
                opener = ""
    return spans


def is_mention(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    if before in QUOTE_CHARS and after in QUOTE_CHARS:
        return True
    return any(lo < start and end <= hi for lo, hi in quoted_spans(text))


def negated(
    toks: list[tuple[str, int, int]], idx: int, cfg: Config
) -> bool:
    lo = max(0, idx - cfg.negation_window)
    hi = min(len(toks), idx + cfg.negation_window + 1)
    for j in range(lo, hi):
        if j == idx:
            continue
        if toks[j][0] in cfg.negators:
            return True
    return False


def in_spans(idx: int, spans: list[tuple[int, int, tuple[str, ...]]]) -> bool:
    return any(lo <= idx <= hi for lo, hi, _ in spans)


def claim_word_indices(
    toks: list[tuple[str, int, int]],
    sent: str,
    cfg: Config,
    toa_spans: list[tuple[int, int, tuple[str, ...]]],
) -> dict[int, str]:
    out: dict[int, str] = {}
    for i, (word, s, e) in enumerate(toks):
        if word in cfg.reserved:
            if in_spans(i, toa_spans):
                continue
            if is_mention(sent, s, e):
                continue
            out[i] = "reserved"
        elif word in cfg.allowed:
            out[i] = "allowed"
    return out


def predicate_object(
    toks: list[tuple[str, int, int]],
    sent: str,
    cfg: Config,
    claims: dict[int, str],
) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    governed: dict[int, list[str]] = {}
    obj_spans = find_phrase_spans(toks, cfg.forbidden_objects)
    exempt_spans = find_phrase_spans(toks, cfg.exempt_object_phrases)
    for lo, hi, phrase in obj_spans:
        if any(elo <= lo <= ehi or elo <= hi <= ehi
               for elo, ehi, _p in exempt_spans):
            continue
        obj = " ".join(phrase)
        for j in range(lo - 1, -1, -1):
            kind = claims.get(j)
            if kind is None:
                continue
            if kind == "reserved" and not negated(toks, j, cfg):
                governed.setdefault(j, [])
                if obj not in governed[j]:
                    governed[j].append(obj)
            break
        k = hi + 1
        limit = min(len(toks), hi + 1 + cfg.passive_window)
        while k < limit:
            if toks[k][0] in cfg.copulas:
                if (
                    k + 1 < len(toks)
                    and toks[k + 1][0] in cfg.reserved_participles
                    and not negated(toks, k + 1, cfg)
                    and not is_mention(sent, toks[k + 1][1], toks[k + 1][2])
                ):
                    hits.append((
                        k + 1,
                        "object",
                        "forbidden object '%s' is passively claimed by "
                        "reserved word '%s'" % (obj, toks[k + 1][0]),
                    ))
                break
            k += 1
    for j, objs in governed.items():
        hits.append((
            j,
            "object",
            "reserved claim word '%s' governs forbidden object(s) %s; "
            "those are STATIC CHECKS (verifier.py VD/VL/VE/VM), not "
            "Z3/Farkas legs" % (toks[j][0], ", ".join("'%s'" % o
                                                      for o in objs)),
        ))
    return hits


def predicate_axis(
    unit: TextUnit,
    toks: list[tuple[str, int, int]],
    sent: str,
    cfg: Config,
    claims: dict[int, str],
) -> list[tuple[int, str, str]]:
    if not unit.axis_ids:
        return []
    ids = set(unit.axis_ids)
    if ids & cfg.axis_required:
        return []
    bad = ids & cfg.axis_forbidden
    if not bad:
        return []
    hits: list[tuple[int, str, str]] = []
    for i, kind in claims.items():
        if kind != "reserved":
            continue
        if negated(toks, i, cfg):
            continue
        hits.append((
            i,
            "axis",
            "renders reserved word '%s' from expression `%s` bound to "
            "forbidden field(s) %s; the reserved word must be rendered from "
            "the tier axis, never the severity axis"
            % (toks[i][0], unit.axis_expr, sorted(bad)),
        ))
    return hits


NUMERAL_ONLY_RE = re.compile(r"^(\d+)\+?$")


def predicate_stat(units: list[TextUnit], cfg: Config) -> list[tuple[
        TextUnit, str, str]]:
    """Stat-card rule (HTML only).

    A BLOCK whose entire text is a bare numeral, immediately followed by a
    BLOCK naming a proof noun, asserts a proof count. It must equal
    declared_proof_legs.

        <div>31+</div><div>Formal Proofs</div>   -> 31 != 3 -> VIOLATION
        <div>3</div><div>Z3/Farkas Proofs</div>  -> 3  == 3 -> OK
        <div>62</div><div>CLI Commands</div>     -> no proof noun -> ignored

    This replaces the v1 prose `count` predicate, which had a 100% false
    positive rate on the live tree (24 hits, 0 true positives) because "N
    proofs" in English is almost always a cardinality of proof INSTANCES
    ("one static proof to many runtime certificates"), never an assertion
    about how many Z3/Farkas legs exist. The stat card is the only shape
    that actually makes the claim.
    """
    out: list[tuple[TextUnit, str, str]] = []
    html = [u for u in units if u.kind == "html"]
    for i in range(len(html) - 1):
        m = NUMERAL_ONLY_RE.match(html[i].text.strip())
        if not m:
            continue
        label = [t[0] for t in tokenize_text(html[i + 1].text)]
        if not any(w in cfg.proof_nouns for w in label):
            continue
        value = int(m.group(1))
        if value == cfg.declared_proof_legs:
            continue
        out.append((
            html[i],
            "stat",
            "stat card claims %d %s; declared_proof_legs is %d "
            "(cost-cap, policy-coverage, sequence-ordering)"
            % (value, " ".join(label), cfg.declared_proof_legs),
        ))
    return out


def line_of(
    text: str,
    offset: int,
    base_line: int,
    line_map: tuple[tuple[int, int], ...] = (),
) -> int:
    if line_map:
        line = line_map[0][1]
        for off, ln in line_map:
            if off <= offset:
                line = ln
            else:
                break
        return line
    return base_line + text.count("\n", 0, offset)


def col_of(text: str, offset: int, base_col: int) -> int:
    nl = text.rfind("\n", 0, offset)
    if nl == -1:
        return base_col + offset
    return offset - nl - 1


_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*+]|<li\b)", re.IGNORECASE)


def predicate_list_binding(
    path: str, unit: TextUnit, cfg: Config, high: bool
) -> list[Violation]:  # __s245_listbind_v1__
    """Cross-sentence list binding (S245).

    SENT_SPLIT_RE breaks on every newline, so a colon-header that introduces a
    numbered/bulleted list puts the reserved claim word and the forbidden
    objects in its list items in DIFFERENT sentences; predicate_object, which
    is sentence-scoped, never binds them. This unit-level predicate binds a
    reserved claim word in a header line (ending ':') to forbidden objects in
    the immediately following list items, stopping at the first blank or
    non-item line so it cannot run into unrelated prose. Scoped to string and
    markdown units; HTML <li> items are separate units, a different mechanism
    with no current site. The allowed-verb escape is implicit: a header with
    no reserved word never fires.
    """
    if unit.schema_literal or not unit.verbatim:
        return []
    if unit.kind not in ("string", "markdown"):
        return []
    text = unit.text
    lines: list[tuple[str, int]] = []
    off = 0
    for raw in text.splitlines(keepends=True):
        lines.append((raw, off))
        off += len(raw)
    out: list[Violation] = []
    n = len(lines)
    for i, (raw, loff) in enumerate(lines):
        header = raw.rstrip("\r\n")
        if not header.rstrip().endswith(":"):
            continue
        htoks = tokenize_text(header)
        if not htoks:
            continue
        toa = find_phrase_spans(htoks, cfg.terms_of_art)
        claims = claim_word_indices(htoks, header, cfg, toa)
        reserved = [k for k, v in claims.items()
                    if v == "reserved" and not negated(htoks, k, cfg)]
        if not reserved:
            continue
        objs: list[str] = []
        j = i + 1
        while j < n:
            item = lines[j][0].rstrip("\r\n")
            if item.strip() == "":
                break
            if not _LIST_ITEM_RE.match(item):
                break
            itoks = tokenize_text(item)
            ospans = find_phrase_spans(itoks, cfg.forbidden_objects)
            espans = find_phrase_spans(itoks, cfg.exempt_object_phrases)
            for lo, hi, phrase in ospans:
                if any(elo <= lo <= ehi or elo <= hi <= ehi
                       for elo, ehi, _p in espans):
                    continue
                if negated(itoks, lo, cfg):
                    continue
                obj = " ".join(phrase)
                if obj not in objs:
                    objs.append(obj)
            j += 1
        if not objs:
            continue
        hidx = min(reserved)
        word, s, _e = htoks[hidx]
        abs_off = loff + s
        out.append(Violation(
            path=path,
            line=line_of(text, abs_off, unit.line, unit.line_map),
            col=col_of(text, abs_off, unit.col),
            word=word,
            predicate="list-object",
            reason="reserved claim word '%s' heads a list whose items claim "
                   "forbidden object(s) %s; those are STATIC CHECKS "
                   "(verifier.py VD/VL/VE/VM), not Z3/Farkas legs"
                   % (word, ", ".join("'%s'" % o for o in objs)),
            symbol=unit.symbol,
            sentence=" ".join(header.split())[:160],
            high=high,
            alternatives=cfg.alternatives.get(word, ()),
        ))
    return out


def scan_unit(
    path: str, unit: TextUnit, cfg: Config, high: bool
) -> list[Violation]:
    if unit.schema_literal:
        return []
    out: list[Violation] = []
    out.extend(predicate_list_binding(path, unit, cfg, high))  # __s245_listbind_wire_v1__
    for sent, sent_off in sentences(unit.text):
        toks = tokenize_text(sent)
        if not toks:
            continue
        toa_spans = find_phrase_spans(toks, cfg.terms_of_art)
        claims = claim_word_indices(toks, sent, cfg, toa_spans)
        hits: list[tuple[int, str, str]] = []
        hits.extend(predicate_object(toks, sent, cfg, claims))
        hits.extend(predicate_axis(unit, toks, sent, cfg, claims))
        seen: set[tuple[int, str]] = set()
        for idx, predicate, reason in hits:
            key = (idx, predicate)
            if key in seen:
                continue
            seen.add(key)
            word, s, _e = toks[idx]
            abs_off = sent_off + s
            line = (
                line_of(unit.text, abs_off, unit.line, unit.line_map)
                if unit.verbatim else unit.line
            )
            out.append(Violation(
                path=path,
                line=line,
                col=col_of(unit.text, abs_off, unit.col),
                word=word,
                predicate=predicate,
                reason=reason,
                symbol=unit.symbol,
                sentence=" ".join(sent.split())[:160],
                high=high,
                alternatives=cfg.alternatives.get(word, ()),
            ))
    return out


def _expr_ids(node: ast.AST) -> tuple[str, ...]:
    ids: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            ids.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            ids.append(sub.attr)
    return tuple(ids)


def _expr_src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"


def _is_schema_literal(value: str, cfg: Config) -> bool:
    toks = tokenize_text(value)
    return len(toks) == 1 and toks[0][0] in cfg.reserved


def python_units(text: str, cfg: Config) -> list[TextUnit]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    def symbol_of(node: ast.AST) -> str:
        cur: Optional[ast.AST] = parent.get(id(node))
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
                return cur.name
            cur = parent.get(id(cur))
        return "<module>"

    joined_children: set[int] = set()
    units: list[TextUnit] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            last_fv: Optional[ast.FormattedValue] = None
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    last_fv = part
                    joined_children.add(id(part))
                    continue
                if isinstance(part, ast.Constant) and isinstance(
                    part.value, str
                ):
                    joined_children.add(id(part))
                    units.append(TextUnit(
                        text=part.value,
                        line=node.lineno,
                        col=node.col_offset,
                        kind="fstring",
                        symbol=symbol_of(node),
                        axis_ids=(
                            _expr_ids(last_fv.value) if last_fv else ()
                        ),
                        axis_expr=(
                            _expr_src(last_fv.value) if last_fv else ""
                        ),
                        verbatim=False,
                    ))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in joined_children:
                continue
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            verbatim = node.value.count("\n") == (end - node.lineno)
            units.append(TextUnit(
                text=node.value,
                line=node.lineno,
                col=node.col_offset,
                kind="string",
                symbol=symbol_of(node),
                schema_literal=_is_schema_literal(node.value, cfg),
                verbatim=verbatim,
            ))

    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                units.append(TextUnit(
                    text=tok.string.lstrip("#"),
                    line=tok.start[0],
                    col=tok.start[1],
                    kind="comment",
                    symbol="<comment>",
                ))
    except (tokenize.TokenError, IndentationError):
        pass

    return units


INLINE_TAGS = frozenset({
    "a", "b", "i", "em", "strong", "span", "code", "small", "sup", "sub",
    "u", "mark", "abbr", "cite", "q", "s", "del", "ins", "var", "kbd",
    "samp", "time", "font", "label",
})


class _TextHTML(HTMLParser):
    """Text-node extractor.

    Consecutive text nodes separated only by INLINE tags are JOINED into one
    unit; a BLOCK tag flushes. Without this, markup splits a claim from its
    object: a stat block that puts the numeral in one span and the noun in the
    next span would produce two units, and the count predicate would never see
    the pair. Attributes and the contents of script/style are never scanned.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.units: list[TextUnit] = []
        self._skip = 0
        self._buf: list[str] = []
        self._marks: list[tuple[int, int]] = []
        self._len = 0

    def _flush(self) -> None:
        if not self._buf:
            return
        text = "".join(self._buf)
        if text.strip():
            self.units.append(TextUnit(
                text=text,
                line=self._marks[0][1] if self._marks else 1,
                col=0,
                kind="html",
                symbol="<text>",
                line_map=tuple(self._marks),
            ))
        self._buf = []
        self._marks = []
        self._len = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._flush()
            self._skip += 1
            return
        if tag not in INLINE_TAGS:
            self._flush()
        elif self._buf:
            self._buf.append(" ")
            self._len += 1

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        if tag not in INLINE_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if self._skip > 0:
                self._skip -= 1
            return
        if tag not in INLINE_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip or not data.strip():
            return
        line, _col = self.getpos()
        self._marks.append((self._len, line))
        self._buf.append(data)
        self._len += len(data)

    def close(self) -> None:
        super().close()
        self._flush()


def html_units(text: str) -> list[TextUnit]:
    parser = _TextHTML()
    parser.feed(text)
    parser.close()
    return parser.units


def markdown_units(text: str) -> list[TextUnit]:
    def blank(m: "re.Match[str]") -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    stripped = MD_FENCE_RE.sub(blank, text)
    stripped = MD_COMMENT_RE.sub(blank, stripped)
    return [TextUnit(text=stripped, line=1, col=0, kind="markdown",
                     symbol="<doc>")]


def iter_files(root: Path, cfg: Config) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        pruned: list[str] = []
        for d in dirnames:
            cand = f"{rel_dir}/{d}" if rel_dir else d
            if any(
                cand == ex or cand.startswith(ex + "/") or d == ex
                for ex in cfg.exclude_dirs
            ):
                continue
            pruned.append(d)
        dirnames[:] = pruned
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if not any(p.match(g) for g in cfg.include_globs):
                continue
            if any(p.match(g) for g in cfg.exclude_globs):
                continue
            yield p


def line_sha(path: Path, line: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if 1 <= line <= len(lines):
        return hashlib.sha256(
            lines[line - 1].strip().encode("utf-8")
        ).hexdigest()
    return ""


def apply_allowlist(
    root: Path, viols: list[Violation], cfg: Config
) -> tuple[list[Violation], list[str], list[str]]:
    kept: list[Violation] = []
    used: list[str] = []
    rotted: list[str] = []
    entries = list(cfg.allowlist)
    matched: set[int] = set()
    for v in viols:
        hit = None
        for n, e in enumerate(entries):
            if (
                e.get("path") == v.path
                and int(e.get("line", -1)) == v.line
                and e.get("word", "").lower() == v.word
            ):
                hit = (n, e)
                break
        if hit is None:
            kept.append(v)
            continue
        n, e = hit
        matched.add(n)
        actual = line_sha(root / v.path, v.line)
        if actual != e.get("region_sha256", ""):
            rotted.append(
                "%s:%d '%s' -- allowlist region_sha256 STALE "
                "(expected %s, actual %s). The justifying region changed; "
                "re-review and re-pin, or delete the entry."
                % (v.path, v.line, v.word,
                   e.get("region_sha256", "")[:16], actual[:16])
            )
            kept.append(v)
            continue
        used.append("%s:%d '%s' -- %s" % (
            v.path, v.line, v.word, e.get("reason", "<no reason>")
        ))
    for n, e in enumerate(entries):
        if n not in matched:
            rotted.append(
                "%s:%s '%s' -- allowlist entry matched NOTHING. The site is "
                "gone or already clean; delete the entry."
                % (e.get("path"), e.get("line"), e.get("word"))
            )
    return kept, used, rotted


def to_sarif(viols: list[Violation], anchor: str) -> dict[str, Any]:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": TOOL_NAME,
                "version": TOOL_VERSION,
                "informationUri": "https://nous-lang.org",
            }},
            "properties": {"anchor": anchor},
            "results": [{
                "ruleId": "claim-%s" % v.predicate,
                "level": "error",
                "message": {"text": v.reason},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": v.path},
                    "region": {
                        "startLine": max(1, v.line),
                        "startColumn": max(1, v.col + 1),
                    },
                }}],
            } for v in viols],
        }],
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="claim_lint",
        description=(
            "Check conformance to the declared claim-word convention. "
            "This tool does NOT determine whether any claim is true. "
            "Passing it EVIDENCES that no declared reserved word appears "
            "without its declared justification; it PROVES nothing."
        ),
    )
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--anchor", default="",
                    help="commit SHA this scan is pinned to (recorded, not "
                         "verified). A byte read is only valid against a "
                         "named commit.")
    ap.add_argument("--sarif", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-allowlist", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print("CONFIG ERROR: %s" % exc, file=sys.stderr)
        return 2

    root = args.root.resolve()
    if not root.is_dir():
        print("ERROR: --root is not a directory: %s" % root, file=sys.stderr)
        return 2

    viols: list[Violation] = []
    scanned = 0
    for path in sorted(iter_files(root, cfg)):
        rel = path.relative_to(root).as_posix()
        high = path.name in cfg.high_severity_modules
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        if path.suffix == ".py":
            try:
                units = python_units(text, cfg)
            except SyntaxError:
                continue
        elif path.suffix == ".html":
            units = html_units(text)
        elif path.suffix == ".md":
            units = markdown_units(text)
        else:
            continue
        for unit in units:
            viols.extend(scan_unit(rel, unit, cfg, high))
        for unit, predicate, reason in predicate_stat(units, cfg):
            viols.append(Violation(
                path=rel, line=unit.line, col=unit.col,
                word=unit.text.strip(), predicate=predicate, reason=reason,
                symbol="<stat-card>",
                sentence=" ".join(unit.text.split())[:160],
                high=high, alternatives=(),
            ))

    viols.sort(key=Violation.sort_key)

    used: list[str] = []
    rotted: list[str] = []
    if not args.no_allowlist:
        viols, used, rotted = apply_allowlist(root, viols, cfg)

    if args.sarif:
        json.dump(to_sarif(viols, args.anchor), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if (viols or rotted) else 0

    if args.json:
        json.dump({
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "anchor": args.anchor,
            "files_scanned": scanned,
            "violations": [v.__dict__ for v in viols],
            "allowlist_used": used,
            "allowlist_stale": rotted,
        }, sys.stdout, indent=2, default=list)
        sys.stdout.write("\n")
        return 1 if (viols or rotted) else 0

    print("%s %s" % (TOOL_NAME, TOOL_VERSION))
    print("anchor:  %s" % (args.anchor or "<none given>"))
    print("root:    %s" % root)
    print("scanned: %d files" % scanned)
    print("legs:    declared_proof_legs = %d" % cfg.declared_proof_legs)
    print("")
    for v in viols:
        tag = "HIGH (external surface)" if v.high else "violation"
        print("%s:%d:%d: %s [claim-%s] '%s'"
              % (v.path, v.line, v.col, tag, v.predicate, v.word))
        print("    symbol:   %s" % v.symbol)
        print("    why:      %s" % v.reason)
        if v.alternatives:
            print("    instead:  %s" % ", ".join(v.alternatives))
        print("    text:     %s" % v.sentence)
        print("")
    for line in used:
        print("allowlisted: %s" % line)
    for line in rotted:
        print("STALE ALLOWLIST: %s" % line)
    if used or rotted:
        print("")
    print("%d violation(s), %d allowlisted, %d stale allowlist entr(ies)"
          % (len(viols), len(used), len(rotted)))
    print("")
    print("This result EVIDENCES conformance to the declared convention.")
    print("It PROVES nothing about the correctness of the scanned system.")
    return 1 if (viols or rotted) else 0


if __name__ == "__main__":
    sys.exit(main())
