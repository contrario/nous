path = "/opt/aetherlang_agents/nous/cli.py"
with open(path, "r") as f:
    content = f.read()

content = content.replace('VERSION = "3.5.0"', 'VERSION = "3.6.0"')

if "cmd_telemetry" not in content:
    telemetry_cmd = '''

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

'''

    old_cmd_retire = "def cmd_retire(args: Any) -> None:"
    if old_cmd_retire in content:
        content = content.replace(old_cmd_retire, telemetry_cmd + old_cmd_retire)

old_retire_subparser = '    p = sub.add_parser("retire"'
new_telemetry_subparser = '''    p = sub.add_parser("telemetry", help="Telemetry configuration analysis")
    p.add_argument("file", help=".nous file to analyze")
    p = sub.add_parser("retire"'''

if old_retire_subparser in content:
    content = content.replace(old_retire_subparser, new_telemetry_subparser)

old_dispatch = '"retire": cmd_retire,'
new_dispatch = '"retire": cmd_retire, "telemetry": cmd_telemetry,'
if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch)

with open(path, "w") as f:
    f.write(content)
print("PATCH T9 OK — CLI: telemetry command, version 3.6.0, 40 commands")
