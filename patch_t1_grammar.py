path = "/opt/aetherlang_agents/nous/nous.lark"
with open(path, "r") as f:
    content = f.read()

old = 'world_body: law_decl | heartbeat_decl | timezone_decl | config_assign'
new = 'world_body: law_decl | heartbeat_decl | timezone_decl | telemetry_block | config_assign'

if old in content:
    content = content.replace(old, new)

telemetry_grammar = '''
// ═══════════════════════════════════════════
// TELEMETRY — τηλεμετρία
// ═══════════════════════════════════════════

telemetry_block: TELEMETRY "{" telemetry_field* "}"
telemetry_field: "enabled" ":" BOOL                -> telemetry_enabled
               | "exporter" ":" NAME               -> telemetry_exporter
               | "endpoint" ":" STRING             -> telemetry_endpoint
               | "sample_rate" ":" (FLOAT | INT)   -> telemetry_sample_rate
               | "trace_senses" ":" BOOL           -> telemetry_trace_senses
               | "trace_llm" ":" BOOL              -> telemetry_trace_llm
               | "buffer_size" ":" INT             -> telemetry_buffer_size

'''

old_mitosis_block = 'mitosis_block: MITOSIS "{" mitosis_field* "}"'
if old_mitosis_block in content:
    content = content.replace(old_mitosis_block, telemetry_grammar + old_mitosis_block)

old_keywords = 'MITOSIS.2: "mitosis" | "μίτωση"'
new_keywords = 'TELEMETRY.2: "telemetry" | "τηλεμετρία"\nMITOSIS.2: "mitosis" | "μίτωση"'
if old_keywords in content:
    content = content.replace(old_keywords, new_keywords)

with open(path, "w") as f:
    f.write(content)
print("PATCH T1 OK — grammar: telemetry_block added to world_body")
