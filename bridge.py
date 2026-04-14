"""
NOUS Bridge — Γέφυρα (Gefyra)
================================
Connects NOUS programs to the live Noosphere ecosystem.
Maps souls → agents, senses → tools, tiers → model configs.
Does NOT modify any existing Noosphere files — read-only analysis + codegen.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, SoulNode, MindNode, Tier

log = logging.getLogger("nous.bridge")

NOOSPHERE_AGENTS_DIR = Path("/opt/aetherlang_agents/agents")
NOOSPHERE_TOOLS_DIR = Path("/opt/aetherlang_agents/tools")
NOOSPHERE_API = "http://localhost:9977"

TIER_MAP: dict[str, dict[str, Any]] = {
    "Tier0A": {
        "provider": "anthropic",
        "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250514"],
        "cost_range": "$0.01-0.30/query",
        "label": "Premium (Anthropic Direct)",
    },
    "Tier0B": {
        "provider": "openai",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "cost_range": "$0.01-0.15/query",
        "label": "Premium Alternate",
    },
    "Tier1": {
        "provider": "openrouter",
        "models": ["deepseek-r1", "deepseek-chat", "xiaomi/mimo-v2-pro"],
        "cost_range": "$0.001-0.01/query",
        "label": "Standard",
    },
    "Tier2": {
        "provider": "openrouter_free",
        "models": ["google/gemini-2.5-flash-lite", "nvidia/nemotron-3-super-120b-a12b:free"],
        "cost_range": "$0.00/query",
        "label": "Free",
    },
    "Groq": {
        "provider": "groq",
        "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
        "base_url": "https://api.groq.com/openai/v1",
        "cost_range": "$0.0001-0.001",
        "label": "Groq (ultra-fast)",
    },
    "Together": {
        "provider": "together",
        "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"],
        "base_url": "https://api.together.xyz/v1",
        "cost_range": "$0.0005-0.002",
        "label": "Together AI",
    },
    "Fireworks": {
        "provider": "fireworks",
        "models": ["accounts/fireworks/models/llama-v3p1-70b-instruct", "accounts/fireworks/models/mixtral-8x22b-instruct"],
        "base_url": "https://api.fireworks.ai/inference/v1",
        "cost_range": "$0.0002-0.001",
        "label": "Fireworks AI (fast)",
    },
    "Cerebras": {
        "provider": "cerebras",
        "models": ["llama3.1-70b", "llama3.1-8b"],
        "base_url": "https://api.cerebras.ai/v1",
        "cost_range": "$0.0001-0.0005",
        "label": "Cerebras (fastest)",
    },
    "Tier3": {
        "provider": "ollama",
        "models": ["gemma3-4b-opt", "qwen3:8b"],
        "cost_range": "$0.00 (local)",
        "label": "Local (Ollama/BitNet)",
    },
}


class NoosphereBridge:
    """Analyzes a NOUS program against the live Noosphere ecosystem."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.available_tools: list[str] = []
        self.available_agents: list[str] = []
        self._scan_noosphere()

    def _scan_noosphere(self) -> None:
        if NOOSPHERE_TOOLS_DIR.exists():
            for f in NOOSPHERE_TOOLS_DIR.glob("*.py"):
                if f.name.startswith("_"):
                    continue
                self.available_tools.append(f.stem)
            log.info(f"Found {len(self.available_tools)} tools in Noosphere")

        if NOOSPHERE_AGENTS_DIR.exists():
            for f in NOOSPHERE_AGENTS_DIR.glob("*.yaml"):
                self.available_agents.append(f.stem)
            for f in NOOSPHERE_AGENTS_DIR.glob("*.toml"):
                self.available_agents.append(f.stem)
            log.info(f"Found {len(self.available_agents)} agents in Noosphere")

    def analyze(self) -> str:
        lines: list[str] = []
        lines.append("═══ NOUS ↔ Noosphere Bridge Analysis ═══")
        lines.append("")

        lines.append(f"Noosphere: {len(self.available_tools)} tools | {len(self.available_agents)} agents")
        lines.append("")

        lines.append("── Soul → Agent Mapping ──")
        for soul in self.program.souls:
            existing = soul.name.lower() in [a.lower() for a in self.available_agents]
            status = "EXISTS" if existing else "NEW"
            tier_info = TIER_MAP.get(soul.mind.tier.value, {}) if soul.mind else {}
            provider = tier_info.get("label", "unknown")
            lines.append(f"  {soul.name}: [{status}] | {soul.mind.model if soul.mind else 'none'} | {provider}")
        lines.append("")

        lines.append("── Sense → Tool Mapping ──")
        all_senses: set[str] = set()
        for soul in self.program.souls:
            all_senses.update(soul.senses)

        matched = 0
        missing = 0
        for sense in sorted(all_senses):
            found = self._find_tool(sense)
            if found:
                matched += 1
                lines.append(f"  {sense}: ✓ → {found}")
            else:
                missing += 1
                lines.append(f"  {sense}: ✗ NOT FOUND — needs implementation")

        lines.append(f"\n  Summary: {matched}/{matched + missing} senses mapped to existing tools")
        lines.append("")

        lines.append("── Tier Cost Analysis ──")
        total_min = 0.0
        total_max = 0.0
        for soul in self.program.souls:
            if soul.mind:
                tier_info = TIER_MAP.get(soul.mind.tier.value, {})
                cost_str = tier_info.get("cost_range", "$0")
                lines.append(f"  {soul.name}: {soul.mind.tier.value} → {cost_str}")

        cost_law = None
        if self.program.world:
            for law in self.program.world.laws:
                if hasattr(law.expr, "amount"):
                    cost_law = law
                    break
        if cost_law:
            lines.append(f"\n  Budget law: {cost_law.name} = ${cost_law.expr.amount}/cycle")
        lines.append("")

        lines.append("── Integration Commands ──")
        lines.append(f"  nous compile gate_alpha.nous -o /opt/aetherlang_agents/nous/output/gate_alpha.py")
        lines.append(f"  nous run gate_alpha.nous")
        lines.append(f"  nous evolve gate_alpha.nous --cycles 5 --save")
        lines.append("")

        if missing > 0:
            lines.append("── Missing Tools (need implementation) ──")
            for sense in sorted(all_senses):
                if not self._find_tool(sense):
                    lines.append(f"  Create: /opt/aetherlang_agents/tools/{sense}.py")
                    lines.append(f"    async def execute(self, **kwargs) -> ToolResult: ...")
            lines.append("")

        lines.append("═══ Bridge Analysis Complete ═══")
        return "\n".join(lines)

    def _find_tool(self, sense_name: str) -> Optional[str]:
        direct = sense_name in self.available_tools
        if direct:
            return f"tools/{sense_name}.py"

        for tool in self.available_tools:
            if sense_name.replace("_", "") == tool.replace("_", ""):
                return f"tools/{tool}.py"

        return None

    def get_soul_config(self, soul_name: str) -> Optional[dict[str, Any]]:
        soul = next((s for s in self.program.souls if s.name == soul_name), None)
        if soul is None:
            return None

        tier_info = TIER_MAP.get(soul.mind.tier.value, {}) if soul.mind else {}

        config = {
            "agent_id": soul_name.lower(),
            "name": soul_name,
            "model": soul.mind.model if soul.mind else "unknown",
            "provider": tier_info.get("provider", "unknown"),
            "tier": soul.mind.tier.value if soul.mind else "Tier2",
            "tools": soul.senses,
            "memory_fields": [f.name for f in soul.memory.fields] if soul.memory else [],
            "dna": {g.name: g.value for g in soul.dna.genes} if soul.dna else {},
            "heal_rules": [r.error_type for r in soul.heal.rules] if soul.heal else [],
        }
        return config

    def generate_agent_yaml(self, soul_name: str) -> Optional[str]:
        config = self.get_soul_config(soul_name)
        if config is None:
            return None

        lines = [
            f"# Auto-generated by NOUS bridge from {soul_name} soul",
            f"agent_id: {config['agent_id']}",
            f"name: {config['name']}",
            f"model: {config['model']}",
            f"provider: {config['provider']}",
            f"tier: {config['tier']}",
            f"",
            f"tools:",
        ]
        for tool in config["tools"]:
            lines.append(f"  - {tool}")

        if config["dna"]:
            lines.append("")
            lines.append("_genesis:")
            lines.append("  genome_version: '1.0.0'")
            lines.append(f"  source: nous/{soul_name}")
            for k, v in config["dna"].items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines)
