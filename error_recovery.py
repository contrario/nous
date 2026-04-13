"""
NOUS Error Recovery — Διάγνωση (Diagnosi)
============================================
Better parse error messages with "did you mean?" suggestions,
context-aware hints, and recovery strategies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


KNOWN_KEYWORDS = {
    "world", "soul", "message", "nervous_system", "evolution", "perception",
    "mind", "senses", "memory", "instinct", "dna", "heal",
    "law", "heartbeat", "timezone",
    "let", "remember", "speak", "listen", "sense", "guard",
    "if", "else", "for", "in", "on", "match", "sleep",
    "import", "test", "deploy", "topology", "nsp",
    "true", "false", "self", "now", "cycle", "per",
    "retry", "lower", "raise", "hibernate", "fallback", "delegate", "alert",
    "wake", "wake_all", "broadcast", "silence", "constitutional",
    "mutate", "strategy", "survive_if", "rollback_if", "fitness", "schedule",
    "assert",
}

COMMON_TYPOS: dict[str, str] = {
    "worl": "world", "wolrd": "world", "wrold": "world",
    "sould": "soul", "soule": "soul", "sol": "soul",
    "mesage": "message", "messge": "message", "msg": "message",
    "nervos_system": "nervous_system", "nervous": "nervous_system",
    "instict": "instinct", "insinct": "instinct",
    "memeory": "memory", "memroy": "memory", "mem": "memory",
    "haelth": "heal", "hael": "heal",
    "spek": "speak", "speek": "speak",
    "lisen": "listen", "listn": "listen",
    "gaurd": "guard", "gard": "guard",
    "remeber": "remember", "rember": "remember",
    "sens": "sense", "sence": "sense",
    "ture": "true", "flase": "false", "fals": "false",
    "imprt": "import", "imoprt": "import",
    "percption": "perception", "percetion": "perception",
    "evoultion": "evolution", "evoluton": "evolution",
}

CONTEXT_HINTS: dict[str, str] = {
    "world_body": "Inside world {{ }}: expected law, heartbeat, timezone, or config_name = value",
    "soul_body": "Inside soul {{ }}: expected mind, senses, memory, instinct, dna, or heal",
    "instinct": "Inside instinct {{ }}: expected let, remember, speak, listen, sense, guard, if, for, sleep",
    "heal_body": "Inside heal {{ }}: expected on <error> => <action>",
    "nervous_system": "Inside nervous_system {{ }}: expected soul -> soul, [souls] -> soul, or match {{ }}",
    "message_body": "Inside message {{ }}: expected field_name: type",
    "memory_body": "Inside memory {{ }}: expected field_name: type = default",
    "dna_body": "Inside dna {{ }}: expected gene_name: value ~ [min, max]",
    "top_level": "At top level: expected world, soul, message, nervous_system, evolution, perception, import, or test",
}


@dataclass
class EnhancedError:
    original: str
    line: int
    column: int
    token: str
    expected: list[str]
    suggestion: Optional[str] = None
    hint: Optional[str] = None
    context: str = ""
    source_line: str = ""

    def format(self) -> str:
        lines: list[str] = []
        lines.append(f"\n  Error at line {self.line}, column {self.column}:")
        if self.source_line:
            lines.append(f"    {self.source_line.rstrip()}")
            pointer = " " * (self.column - 1 + 4) + "^"
            lines.append(pointer)
        lines.append(f"    Unexpected: {self.token}")
        if self.expected:
            expected_readable = [_readable_token(e) for e in self.expected[:5]]
            lines.append(f"    Expected:   {', '.join(expected_readable)}")
        if self.suggestion:
            lines.append(f"    Did you mean: {self.suggestion}")
        if self.hint:
            lines.append(f"    Hint: {self.hint}")
        return "\n".join(lines)


def enhance_parse_error(error_msg: str, source: str) -> EnhancedError:
    lines = source.split("\n")
    line_num = 1
    col_num = 1
    token_str = ""
    expected: list[str] = []

    m = re.search(r"line (\d+)", error_msg)
    if m:
        line_num = int(m.group(1))

    m = re.search(r"column (\d+)", error_msg)
    if m:
        col_num = int(m.group(1))

    m = re.search(r"Token\('(\w+)',\s*'([^']*)'\)", error_msg)
    if m:
        token_str = m.group(2)

    for m in re.finditer(r"\* (\w+)", error_msg):
        expected.append(m.group(1))

    source_line = lines[line_num - 1] if line_num <= len(lines) else ""
    context = _detect_context(lines, line_num)
    suggestion = _find_suggestion(token_str, expected, context, source_line)
    hint = _find_hint(token_str, expected, context, source_line, lines, line_num)

    return EnhancedError(
        original=error_msg,
        line=line_num,
        column=col_num,
        token=token_str,
        expected=expected,
        suggestion=suggestion,
        hint=hint,
        context=context,
        source_line=source_line,
    )


def _detect_context(lines: list[str], error_line: int) -> str:
    brace_stack: list[str] = []
    for i in range(error_line - 1):
        line = lines[i].strip()
        if line.startswith("#"):
            continue
        m = re.match(r"(world|soul|message|nervous_system|evolution|perception|instinct|memory|dna|heal|test)\b", line)
        if m:
            brace_stack.append(m.group(1))
        brace_stack_delta = line.count("{") - line.count("}")
        if brace_stack_delta < 0 and brace_stack:
            for _ in range(abs(brace_stack_delta)):
                if brace_stack:
                    brace_stack.pop()
    if brace_stack:
        ctx = brace_stack[-1]
        if ctx in ("world",):
            return "world_body"
        elif ctx in ("soul",):
            return "soul_body"
        elif ctx in ("instinct",):
            return "instinct"
        elif ctx in ("heal",):
            return "heal_body"
        elif ctx in ("nervous_system",):
            return "nervous_system"
        elif ctx in ("message",):
            return "message_body"
        elif ctx in ("memory",):
            return "memory_body"
        elif ctx in ("dna",):
            return "dna_body"
        elif ctx in ("test",):
            return "instinct"
        return ctx
    return "top_level"


def _find_suggestion(token: str, expected: list[str], context: str, source_line: str) -> Optional[str]:
    if token in COMMON_TYPOS:
        return COMMON_TYPOS[token]

    if token:
        best_match: Optional[str] = None
        best_dist = 3
        for kw in KNOWN_KEYWORDS:
            d = _levenshtein(token.lower(), kw)
            if d < best_dist:
                best_dist = d
                best_match = kw
        if best_match:
            return best_match

    if len(expected) == 1:
        readable = _readable_token(expected[0])
        return f"add '{readable}' here"

    return None


def _find_hint(token: str, expected: list[str], context: str, source_line: str, lines: list[str], line_num: int) -> Optional[str]:
    if context in CONTEXT_HINTS:
        ctx_hint = CONTEXT_HINTS[context]
    else:
        ctx_hint = None

    stripped = source_line.strip()

    if "}" in expected and token:
        open_count = sum(l.count("{") for l in lines[:line_num])
        close_count = sum(l.count("}") for l in lines[:line_num])
        if open_count > close_count:
            return f"Missing closing '}}' — {open_count} opened, {close_count} closed before this line"

    if context == "instinct" and token in ("soul", "message", "world"):
        return f"'{token}' is a top-level declaration — you may be missing a closing '}}' for instinct"

    if context == "world_body" and "PER" in expected:
        return "Currency law needs 'per cycle' suffix: law Name = $0.10 per cycle. Or use standalone: law Name = $500"

    if context == "soul_body" and token == "let":
        return "'let' is only valid inside instinct {{ }}. Did you forget to open an instinct block?"

    if stripped.startswith("speak") and "(" not in stripped:
        return "speak syntax: speak MessageName(field: value, ...)"

    if stripped.startswith("listen") and "::" not in stripped:
        return "listen syntax: let x = listen SoulName::MessageType"

    if "{" in stripped and "}" in stripped and stripped.index("}") < stripped.index("{"):
        return "Closing '}}' before opening '{{' — check brace order"

    return ctx_hint


def _readable_token(token_type: str) -> str:
    readable_map: dict[str, str] = {
        "NAME": "identifier",
        "INT": "number",
        "FLOAT": "decimal number",
        "STRING": "quoted string",
        "BOOL": "true/false",
        "LBRACE": "{",
        "RBRACE": "}",
        "LPAR": "(",
        "RPAR": ")",
        "LSQB": "[",
        "RSQB": "]",
        "COLON": ":",
        "COMMA": ",",
        "EQUAL": "=",
        "PER": "per",
        "CYCLE": "cycle",
        "LAW": "law",
        "SOUL": "soul",
        "WORLD": "world",
        "MESSAGE": "message",
        "LET": "let",
        "IF": "if",
        "ELSE": "else",
        "FOR": "for",
        "SPEAK": "speak",
        "LISTEN": "listen",
        "SENSE": "sense",
        "GUARD": "guard",
        "REMEMBER": "remember",
    }
    return readable_map.get(token_type, token_type.lower())


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]


def format_parse_error(error_msg: str, source: str) -> str:
    enhanced = enhance_parse_error(error_msg, source)
    return enhanced.format()
