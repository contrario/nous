path = "/opt/aetherlang_agents/nous/cli.py"
with open(path, "r") as f:
    content = f.read()

content = content.replace('__version__ = "3.4.0"', '__version__ = "3.5.0"')

if "cmd_retire" not in content:
    retire_cmd = '''

def cmd_retire(args: Any) -> None:
    """Show clone retirement analysis for a .nous program."""
    from parser import NousParser
    from validator import NousValidator
    from verifier import NousVerifier

    source = Path(args.file).read_text()
    parser = NousParser()
    program = parser.parse(source)

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
'''

    if "def cmd_mitosis" in content:
        idx = content.index("def cmd_mitosis")
        content = content[:idx] + retire_cmd + "\n" + content[idx:]

    if 'sub = subparsers.add_parser("mitosis"' in content:
        retire_parser = '''
    sub = subparsers.add_parser("retire", help="Clone retirement analysis")
    sub.add_argument("file")
    sub.set_defaults(func=cmd_retire)
'''
        idx = content.index('sub = subparsers.add_parser("mitosis"')
        content = content[:idx] + retire_parser + "\n    " + content[idx:]

with open(path, "w") as f:
    f.write(content)
print("PATCH 9 OK — CLI updated with retire command, version 3.5.0")
