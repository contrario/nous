"""
Νόηση Feeder — Τροφοδοσία (Trophodosía)
==========================================
Bulk knowledge ingestion + auto-learning.

Usage:
    python3 noesis_feeder.py                     # Feed all known sources
    python3 noesis_feeder.py --file /path/to.txt # Feed single file
    python3 noesis_feeder.py --dir /path/to/dir  # Feed directory
    python3 noesis_feeder.py --web "query"       # Learn from web search
    python3 noesis_feeder.py --stats             # Show lattice stats

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from noesis_engine import NoesisEngine

log = logging.getLogger("nous.feeder")

LATTICE_PATH = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")

NOUS_DIR = Path("/opt/aetherlang_agents/nous")

KNOWN_SOURCES: list[dict[str, Any]] = [
    {"path": NOUS_DIR / "README.md", "name": "NOUS README"},
    {"path": NOUS_DIR / "NOUS_COMPLETE_HANDOFF.md", "name": "NOUS Complete Handoff"},
    {"path": NOUS_DIR / "NOUS_SESSION_1_HANDOFF.md", "name": "Session 1 Handoff"},
    {"path": NOUS_DIR / "NOUS_SESSION_2_HANDOFF.md", "name": "Session 2 Handoff"},
    {"path": NOUS_DIR / "NOUS_SESSION_3_HANDOFF.md", "name": "Session 3 Handoff"},
    {"path": NOUS_DIR / "gate_alpha.nous", "name": "Gate Alpha Source"},
    {"path": NOUS_DIR / "noesis_alpha.nous", "name": "Noesis Alpha Source"},
]

TEXT_EXTENSIONS: set[str] = {".md", ".txt", ".nous", ".py", ".json", ".toml", ".yaml", ".yml", ".csv", ".rst"}

MAX_FILE_SIZE: int = 500_000


def feed_file(engine: NoesisEngine, path: Path, name: str = "") -> int:
    if not path.exists():
        log.warning(f"File not found: {path}")
        return 0
    if path.stat().st_size > MAX_FILE_SIZE:
        log.warning(f"File too large (>{MAX_FILE_SIZE}B): {path}")
        return 0
    if path.suffix not in TEXT_EXTENSIONS:
        log.warning(f"Unsupported extension: {path.suffix}")
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        log.warning(f"Cannot read as UTF-8: {path}")
        return 0
    if len(text.strip()) < 20:
        return 0
    source = name or str(path)
    added = engine.learn(text, source=source)
    return added


def feed_directory(engine: NoesisEngine, directory: Path, recursive: bool = True) -> tuple[int, int]:
    total_files = 0
    total_atoms = 0
    pattern = "**/*" if recursive else "*"
    for path in sorted(directory.glob(pattern)):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        if "__pycache__" in str(path):
            continue
        added = feed_file(engine, path)
        if added > 0:
            total_files += 1
            total_atoms += added
            print(f"  +{added:4d} atoms | {path.name}")
    return total_files, total_atoms


def feed_web(engine: NoesisEngine, query: str) -> int:
    try:
        from noesis_oracle import create_oracle_fn
        oracle_fn, oracle = create_oracle_fn()
    except ImportError:
        print("  Error: noesis_oracle.py not found")
        return 0

    available = oracle.stats["available_tiers"]
    if not available:
        print("  Error: no API keys available")
        return 0

    prompts = [
        f"Give me a comprehensive factual summary about: {query}",
        f"What are the key facts and details about: {query}",
        f"Explain the following topic in detail: {query}",
    ]

    total_added = 0
    for i, prompt in enumerate(prompts):
        response = oracle_fn(prompt)
        if response:
            added = engine.learn(response, source=f"web:{query}:{i}")
            total_added += added
            print(f"  +{added:4d} atoms | query #{i+1}")

    return total_added


def feed_known_sources(engine: NoesisEngine) -> tuple[int, int]:
    total_files = 0
    total_atoms = 0
    for source in KNOWN_SOURCES:
        path = source["path"]
        name = source["name"]
        if not path.exists():
            continue
        added = feed_file(engine, path, name=name)
        if added > 0:
            total_files += 1
            total_atoms += added
            print(f"  +{added:4d} atoms | {name}")
    return total_files, total_atoms


def main() -> None:
    parser = argparse.ArgumentParser(description="Νόηση Feeder — Bulk Knowledge Ingestion")
    parser.add_argument("--file", type=Path, help="Feed a single file")
    parser.add_argument("--dir", type=Path, help="Feed all text files in directory")
    parser.add_argument("--web", type=str, help="Learn about topic from web/oracle")
    parser.add_argument("--stats", action="store_true", help="Show lattice statistics")
    parser.add_argument("--lattice", type=Path, default=LATTICE_PATH)
    parser.add_argument("--recursive", action="store_true", default=True)
    args = parser.parse_args()

    engine = NoesisEngine()
    if args.lattice.exists():
        loaded = engine.load(args.lattice)
        print(f"  Loaded {loaded} atoms from {args.lattice}")
    else:
        print(f"  Starting with empty lattice")

    if args.stats:
        print()
        s = engine.stats()
        for k, v in s.items():
            print(f"  {k}: {v}")
        print()
        return

    print()
    t0 = time.perf_counter()
    total_files = 0
    total_atoms = 0

    if args.file:
        print(f"═══ Feeding file: {args.file} ═══\n")
        added = feed_file(engine, args.file)
        total_files = 1
        total_atoms = added
        print(f"  +{added} atoms")

    elif args.dir:
        print(f"═══ Feeding directory: {args.dir} ═══\n")
        total_files, total_atoms = feed_directory(engine, args.dir, recursive=args.recursive)

    elif args.web:
        print(f"═══ Learning from oracle: {args.web} ═══\n")
        total_atoms = feed_web(engine, args.web)
        total_files = 1

    else:
        print(f"═══ Feeding all known sources ═══\n")
        total_files, total_atoms = feed_known_sources(engine)

    elapsed = time.perf_counter() - t0

    before_evo = engine.lattice.size
    evo = engine.evolve(min_confidence=0.1, min_usage=0)

    engine.save(args.lattice)

    print(f"\n═══ Summary ═══\n")
    print(f"  Files processed: {total_files}")
    print(f"  New atoms: {total_atoms}")
    print(f"  Evolution: {evo.pruned} pruned, {evo.merged} merged")
    print(f"  Lattice: {before_evo} → {engine.lattice.size} atoms")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Saved to: {args.lattice}")
    print()


if __name__ == "__main__":
    main()
