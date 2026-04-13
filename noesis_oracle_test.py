"""
Noesis Oracle Test — Hybrid Thinking Demo
===========================================
Demonstrates:
1. Ask something Noesis knows → answers from lattice (0 cost)
2. Ask something Noesis doesn't know → asks oracle, learns, answers
3. Ask the SAME thing again → answers from lattice (0 cost)

This is the core innovation: gradual autonomy.
"""
from __future__ import annotations

import sys
from pathlib import Path

from noesis_engine import NoesisEngine
from noesis_oracle import create_oracle_fn

LATTICE_PATH = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")


def main() -> None:
    print("╔═══════════════════════════════════════════════╗")
    print("║  Νόηση + Χρησμός — Hybrid Thinking Test       ║")
    print("╚═══════════════════════════════════════════════╝\n")

    oracle_fn, oracle = create_oracle_fn()

    available = oracle.stats["available_tiers"]
    if not available:
        print("  ✗ No oracle tiers available. Check API keys in .env")
        print("  Required: OPENROUTER_API_KEY or ANTHROPIC_API_KEY")
        sys.exit(1)
    print(f"  Oracle tiers: {', '.join(available)}\n")

    engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.3)
    if LATTICE_PATH.exists():
        loaded = engine.load(LATTICE_PATH)
        print(f"  Loaded {loaded} atoms from lattice\n")

    print("═══ Test 1: Known question (from lattice) ═══\n")
    r1 = engine.think("What is the Sun?", use_oracle=True)
    print(f"  Q: What is the Sun?")
    print(f"  A: {r1.response[:200]}")
    print(f"  Oracle used: {r1.oracle_used} | Score: {r1.top_score:.3f} | {r1.elapsed_ms:.1f}ms\n")

    print("═══ Test 2: Unknown question (oracle needed) ═══\n")
    r2 = engine.think("What is quantum entanglement?", use_oracle=True)
    print(f"  Q: What is quantum entanglement?")
    print(f"  A: {r2.response[:300]}")
    print(f"  Oracle used: {r2.oracle_used} | Score: {r2.top_score:.3f} | {r2.elapsed_ms:.1f}ms\n")

    print("═══ Test 3: Same question again (should use lattice now) ═══\n")
    r3 = engine.think("What is quantum entanglement?", use_oracle=True)
    print(f"  Q: What is quantum entanglement?")
    print(f"  A: {r3.response[:300]}")
    print(f"  Oracle used: {r3.oracle_used} | Score: {r3.top_score:.3f} | {r3.elapsed_ms:.1f}ms\n")

    print("═══ Test 4: Related question (should partially know) ═══\n")
    r4 = engine.think("How does entanglement relate to quantum computing?", use_oracle=True)
    print(f"  Q: How does entanglement relate to quantum computing?")
    print(f"  A: {r4.response[:300]}")
    print(f"  Oracle used: {r4.oracle_used} | Score: {r4.top_score:.3f} | {r4.elapsed_ms:.1f}ms\n")

    print("═══ Test 5: Greek question (oracle needed) ═══\n")
    r5 = engine.think("Τι είναι η τεχνητή νοημοσύνη;", use_oracle=True)
    print(f"  Q: Τι είναι η τεχνητή νοημοσύνη;")
    print(f"  A: {r5.response[:300]}")
    print(f"  Oracle used: {r5.oracle_used} | Score: {r5.top_score:.3f} | {r5.elapsed_ms:.1f}ms\n")

    engine.save(LATTICE_PATH)
    print(f"  Lattice saved: {engine.lattice.size} atoms\n")

    print("═══ Oracle Statistics ═══\n")
    stats = oracle.stats
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print()

    print("═══ Engine Statistics ═══\n")
    estats = engine.stats()
    for k, v in estats.items():
        print(f"  {k}: {v}")
    print()

    oracle_queries = sum(1 for r in [r1, r2, r3, r4, r5] if r.oracle_used)
    lattice_queries = 5 - oracle_queries
    print("╔═══════════════════════════════════════════════╗")
    print(f"║  Oracle calls:  {oracle_queries}/5                           ║")
    print(f"║  Lattice calls: {lattice_queries}/5 (free, instant)           ║")
    print(f"║  Total cost:    ${stats['total_cost_usd']:.6f}                   ║")
    print(f"║  Lattice size:  {engine.lattice.size} atoms                    ║")
    print("╚═══════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
