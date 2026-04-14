path = "/opt/aetherlang_agents/nous/cli.py"
with open(path, "r") as f:
    content = f.read()

content = content.replace('VERSION = "3.6.0"', 'VERSION = "3.7.0"')

old_run = '''def cmd_run(args: argparse.Namespace) -> int:
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
        print("\\n\\nWorld stopped by user.")
        return 0
    except Exception as e:
        print(f"Runtime error: {e}", file=sys.stderr)
        return 1'''

new_run = '''def cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    hot = getattr(args, "hot", False)
    mode = getattr(args, "mode", "dry-run")
    cycles = getattr(args, "cycles", 3)
    budget = getattr(args, "budget", 0.33)
    if hot:
        return _run_hot_reload(source)
    try:
        from nous_ast_runner import run_program
        run_program(str(source), mode=mode, max_cycles=cycles, daily_budget=budget)
        return 0
    except KeyboardInterrupt:
        print("\\n\\nWorld stopped by user.")
        return 0
    except Exception as e:
        print(f"Runtime error: {e}", file=sys.stderr)
        return 1


def _run_hot_reload(source: Path) -> int:
    """Run with hot reload: watches source, swaps souls on change."""
    import asyncio
    from parser import parse_nous
    from validator import NousValidator
    from codegen import NousCodeGen
    import importlib.util
    import tempfile
    import py_compile as _pyc

    print(f"\\n  ═══ NOUS Hot Reload Mode ═══")
    print(f"  Source:  {source}")
    print(f"  Edit {source.name}, save, and souls swap live.")
    print(f"  Press Ctrl+C to stop.\\n")

    src_text = source.read_text(encoding="utf-8")
    program = parse_nous(src_text)
    v = NousValidator(program)
    vr = v.validate()
    if not vr.ok:
        for e in vr.errors:
            print(f"  ERROR: {e}")
        return 1

    cg = NousCodeGen(program)
    code = cg.generate()

    tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False,
                                      dir=str(source.parent), prefix="_hot_init_")
    tmp.write(code)
    tmp.close()
    tmp_path = Path(tmp.name)

    try:
        _pyc.compile(str(tmp_path), doraise=True)
    except _pyc.PyCompileError as e:
        print(f"  Compile FAILED: {e}")
        tmp_path.unlink(missing_ok=True)
        return 1

    spec = importlib.util.spec_from_file_location("_hot_init", str(tmp_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tmp_path.unlink(missing_ok=True)

    if not hasattr(mod, 'build_runtime'):
        print("  Error: generated code has no build_runtime()")
        return 1

    rt = mod.build_runtime()

    from hot_reload_engine import HotReloadEngine
    hr = HotReloadEngine(rt, source, poll_interval=2.0)
    rt._hot_reload_engine = hr

    world_name = program.world.name if program.world else "Unknown"
    print(f"  World:   {world_name}")
    print(f"  Souls:   {len(program.souls)}")
    print(f"  Hot reload active (polling every 2s)\\n")

    try:
        asyncio.run(rt.run())
    except KeyboardInterrupt:
        print("\\n\\n  World stopped by user.")
    return 0'''

if old_run in content:
    content = content.replace(old_run, new_run)

# Add --hot flag to run subparser
old_run_parser = 'sub = subparsers.add_parser("run", help="Run a .nous program")'
if old_run_parser in content:
    # Find the run subparser section and add --hot
    idx = content.index(old_run_parser)
    # Find next add_argument after file
    file_arg_str = 'p.add_argument("file"'
    # Search for the run parser's file argument
    search_start = idx
    # Look for the pattern where run arguments are added
    pass

# Try to find where run arguments are set
import re
run_section = re.search(r'(sub = subparsers\.add_parser\("run".*?\n(?:.*?p\.add_argument.*?\n)*)', content)

# Simpler approach: add --hot after the run subparser's file argument
old_run_args = '''    sub = subparsers.add_parser("run", help="Run a .nous program")
    sub.add_argument("file"'''

if old_run_args not in content:
    # Try different pattern
    pass

# Find run subparser setup
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'add_parser("run"' in line:
        # Find next line with add_argument that doesn't have --hot
        for j in range(i+1, min(i+10, len(lines))):
            if '--hot' in lines[j]:
                break
            if 'add_parser(' in lines[j] and 'run' not in lines[j]:
                # Insert --hot before next subparser
                lines.insert(j, '    sub.add_argument("--hot", action="store_true", help="Enable hot reload — swap souls on save")')
                break
            if lines[j].strip().startswith('sub.add_argument') and 'file' not in lines[j] and 'mode' not in lines[j] and 'cycles' not in lines[j] and 'budget' not in lines[j]:
                lines.insert(j, '    sub.add_argument("--hot", action="store_true", help="Enable hot reload — swap souls on save")')
                break
        break

content = '\n'.join(lines)

with open(path, "w") as f:
    f.write(content)
print("PATCH HR3 OK — CLI: --hot flag on nous run, version 3.7.0")
