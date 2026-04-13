#!/usr/bin/env python3
"""Patch cli.py to add 'nous watch' command."""
from pathlib import Path

p = Path("/opt/aetherlang_agents/nous/cli.py")
c = p.read_text()

if "cmd_watch" in c:
    print("Already patched")
    raise SystemExit(0)

# 1. Add import
c = c.replace(
    "from codegen import generate_python",
    "from codegen import generate_python\nfrom watch import watch",
)

# 2. Add cmd_watch function before main()
cmd_watch = '''
def cmd_watch(args: argparse.Namespace) -> int:
    sources = [Path(f) for f in args.files]
    return watch(sources, poll=args.interval)

'''
c = c.replace("\ndef main()", cmd_watch + "\ndef main()")

# 3. Add subparser
c = c.replace(
    '    sub.add_parser("version"',
    '    p = sub.add_parser("watch", help="Watch and hot-reload on changes")\n'
    '    p.add_argument("files", nargs="+", help=".nous files to watch")\n'
    '    p.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds")\n\n'
    '    sub.add_parser("version"',
)

# 4. Add to dispatch
c = c.replace(
    '"version": cmd_version,',
    '"version": cmd_version, "watch": cmd_watch,',
)

p.write_text(c)
print("CLI patched: nous watch <files> [--interval N]")
