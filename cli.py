#!/usr/bin/env python3
"""
NOUS CLI — Νοῦς Command Line Interface v1.1
=============================================
Usage:
    nous compile <file.nous> [-o output.py]
    nous run <file.nous>
    nous validate <file.nous>
    nous ast <file.nous> [--json]
    nous evolve <file.nous> [--cycles N] [--save]
    nous nsp <text> [--compress]
    nous info <file.nous>
    nous bridge <file.nous>
    nous version
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python

VERSION = "1.3.0"
BANNER = r"""
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \
 | |\  | |_| | |_| |___) |
 |_| \_|\___/ \___/|____/   v{version}

 The Living Language — Noosphere Project
""".format(version=VERSION)


def cmd_compile(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    t0 = time.perf_counter()
    print(f"[1/3] Parsing {source.name}...")
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    world_name = program.world.name if program.world else "Unknown"
    print(f"      World: {world_name} | {len(program.souls)} souls | {len(program.messages)} messages")
    print("[2/3] Validating laws...")
    result = validate_program(program)
    for w in result.warnings:
        print(f"      {w}")
    if not result.ok:
        for e in result.errors:
            print(f"      {e}")
        print(f"\nValidation FAILED: {len(result.errors)} errors")
        return 1
    print(f"      Validation PASS")
    print("[3/3] Generating Python...")
    code = generate_python(program)
    out_path = Path(args.output) if args.output else source.with_suffix(".py")
    out_path.write_text(code, encoding="utf-8")
    elapsed = time.perf_counter() - t0
    print(f"      Output: {out_path} ({len(code.splitlines())} lines)")
    print(f"\n✓ Compiled in {elapsed:.2f}s")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    t0 = time.perf_counter()
    print(f"[1/3] Parsing {source.name}...")
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    world_name = program.world.name if program.world else "Unknown"
    print(f"      World: {world_name}")
    print("[2/3] Validating laws...")
    result = validate_program(program)
    if not result.ok:
        for e in result.errors:
            print(f"      {e}")
        return 1
    print(f"      Validation PASS")
    print("[3/3] Generating & executing...")
    code = generate_python(program)
    tmp_path = source.with_suffix(".gen.py")
    tmp_path.write_text(code, encoding="utf-8")
    print(f"      Compiled in {time.perf_counter() - t0:.2f}s")
    print(f"      Running {world_name}...\n")
    print("=" * 50)
    try:
        proc = subprocess.run([sys.executable, str(tmp_path)], cwd=str(source.parent))
        return proc.returncode
    except KeyboardInterrupt:
        print("\n\nWorld stopped by user.")
        return 0
    finally:
        if tmp_path.exists() and not args.keep:
            tmp_path.unlink()


def cmd_validate(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    result = validate_program(program)
    print(result.summary())
    return 0 if result.ok else 1


def cmd_ast(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    data = program.model_dump(exclude_none=True)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        _print_ast(data)
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    from aevolver import Aevolver
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    result = validate_program(program)
    if not result.ok:
        print("Validation FAILED — cannot evolve")
        for e in result.errors:
            print(f"  {e}")
        return 1
    evo = Aevolver(program)
    print(f"═══ NOUS Evolution — {program.world.name} ═══")
    print(f"Cycles: {args.cycles}\n")
    for i in range(args.cycles):
        report = evo.evolve()
        for c in report.cycles:
            status = "✓" if c.accepted else "✗"
            print(f"  [{i+1}/{args.cycles}] {c.soul_name}: {status} fitness {c.parent_fitness:.3f} → {c.child_fitness:.3f}")
            for m in c.mutations:
                print(f"         {m.gene_name}: {m.old_value} → {m.new_value}")
    print("\nFinal DNA:")
    for soul in program.souls:
        if soul.dna and soul.dna.genes:
            print(f"  {soul.name}:")
            for g in soul.dna.genes:
                print(f"    {g.name}: {g.value}")
    if args.save:
        history_path = source.with_suffix(".evolution.json")
        evo.export_history(history_path)
        print(f"\nHistory saved: {history_path}")
    return 0


def cmd_nsp(args: argparse.Namespace) -> int:
    from nsp import create_nsp_parser
    nsp_parser = create_nsp_parser()
    text = args.text
    if args.compress:
        pairs = {}
        for item in text.split(","):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                try:
                    v = float(v) if "." in v else int(v)
                except ValueError:
                    pass
                pairs[k.strip()] = v
        print(nsp_parser.compress(pairs))
        return 0
    tokens = nsp_parser.extract_all(text)
    if not tokens:
        print("No NSP tokens found.")
        return 1
    for t in tokens:
        print(f"Raw:      {t.raw}")
        print(f"Parsed:   {t.to_dict()}")
        print(f"Expanded: {t.to_prompt_expansion()}")
        print(f"Savings:  {t.token_savings['savings_pct']}%")
        if not t.valid:
            print(f"Errors:   {t.errors}")
        print()
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    result = validate_program(program)
    w = program.world
    print(f"═══ NOUS Program Info ═══")
    print(f"File:       {source.name}")
    print(f"World:      {w.name if w else 'None'}")
    print(f"Heartbeat:  {w.heartbeat if w else 'N/A'}")
    print(f"Status:     {'VALID' if result.ok else 'INVALID'}")
    if w and w.laws:
        print(f"\nLaws ({len(w.laws)}):")
        for law in w.laws:
            print(f"  {law.name} = {law.expr}")
    print(f"\nMessages ({len(program.messages)}):")
    for msg in program.messages:
        fields = ", ".join(f"{f.name}:{f.type_expr}" for f in msg.fields)
        print(f"  {msg.name}({fields})")
    print(f"\nSouls ({len(program.souls)}):")
    for soul in program.souls:
        mind = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none"
        senses = len(soul.senses)
        mem = len(soul.memory.fields) if soul.memory else 0
        genes = len(soul.dna.genes) if soul.dna else 0
        heals = len(soul.heal.rules) if soul.heal else 0
        print(f"  {soul.name}: mind={mind} | {senses} senses | {mem} memory | {genes} genes | {heals} heal rules")
    if program.nervous_system:
        print(f"\nNervous System ({len(program.nervous_system.routes)} routes):")
        for r in program.nervous_system.routes:
            rtype = type(r).__name__.replace("Node", "")
            if hasattr(r, "source") and hasattr(r, "target"):
                print(f"  {r.source} → {r.target}")
    if program.evolution:
        print(f"\nEvolution: {len(program.evolution.mutations)} mutation targets")
    if program.perception:
        print(f"\nPerception: {len(program.perception.rules)} event rules")
    return 0


def cmd_bridge(args: argparse.Namespace) -> int:
    from bridge import NoosphereBridge
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    result = validate_program(program)
    if not result.ok:
        print("Validation FAILED")
        for e in result.errors:
            print(f"  {e}")
        return 1
    bridge = NoosphereBridge(program)
    report = bridge.analyze()
    print(report)
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(BANNER)
    return 0


def _print_ast(data: dict | list | Any, indent: int = 0) -> None:
    prefix = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}:")
                _print_ast(v, indent + 1)
            else:
                print(f"{prefix}{k}: {v}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                name = item.get("name", item.get("kind", f"[{i}]"))
                print(f"{prefix}- {name}:")
                _print_ast(item, indent + 1)
            else:
                print(f"{prefix}- {item}")
    else:
        print(f"{prefix}{data}")


def cmd_shell(args: argparse.Namespace) -> int:
    from repl import NousREPL
    repl = NousREPL()
    if hasattr(args, "file") and args.file:
        repl._cmd_load(args.file)
    repl.start()
    return 0


def cmd_evolve_live(args: argparse.Namespace) -> int:
    import asyncio
    from aevolver_live import run_evolution_now, EvolutionScheduler
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    if args.daemon:
        async def run_daemon() -> None:
            scheduler = EvolutionScheduler(source)
            await scheduler.start()
            try:
                while True:
                    await asyncio.sleep(3600)
            except KeyboardInterrupt:
                await scheduler.stop()
        asyncio.run(run_daemon())
    else:
        report = asyncio.run(run_evolution_now(source))
        print(report.summary())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="nous", description="NOUS — The Living Language")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("compile", help="Compile .nous to Python")
    p.add_argument("file"); p.add_argument("-o", "--output")

    p = sub.add_parser("run", help="Compile and execute")
    p.add_argument("file"); p.add_argument("--keep", action="store_true")

    p = sub.add_parser("validate", help="Validate .nous file")
    p.add_argument("file")

    p = sub.add_parser("ast", help="Print Living AST")
    p.add_argument("file"); p.add_argument("--json", action="store_true")

    p = sub.add_parser("evolve", help="Run evolution cycles")
    p.add_argument("file"); p.add_argument("--cycles", type=int, default=3)
    p.add_argument("--save", action="store_true")

    p = sub.add_parser("evolve-live", help="Run live evolution with Langfuse/Telegram")
    p.add_argument("file"); p.add_argument("--daemon", action="store_true")

    p = sub.add_parser("shell", help="Interactive NOUS REPL")
    p.add_argument("file", nargs="?", default="")

    p = sub.add_parser("nsp", help="Parse/compress NSP tokens")
    p.add_argument("text"); p.add_argument("--compress", action="store_true")

    p = sub.add_parser("info", help="Show program summary")
    p.add_argument("file")

    p = sub.add_parser("bridge", help="Analyze Noosphere integration")
    p.add_argument("file")

    sub.add_parser("version", help="Show version")

    args = ap.parse_args()
    commands = {
        "compile": cmd_compile, "run": cmd_run, "validate": cmd_validate,
        "ast": cmd_ast, "evolve": cmd_evolve, "evolve-live": cmd_evolve_live,
        "shell": cmd_shell, "nsp": cmd_nsp,
        "info": cmd_info, "bridge": cmd_bridge, "version": cmd_version,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
