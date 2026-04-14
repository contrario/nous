#!/usr/bin/env python3
"""
NOUS CLI — Νοῦς Command Line Interface v2.0
=============================================
Usage:
    nous compile <file.nous> [-o output.py]
    nous run <file.nous>
    nous validate <file.nous>
    nous typecheck <file.nous>
    nous docker <file.nous> [--tag NAME] [--port PORT]
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
import os
import py_compile
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python
from typechecker import typecheck_program

VERSION = "3.6.0"
BANNER = r"""
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \
 | |\  | |_| | |_| |___) |
 |_| \_|\___/ \___/|____/   v{version}

 The Living Language — Noosphere Project
""".format(version=VERSION)


def _parse_and_validate(source: Path, typecheck: bool = True) -> tuple:
    t0 = time.perf_counter()
    print(f"[1/4] Parsing {source.name}...")
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return None, None, None, 1
    world_name = program.world.name if program.world else "Unknown"
    print(f"      World: {world_name} | {len(program.souls)} souls | {len(program.messages)} messages")

    print("[2/4] Validating laws...")
    vresult = validate_program(program)
    for w in vresult.warnings:
        print(f"      {w}")
    if not vresult.ok:
        for e in vresult.errors:
            print(f"      {e}")
        print(f"\nValidation FAILED: {len(vresult.errors)} errors")
        return None, None, None, 1
    print(f"      Validation PASS")

    if typecheck:
        print("[3/4] Type checking...")
        tresult = typecheck_program(program)
        for w in tresult.warnings:
            print(f"      {w}")
        if not tresult.ok:
            for e in tresult.errors:
                print(f"      {e}")
            print(f"\nType check FAILED: {len(tresult.errors)} errors")
            return None, None, None, 1
        tc_info = f"{len(tresult.warnings)} warnings" if tresult.warnings else "clean"
        print(f"      Type check PASS ({tc_info})")
    else:
        tresult = None

    elapsed = time.perf_counter() - t0
    return program, vresult, tresult, elapsed


def cmd_compile(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1

    program, _, _, result = _parse_and_validate(source)
    if program is None:
        return result

    target = getattr(args, "target", "python")
    if target in ("js", "wasm"):
        print(f"[4/4] Generating JavaScript...")
        from codegen_js import generate_javascript
        code = generate_javascript(program)
        out_path = Path(args.output) if args.output else source.with_suffix(".mjs" if target == "js" else ".html")
        if target == "wasm":
            from wasm_builder import build_html
            out_path_final = Path(args.output) if args.output else None
            result_path = build_html(program, out_path_final)
            print(f"      Output: {result_path}")
            elapsed = result if isinstance(result, float) else 0
            print(f"\n\u2713 Built in {elapsed:.2f}s")
            return 0
        out_path.write_text(code, encoding="utf-8")
        print(f"      Output: {out_path} ({len(code.splitlines())} lines)")
        elapsed = result if isinstance(result, float) else 0
        print(f"\n\u2713 Compiled in {elapsed:.2f}s")
        return 0
    print("[4/4] Generating Python...")
    code = generate_python(program)
    out_path = Path(args.output) if args.output else source.with_suffix(".py")
    out_path.write_text(code, encoding="utf-8")

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        print(f"      py_compile PASS")
    except py_compile.PyCompileError as e:
        print(f"      py_compile FAIL: {e}")
        return 1
    finally:
        os.unlink(tmp)

    print(f"      Output: {out_path} ({len(code.splitlines())} lines)")
    elapsed = result if isinstance(result, float) else 0
    print(f"\n✓ Compiled in {elapsed:.2f}s")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    mode = getattr(args, "mode", "dry-run")
    cycles = getattr(args, "cycles", 3)
    budget = getattr(args, "budget", 0.33)
    try:
        from nous_ast_runner import run_program
        run_program(str(source), mode=mode, max_cycles=cycles, daily_budget=budget)
        return 0
    except KeyboardInterrupt:
        print("\n\nWorld stopped by user.")
        return 0
    except Exception as e:
        print(f"Runtime error: {e}", file=sys.stderr)
        return 1


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


def cmd_typecheck(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    vresult = validate_program(program)
    if not vresult.ok:
        print("Validation FAILED — cannot type check")
        for e in vresult.errors:
            print(f"  {e}")
        return 1
    tresult = typecheck_program(program)
    print(tresult.summary())
    return 0 if tresult.ok else 1


def cmd_docker(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1

    program, _, _, result = _parse_and_validate(source)
    if program is None:
        return result

    world_name = program.world.name if program.world else "nous_app"
    tag = args.tag or world_name.lower().replace(" ", "_")
    port = args.port or 8080

    print("[4/4] Generating Docker artifacts...")
    code = generate_python(program)
    out_dir = source.parent / "docker"
    out_dir.mkdir(exist_ok=True)

    app_py = out_dir / "app.py"
    app_py.write_text(code, encoding="utf-8")

    soul_names = [s.name for s in program.souls]
    soul_senses: list[str] = []
    for s in program.souls:
        soul_senses.extend(s.senses)
    unique_senses = sorted(set(soul_senses))

    env_vars: dict[str, str] = {}
    if program.world and program.world.config:
        for k, v in program.world.config.items():
            env_vars[k.upper()] = str(v)

    dockerfile = _generate_dockerfile(tag, port)
    (out_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    compose = _generate_compose(tag, port, env_vars)
    (out_dir / "docker-compose.yml").write_text(compose, encoding="utf-8")

    requirements = "pydantic>=2.0\nhttpx>=0.25\n"
    (out_dir / "requirements.txt").write_text(requirements, encoding="utf-8")

    healthcheck = _generate_healthcheck(port, world_name, soul_names)
    (out_dir / "healthcheck.py").write_text(healthcheck, encoding="utf-8")

    env_file = "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n" if env_vars else ""
    (out_dir / ".env").write_text(env_file, encoding="utf-8")

    print(f"      Output: {out_dir}/")
    print(f"        Dockerfile          (multi-stage)")
    print(f"        docker-compose.yml  (tag: {tag})")
    print(f"        app.py              ({len(code.splitlines())} lines)")
    print(f"        requirements.txt")
    print(f"        healthcheck.py")
    if env_vars:
        print(f"        .env                ({len(env_vars)} vars)")
    print(f"\n✓ Docker artifacts generated")
    print(f"\n  Build:  cd {out_dir} && docker compose build")
    print(f"  Run:    cd {out_dir} && docker compose up -d")
    print(f"  Health: curl http://localhost:{port}/health")
    return 0


def _generate_dockerfile(tag: str, port: int) -> str:
    return f"""# NOUS Generated Dockerfile — {tag}
# Multi-stage build for minimal runtime image

# ── Stage 1: Dependencies ──
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY app.py .
COPY healthcheck.py .

ENV PYTHONUNBUFFERED=1
ENV NOUS_PORT={port}

EXPOSE {port}

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD python healthcheck.py || exit 1

CMD ["python", "app.py"]
"""


def _generate_compose(tag: str, port: int, env_vars: dict[str, str]) -> str:
    env_section = ""
    if env_vars:
        env_lines = "\n".join(f"      {k}: ${{{k}}}" for k in env_vars)
        env_section = f"\n    environment:\n{env_lines}"

    return f"""# NOUS Generated docker-compose.yml
version: "3.9"

services:
  nous-{tag}:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: nous-{tag}
    ports:
      - "{port}:{port}"
    restart: unless-stopped
    env_file:
      - .env{env_section}
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
"""


def _generate_healthcheck(port: int, world_name: str, soul_names: list[str]) -> str:
    return f"""#!/usr/bin/env python3
\"\"\"NOUS Health Check — {world_name}\"\"\"
from __future__ import annotations

import asyncio
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("NOUS_PORT", {port}))
WORLD = "{world_name}"
SOULS = {soul_names}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({{
                "status": "healthy",
                "world": WORLD,
                "souls": SOULS,
            }})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    import urllib.request
    try:
        r = urllib.request.urlopen(f"http://localhost:{{PORT}}/health", timeout=5)
        data = json.loads(r.read())
        if data.get("status") == "healthy":
            sys.exit(0)
    except Exception:
        pass
    sys.exit(1)
"""


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


def cmd_debug(args: argparse.Namespace) -> int:
    from debugger import debug_file
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    debug_file(source)
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    from repl import start_repl
    file_path = args.file if hasattr(args, "file") and args.file else None
    start_repl(file_path)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    from test_runner import cmd_test as _cmd_test
    return _cmd_test(args.file)


def cmd_watch(args: argparse.Namespace) -> int:
    from watcher import watch_file
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    output = Path(args.output) if args.output else None
    watch_file(source, output=output, interval=args.interval)
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    from profiler import cmd_profile as _cmd_profile
    return _cmd_profile(args.file)


def cmd_plugins(args: argparse.Namespace) -> int:
    from plugin_manager import cmd_plugins as _cmd_plugins
    plugin_args = [args.subcmd] if args.subcmd else ["list"]
    if hasattr(args, "file") and args.file:
        plugin_args.append(args.file)
    return _cmd_plugins(plugin_args)


def cmd_pkg(args: argparse.Namespace) -> int:
    from stdlib_manager import cmd_pkg as _cmd_pkg
    pkg_args = [args.subcmd] if args.subcmd else []
    if hasattr(args, "target") and args.target:
        pkg_args.append(args.target)
    return _cmd_pkg(pkg_args)






def cmd_crossworld(args: argparse.Namespace) -> int:
    from cross_world import check_cross_world, print_cross_world_report
    result = check_cross_world(args.files)
    print_cross_world_report(result)
    return 0 if result.ok else 1

def cmd_bench(args: argparse.Namespace) -> int:
    from benchmarks import bench_cli
    return bench_cli(args.file, save_bl=args.save_baseline, json_out=args.json, runs=args.runs)

def cmd_docs(args: argparse.Namespace) -> int:
    from docs_generator import generate_docs_file
    out = generate_docs_file(args.file, args.output)
    print(f'Documentation generated: {out}')
    return 0

def cmd_fmt(args: argparse.Namespace) -> int:
    from formatter import fmt_file
    path = args.file
    if args.check:
        _, changed = fmt_file(path, check=True)
        if changed:
            print(f'Would reformat {path}')
            return 1
        print(f'{path} — already formatted')
        return 0
    formatted, changed = fmt_file(path, write=args.write)
    if args.write:
        if changed:
            print(f'Reformatted {path}')
        else:
            print(f'{path} — no changes')
    else:
        print(formatted)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from workspace import open_workspace, Workspace, WorkspaceConfig, load_config, init_workspace, print_workspace_report
    from codegen import generate_python
    ws = open_workspace()
    if ws is None:
        print("Error: no nous.toml found. Run 'nous init' first.", file=sys.stderr)
        return 1
    result = ws.build()
    print_workspace_report(result)
    if not result.ok:
        return 1
    if result.merged:
        code = generate_python(result.merged)
        out_dir = ws.config.root / ws.config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{ws.config.name.replace('-', '_')}.py"
        out_path.write_text(code, encoding="utf-8")
        import py_compile, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            py_compile.compile(tmp, doraise=True)
            print(f"\n  py_compile PASS")
        except py_compile.PyCompileError as e:
            print(f"\n  py_compile FAIL: {e}")
            return 1
        finally:
            os.unlink(tmp)
        print(f"  Output: {out_path} ({len(code.splitlines())} lines)")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    from workspace import init_workspace
    target = Path(args.directory) if args.directory else Path.cwd()
    name = args.name or target.name
    entry = args.entry or None
    toml_path = init_workspace(target, name=name, entry=entry)
    print(f"Initialized NOUS workspace: {toml_path}")
    return 0



def cmd_migrate(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    if source.suffix == ".py":
        from migrate_v2 import migrate_python, print_migration_report
        output = Path(args.output) if args.output else source.with_suffix(".nous")
        result = migrate_python(source, output)
        print_migration_report(result)
        if result.ok:
            print(f"\nOutput: {output}")
            return 0
        return 1
    else:
        from migrate import migrate_file, migrate_directory
        if source.is_dir():
            output = Path(args.output) if args.output else None
            report = migrate_directory(source, output)
            print(report)
        else:
            soul = migrate_file(source)
            if soul:
                if args.output:
                    Path(args.output).write_text(soul, encoding="utf-8")
                    print(f"Written: {args.output}")
                else:
                    print(soul)
            else:
                print(f"Could not migrate: {source}")
                return 1
        return 0


def cmd_viz(args: argparse.Namespace) -> int:
    from visualizer import visualize_file, visualize_workspace
    output = Path(args.output) if args.output else None
    try:
        if args.file:
            source = Path(args.file)
            if not source.exists():
                print(f"Error: file not found: {source}", file=sys.stderr)
                return 1
            out = visualize_file(source, output)
        else:
            out = visualize_workspace(output)
        print(f"Visualization generated: {out}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_create(args: argparse.Namespace) -> int:
    from natural_lang import generate_from_description, print_generation_report
    description = args.description
    use_llm = not args.template_only
    result = generate_from_description(description, use_llm=use_llm)
    print_generation_report(result)
    if result.ok:
        print(f"\n  Generated source:\n")
        for line in result.source.splitlines():
            print(f"    {line}")
        if args.output:
            out = Path(args.output)
            out.write_text(result.source, encoding="utf-8")
            print(f"\n  Written to: {out}")
    return 0 if result.ok else 1


def cmd_verify(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    program, _, _, result = _parse_and_validate(source)
    if program is None:
        return result
    from verifier import verify_program, print_verification_report
    world_name = program.world.name if program.world else "Unknown"
    vresult = verify_program(program)
    print_verification_report(vresult, world_name)
    return 0 if vresult.ok else 1


def cmd_selfcompile(args: argparse.Namespace) -> int:
    from self_compiler import cmd_self_compile
    sc_args = list(args.files)
    if args.target:
        sc_args.extend(["--target", args.target])
    if args.output:
        sc_args.extend(["-o", args.output])
    return cmd_self_compile(sc_args)


def cmd_wasm(args: argparse.Namespace) -> int:
    from wasm_builder import build_wasm_target
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    output = Path(args.output) if args.output else None
    target = args.target or "html"
    try:
        out = build_wasm_target(source, output, target=target)
        print(f"WASM build complete: {out}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_lsp(args: argparse.Namespace) -> int:
    if hasattr(args, "subcmd") and args.subcmd == "check":
        target = args.target if hasattr(args, "target") and args.target else None
        if not target:
            print("Usage: nous lsp check <file.nous>", file=sys.stderr)
            return 1
        from lsp_server import check_file
        diags, actions = check_file(target)
        print(f"Diagnostics ({len(diags)}):")
        for d in diags:
            sev = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "HINT"}.get(d["severity"], "?")
            line = d["range"]["start"]["line"] + 1
            print(f"  line {line:3d} [{sev:5s}] {d['code']}: {d['message']}")
        print(f"\nCode Actions ({len(actions)}):")
        for a in actions:
            print(f"  → {a['title']}")
        errors = [d for d in diags if d["severity"] == 1]
        return 1 if errors else 0
    else:
        from lsp_server import run_lsp
        run_lsp()
        return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(BANNER)
    return 0


def _print_ast(data: dict | list | object, indent: int = 0) -> None:
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



def cmd_noesis(args: argparse.Namespace) -> int:
    sub_args = [sys.executable, str(Path(__file__).parent / "noesis_cli_noesis.py")]
    sub_args.append(args.noesis_command)
    if args.noesis_command == "search" and hasattr(args, "query"):
        sub_args.append(args.query)
        if hasattr(args, "top_k") and args.top_k:
            sub_args.extend(["--top-k", str(args.top_k)])
    elif args.noesis_command == "think" and hasattr(args, "query"):
        sub_args.append(args.query)
    elif args.noesis_command == "gaps" and hasattr(args, "limit") and args.limit:
        sub_args.extend(["--limit", str(args.limit)])
    elif args.noesis_command == "evolve" and hasattr(args, "save") and args.save:
        sub_args.append("--save")
    elif args.noesis_command == "export" and hasattr(args, "json_export") and args.json_export:
        sub_args.append("--json")
    try:
        result = subprocess.run(sub_args, cwd=str(Path(__file__).parent))
        return result.returncode
    except FileNotFoundError:
        print("Error: noesis_cli_noesis.py not found", file=sys.stderr)
        return 1

def cmd_dream(args: argparse.Namespace) -> int:
    """Dream system analysis."""
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    program, _, _, result = _parse_and_validate(source)
    if program is None:
        return result
    dream_souls = [s for s in program.souls if s.dream_system is not None]
    if not dream_souls:
        print("No souls with dream_system blocks found.")
        return 0
    world_name = program.world.name if program.world else "Unknown"
    print(f"\n  \u2550\u2550\u2550 NOUS Dream Analysis \u2014 {world_name} \u2550\u2550\u2550")
    print()
    from verifier import verify_program
    vresult = verify_program(program)
    for soul in dream_souls:
        ds = soul.dream_system
        dm = f"{ds.dream_mind.model}@{ds.dream_mind.tier.value}" if ds.dream_mind else "default"
        print(f"  \u2500\u2500 {soul.name} \u2500\u2500")
        print(f"  Enabled:          {ds.enabled}")
        print(f"  Dream mind:       {dm}")
        print(f"  Idle trigger:     {ds.trigger_idle_sec}s")
        print(f"  Max cache:        {ds.max_cache}")
        print(f"  Depth:            {ds.speculation_depth}")
        print()
    dream_items = [i for i in vresult.items if i.category == "dream"]
    if dream_items:
        print("  \u2500\u2500 Verification \u2500\u2500")
        for item in dream_items:
            icon = {"PROVEN": "\u2713", "WARNING": "\u26a0", "INFO": "\u2139", "ERROR": "\u2717"}.get(item.severity, "?")
            print(f"  {icon} [{item.code}] {item.message}")
        print()
    proven = len([i for i in dream_items if i.severity == "PROVEN"])
    errors = len([i for i in dream_items if i.severity == "ERROR"])
    print(f"  \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550")
    print(f"  {len(dream_souls)} soul(s) with dream system | {proven} proven, {errors} errors")
    return 1 if errors else 0


def cmd_immune(args: argparse.Namespace) -> int:
    """Immune system analysis — show adaptive recovery config."""
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    program, _, _, result = _parse_and_validate(source)
    if program is None:
        return result

    immune_souls = [s for s in program.souls if s.immune_system is not None]
    if not immune_souls:
        print("No souls with immune_system blocks found.")
        return 0

    world_name = program.world.name if program.world else "Unknown"
    print(f"\n  ═══ NOUS Immune Analysis — {world_name} ═══")
    print()

    from verifier import verify_program
    vresult = verify_program(program)

    for soul in immune_souls:
        im = soul.immune_system
        has_mitosis = soul.mitosis is not None
        has_heal = soul.heal is not None
        print(f"  ── {soul.name} ──")
        print(f"  Adaptive recovery:   {im.adaptive_recovery}")
        print(f"  Share with clones:   {im.share_with_clones}")
        print(f"  Antibody lifespan:   {im.antibody_lifespan}")
        print(f"  Has heal block:      {has_heal}")
        print(f"  Has mitosis:         {has_mitosis}")
        if has_mitosis:
            print(f"  Max clones:          {soul.mitosis.max_clones}")
        print()

    immune_items = [i for i in vresult.items if i.category == "immune"]
    if immune_items:
        print("  ── Verification ──")
        for item in immune_items:
            icon = {"ERROR": "\u2717", "WARNING": "\u26a0", "INFO": "\u2139", "PROVEN": "\u2713"}.get(item.severity, "?")
            print(f"  {icon} [{item.code}] {item.message}")
        print()

    proven = len([i for i in immune_items if i.severity == "PROVEN"])
    errors = len([i for i in immune_items if i.severity == "ERROR"])
    warnings = len([i for i in immune_items if i.severity == "WARNING"])
    print(f"  ══════════════════════════════════════")
    print(f"  {len(immune_souls)} soul(s) with immune system")
    print(f"  Verification: {proven} proven, {warnings} warnings, {errors} errors")
    return 1 if errors else 0






def cmd_telemetry(args: Any) -> None:
    """Show telemetry configuration for a .nous program."""
    from parser import parse_nous
    from validator import NousValidator
    from verifier import NousVerifier

    source = Path(args.file).read_text()
    program = parse_nous(source)

    validator = NousValidator(program)
    val_result = validator.validate()
    for e in val_result.errors:
        print(f"  ERROR [{e.code}] {e.message}")
    for w in val_result.warnings:
        print(f"  WARN  [{w.code}] {w.message}")

    verifier = NousVerifier(program)
    ver_result = verifier.verify()

    print("")
    print("  ═══ NOUS Telemetry Analysis ═══")
    print("")

    if not program.world or not program.world.telemetry:
        print("  No telemetry block found in world declaration.")
        print("  Add: telemetry { enabled: true exporter: console }")
        return

    t = program.world.telemetry
    print(f"  Enabled:        {t.enabled}")
    print(f"  Exporter:       {t.exporter}")
    if t.endpoint:
        print(f"  Endpoint:       {t.endpoint}")
    print(f"  Sample rate:    {t.sample_rate}")
    print(f"  Trace senses:   {t.trace_senses}")
    print(f"  Trace LLM:      {t.trace_llm}")
    print(f"  Buffer size:    {t.buffer_size}")
    print("")

    soul_count = len(program.souls)
    print(f"  Souls monitored: {soul_count}")
    for soul in program.souls:
        subsystems = []
        if soul.mitosis:
            subsystems.append("mitosis")
        if soul.immune_system:
            subsystems.append("immune")
        if soul.dream_system:
            subsystems.append("dream")
        sub_str = ", ".join(subsystems) if subsystems else "—"
        print(f"    {soul.name}: {sub_str}")
    print("")

    tl_proofs = [p for p in ver_result.proven if "VTL" in str(getattr(p, 'code', ''))]
    tl_warns = [w for w in ver_result.warnings if "VTL" in str(getattr(w, 'code', ''))]
    for p in tl_proofs:
        print(f"  ✓ [{p.code}] {p.message}")
    for w in tl_warns:
        print(f"  ⚠ [{w.code}] {w.message}")

    print("")
    print("  ══════════════════════════════════════")

def cmd_retire(args: Any) -> None:
    """Show clone retirement analysis for a .nous program."""
    from parser import parse_nous
    from validator import NousValidator
    from verifier import NousVerifier

    source = Path(args.file).read_text()
    pass
    program = parse_nous(source)

    validator = NousValidator(program)
    val_result = validator.validate()
    for e in val_result.errors:
        print(f"  ERROR [{e.code}] {e.message}")
    for w in val_result.warnings:
        print(f"  WARN  [{w.code}] {w.message}")

    verifier = NousVerifier(program)
    ver_result = verifier.verify()

    print("")
    print("  ═══ NOUS Clone Retirement Analysis ═══")
    print("")

    mitosis_souls = [s for s in program.souls if s.mitosis is not None]
    if not mitosis_souls:
        print("  No souls with mitosis found.")
        return

    for soul in mitosis_souls:
        m = soul.mitosis
        has_retire = m.retire_trigger is not None
        print(f"  ── {soul.name} ──")
        print(f"  Max clones:       {m.max_clones}")
        print(f"  Min clones:       {m.min_clones}")
        print(f"  Spawn cooldown:   {m.cooldown}")
        print(f"  Retirement:       {'ENABLED' if has_retire else 'DISABLED — clones never die'}")
        if has_retire:
            print(f"  Retire cooldown:  {m.retire_cooldown}")
            print(f"  Retire window:    {m.max_clones - m.min_clones} clones can be retired")
        print("")

    retire_proofs = [p for p in ver_result.proven if "VRT" in str(getattr(p, 'code', ''))]
    retire_warns = [w for w in ver_result.warnings if "VRT" in str(getattr(w, 'code', ''))]
    for p in retire_proofs:
        print(f"  ✓ [{p.code}] {p.message}")
    for w in retire_warns:
        print(f"  ⚠ [{w.code}] {w.message}")

    print("")
    print("  ══════════════════════════════════════")

def cmd_mitosis(args: argparse.Namespace) -> int:
    """Mitosis analysis — show self-replication config and verification."""
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    program, _, _, result = _parse_and_validate(source)
    if program is None:
        return result

    mitosis_souls = [s for s in program.souls if s.mitosis is not None]
    if not mitosis_souls:
        print("No souls with mitosis blocks found.")
        return 0

    world_name = program.world.name if program.world else "Unknown"
    print(f"\n  ═══ NOUS Mitosis Analysis — {world_name} ═══")
    print()

    from verifier import verify_program, TIER_COSTS
    vresult = verify_program(program)

    for soul in mitosis_souls:
        m = soul.mitosis
        tier = soul.mind.tier.value if soul.mind else "Tier1"
        clone_tier = m.clone_tier or tier
        print(f"  ── {soul.name} ──")
        print(f"  Parent tier:     {tier}")
        print(f"  Clone tier:      {clone_tier}")
        print(f"  Max clones:      {m.max_clones}")
        print(f"  Cooldown:        {m.cooldown}")
        print(f"  Verify clones:   {m.verify}")
        print(f"  Trigger:         {m.trigger}")
        print()

    # Print mitosis-specific verification results
    mitosis_items = [i for i in vresult.items if i.category == "mitosis"]
    if mitosis_items:
        print("  ── Verification ──")
        for item in mitosis_items:
            icon = {"ERROR": "✗", "WARNING": "⚠", "INFO": "ℹ", "PROVEN": "✓"}.get(item.severity, "?")
            print(f"  {icon} [{item.code}] {item.message}")
        print()

    proven = len([i for i in mitosis_items if i.severity == "PROVEN"])
    errors = len([i for i in mitosis_items if i.severity == "ERROR"])
    warnings = len([i for i in mitosis_items if i.severity == "WARNING"])
    total_clones = sum(s.mitosis.max_clones for s in mitosis_souls)
    print(f"  ══════════════════════════════════════")
    print(f"  {len(mitosis_souls)} soul(s) with mitosis | {total_clones} max clones")
    print(f"  Verification: {proven} proven, {warnings} warnings, {errors} errors")
    return 1 if errors else 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Behavioral diff between two .nous files."""
    from behavioral_diff import diff_files
    output = diff_files(args.file, args.target, output_json=getattr(args, 'json_output', False))
    print(output)
    return 0

def cmd_cost(args: argparse.Namespace) -> int:
    """Cost Oracle — predictive cost analysis."""
    from cost_oracle import oracle_file
    output = oracle_file(args.file, period_days=getattr(args, 'period', 30), output_json=getattr(args, 'json_output', False))
    print(output)
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(prog="nous", description="NOUS — The Living Language v2.0")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("compile", help="Compile .nous to Python")
    p.add_argument("file"); p.add_argument("-o", "--output")
    p.add_argument("--node", default=None, help="Node filter for distributed compilation")
    p.add_argument("--target", default="python", choices=["python", "js", "wasm"], help="Compilation target")

    p = sub.add_parser("run", help="Compile and execute")
    p.add_argument("file"); p.add_argument("--keep", action="store_true")
    p.add_argument("--node", default=None, help="Node name for distributed execution")
    p.add_argument("--mode", default="dry-run", choices=["dry-run", "live"], help="Runtime mode")
    p.add_argument("--cycles", type=int, default=3, help="Max cycles")
    p.add_argument("--budget", type=float, default=0.33, help="Daily budget USD")

    p = sub.add_parser("validate", help="Validate .nous file")
    p.add_argument("file")

    p = sub.add_parser("typecheck", help="Type check .nous file")
    p.add_argument("file")

    p = sub.add_parser("docker", help="Generate Docker deployment")
    p.add_argument("file")
    p.add_argument("--tag", default=None, help="Docker image tag")
    p.add_argument("--port", type=int, default=8080, help="Health check port")

    p = sub.add_parser("debug", help="Interactive debugger")
    p.add_argument("file")

    p = sub.add_parser("shell", help="Interactive REPL v3")
    p.add_argument("file", nargs="?", default=None, help=".nous file to load")

    p = sub.add_parser("test", help="Run test blocks")
    p.add_argument("file")

    p = sub.add_parser("watch", help="Watch mode — auto-recompile on save")
    p.add_argument("file")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--interval", type=float, default=1.0)

    p = sub.add_parser("profile", help="Per-soul cost and performance analysis")
    p.add_argument("file")

    p = sub.add_parser("plugins", help="Plugin manager")
    p.add_argument("subcmd", choices=["list", "check"], help="Subcommand")
    p.add_argument("file", nargs="?", default=None, help=".nous file for check")

    p = sub.add_parser("pkg", help="Package manager")
    p.add_argument("subcmd", choices=["install", "list", "init", "uninstall", "publish", "registry"], help="Subcommand")
    p.add_argument("target", nargs="?", default=None, help="Package path or name")

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

    p = sub.add_parser("crossworld", help="Cross-world type check")
    p.add_argument("files", nargs="+")
    p = sub.add_parser("bench", help="Run benchmarks")
    p.add_argument("file"); p.add_argument("--save-baseline", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--runs", type=int, default=50)
    p = sub.add_parser("docs", help="Generate HTML documentation")
    p.add_argument("file"); p.add_argument("-o", "--output", help="Output path")
    p = sub.add_parser("fmt", help="Format .nous file")
    p.add_argument("file"); p.add_argument("-w", "--write", action="store_true", help="Write in-place")
    p.add_argument("--check", action="store_true", help="Check only, exit 1 if would change")

    p = sub.add_parser("noesis", help="Noesis intelligence engine")
    noesis_sub = p.add_subparsers(dest="noesis_command", required=True)
    noesis_sub.add_parser("stats", help="Lattice statistics")
    ns_p = noesis_sub.add_parser("gaps", help="Knowledge gaps")
    ns_p.add_argument("--limit", type=int, default=10)
    noesis_sub.add_parser("topics", help="Topic discovery")
    ns_p = noesis_sub.add_parser("evolve", help="Run evolution cycle")
    ns_p.add_argument("--save", action="store_true")
    ns_p = noesis_sub.add_parser("search", help="Search lattice")
    ns_p.add_argument("query"); ns_p.add_argument("--top-k", type=int, default=5)
    ns_p = noesis_sub.add_parser("think", help="Think with oracle fallback")
    ns_p.add_argument("query")
    noesis_sub.add_parser("feeds", help="Suggest feeds")
    noesis_sub.add_parser("weaning", help="Oracle weaning status")
    ns_p = noesis_sub.add_parser("export", help="Export lattice summary")
    ns_p.add_argument("--json", dest="json_export", action="store_true")

    p = sub.add_parser("build", help="Build entire workspace from nous.toml")

    p = sub.add_parser("init", help="Initialize nous.toml in current directory")
    p.add_argument("directory", nargs="?", default=None, help="Target directory")
    p.add_argument("--name", default=None, help="Project name")
    p.add_argument("--entry", default=None, help="Entry .nous file")

    p = sub.add_parser("migrate", help="Migrate Python/YAML agents to .nous")
    p.add_argument("file", help="Python file, YAML file, or directory")
    p.add_argument("-o", "--output", default=None, help="Output .nous path")

    p = sub.add_parser("viz", help="Visualize nervous system as HTML graph")
    p.add_argument("file", nargs="?", default=None, help=".nous file (or omit for workspace)")
    p.add_argument("-o", "--output", default=None, help="Output HTML path")

    p = sub.add_parser("lsp", help="Language Server Protocol / code check")
    p.add_argument("subcmd", nargs="?", default=None, choices=["check"], help="Subcommand")
    p.add_argument("target", nargs="?", default=None, help=".nous file for check mode")

    p = sub.add_parser("create", help="Generate .nous from natural language description")
    p.add_argument("description", help="Natural language description of the agent system")
    p.add_argument("-o", "--output", default=None, help="Output .nous file path")
    p.add_argument("--template-only", action="store_true", help="Use template engine only (no LLM)")

    p = sub.add_parser("verify", help="Formal verification of .nous program")
    p.add_argument("file")

    p = sub.add_parser("self-compile", help="Self-hosting: compile .nous via compiler.nous")
    p.add_argument("files", nargs="+", help=".nous files to compile")
    p.add_argument("--target", default="python", choices=["python", "js"])
    p.add_argument("-o", "--output", default=None, help="Output directory")

    p = sub.add_parser("wasm", help="Build browser-ready WASM/JS bundle")
    p.add_argument("file", help=".nous source file")
    p.add_argument("-o", "--output", default=None, help="Output path")
    p.add_argument("--target", default="html", choices=["html", "js", "mjs"], help="Output format")

    p = sub.add_parser("cost", help="Cost Oracle - predictive cost analysis")
    p.add_argument("file", help=".nous file to analyze")
    p.add_argument("--period", type=int, default=30, help="Projection period in days")
    p.add_argument("--json-output", action="store_true", dest="json_output", help="JSON output")

    sub.add_parser("version", help="Show version")

    p = sub.add_parser("dream", help="Dream system analysis")
    p.add_argument("file", help=".nous file to analyze")

    p = sub.add_parser("immune", help="Immune system analysis")
    p.add_argument("file", help=".nous file to analyze")

    p = sub.add_parser("mitosis", help="Mitosis analysis — self-replication config")
    p.add_argument("file", help=".nous file to analyze")

    p = sub.add_parser("telemetry", help="Telemetry configuration analysis")
    p.add_argument("file", help=".nous file to analyze")
    p = sub.add_parser("retire", help="Clone retirement analysis")
    p.add_argument("file", help=".nous file to analyze")
    p = sub.add_parser("diff", help="Behavioral diff between two .nous files")

    p.add_argument("file", help="Original .nous file")
    p.add_argument("target", help="Modified .nous file")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    args = ap.parse_args()
    commands = {
        "compile": cmd_compile, "run": cmd_run, "validate": cmd_validate,
        "typecheck": cmd_typecheck, "docker": cmd_docker, "debug": cmd_debug,
        "shell": cmd_shell, "test": cmd_test, "watch": cmd_watch,
        "profile": cmd_profile, "plugins": cmd_plugins, "pkg": cmd_pkg,
        "ast": cmd_ast, "evolve": cmd_evolve, "nsp": cmd_nsp,
        "info": cmd_info, "bridge": cmd_bridge, "crossworld": cmd_crossworld, "bench": cmd_bench, "docs": cmd_docs, "fmt": cmd_fmt, "noesis": cmd_noesis, "build": cmd_build, "migrate": cmd_migrate, "init": cmd_init, "viz": cmd_viz, "lsp": cmd_lsp, "wasm": cmd_wasm, "create": cmd_create, "verify": cmd_verify, "self-compile": cmd_selfcompile, "version": cmd_version, "diff": cmd_diff, "cost": cmd_cost, "mitosis": cmd_mitosis, "immune": cmd_immune, "dream": cmd_dream, "retire": cmd_retire, "telemetry": cmd_telemetry,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())




