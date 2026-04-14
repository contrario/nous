path = "/opt/aetherlang_agents/nous/cli.py"
with open(path, "r") as f:
    content = f.read()

content = content.replace('VERSION = "3.7.0"', 'VERSION = "3.8.0"')

if "cmd_symbiosis" not in content:
    sym_cmd = '''
def cmd_symbiosis(args: Any) -> None:
    """Show symbiosis bonds and shared memory analysis."""
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
    print("  ═══ NOUS Symbiosis Analysis ═══")
    print("")

    sym_souls = [s for s in program.souls if s.symbiosis is not None]
    if not sym_souls:
        print("  No souls with symbiosis found.")
        return

    for soul in sym_souls:
        sym = soul.symbiosis
        print(f"  ── {soul.name} ──")
        print(f"  Bonds:            {', '.join(sym.bond_with)}")
        print(f"  Shared memory:    {', '.join(sym.shared_memory) if sym.shared_memory else '—'}")
        print(f"  Sync interval:    {sym.sync_interval}")
        print(f"  Evolve together:  {sym.evolve_together}")
        print("")

    sy_proofs = [p for p in ver_result.proven if "VSY" in str(getattr(p, 'code', ''))]
    sy_warns = [w for w in ver_result.warnings if "VSY" in str(getattr(w, 'code', ''))]
    for p in sy_proofs:
        print(f"  \\u2713 [{p.code}] {p.message}")
    for w in sy_warns:
        print(f"  \\u26a0 [{w.code}] {w.message}")

    print("")
    print("  \\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550")

'''
    old_telemetry_cmd = "def cmd_telemetry(args: Any) -> None:"
    if old_telemetry_cmd in content:
        content = content.replace(old_telemetry_cmd, sym_cmd + old_telemetry_cmd)

old_telemetry_sub = '    p = sub.add_parser("telemetry"'
new_sym_sub = '''    p = sub.add_parser("symbiosis", help="Symbiosis bond analysis")
    p.add_argument("file", help=".nous file to analyze")
    p = sub.add_parser("telemetry"'''
if old_telemetry_sub in content:
    content = content.replace(old_telemetry_sub, new_sym_sub)

old_dispatch = '"telemetry": cmd_telemetry,'
new_dispatch = '"telemetry": cmd_telemetry, "symbiosis": cmd_symbiosis,'
if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch)

with open(path, "w") as f:
    f.write(content)
print("PATCH S9 OK — CLI: symbiosis command, v3.8.0, 41 commands")
