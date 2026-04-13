"""
Noesis Phase 3: Reasoning Engine
Logic atoms, math atoms, temporal atoms, contradiction detection.
Uses existing relations dict with _prefixed keys — zero changes to Atom class.

Relation key conventions:
    _type:       "logic" | "math" | "temporal" | "fact" (default)
    _condition:  IF part of logic atom (e.g. "temperature > 140")
    _conclusion: THEN part of logic atom (e.g. "maillard_reaction = active")
    _formula:    math expression (e.g. "(win_prob * odds - 1) / (odds - 1)")
    _variables:  comma-separated variable names
    _expires:    ISO timestamp or unix epoch for temporal atoms
    _valid_from: ISO timestamp or unix epoch for temporal atoms
    _negates:    pattern that this atom contradicts

Usage: add ONE line at the bottom of noesis_engine.py:
    import noesis_reasoning_patch
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any

log = logging.getLogger("noesis.reasoning")


_LOGIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^if\s+(.+?)\s+then\s+(.+)$", re.I),
    re.compile(r"^when\s+(.+?)\s*[,;]\s*(.+)$", re.I),
    re.compile(r"^(.+?)\s+implies\s+(.+)$", re.I),
    re.compile(r"^αν\s+(.+?)\s+τότε\s+(.+)$", re.I),
    re.compile(r"^όταν\s+(.+?)\s*[,;]\s*(.+)$", re.I),
]

_MATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(.+?)\s*=\s*(.+[+\-*/×÷^].+)$"),
    re.compile(r"^(.+?)\s+equals?\s+(.+[+\-*/×÷^].+)$", re.I),
    re.compile(r"^formula:\s*(.+?)\s*=\s*(.+)$", re.I),
]

_TEMPORAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\(valid(?:\s+until)?:\s*(\d{4}-\d{2}-\d{2}(?:T[\d:]+)?)\s*(?:,\s*expires?:\s*(\d{4}-\d{2}-\d{2}(?:T[\d:]+)?))?\)", re.I),
    re.compile(r"as\s+of\s+(\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"updated?\s+(\d{4}-\d{2}-\d{2})", re.I),
]

_NEGATION_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(.+?)\s+is\s+not\s+(.+)", re.I), "is"),
    (re.compile(r"(.+?)\s+are\s+not\s+(.+)", re.I), "are"),
    (re.compile(r"(.+?)\s+does\s+not\s+(.+)", re.I), "does"),
    (re.compile(r"(.+?)\s+cannot\s+(.+)", re.I), "can"),
    (re.compile(r"(.+?)\s+δεν\s+(?:είναι|μπορεί|έχει)\s+(.+)", re.I), "den"),
    (re.compile(r"contrary\s+to\s+(.+?),\s*(.+)", re.I), "contrary"),
]

_EXPIRY_PRESETS: dict[str, float] = {
    "crypto": 86400,
    "bitcoin": 86400,
    "ethereum": 86400,
    "weather": 21600,
    "temperature": 21600,
    "stock": 86400,
    "price": 86400,
    "exchange_rate": 86400,
    "score": 7200,
    "earthquake": 3600,
    "news": 172800,
}


def detect_atom_type(template: str, relations: dict[str, str]) -> dict[str, str]:
    extra: dict[str, str] = {}

    for pat in _LOGIC_PATTERNS:
        m = pat.search(template)
        if m:
            extra["_type"] = "logic"
            extra["_condition"] = m.group(1).strip()
            extra["_conclusion"] = m.group(2).strip()
            return extra

    for pat in _MATH_PATTERNS:
        m = pat.search(template)
        if m:
            lhs = m.group(1).strip()
            rhs = m.group(2).strip()
            variables = _extract_variables(rhs)
            if variables:
                extra["_type"] = "math"
                extra["_formula"] = f"{lhs} = {rhs}"
                extra["_variables"] = ",".join(variables)
                return extra

    for pat in _TEMPORAL_PATTERNS:
        m = pat.search(template)
        if m:
            extra["_type"] = "temporal"
            valid_date = m.group(1)
            extra["_valid_from"] = valid_date
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                extra["_expires"] = m.group(2)
            else:
                extra["_expires"] = str(time.time() + 86400)
            return extra

    patterns_lower = [p.lower() for p in relations.get("subject", "").split()] if "subject" in relations else []
    template_lower = template.lower()
    for keyword, ttl_seconds in _EXPIRY_PRESETS.items():
        if keyword in template_lower or keyword in patterns_lower:
            extra["_type"] = "temporal"
            extra["_valid_from"] = str(time.time())
            extra["_expires"] = str(time.time() + ttl_seconds)
            return extra

    for neg_pat, neg_type in _NEGATION_SIGNALS:
        m = neg_pat.search(template)
        if m:
            extra["_negates"] = f"{m.group(1).strip().lower()}|{neg_type}|{m.group(2).strip().lower()}"
            break

    return extra


def _extract_variables(expr: str) -> list[str]:
    expr_clean = re.sub(r'[+\-*/×÷^()=,\d.\s]', ' ', expr)
    words = expr_clean.split()
    skip = {"sin", "cos", "tan", "log", "ln", "sqrt", "abs", "min", "max", "pi", "e", "mod"}
    variables = []
    for w in words:
        w = w.strip("_")
        if w and w.lower() not in skip and re.match(r'^[a-zA-Z_]\w*$', w):
            if w.lower() not in variables:
                variables.append(w.lower())
    return variables


def is_expired(atom: Any) -> bool:
    relations = getattr(atom, "relations", {})
    if relations.get("_type") != "temporal":
        return False
    expires_str = relations.get("_expires", "")
    if not expires_str:
        return False
    try:
        expires = float(expires_str)
    except ValueError:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(expires_str)
            expires = dt.timestamp()
        except (ValueError, TypeError):
            return False
    return time.time() > expires


def evaluate_logic(atom: Any, context: dict[str, Any] | None = None) -> bool | None:
    relations = getattr(atom, "relations", {})
    if relations.get("_type") != "logic":
        return None
    condition = relations.get("_condition", "")
    if not condition or not context:
        return None
    try:
        return _eval_condition(condition, context)
    except Exception:
        return None


def _eval_condition(condition: str, context: dict[str, Any]) -> bool | None:
    condition = condition.strip()

    and_parts = re.split(r'\s+and\s+', condition, flags=re.I)
    if len(and_parts) > 1:
        results = [_eval_condition(p, context) for p in and_parts]
        if None in results:
            return None
        return all(results)

    or_parts = re.split(r'\s+or\s+', condition, flags=re.I)
    if len(or_parts) > 1:
        results = [_eval_condition(p, context) for p in or_parts]
        if None in results:
            return None
        return any(results)

    m = re.match(r'^(\w+)\s*(>|<|>=|<=|==|!=|=)\s*(.+)$', condition)
    if m:
        var_name = m.group(1).lower()
        op = m.group(2)
        if op == "=":
            op = "=="
        rhs = m.group(3).strip()

        if var_name not in context:
            return None

        lhs_val = context[var_name]

        try:
            rhs_val: Any = float(rhs)
        except ValueError:
            rhs_val = rhs.strip('"\'').lower()
            lhs_val = str(lhs_val).lower()

        ops = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        return ops[op](lhs_val, rhs_val)

    return None


def evaluate_math(atom: Any, variables: dict[str, float] | None = None) -> float | None:
    relations = getattr(atom, "relations", {})
    if relations.get("_type") != "math":
        return None
    formula = relations.get("_formula", "")
    if not formula:
        return None

    parts = formula.split("=", 1)
    if len(parts) != 2:
        return None
    expr = parts[1].strip()

    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")

    if variables:
        for var_name, var_val in variables.items():
            expr = re.sub(rf'\b{re.escape(var_name)}\b', str(var_val), expr, flags=re.I)

    allowed_names = {"abs": abs, "min": min, "max": max, "sqrt": math.sqrt,
                     "log": math.log, "sin": math.sin, "cos": math.cos,
                     "tan": math.tan, "pi": math.pi, "e": math.e}

    if re.search(r'[a-zA-Z_]\w*', expr):
        remaining = re.findall(r'[a-zA-Z_]\w*', expr)
        for r in remaining:
            if r not in allowed_names:
                return None

    try:
        result = eval(expr, {"__builtins__": {}}, allowed_names)
        return float(result)
    except Exception:
        return None


def find_contradictions(atoms: list[Any]) -> list[tuple[Any, Any, str]]:
    contradictions: list[tuple[Any, Any, str]] = []
    negation_map: dict[str, Any] = {}

    for atom in atoms:
        relations = getattr(atom, "relations", {})
        negates = relations.get("_negates", "")
        if negates:
            negation_map[negates] = atom

    for atom in atoms:
        relations = getattr(atom, "relations", {})
        subject = relations.get("subject", "").lower()
        is_a = relations.get("is_a", "").lower()

        if subject and is_a:
            neg_key = f"{subject}|is|{is_a}"
            if neg_key in negation_map:
                other = negation_map[neg_key]
                contradictions.append((atom, other, f"'{subject} is {is_a}' vs negation"))

    for i, atom_a in enumerate(atoms):
        rel_a = getattr(atom_a, "relations", {})
        subj_a = rel_a.get("subject", "").lower()
        if not subj_a:
            continue
        for atom_b in atoms[i + 1:]:
            rel_b = getattr(atom_b, "relations", {})
            subj_b = rel_b.get("subject", "").lower()
            if subj_a != subj_b:
                continue
            for key in rel_a:
                if key.startswith("_"):
                    continue
                if key == "subject":
                    continue
                if key in rel_b and rel_a[key].lower() != rel_b[key].lower():
                    a_conf = getattr(atom_a, "confidence", 0.5)
                    b_conf = getattr(atom_b, "confidence", 0.5)
                    a_birth = getattr(atom_a, "birth", 0)
                    b_birth = getattr(atom_b, "birth", 0)
                    reason = f"'{subj_a}' has conflicting '{key}': '{rel_a[key]}' vs '{rel_b[key]}'"
                    if a_conf > b_conf or (a_conf == b_conf and a_birth > b_birth):
                        contradictions.append((atom_a, atom_b, reason))
                    else:
                        contradictions.append((atom_b, atom_a, reason))

    return contradictions


def resolve_contradictions(
    contradictions: list[tuple[Any, Any, str]],
    lattice: Any | None = None,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for winner, loser, reason in contradictions:
        loser_id = getattr(loser, "id", "unknown")
        winner_id = getattr(winner, "id", "unknown")
        loser.confidence = max(0.0, getattr(loser, "confidence", 0.5) - 0.2)
        actions.append({
            "action": "demote",
            "loser_id": loser_id,
            "winner_id": winner_id,
            "reason": reason,
            "new_confidence": str(loser.confidence),
        })
        if loser.confidence <= 0.0 and lattice is not None and hasattr(lattice, "atoms"):
            if loser_id in lattice.atoms:
                del lattice.atoms[loser_id]
                actions[-1]["action"] = "removed"
    return actions


def filter_expired(atoms: list[tuple[Any, float]]) -> list[tuple[Any, float]]:
    return [(atom, score) for atom, score in atoms if not is_expired(atom)]
