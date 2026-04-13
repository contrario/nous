"""
NOUS Noesis CLI — nous noesis <command>
========================================
Standalone CLI for Noesis lattice management.

Commands:
    nous noesis stats              Show lattice statistics
    nous noesis gaps               Show knowledge gaps
    nous noesis topics             Discover topics
    nous noesis evolve             Run evolution cycle
    nous noesis search "query"     Search lattice
    nous noesis think "query"      Think (with oracle if needed)
    nous noesis feeds              Suggest feeds for weak topics
    nous noesis weaning            Show oracle weaning status
    nous noesis export [--json]    Export lattice summary

Can run standalone: python3 noesis_cli_noesis.py <command> [args]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional


DEFAULT_LATTICE = "noesis_lattice.json"


def _load_engine(lattice_path: str = DEFAULT_LATTICE) -> Any:
    sys.path.insert(0, str(Path(__file__).parent))
    from noesis_engine import NoesisEngine

    engine = NoesisEngine()
    lp = Path(lattice_path)
    if lp.exists():
        engine.load(lp)
        engine.init_autofeeding()
    else:
        print(f"Warning: lattice not found at {lp}", file=sys.stderr)
    return engine


def cmd_noesis_stats(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)
    lattice = engine.lattice

    atom_count = len(lattice.atoms)
    concept_count = len(lattice.concepts) if hasattr(lattice, "concepts") else 0
    relation_count = len(lattice.relations) if hasattr(lattice, "relations") else 0

    sources: dict[str, int] = {}
    levels: dict[int, int] = {}
    total_confidence = 0.0
    total_usage = 0

    for atom in lattice.atoms.values():
        a = atom if isinstance(atom, dict) else atom.__dict__ if hasattr(atom, "__dict__") else {}
        src = a.get("source", a.get("_source", "unknown"))
        if src:
            tag = src.split(":")[0] if ":" in str(src) else str(src)
            sources[tag] = sources.get(tag, 0) + 1
        lvl = a.get("level", a.get("_level", 0))
        levels[lvl] = levels.get(lvl, 0) + 1
        total_confidence += a.get("confidence", a.get("_confidence", 0.5))
        total_usage += a.get("usage", a.get("_usage", 0))

    avg_confidence = total_confidence / max(1, atom_count)

    print(f"═══ ΝΟΗΣΗ — Lattice Statistics ═══")
    print(f"")
    print(f"  Atoms:      {atom_count}")
    print(f"  Concepts:   {concept_count}")
    print(f"  Relations:  {relation_count}")
    print(f"  Avg conf:   {avg_confidence:.3f}")
    print(f"  Total usage: {total_usage}")
    print(f"")

    if sources:
        print(f"  Sources ({len(sources)}):")
        for src, count in sorted(sources.items(), key=lambda x: -x[1])[:15]:
            print(f"    {src}: {count}")

    if levels:
        print(f"")
        print(f"  Levels:")
        for lvl in sorted(levels):
            print(f"    Level {lvl}: {levels[lvl]}")

    if hasattr(engine, "hardening_status"):
        hs = engine.hardening_status()
        today = hs.get("today", {})
        if today:
            print(f"")
            print(f"  Today:")
            print(f"    Queries:  {today.get('queries', 0)}")
            print(f"    Autonomy: {today.get('autonomy', 0)}%")

    return 0


def cmd_noesis_gaps(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not hasattr(engine, "knowledge_gaps"):
        print("Knowledge gaps not available (Phase 5 not loaded)")
        return 1

    gaps = engine.knowledge_gaps(limit=args.limit)
    if not gaps:
        print("No knowledge gaps found.")
        return 0

    print(f"═══ ΝΟΗΣΗ — Knowledge Gaps ═══")
    print(f"")
    for i, gap in enumerate(gaps, 1):
        query = gap.get("query", gap) if isinstance(gap, dict) else str(gap)
        score = gap.get("score", 0) if isinstance(gap, dict) else 0
        print(f"  {i}. [{score:.2f}] {query}")

    return 0


def cmd_noesis_topics(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not hasattr(engine, "discover_topics"):
        print("Topic discovery not available (Phase 5 not loaded)")
        return 1

    data = engine.discover_topics()
    if not data:
        print("No topics discovered.")
        return 0

    if isinstance(data, dict):
        total = data.get("total_topics", 0)
        strong = data.get("strong_topics", [])
        weak = data.get("weak_topics", [])
        all_topics = data.get("all_topics", [])
        sources = data.get("sources", {})
    else:
        total = len(data)
        strong, weak, all_topics, sources = [], [], [], {}

    print(f"═══ ΝΟΗΣΗ — Topics ({total} total) ═══")
    print(f"  Atoms: {data.get('total_atoms', '?')}")
    print(f"")

    if strong:
        print(f"  Strong ({len(strong)}):")
        for t in strong[:15]:
            name = t.get("topic", "?")
            strength = t.get("strength", 0)
            atoms = t.get("atoms", 0)
            print(f"    {name}: {strength:.1f} ({atoms} atoms)")

    if weak:
        print(f"")
        print(f"  Weak ({len(weak)}):")
        for t in weak[:10]:
            name = t.get("topic", "?")
            strength = t.get("strength", 0)
            atoms = t.get("atoms", 0)
            print(f"    {name}: {strength:.1f} ({atoms} atoms)")

    if sources:
        print(f"")
        print(f"  Sources ({len(sources)}):")
        for src, count in sorted(sources.items(), key=lambda x: -x[1])[:10]:
            print(f"    {src}: {count}")

    return 0


def cmd_noesis_evolve(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not hasattr(engine, "evolve"):
        print("Evolution not available")
        return 1

    atoms_before = len(engine.lattice.atoms)
    t0 = time.time()

    result = engine.evolve()

    elapsed = time.time() - t0
    atoms_after = len(engine.lattice.atoms)

    print(f"═══ ΝΟΗΣΗ — Evolution ═══")
    print(f"")
    print(f"  Duration: {elapsed:.2f}s")
    print(f"  Atoms before: {atoms_before}")
    print(f"  Atoms after:  {atoms_after}")
    print(f"  Pruned: {atoms_before - atoms_after}")

    if hasattr(result, "merged"):
        print(f"  Merged: {result.merged}")
    if hasattr(result, "reinforced"):
        print(f"  Reinforced: {result.reinforced}")

    if args.save:
        lp = Path(args.lattice)
        engine.save(lp)
        print(f"  Saved: {lp}")

    return 0


def cmd_noesis_search(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not args.query:
        print("Usage: nous noesis search 'query'")
        return 1

    if not hasattr(engine, "lattice") or not hasattr(engine.lattice, "atoms"):
        print("Lattice not loaded")
        return 1

    from noesis_engine import Resonator
    resonator = Resonator()
    results = resonator.resonate(args.query, engine.lattice, top_k=args.top_k)

    print(f"═══ ΝΟΗΣΗ — Search: {args.query} ═══")
    print(f"")

    if not results:
        print("  No results found.")
        return 0

    for i, item in enumerate(results[:args.top_k], 1):
        if isinstance(item, tuple):
            atom, score = item
        else:
            atom, score = item, 0.0
        template = getattr(atom, "template", getattr(atom, "_template", str(atom)[:100]))
        print(f"  {i}. [{score:.3f}] {template[:120]}")

    return 0


def cmd_noesis_think(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not args.query:
        print("Usage: nous noesis think 'query'")
        return 1

    t0 = time.time()
    result = engine.think(args.query)
    elapsed = time.time() - t0

    print(f"═══ ΝΟΗΣΗ — Think: {args.query} ═══")
    print(f"")

    if result:
        print(f"  Score:    {getattr(result, 'top_score', 0):.3f}")
        print(f"  Oracle:   {'Yes' if getattr(result, 'used_oracle', False) else 'No'}")
        print(f"  Latency:  {elapsed*1000:.1f}ms")
        print(f"")
        response = getattr(result, "response", str(result))
        print(f"  Response:")
        for line in str(response).split("\n"):
            print(f"    {line}")
    else:
        print("  No result.")

    return 0


def cmd_noesis_feeds(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not hasattr(engine, "suggest_feeds"):
        print("Feed suggestions not available (Phase 5 not loaded)")
        return 1

    feeds = engine.suggest_feeds()
    if not feeds:
        print("No feed suggestions.")
        return 0

    print(f"═══ ΝΟΗΣΗ — Feed Suggestions ═══")
    print(f"")
    for f in feeds:
        topic = f.get("topic", "?")
        source = f.get("source", "?")
        query = f.get("query", "")
        print(f"  {topic}: {source} → {query}")

    return 0


def cmd_noesis_weaning(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    if not hasattr(engine, "weaning_status"):
        print("Weaning status not available (Phase 5 not loaded)")
        return 1

    status = engine.weaning_status()
    print(f"═══ ΝΟΗΣΗ — Oracle Weaning ═══")
    print(f"")
    for k, v in status.items():
        print(f"  {k}: {v}")

    return 0


def cmd_noesis_export(args: argparse.Namespace) -> int:
    engine = _load_engine(args.lattice)

    atom_count = len(engine.lattice.atoms)
    concept_count = len(engine.lattice.concepts) if hasattr(engine.lattice, "concepts") else 0

    data = {
        "atoms": atom_count,
        "concepts": concept_count,
        "lattice_path": args.lattice,
    }

    if hasattr(engine, "weaning_status"):
        data["weaning"] = engine.weaning_status()
    if hasattr(engine, "curiosity_stats"):
        data["curiosity"] = engine.curiosity_stats()

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(f"═══ ΝΟΗΣΗ — Export ═══")
        for k, v in data.items():
            print(f"  {k}: {v}")

    return 0


def build_noesis_parser(subparsers: Any = None) -> argparse.ArgumentParser:
    if subparsers:
        noesis_parser = subparsers.add_parser("noesis", help="Noesis lattice management")
    else:
        noesis_parser = argparse.ArgumentParser(
            prog="nous noesis",
            description="Noesis Lattice Management CLI",
        )

    noesis_parser.add_argument("--lattice", default=DEFAULT_LATTICE, help="Lattice file path")

    sub = noesis_parser.add_subparsers(dest="noesis_command")

    sub.add_parser("stats", help="Lattice statistics")

    p = sub.add_parser("gaps", help="Knowledge gaps")
    p.add_argument("--limit", type=int, default=10)

    sub.add_parser("topics", help="Discover topics")

    p = sub.add_parser("evolve", help="Run evolution")
    p.add_argument("--save", action="store_true")

    p = sub.add_parser("search", help="Search lattice")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--top-k", type=int, default=10)

    p = sub.add_parser("think", help="Think (with oracle)")
    p.add_argument("query", nargs="?", default="")

    sub.add_parser("feeds", help="Suggest feeds")
    sub.add_parser("weaning", help="Oracle weaning status")

    p = sub.add_parser("export", help="Export summary")
    p.add_argument("--json", action="store_true")

    return noesis_parser


def cmd_noesis(args: argparse.Namespace) -> int:
    commands = {
        "stats": cmd_noesis_stats,
        "gaps": cmd_noesis_gaps,
        "topics": cmd_noesis_topics,
        "evolve": cmd_noesis_evolve,
        "search": cmd_noesis_search,
        "think": cmd_noesis_think,
        "feeds": cmd_noesis_feeds,
        "weaning": cmd_noesis_weaning,
        "export": cmd_noesis_export,
    }

    subcmd = getattr(args, "noesis_command", None)
    if not subcmd:
        print("Usage: nous noesis <command>")
        print("Commands: stats, gaps, topics, evolve, search, think, feeds, weaning, export")
        return 1

    if subcmd not in commands:
        print(f"Unknown command: {subcmd}")
        return 1

    return commands[subcmd](args)


def main() -> int:
    parser = build_noesis_parser()
    args = parser.parse_args()
    return cmd_noesis(args)


if __name__ == "__main__":
    sys.exit(main())
