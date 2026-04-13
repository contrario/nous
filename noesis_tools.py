"""
Noesis NOUS Tools — Sense Wrappers
====================================
These tools make the Noesis engine available as NOUS senses.
Each tool follows the NOUS tool protocol: async execute() -> dict.

Usage in .nous:
    let result = sense noesis_think(query)
    let added = sense noesis_learn(text, source)
    let stats = sense noesis_stats()
    let evolved = sense noesis_evolve()
    let atoms = sense noesis_search(query, top_k)
    sense noesis_save()
    let atom = sense noesis_inspect(atom_id)
    sense noesis_reinforce(query, helpful)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from noesis_engine import NoesisEngine, NoesisSoul

_LATTICE_PATH = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")

_engine: NoesisEngine | None = None


def _get_engine() -> NoesisEngine:
    global _engine
    if _engine is None:
        _engine = NoesisEngine()
        if _LATTICE_PATH.exists():
            _engine.load(_LATTICE_PATH)
    return _engine


async def execute_noesis_think(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    query = params.get("query", params.get("_pos_0", ""))
    mode = params.get("mode", "compose")
    top_k = params.get("top_k", 5)
    use_oracle = params.get("use_oracle", True)
    result = engine.think(query, mode=mode, top_k=top_k, use_oracle=use_oracle)
    return {
        "response": result.response,
        "atoms_matched": result.atoms_matched,
        "score": round(result.top_score, 4),
        "oracle_used": result.oracle_used,
        "elapsed_ms": round(result.elapsed_ms, 2),
    }


async def execute_noesis_learn(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    text = params.get("text", params.get("_pos_0", ""))
    source = params.get("source", params.get("_pos_1", "input"))
    added = engine.learn(text, source=source)
    return {
        "atoms_added": added,
        "lattice_size": engine.lattice.size,
    }


async def execute_noesis_stats(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    return engine.stats()


async def execute_noesis_evolve(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    min_confidence = params.get("min_confidence", 0.1)
    min_usage = params.get("min_usage", 0)
    result = engine.evolve(min_confidence=min_confidence, min_usage=min_usage)
    return {
        "pruned": result.pruned,
        "merged": result.merged,
        "before": result.initial_size,
        "after": result.final_size,
    }


async def execute_noesis_search(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    query = params.get("query", params.get("_pos_0", ""))
    top_k = params.get("top_k", params.get("_pos_1", 5))
    results = engine.search_atoms(query, top_k=top_k)
    return {"results": results, "count": len(results)}


async def execute_noesis_save(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    path = Path(params.get("path", str(_LATTICE_PATH)))
    engine.save(path)
    return {"saved": True, "path": str(path), "atoms": engine.lattice.size}


async def execute_noesis_inspect(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    atom_id = params.get("atom_id", params.get("_pos_0", ""))
    result = engine.inspect(atom_id)
    if result is None:
        return {"error": f"Atom {atom_id} not found"}
    return result


async def execute_noesis_reinforce(params: dict[str, Any]) -> dict[str, Any]:
    engine = _get_engine()
    query = params.get("query", params.get("_pos_0", ""))
    helpful = params.get("helpful", params.get("_pos_1", True))
    engine.reinforce(query, was_helpful=helpful)
    return {"reinforced": True, "query": query, "helpful": helpful}


TOOL_REGISTRY: dict[str, Any] = {
    "noesis_think": execute_noesis_think,
    "noesis_learn": execute_noesis_learn,
    "noesis_stats": execute_noesis_stats,
    "noesis_evolve": execute_noesis_evolve,
    "noesis_search": execute_noesis_search,
    "noesis_save": execute_noesis_save,
    "noesis_inspect": execute_noesis_inspect,
    "noesis_reinforce": execute_noesis_reinforce,
}
