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

VERSION = "1.8.0"
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


def cmd_deploy(args: argparse.Namespace) -> int:
    import asyncio as _asyncio
    from topology import TopologyManager
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    t0 = time.perf_counter()
    print(f"[1/4] Parsing {source.name}...")
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    if not program.topology:
        print("Error: no topology block found in .nous file", file=sys.stderr)
        return 1
    print(f"      Found {len(program.topology.servers)} servers")
    print("[2/4] Validating...")
    result = validate_program(program)
    for w in result.warnings:
        print(f"      {w}")
    if not result.ok:
        for e in result.errors:
            print(f"      {e}")
        print(f"\nValidation FAILED")
        return 1
    print("[3/4] Compiling...")
    code = generate_python(program)
    print(f"      {len(code.splitlines())} lines generated")
    print("[4/4] Deploying to servers...")
    mgr = TopologyManager(program, code)

    async def _deploy() -> list:
        return await mgr.deploy()

    results = _asyncio.run(_deploy())
    elapsed = time.perf_counter() - t0
    print()
    successes = 0
    for r in results:
        icon = "✓" if r.success else "✗"
        print(f"  {icon} {r.server} ({r.host}): {r.message} [{r.elapsed:.2f}s]")
        if r.success:
            successes += 1
    print(f"\nDeployed {successes}/{len(results)} servers in {elapsed:.2f}s")
    return 0 if successes == len(results) else 1


def cmd_topology(args: argparse.Namespace) -> int:
    import asyncio as _asyncio
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    if not program.topology:
        print("Error: no topology block found", file=sys.stderr)
        return 1

    if args.action == "show":
        print(f"═══ Topology ═══")
        for srv in program.topology.servers:
            souls = srv.config.get("souls", [])
            soul_list = ", ".join(str(s) for s in souls) if isinstance(souls, list) else str(souls)
            port = srv.config.get("port", 9100)
            print(f"  {srv.name}: {srv.host}")
            print(f"    souls: [{soul_list}]")
            print(f"    port:  {port}")
        return 0

    elif args.action == "status":
        from topology import HealthMonitor, ServerSpec
        servers = [ServerSpec.from_ast(s) for s in program.topology.servers]
        monitor = HealthMonitor(servers)

        async def _check() -> dict:
            return await monitor.check_all()

        status = _asyncio.run(_check())
        print(f"═══ Topology Status ═══")
        for name, s in status.items():
            icon = "🟢" if s.alive else "🔴"
            pid_str = f"PID {s.pid}" if s.pid else "no PID"
            uptime_str = f"uptime {s.uptime:.0f}s" if s.uptime else ""
            souls_str = f"souls: {', '.join(s.souls_running)}" if s.souls_running else ""
            parts = [p for p in [pid_str, uptime_str, souls_str] if p]
            detail = " | ".join(parts)
            err = f" — {s.error}" if s.error else ""
            print(f"  {icon} {name} ({s.host}): {detail}{err}")
        return 0

    elif args.action == "stop":
        from topology import SSHDeployer
        code = generate_python(program)
        deployer = SSHDeployer(program, code)

        async def _stop() -> list:
            return await deployer.stop_all()

        results = _asyncio.run(_stop())
        for r in results:
            icon = "✓" if r.success else "✗"
            print(f"  {icon} {r.server}: {r.message}")
        return 0

    print(f"Unknown topology action: {args.action}", file=sys.stderr)
    return 1


def cmd_version(_args: argparse.Namespace) -> int:
    print(BANNER)
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    from shell import run_shell
    source = args.file if hasattr(args, "file") and args.file else None
    run_shell(source)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    from test_runner import run_tests, print_results
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    suite = run_tests(str(source), verbose=args.verbose if hasattr(args, "verbose") else False)
    print_results(suite)
    return 0 if suite.ok else 1


def cmd_pkg(args: argparse.Namespace) -> int:
    from package_manager import cmd_install, cmd_uninstall, cmd_list, cmd_init, cmd_search
    action = args.action
    if action == "install":
        if not args.pkg_name:
            print("Usage: nous pkg install <name>", file=sys.stderr)
            return 1
        ver = args.pkg_version if hasattr(args, "pkg_version") and args.pkg_version else "latest"
        return cmd_install(args.pkg_name, ver)
    elif action == "uninstall":
        if not args.pkg_name:
            print("Usage: nous pkg uninstall <name>", file=sys.stderr)
            return 1
        return cmd_uninstall(args.pkg_name)
    elif action == "list":
        return cmd_list()
    elif action == "init":
        return cmd_init(args.pkg_name)
    elif action == "search":
        return cmd_search(args.pkg_name or "")
    print(f"Unknown pkg action: {action}", file=sys.stderr)
    return 1


def cmd_docs(args: argparse.Namespace) -> int:
    from docs_generator import generate_docs_file
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    out = args.output if hasattr(args, "output") and args.output else None
    try:
        result = generate_docs_file(str(source), out)
        print(f"✓ Documentation generated: {result}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_profile(args: argparse.Namespace) -> int:
    from profiler import profile, print_profile
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        result = profile(str(source))
        print_profile(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


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

    p = sub.add_parser("nsp", help="Parse/compress NSP tokens")
    p.add_argument("text"); p.add_argument("--compress", action="store_true")

    p = sub.add_parser("info", help="Show program summary")
    p.add_argument("file")

    p = sub.add_parser("bridge", help="Analyze Noosphere integration")
    p.add_argument("file")

    p = sub.add_parser("deploy", help="Deploy topology to remote servers")
    p.add_argument("file")

    p = sub.add_parser("topology", help="Show/check/stop topology")
    p.add_argument("file")
    p.add_argument("action", choices=["show", "status", "stop"], nargs="?", default="show")

    p = sub.add_parser("shell", help="Interactive REPL")
    p.add_argument("file", nargs="?", default=None)

    p = sub.add_parser("test", help="Run .nous test blocks")
    p.add_argument("file")
    p.add_argument("-v", "--verbose", action="store_true")

    p = sub.add_parser("pkg", help="Package manager")
    p.add_argument("action", choices=["install", "uninstall", "list", "init", "search"])
    p.add_argument("pkg_name", nargs="?", default=None)
    p.add_argument("pkg_version", nargs="?", default="latest")

    p = sub.add_parser("docs", help="Generate HTML documentation")
    p.add_argument("file")
    p.add_argument("-o", "--output")

    p = sub.add_parser("profile", help="Profile .nous program")
    p.add_argument("file")

    sub.add_parser("version", help="Show version")

    args = ap.parse_args()
    commands = {
        "compile": cmd_compile, "run": cmd_run, "validate": cmd_validate,
        "ast": cmd_ast, "evolve": cmd_evolve, "nsp": cmd_nsp,
        "info": cmd_info, "bridge": cmd_bridge, "deploy": cmd_deploy,
        "topology": cmd_topology, "shell": cmd_shell, "test": cmd_test,
        "pkg": cmd_pkg, "docs": cmd_docs, "profile": cmd_profile,
        "version": cmd_version,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
