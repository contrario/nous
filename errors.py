"""
NOUS Error Diagnostics — Σφάλμα (Sfalma)
==========================================
Human-friendly error messages with source context and "did you mean?" suggestions.
"""
from __future__ import annotations

from typing import Optional

from lark.exceptions import UnexpectedCharacters, UnexpectedToken, UnexpectedInput


NOUS_KEYWORDS: list[str] = [
    "world", "κόσμος", "soul", "ψυχή", "mind", "νους",
    "memory", "μνήμη", "instinct", "ένστικτο", "sense", "αίσθηση",
    "speak", "λέω", "listen", "ακούω", "remember", "θυμάμαι",
    "guard", "φύλακας", "heal", "θεραπεία", "dna", "DNA",
    "law", "νόμος", "message", "μήνυμα", "senses",
    "nervous_system", "νευρικό", "evolution", "εξέλιξη",
    "perception", "αντίληψη", "deploy", "topology", "nsp",
    "let", "for", "in", "if", "else", "on", "self",
    "sleep", "cycle", "per", "constitutional",
    "wake", "wake_all", "broadcast", "alert", "silence", "σιωπή",
    "retry", "lower", "raise", "hibernate", "fallback", "delegate", "then",
    "mutate", "strategy", "survive_if", "rollback_if",
    "schedule", "fitness", "heartbeat", "timezone",
    "true", "false",
]

NOUS_TYPES: list[str] = ["string", "int", "float", "bool", "SoulRef"]

NOUS_TIERS: list[str] = ["Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3"]

ALL_KNOWN: list[str] = NOUS_KEYWORDS + NOUS_TYPES + NOUS_TIERS


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


def did_you_mean(word: str, candidates: Optional[list[str]] = None, max_distance: int = 3) -> Optional[str]:
    if candidates is None:
        candidates = ALL_KNOWN
    word_lower = word.lower()
    best: Optional[str] = None
    best_dist = max_distance + 1
    for candidate in candidates:
        dist = _levenshtein(word_lower, candidate.lower())
        if dist < best_dist and dist > 0:
            best_dist = dist
            best = candidate
    if best and best_dist <= max_distance:
        return best
    return None


def _source_context(source: str, line: int, col: int) -> str:
    lines = source.splitlines()
    out: list[str] = []
    line_idx = line - 1

    if line_idx - 1 >= 0:
        ln = line_idx
        out.append(f"  {ln:4d} │ {lines[line_idx - 1]}")

    if 0 <= line_idx < len(lines):
        current = lines[line_idx]
        out.append(f"  {line_idx + 1:4d} │ {current}")
        pointer = " " * (9 + col) + "^"
        out.append(pointer)
    else:
        out.append(f"  {line_idx + 1:4d} │ <end of file>")

    if line_idx + 1 < len(lines):
        ln = line_idx + 2
        out.append(f"  {ln:4d} │ {lines[line_idx + 1]}")

    return "\n".join(out)


def _extract_token_at(source: str, line: int, col: int) -> str:
    lines = source.splitlines()
    line_idx = line - 1
    if line_idx < 0 or line_idx >= len(lines):
        return ""
    text = lines[line_idx]
    start = col
    end = col
    while end < len(text) and (text[end].isalnum() or text[end] in "_"):
        end += 1
    return text[start:end]


def _find_misspelled_keywords(source: str, line: int) -> Optional[tuple[str, str]]:
    lines = source.splitlines()
    line_idx = line - 1
    if line_idx < 0 or line_idx >= len(lines):
        return None
    text = lines[line_idx]
    import re
    tokens = re.findall(r'[a-zA-Z_\u0370-\u03FF][a-zA-Z0-9_\u0370-\u03FF]*', text)
    for token in tokens:
        suggestion = did_you_mean(token, max_distance=2)
        if suggestion and suggestion.lower() != token.lower():
            return (token, suggestion)
    return None


def format_parse_error(exc: Exception, source: str, filename: str = "<stdin>") -> str:
    parts: list[str] = []

    if isinstance(exc, UnexpectedCharacters):
        line = exc.line or 1
        col = (exc.column or 1) - 1
        token = _extract_token_at(source, line, col)
        parts.append(f"\n── Parse Error ── {filename}:{line}:{col + 1}")
        parts.append("")
        parts.append(_source_context(source, line, col))
        parts.append("")

        if token:
            suggestion = did_you_mean(token)
            misspell = _find_misspelled_keywords(source, line)
            if misspell and misspell[0] != token:
                parts.append(f"  '{misspell[0]}' is not a keyword. Did you mean '{misspell[1]}'?")
            elif suggestion:
                parts.append(f"  Unexpected '{token}'. Did you mean '{suggestion}'?")
            else:
                parts.append(f"  Unexpected character '{token}'.")
        else:
            parts.append(f"  Unexpected character at this position.")

        allowed = exc.allowed or set()
        if allowed:
            friendly = _friendly_expected(allowed)
            if friendly:
                parts.append(f"  Expected: {friendly}")

    elif isinstance(exc, UnexpectedToken):
        line = exc.line or 1
        col = (exc.column or 1) - 1
        token_str = str(exc.token).strip()
        parts.append(f"\n── Parse Error ── {filename}:{line}:{col + 1}")
        parts.append("")
        parts.append(_source_context(source, line, col))
        parts.append("")

        misspell = _find_misspelled_keywords(source, line)
        if misspell:
            parts.append(f"  '{misspell[0]}' is not a keyword. Did you mean '{misspell[1]}'?")
        elif token_str:
            suggestion = did_you_mean(token_str)
            if suggestion:
                parts.append(f"  Unexpected '{token_str}'. Did you mean '{suggestion}'?")
            else:
                parts.append(f"  Unexpected token '{token_str}'.")
        else:
            parts.append(f"  Unexpected token at this position.")

        expected = exc.expected or set()
        if expected:
            friendly = _friendly_expected(expected)
            if friendly:
                parts.append(f"  Expected: {friendly}")

    else:
        parts.append(f"\n── Parse Error ── {filename}")
        parts.append(f"  {exc}")

    parts.append("")
    return "\n".join(parts)


_EXPECTED_MAP: dict[str, str] = {
    "LBRACE": "'{'",
    "RBRACE": "'}'",
    "LSQB": "'['",
    "RSQB": "']'",
    "LPAR": "'('",
    "RPAR": "')'",
    "COLON": "':'",
    "COMMA": "','",
    "EQUAL": "'='",
    "SEMICOLON": "';'",
    "NAME": "identifier",
    "STRING": "string literal",
    "INT": "integer",
    "FLOAT": "number",
    "BOOL": "true/false",
    "NEWLINE": "newline",
    "$END": "end of file",
    "ARROW": "'->'",
    "FAT_ARROW": "'=>'",
    "COMP_OP": "comparison operator",
    "ADD_OP": "'+' or '-'",
    "MUL_OP": "'*' or '/'",
    "DEPLOY": "'deploy'",
    "NSP": "'nsp'",
    "TOPOLOGY": "'topology'",
    "WORLD": "'world'",
    "SOUL": "'soul'",
    "MESSAGE": "'message'",
    "MEMORY": "'memory'",
    "INSTINCT": "'instinct'",
    "DNA": "'dna'",
    "HEAL": "'heal'",
    "LAW": "'law'",
    "SENSE": "'sense'",
    "SPEAK": "'speak'",
    "LISTEN": "'listen'",
    "GUARD": "'guard'",
    "REMEMBER": "'remember'",
    "NERVOUS_SYSTEM": "'nervous_system'",
    "EVOLUTION": "'evolution'",
    "PERCEPTION": "'perception'",
    "TIER": "tier (Tier0A..Tier3)",
}


def _friendly_expected(tokens: set[str]) -> str:
    friendly: list[str] = []
    for tok in sorted(tokens):
        tok_str = str(tok)
        if tok_str in _EXPECTED_MAP:
            friendly.append(_EXPECTED_MAP[tok_str])
        elif tok_str.startswith("__"):
            continue
        elif tok_str.startswith("_"):
            continue
        else:
            friendly.append(tok_str)
    unique = list(dict.fromkeys(friendly))
    if len(unique) > 6:
        return ", ".join(unique[:6]) + ", ..."
    return ", ".join(unique)


def format_validation_errors(source: str, errors: list[object], filename: str = "<stdin>") -> str:
    if not errors:
        return ""
    parts: list[str] = []
    for err in errors:
        sev = getattr(err, "severity", "ERROR")
        code = getattr(err, "code", "???")
        msg = getattr(err, "message", str(err))
        loc = getattr(err, "location", "")
        icon = "✗" if sev == "ERROR" else "⚠"
        header = f"  {icon} [{code}]"
        if loc:
            header += f" @ {loc}"
        header += f": {msg}"
        parts.append(header)
    return "\n".join(parts)
