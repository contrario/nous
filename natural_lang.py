"""
NOUS Natural Language Interface — Φυσική Γλώσσα (Fysiki Glossa)
==================================================================
Translates plain English/Greek descriptions into valid .nous source code.
Uses LLM (Claude) with NOUS grammar reference as system context.
Validates output through parser/validator pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("nous.natural_lang")

NOUS_REFERENCE = '''
NOUS is a programming language for agentic AI systems. Here is the complete syntax reference:

## World Declaration
world WorldName {
law cost_ceiling = $0.10 per cycle
law max_retries = 5
heartbeat = 5m
timezone = "UTC"
}
Laws can be: cost ($X.XX per cycle), duration (5m, 30s, 1h), int, bool, constitutional(N).
Heartbeat units: ms, s, m, h, d.

## Messages
message SignalName {
field_name: type = default_value
}
Types: string, int, float, bool, timestamp, duration, currency, [type] (list), type? (optional).

## Souls
soul SoulName {
mind: model-name @ TierXY
senses: [http_get, http_post, tool_name]
memory {
field_name: type = default
}
instinct {
let var = expr
let data = sense http_get(url: "https://...")
let msg = listen OtherSoul::MessageType
remember field_name = value
remember field_name += value
speak MessageType(field: value, field2: value2)
guard condition
if condition {
...
} else {
...
}
for item in list_expr {
...
}
sleep 5s
}
dna {
gene_name: value ~ [min, max]
}
heal {
on timeout => retry(3, exponential)
on api_error => retry(2, exponential)
on rate_limit => sleep 30s
on connection_error => hibernate until next_cycle
}
}
Mind tiers: Tier0A (claude), Tier0B (gpt-4), Tier1 (deepseek), Tier2 (gemini), Tier3 (llama/local).

## Nervous System
nervous_system {
SoulA -> SoulB
SoulA -> SoulB -> SoulC
[SoulA, SoulB] -> SoulC
SoulA -> [SoulB, SoulC]
SoulA -> match {
condition1 => SoulB,
condition2 => SoulC,
_ => silence,
}
}

## Topology (
## Topology (distributed)
## Evolution
evolution {
schedule: 6:00 daily
fitness: some_metric
mutate SoulName.dna {
strategy: gradient(step: 0.1)
survive_if: fitness > 0.5
rollback_if: cost > $0.50
}
}

## Rules:
1. Every file MUST have exactly one world block.
2. Every soul MUST have a mind declaration.
3. Every soul MUST have a heal block.
4. Every speak/listen must reference a defined message type.
5. Every message field must have a type.
6. Nervous system references must point to defined souls.
7. Memory fields must be declared before use in remember statements.
'''

SYSTEM_PROMPT = f"""You are a NOUS language code generator. You translate natural language descriptions of AI agent systems into valid NOUS source code.

{NOUS_REFERENCE}

CRITICAL RULES:
1. Output ONLY valid .nous code. No markdown, no explanations, no backticks.
2. Every soul MUST have: mind, heal block.
3. Every speak/listen MUST reference a defined message type.
4. Use realistic field names and types.
5. Include appropriate senses based on the description.
6. Set reasonable cost ceilings and heartbeat intervals.
7. If the user mentions multiple agents/souls, wire them with nervous_system.
8. Add memory fields for any state the soul needs to track.
9. Add heal blocks with retry for timeout and api_error at minimum.
10. Output clean, production-ready .nous code.
"""


@dataclass
class GenerationResult:
    ok: bool
    source: str = ""
    world_name: str = ""
    soul_count: int = 0
    message_count: int = 0
    route_count: int = 0
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    attempts: int = 0
    error: str = ""


def _call_llm_local(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    try:
        import httpx
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        data = resp.json()
        if "content" in data and data["content"]:
            return data["content"][0].get("text", "")
        return ""
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        return ""


def _get_api_key() -> str:
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        key_file = Path.home() / ".anthropic" / "api_key"
        if key_file.exists():
            key = key_file.read_text().strip()
    return key


def _extract_nous_code(raw: str) -> str:
    code = raw.strip()
    if code.startswith("```"):
        lines = code.splitlines()
        start = 1
        end = len(lines)
        for i in range(1, len(lines)):
            if lines[i].strip() == "```":
                end = i
                break
        code = "\n".join(lines[start:end])
    code = re.sub(r'^```\w*\n', '', code)
    code = re.sub(r'\n```$', '', code)
    return code.strip()


def _validate_generated(source: str) -> tuple[bool, list[str], list[str], dict[str, Any]]:
    try:
        from parser import parse_nous
        program = parse_nous(source)
    except Exception as e:
        return False, [f"Parse error: {e}"], [], {}

    from validator import validate_program
    result = validate_program(program)
    errors = [f"{e.code}: {e.message}" for e in result.errors]
    warnings = [f"{w.code}: {w.message}" for w in result.warnings]

    info = {
        "world": program.world.name if program.world else "Unknown",
        "souls": len(program.souls),
        "messages": len(program.messages),
        "routes": len(program.nervous_system.routes) if program.nervous_system else 0,
    }

    return result.ok, errors, warnings, info


def generate_from_description(
    description: str,
    max_attempts: int = 3,
    use_llm: bool = True,
) -> GenerationResult:
    if not use_llm or not _get_api_key():
        return _generate_template(description)

    result = GenerationResult(ok=False)

    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt

        if attempt == 1:
            prompt = f"Create a NOUS program for the following:\n\n{description}"
        else:
            error_context = "\n".join(result.validation_errors)
            prompt = (
                f"The previous NOUS code had these errors:\n{error_context}\n\n"
                f"Fix the code. Original request:\n{description}\n\n"
                f"Previous code:\n{result.source}"
            )

        raw = _call_llm_local(prompt)
        if not raw:
            result.error = "LLM returned empty response"
            continue

        source = _extract_nous_code(raw)
        if not source:
            result.error = "Could not extract NOUS code from response"
            continue

        result.source = source
        ok, errors, warnings, info = _validate_generated(source)
        result.validation_errors = errors
        result.validation_warnings = warnings
        result.world_name = info.get("world", "Unknown")
        result.soul_count = info.get("souls", 0)
        result.message_count = info.get("messages", 0)
        result.route_count = info.get("routes", 0)

        if ok:
            result.ok = True
            return result

    return result


def _generate_template(description: str) -> GenerationResult:
    desc_lower = description.lower()
    world_name = _extract_world_name(description)
    souls = _extract_souls(description)
    messages = _extract_messages(souls)

    lines: list[str] = []
    lines.append(f"world {world_name} {{")
    lines.append("    law cost_ceiling = $0.50 per cycle")
    lines.append("    heartbeat = 5m")
    lines.append("}")
    lines.append("")

    for msg_name, msg_fields in messages:
        lines.append(f"message {msg_name} {{")
        for fname, ftype, fdefault in msg_fields:
            if fdefault:
                lines.append(f"    {fname}: {ftype} = {fdefault}")
            else:
                lines.append(f"    {fname}: {ftype}")
        lines.append("}")
        lines.append("")

    has_http = any(w in desc_lower for w in ["api", "http", "web", "fetch", "scrape", "url", "endpoint"])
    has_data = any(w in desc_lower for w in ["data", "database", "db", "store", "save"])

    for i, (soul_name, soul_role) in enumerate(souls):
        senses: list[str] = []
        if has_http or i == 0:
            senses.append("http_get")
        if has_data or "write" in soul_role.lower() or "execute" in soul_role.lower():
            senses.append("http_post")

        tier = "Tier0A"
        if "simple" in soul_role.lower() or "basic" in soul_role.lower():
            tier = "Tier2"

        lines.append(f"soul {soul_name} {{")
        lines.append(f"    mind: claude-sonnet @ {tier}")
        if senses:
            lines.append(f"    senses: [{', '.join(senses)}]")
        lines.append("    memory {")
        lines.append("        cycle_count: int = 0")
        lines.append("    }")
        lines.append("    instinct {")
        lines.append("        remember cycle_count += 1")

        if i < len(souls) - 1 and messages:
            msg_name = messages[min(i, len(messages)-1)][0]
            msg_fields = messages[min(i, len(messages)-1)][1]
            args = ", ".join(f'{f[0]}: ""' if f[1] == "string" else f"{f[0]}: 0" for f in msg_fields[:3])
            lines.append(f"        speak {msg_name}({args})")

        if i > 0 and messages:
            prev_soul = souls[i-1][0]
            msg_name = messages[min(i-1, len(messages)-1)][0]
            lines.append(f"        let input = listen {prev_soul}::{msg_name}")

        lines.append("    }")
        lines.append("    heal {")
        lines.append("        on timeout => retry(3, exponential)")
        lines.append("        on api_error => retry(2, exponential)")
        lines.append("    }")
        lines.append("}")
        lines.append("")

    if len(souls) > 1:
        lines.append("nervous_system {")
        for i in range(len(souls) - 1):
            lines.append(f"    {souls[i][0]} -> {souls[i+1][0]}")
        lines.append("}")

    source = "\n".join(lines)

    ok, errors, warnings, info = _validate_generated(source)

    return GenerationResult(
        ok=ok,
        source=source,
        world_name=info.get("world", world_name),
        soul_count=info.get("souls", len(souls)),
        message_count=info.get("messages", len(messages)),
        route_count=info.get("routes", 0),
        validation_errors=errors,
        validation_warnings=warnings,
        attempts=1,
    )


def _extract_world_name(desc: str) -> str:
    words = re.findall(r'[A-Z][a-z]+', desc)
    if len(words) >= 2:
        return words[0] + words[1]
    if words:
        return words[0] + "World"
    clean = re.sub(r'[^a-zA-Z]', '', desc.split()[0] if desc.split() else "My")
    return clean.capitalize() + "World"


def _extract_souls(desc: str) -> list[tuple[str, str]]:
    desc_lower = desc.lower()
    soul_patterns = [
        (r'\b(?:agent|soul|worker|bot)\s+(?:called|named)\s+(\w+)', None),
        (r'\b(\w+)\s+(?:agent|soul|worker|bot)\b', None),
    ]

    found: list[tuple[str, str]] = []
    for pattern, _ in soul_patterns:
        for m in re.finditer(pattern, desc, re.IGNORECASE):
            name = m.group(1).capitalize()
            if name.lower() not in ("the", "a", "an", "this", "that", "my", "your", "one", "each"):
                found.append((name, desc))

    if not found:
        role_keywords = {
            "scan": "Scanner", "monitor": "Monitor", "watch": "Watcher",
            "analyz": "Analyzer", "process": "Processor", "evaluat": "Evaluator",
            "execut": "Executor", "act": "Actor", "write": "Writer",
            "read": "Reader", "fetch": "Fetcher", "collect": "Collector",
            "filter": "Filter", "transform": "Transformer", "route": "Router",
            "alert": "Alerter", "notify": "Notifier", "report": "Reporter",
            "trade": "Trader", "invest": "Investor", "price": "PriceTracker",
            "news": "NewsScanner", "weather": "WeatherMonitor",
            "email": "EmailHandler", "chat": "ChatBot",
            "summariz": "Summarizer", "translat": "Translator",
        }
        for keyword, soul_name in role_keywords.items():
            if keyword in desc_lower:
                found.append((soul_name, keyword))

    if not found:
        found = [("Agent", "general purpose agent")]

    if len(found) == 1:
        name = found[0][0]
        if any(w in desc_lower for w in ["pipeline", "chain", "process", "then", "and then"]):
            found = [
                (f"{name}Input", "input stage"),
                (f"{name}Logic", "processing stage"),
                (f"{name}Output", "output stage"),
            ]

    return found


def _extract_messages(souls: list[tuple[str, str]]) -> list[tuple[str, list[tuple[str, str, str]]]]:
    messages: list[tuple[str, list[tuple[str, str, str]]]] = []
    for i in range(len(souls) - 1):
        src_name = souls[i][0]
        msg_name = f"{src_name}Output"
        fields = [
            ("data", "string", '""'),
            ("timestamp", "float", "0.0"),
            ("confidence", "float", "0.0"),
        ]
        messages.append((msg_name, fields))
    return messages


def print_generation_report(result: GenerationResult) -> None:
    print(f"\n  ═══ NOUS Natural Language Generation ═══")
    if result.ok:
        print(f"  Status:   GENERATED ✓")
    else:
        print(f"  Status:   FAILED ✗")
    print(f"  World:    {result.world_name}")
    print(f"  Souls:    {result.soul_count}")
    print(f"  Messages: {result.message_count}")
    print(f"  Routes:   {result.route_count}")
    print(f"  Attempts: {result.attempts}")
    if result.validation_errors:
        print(f"  Errors:")
        for e in result.validation_errors:
            print(f"    ✗ {e}")
    if result.validation_warnings:
        print(f"  Warnings:")
        for w in result.validation_warnings:
            print(f"    ⚠ {w}")
    if result.error:
        print(f"  Error: {result.error}")
