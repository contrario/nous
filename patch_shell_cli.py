#!/usr/bin/env python3
"""Patch cli.py to add 'nous shell' command."""
from pathlib import Path

p = Path("/opt/aetherlang_agents/nous/cli.py")
c = p.read_text()

if "cmd_shell" in c:
    print("[SKIP] Already patched")
    raise SystemExit(0)

c = c.replace(
    "from watch import watch",
    "from watch import watch\nfrom shell import start_repl",
)

cmd_shell = '''
def cmd_shell(args: argparse.Namespace) -> int:
    source = Path(args.file) if args.file else None
    if source and not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1
    return start_repl(source)

'''
c = c.replace("\ndef main()", cmd_shell + "\ndef main()")

c = c.replace(
    '    p = sub.add_parser("watch"',
    '    p = sub.add_parser("shell", help="Interactive REPL")\n'
    '    p.add_argument("file", nargs="?", default=None, help=".nous file to load")\n\n'
    '    p = sub.add_parser("watch"',
)

c = c.replace(
    '"watch": cmd_watch,',
    '"watch": cmd_watch, "shell": cmd_shell,',
)

p.write_text(c)
print("[OK] CLI patched: nous shell [file.nous]")
