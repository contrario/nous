#!/usr/bin/env python3
"""Wire tool_validator into validator.py"""
from pathlib import Path

BASE = Path("/opt/aetherlang_agents/nous")

p = BASE / "validator.py"
c = p.read_text()

if "tool_validator" in c:
    print("[SKIP] Already patched")
    raise SystemExit(0)

# Add import
c = c.replace(
    "from ast_nodes import",
    "from tool_validator import validate_sense_args\nfrom ast_nodes import",
)

# Add tool validation call before return result
# Find the last 'return result' in the validate function
idx = c.rfind("return result")
if idx == -1:
    print("[ERROR] 'return result' not found")
    raise SystemExit(1)

insert = (
    "    # T002: Tool argument validation\n"
    "    tool_warnings = validate_sense_args(program)\n"
    "    result.warnings.extend(tool_warnings)\n\n"
    "    "
)

c = c[:idx] + insert + c[idx:]

p.write_text(c)
print("[OK] tool_validator wired into validator.py")
