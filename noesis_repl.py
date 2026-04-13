"""
Νόηση REPL — Interactive Thinking Shell
=========================================
Commands:
    think <query>       Ask Noesis a question
    learn <text>        Teach Noesis new knowledge
    learn_file <path>   Ingest a text file
    search <query>      Search the lattice for atoms
    evolve              Run evolution (prune + merge)
    stats               Show engine statistics
    inspect <atom_id>   Inspect a specific atom
    save [path]         Save lattice to disk
    load [path]         Load lattice from disk
    reinforce <+|-> <query>  Mark last answer as helpful or not
    mode <compose|reason|direct>  Set response mode
    oracle on|off       Enable/disable oracle (hybrid LLM mode)
    oracle stats        Show oracle statistics
    help                Show this help
    quit                Exit

Usage:
    python3 noesis_repl.py [--lattice path] [--bootstrap path] [--oracle]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from noesis_engine import NoesisEngine


DEFAULT_LATTICE = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")


def print_banner() -> None:
    print()
    print("  ╔═══════════════════════════════════════╗")
    print("  ║  Νόηση (Noesis) — Thinking Shell      ║")
    print("  ║  Type 'help' for commands              ║")
    print("  ╚═══════════════════════════════════════╝")
    print()


def print_help() -> None:
    print("  Commands:")
    print("    think <query>         Ask a question")
    print("    learn <text>          Teach new knowledge")
    print("    learn_file <path>     Ingest a text file")
    print("    search <query>        Search lattice atoms")
    print("    evolve                Prune + merge atoms")
    print("    stats                 Engine statistics")
    print("    inspect <id>          Inspect atom by ID")
    print("    save [path]           Save lattice")
    print("    load [path]           Load lattice")
    print("    reinforce +|- <q>     Feedback on answer")
    print("    mode compose|reason   Set weaving mode")
    print("    oracle on|off         Enable/disable oracle")
    print("    oracle stats          Show oracle stats")
    print("    help                  This help")
    print("    quit                  Exit")
    print()


def run_repl(lattice_path: Path, bootstrap_path: Path | None, use_oracle: bool = False) -> None:
    oracle_obj = None
    oracle_active = False

    if use_oracle:
        try:
            from noesis_oracle import create_oracle_fn
            oracle_fn, oracle_obj = create_oracle_fn()
            engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.3)
            available = oracle_obj.stats["available_tiers"]
            if available:
                oracle_active = True
                print(f"  Oracle: ON ({', '.join(available)})")
            else:
                print("  Oracle: no API keys found, disabled")
                engine = NoesisEngine()
        except ImportError:
            print("  Oracle: noesis_oracle.py not found, disabled")
            engine = NoesisEngine()
    else:
        engine = NoesisEngine()

    if lattice_path.exists():
        loaded = engine.load(lattice_path)
        print(f"  Loaded {loaded} atoms from {lattice_path}")

    if bootstrap_path and bootstrap_path.exists():
        text = bootstrap_path.read_text(encoding="utf-8")
        added = engine.learn(text, source=str(bootstrap_path))
        print(f"  Bootstrapped {added} atoms from {bootstrap_path}")

    current_mode = "compose"

    print_banner()

    while True:
        try:
            prompt = "νόηση[oracle]> " if oracle_active else "νόηση> "
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Αντίο.")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            print("  Αντίο.")
            break

        elif cmd == "help":
            print_help()

        elif cmd == "oracle":
            if arg == "on":
                if oracle_obj is not None:
                    oracle_active = True
                    print("  Oracle: ON\n")
                else:
                    try:
                        from noesis_oracle import create_oracle_fn
                        oracle_fn, oracle_obj = create_oracle_fn()
                        engine.oracle.call_fn = oracle_fn
                        available = oracle_obj.stats["available_tiers"]
                        if available:
                            oracle_active = True
                            print(f"  Oracle: ON ({', '.join(available)})\n")
                        else:
                            print("  Oracle: no API keys found\n")
                    except ImportError:
                        print("  Oracle: noesis_oracle.py not found\n")
            elif arg == "off":
                oracle_active = False
                print("  Oracle: OFF\n")
            elif arg == "stats":
                if oracle_obj:
                    stats = oracle_obj.stats
                    print()
                    for k, v in stats.items():
                        print(f"  {k}: {v}")
                    print()
                else:
                    print("  Oracle not initialized\n")
            else:
                print("  Usage: oracle on|off|stats\n")

        elif cmd == "think":
            if not arg:
                print("  Usage: think <query>")
                continue
            result = engine.think(arg, mode=current_mode, top_k=5, use_oracle=oracle_active)
            print(f"\n  {result.response}\n")
            oracle_tag = " [oracle]" if result.oracle_used else ""
            print(f"  [{result.atoms_matched} atoms | score={result.top_score:.3f} | {result.elapsed_ms:.1f}ms{oracle_tag}]\n")

        elif cmd == "learn":
            if not arg:
                print("  Usage: learn <text>")
                continue
            added = engine.learn(arg, source="repl")
            print(f"  +{added} atoms | lattice: {engine.lattice.size}\n")

        elif cmd == "learn_file":
            if not arg:
                print("  Usage: learn_file <path>")
                continue
            p = Path(arg)
            if not p.exists():
                print(f"  File not found: {p}")
                continue
            text = p.read_text(encoding="utf-8")
            added = engine.learn(text, source=str(p))
            print(f"  +{added} atoms from {p} | lattice: {engine.lattice.size}\n")

        elif cmd == "search":
            if not arg:
                print("  Usage: search <query>")
                continue
            results = engine.search_atoms(arg, top_k=5)
            if not results:
                print("  No atoms found.\n")
                continue
            for sr in results:
                atom = sr["atom"]
                print(f"  [{atom['id'][:12]}] score={sr['score']:.3f} conf={atom['confidence']:.2f}")
                print(f"    patterns: {atom['patterns'][:5]}")
                print(f"    template: {atom['template'][:100]}")
                print()

        elif cmd == "evolve":
            result = engine.evolve()
            print(f"  {result}\n")

        elif cmd == "stats":
            s = engine.stats()
            print()
            for k, v in s.items():
                print(f"  {k}: {v}")
            if oracle_obj:
                print(f"  oracle_active: {oracle_active}")
                ostats = oracle_obj.stats
                print(f"  oracle_total_calls: {ostats['total_calls']}")
                print(f"  oracle_total_cost: ${ostats['total_cost_usd']:.6f}")
            print()

        elif cmd == "inspect":
            if not arg:
                print("  Usage: inspect <atom_id>")
                continue
            result = engine.inspect(arg)
            if result is None:
                matching = [aid for aid in engine.lattice.atoms if aid.startswith(arg)]
                if matching:
                    result = engine.inspect(matching[0])
                else:
                    print(f"  Atom not found: {arg}\n")
                    continue
            if result:
                print()
                for k, v in result.items():
                    print(f"  {k}: {v}")
                print()

        elif cmd == "save":
            path = Path(arg) if arg else lattice_path
            engine.save(path)
            print(f"  Saved {engine.lattice.size} atoms to {path}\n")

        elif cmd == "load":
            path = Path(arg) if arg else lattice_path
            if not path.exists():
                print(f"  File not found: {path}")
                continue
            loaded = engine.load(path)
            print(f"  Loaded {loaded} atoms from {path}\n")

        elif cmd == "reinforce":
            if not arg:
                print("  Usage: reinforce +|- <query>")
                continue
            rparts = arg.split(maxsplit=1)
            if len(rparts) < 2:
                print("  Usage: reinforce + <query> or reinforce - <query>")
                continue
            helpful = rparts[0] == "+"
            engine.reinforce(rparts[1], was_helpful=helpful)
            tag = "positive" if helpful else "negative"
            print(f"  Reinforced ({tag}): {rparts[1]}\n")

        elif cmd == "mode":
            if arg in ("compose", "reason", "direct"):
                current_mode = arg
                print(f"  Mode: {current_mode}\n")
            else:
                print("  Modes: compose, reason, direct\n")

        else:
            result = engine.think(raw, mode=current_mode, top_k=5, use_oracle=oracle_active)
            if result.response:
                print(f"\n  {result.response}\n")
                oracle_tag = " [oracle]" if result.oracle_used else ""
                print(f"  [{result.atoms_matched} atoms | score={result.top_score:.3f} | {result.elapsed_ms:.1f}ms{oracle_tag}]\n")
            else:
                print(f"  Unknown command: {cmd}. Type 'help' for commands.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Νόηση REPL")
    parser.add_argument("--lattice", type=Path, default=DEFAULT_LATTICE)
    parser.add_argument("--bootstrap", type=Path, default=None)
    parser.add_argument("--oracle", action="store_true", help="Enable oracle (hybrid LLM mode)")
    args = parser.parse_args()
    run_repl(args.lattice, args.bootstrap, use_oracle=args.oracle)


if __name__ == "__main__":
    main()
