path = "/opt/aetherlang_agents/nous/nous.lark"
with open(path, "r") as f:
    content = f.read()

old = '         | dream_system_block'
new = '         | dream_system_block\n         | symbiosis_block'
if old in content and 'symbiosis_block' not in content:
    content = content.replace(old, new)

symbiosis_grammar = '''
// ═══════════════════════════════════════════
// SYMBIOSIS — συμβίωση
// ═══════════════════════════════════════════

symbiosis_block: SYMBIOSIS "{" symbiosis_field* "}"
symbiosis_field: "bond_with" ":" "[" name_list "]"        -> symbiosis_bond
               | "shared_memory" ":" "[" name_list "]"    -> symbiosis_shared_memory
               | "sync_interval" ":" duration_lit         -> symbiosis_sync_interval
               | "evolve_together" ":" BOOL               -> symbiosis_evolve_together

'''

old_telemetry = 'TELEMETRY.2: "telemetry" | "τηλεμετρία"'
new_telemetry = 'SYMBIOSIS.2: "symbiosis" | "συμβίωση"\nTELEMETRY.2: "telemetry" | "τηλεμετρία"'
if old_telemetry in content and 'SYMBIOSIS' not in content:
    content = content.replace(old_telemetry, new_telemetry)

old_mitosis_block = 'mitosis_block: MITOSIS "{" mitosis_field* "}"'
if old_mitosis_block in content and 'symbiosis_block' not in content:
    content = content.replace(old_mitosis_block, symbiosis_grammar + old_mitosis_block)

with open(path, "w") as f:
    f.write(content)
print("PATCH S1 OK — grammar: symbiosis_block")
