"""
NOUS Migration — Μετανάστευση (Metanasteysi)
==============================================
Converts existing Noosphere YAML/TOML agent configs to .nous soul definitions.
Read-only: never modifies original files.

Usage:
    python3 migrate.py /opt/aetherlang_agents/agents/
    python3 migrate.py /opt/aetherlang_agents/agents/greek_tax_advisor.yaml
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional


def _load_yaml(path: Path) -> dict:
    import yaml
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _load_toml(path: Path) -> dict:
    try:
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        import tomli
        with open(path, "rb") as f:
            return tomli.load(f)


def load_agent_config(path: Path) -> Optional[dict]:
    try:
        if path.suffix == ".yaml" or path.suffix == ".yml":
            return _load_yaml(path)
        elif path.suffix == ".toml":
            return _load_toml(path)
    except Exception as e:
        print(f"  Warning: could not load {path.name}: {e}", file=sys.stderr)
    return None


def detect_tier(config: dict) -> str:
    model_raw = config.get("model", config.get("llm", ""))
    model = _extract_model_string(model_raw).lower()
    provider_raw = config.get("provider", "")
    if isinstance(provider_raw, dict):
        provider_raw = provider_raw.get("name", provider_raw.get("provider", ""))
    provider = str(provider_raw).lower()

    if "claude" in model and "anthropic" in provider:
        return "Tier0A"
    if "gpt" in model or "openai" in provider:
        return "Tier0B"
    if "deepseek" in model or "mimo" in model:
        return "Tier1"
    if "gemini" in model and ("free" in provider or "lite" in model):
        return "Tier2"
    if "ollama" in provider or "local" in provider:
        return "Tier3"
    if "free" in provider or "openrouter" in provider:
        return "Tier2"
    return "Tier1"


def _extract_model_string(val: Any) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        for key in ("model", "primary", "name", "id"):
            if key in val and isinstance(val[key], str):
                return val[key]
        for key in ("model", "primary", "name", "id"):
            if key in val:
                return _extract_model_string(val[key])
        return "unknown"
    return str(val)


def _sanitize_model_name(raw: str) -> str:
    raw = raw.strip()
    for ch in ("'", '"', "{", "}", "[", "]", ","):
        raw = raw.replace(ch, "")
    raw = raw.split("/")[-1]
    raw = raw.strip()
    parts = raw.split("-")
    clean = []
    for p in parts:
        p = p.strip().replace(":", "-")
        if not p:
            continue
        if p[0].isalpha() or (clean and p[0].isdigit()):
            clean.append(p)
    return "-".join(clean) if clean else "unknown"


def detect_model_name(config: dict) -> str:
    model_raw = config.get("model", config.get("llm", "unknown"))
    model_str = _extract_model_string(model_raw)
    return _sanitize_model_name(model_str)


def extract_tools(config: dict) -> list[str]:
    tools = config.get("tools", [])
    if isinstance(tools, list):
        result = []
        for t in tools:
            if isinstance(t, str):
                result.append(t)
            elif isinstance(t, dict):
                result.append(t.get("name", t.get("id", str(t))))
        return result
    return []


def config_to_soul(config: dict, agent_id: str) -> str:
    name = _to_pascal(agent_id)
    model = detect_model_name(config)
    tier = detect_tier(config)
    tools = extract_tools(config)
    temperature = config.get("temperature", config.get("temperature_default", 0.1))
    if not isinstance(temperature, (int, float)):
        temperature = 0.1
    max_tokens = config.get("max_tokens", 1500)
    if not isinstance(max_tokens, (int, float)):
        max_tokens = 1500
    max_cost = config.get("max_cost", 0.50)
    max_steps = config.get("max_steps", 15)

    genesis = config.get("_genesis", {})
    genome_version = genesis.get("genome_version", "1.0.0")

    lines = []
    lines.append(f"soul {name} {{")
    lines.append(f"    mind: {model} @ {tier}")

    if tools:
        tool_str = ", ".join(tools[:10])
        lines.append(f"    senses: [{tool_str}]")

    lines.append("")
    lines.append("    memory {")
    lines.append("        query_count: int = 0")
    lines.append("        last_result: string = \"\"")
    lines.append("    }")

    lines.append("")
    lines.append("    instinct {")
    lines.append("        # migrated from YAML — implement instinct logic")
    lines.append("        remember query_count += 1")
    lines.append("    }")

    lines.append("")
    lines.append("    dna {")
    lines.append(f"        temperature: {temperature} ~ [0.0, 1.0]")
    lines.append(f"        max_tokens: {max_tokens} ~ [500, 8000]")
    lines.append("    }")

    lines.append("")
    lines.append("    heal {")
    lines.append("        on timeout => retry(3, exponential)")
    lines.append("        on api_error => retry(2, exponential)")
    lines.append("        on budget_exceeded => hibernate until next_cycle")
    lines.append("    }")

    lines.append("}")
    return "\n".join(lines)


def migrate_file(path: Path) -> Optional[str]:
    config = load_agent_config(path)
    if config is None:
        return None

    agent_id = config.get("agent_id", path.stem)
    return config_to_soul(config, agent_id)


def migrate_directory(agents_dir: Path, output_path: Optional[Path] = None) -> str:
    configs = list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml")) + list(agents_dir.glob("*.toml"))
    configs.sort(key=lambda p: p.stem)

    if not configs:
        return f"No agent configs found in {agents_dir}"

    souls: list[str] = []
    skipped: list[str] = []

    for cfg_path in configs:
        soul = migrate_file(cfg_path)
        if soul:
            souls.append(soul)
        else:
            skipped.append(cfg_path.name)

    world_name = agents_dir.parent.name.replace("-", "_").replace(" ", "_")
    world_name = _to_pascal(world_name)

    lines = [
        f"# {world_name}.nous — Auto-migrated from {len(souls)} YAML/TOML configs",
        f"# Generated by NOUS Migration Tool",
        f"# Source: {agents_dir}",
        "",
        f"world {world_name} {{",
        "    law CostCeiling = $0.50 per cycle",
        "    law MaxLatency = 90s",
        "    heartbeat = 5m",
        "}",
        "",
    ]

    for soul in souls:
        lines.append(soul)
        lines.append("")

    result = "\n".join(lines)

    if output_path:
        output_path.write_text(result, encoding="utf-8")

    summary = [
        f"═══ NOUS Migration Report ═══",
        f"Source:    {agents_dir}",
        f"Migrated: {len(souls)} agents → souls",
        f"Skipped:  {len(skipped)} ({', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''})",
        f"Output:   {output_path or 'stdout'}",
        f"Lines:    {len(result.splitlines())}",
    ]

    return "\n".join(summary) + "\n\n" + result


def _to_pascal(name: str) -> str:
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 migrate.py <path-to-agents-dir-or-file> [-o output.nous]")
        return 1

    target = Path(sys.argv[1])
    output = None
    if "-o" in sys.argv:
        idx = sys.argv.index("-o")
        if idx + 1 < len(sys.argv):
            output = Path(sys.argv[idx + 1])

    if target.is_dir():
        result = migrate_directory(target, output)
        print(result)
    elif target.is_file():
        soul = migrate_file(target)
        if soul:
            if output:
                output.write_text(soul, encoding="utf-8")
                print(f"Written: {output}")
            else:
                print(soul)
        else:
            print(f"Could not migrate: {target}")
            return 1
    else:
        print(f"Not found: {target}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
