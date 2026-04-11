"""
NOUS NSP — Noosphere Shorthand Protocol
=========================================
Parses [NSP|CT.88|F.78|R.scout] tokens from prompt strings
into validated, structured objects. Saves 40-60% of prompt tokens.

Protocol format:
    [NSP|KEY.VALUE|KEY.VALUE|...]

Examples:
    [NSP|CT.88|F.78|R.scout]        → {CT: 0.88, F: 0.78, R: "scout"}
    [NSP|T.Tier1|M.safe|P.90]       → {T: "Tier1", M: "safe", P: 90}
    [NSP|S.concise|CT.95]           → {S: "concise", CT: 0.95}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

NSP_PATTERN = re.compile(r"\[NSP\|([^\]]+)\]")
NSP_FIELD_PATTERN = re.compile(r"^([A-Za-z_]+)\.(.+)$")

# Built-in NSP field definitions
BUILTIN_FIELDS: dict[str, dict[str, Any]] = {
    "CT": {"type": "float", "name": "Confidence Threshold", "range": (0.0, 1.0)},
    "F":  {"type": "float", "name": "Focus coefficient", "range": (0.0, 1.0)},
    "R":  {"type": "string", "name": "Router target reference"},
    "T":  {"type": "tier", "name": "Model tier override", "values": ["Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3"]},
    "M":  {"type": "mode", "name": "Operating mode", "values": ["normal", "safe", "aggressive", "stealth"]},
    "P":  {"type": "int", "name": "Priority", "range": (0, 100)},
    "S":  {"type": "style", "name": "Prompt style", "values": ["concise", "analytical", "creative", "technical"]},
    "TP": {"type": "float", "name": "Temperature", "range": (0.0, 2.0)},
    "MT": {"type": "int", "name": "Max tokens", "range": (1, 32000)},
    "TL": {"type": "float", "name": "Time limit seconds", "range": (0.0, 300.0)},
}


@dataclass
class NSPField:
    key: str
    raw_value: str
    typed_value: Any = None
    field_name: str = ""
    valid: bool = True
    error: str = ""


@dataclass
class NSPToken:
    raw: str
    fields: list[NSPField] = field(default_factory=list)
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {f.key: f.typed_value for f in self.fields if f.valid}

    def to_prompt_expansion(self) -> str:
        parts = []
        for f in self.fields:
            if not f.valid:
                continue
            parts.append(f"{f.field_name}: {f.typed_value}")
        return " | ".join(parts)

    @property
    def token_savings(self) -> dict[str, int]:
        expanded = self.to_prompt_expansion()
        return {
            "compressed_chars": len(self.raw),
            "expanded_chars": len(expanded),
            "savings_pct": round((1 - len(self.raw) / max(len(expanded), 1)) * 100) if expanded else 0,
        }


@dataclass
class NSPValidationError:
    field_key: str
    message: str

    def __str__(self) -> str:
        return f"[NSP] {self.field_key}: {self.message}"


class NSPRegistry:
    """Registry of NSP field definitions. Starts with builtins, extended by nsp{} blocks."""

    def __init__(self) -> None:
        self.fields: dict[str, dict[str, Any]] = dict(BUILTIN_FIELDS)

    def register(self, key: str, type_expr: str, name: str = "") -> None:
        self.fields[key] = {
            "type": type_expr,
            "name": name or key,
        }

    def has(self, key: str) -> bool:
        return key in self.fields

    def get_def(self, key: str) -> Optional[dict[str, Any]]:
        return self.fields.get(key)


class NSPParser:
    """Parses and validates NSP tokens from strings."""

    def __init__(self, registry: Optional[NSPRegistry] = None) -> None:
        self.registry = registry or NSPRegistry()

    def extract_all(self, text: str) -> list[NSPToken]:
        tokens = []
        for match in NSP_PATTERN.finditer(text):
            raw = match.group(0)
            body = match.group(1)
            token = self._parse_token(raw, body)
            tokens.append(token)
        return tokens

    def expand(self, text: str) -> str:
        def replacer(match: re.Match) -> str:
            body = match.group(1)
            token = self._parse_token(match.group(0), body)
            if token.valid:
                return token.to_prompt_expansion()
            return match.group(0)
        return NSP_PATTERN.sub(replacer, text)

    def validate_text(self, text: str) -> list[NSPValidationError]:
        errors = []
        for token in self.extract_all(text):
            for e in token.errors:
                errors.append(NSPValidationError("NSP", e))
            for f in token.fields:
                if not f.valid:
                    errors.append(NSPValidationError(f.key, f.error))
        return errors

    def compress(self, params: dict[str, Any]) -> str:
        parts = []
        for key, value in params.items():
            if not self.registry.has(key):
                continue
            parts.append(f"{key}.{value}")
        return "[NSP|" + "|".join(parts) + "]"

    def _parse_token(self, raw: str, body: str) -> NSPToken:
        token = NSPToken(raw=raw)
        segments = body.split("|")

        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue

            m = NSP_FIELD_PATTERN.match(seg)
            if not m:
                token.errors.append(f"Invalid NSP field format: {seg}")
                token.valid = False
                continue

            key = m.group(1)
            raw_val = m.group(2)
            nsp_field = self._parse_field(key, raw_val)
            token.fields.append(nsp_field)

            if not nsp_field.valid:
                token.valid = False
                token.errors.append(nsp_field.error)

        return token

    def _parse_field(self, key: str, raw_value: str) -> NSPField:
        field_def = self.registry.get_def(key)
        nsp_field = NSPField(key=key, raw_value=raw_value)

        if field_def is None:
            nsp_field.field_name = key
            nsp_field.typed_value = raw_value
            nsp_field.valid = True
            return nsp_field

        nsp_field.field_name = field_def.get("name", key)
        field_type = field_def.get("type", "string")

        try:
            if field_type == "float":
                val = float(raw_value) if "." in raw_value else float(raw_value) / 100
                nsp_field.typed_value = val
                rng = field_def.get("range")
                if rng and not (rng[0] <= val <= rng[1]):
                    nsp_field.valid = False
                    nsp_field.error = f"{key} value {val} out of range [{rng[0]}, {rng[1]}]"

            elif field_type == "int":
                val = int(raw_value)
                nsp_field.typed_value = val
                rng = field_def.get("range")
                if rng and not (rng[0] <= val <= rng[1]):
                    nsp_field.valid = False
                    nsp_field.error = f"{key} value {val} out of range [{rng[0]}, {rng[1]}]"

            elif field_type in ("tier", "mode", "style"):
                allowed = field_def.get("values", [])
                if allowed and raw_value not in allowed:
                    nsp_field.valid = False
                    nsp_field.error = f"{key} value '{raw_value}' not in {allowed}"
                nsp_field.typed_value = raw_value

            else:
                nsp_field.typed_value = raw_value

        except (ValueError, TypeError) as e:
            nsp_field.valid = False
            nsp_field.error = f"{key}: cannot parse '{raw_value}' as {field_type}: {e}"

        return nsp_field


def create_nsp_parser(nsp_block: Optional[dict] = None) -> NSPParser:
    """Create an NSP parser, optionally extending with fields from an nsp{} block."""
    registry = NSPRegistry()
    if nsp_block:
        for key, type_expr in nsp_block.items():
            registry.register(key, type_expr)
    return NSPParser(registry)
