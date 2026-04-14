path = "/opt/aetherlang_agents/nous/validator.py"
with open(path, "r") as f:
    content = f.read()

old_check_souls = '''    def _check_souls(self) -> None:'''

new_check_souls = '''    def _check_telemetry(self) -> None:
        if not self.program.world or not self.program.world.telemetry:
            return
        t = self.program.world.telemetry
        loc = "world > telemetry"

        valid_exporters = {"console", "jsonl", "http", "langfuse", "otlp"}
        if t.exporter not in valid_exporters:
            self.result.error("TL001", f"Invalid telemetry exporter: {t.exporter}. Valid: {', '.join(sorted(valid_exporters))}", loc)

        if t.exporter in ("http", "langfuse", "otlp") and not t.endpoint:
            self.result.error("TL002", f"Telemetry exporter '{t.exporter}' requires an endpoint URL.", loc)

        if not (0.0 < t.sample_rate <= 1.0):
            self.result.error("TL003", f"Telemetry sample_rate must be in (0.0, 1.0], got {t.sample_rate}", loc)

        if t.buffer_size < 10:
            self.result.warn("TL004", f"Telemetry buffer_size={t.buffer_size} is very small. Recommended >= 100.", loc)

    def _check_souls(self) -> None:'''

if old_check_souls in content:
    content = content.replace(old_check_souls, new_check_souls)

old_validate_call = '''        self._check_world_exists()'''

if old_validate_call in content and '_check_telemetry' not in content.split('_check_world_exists')[0]:
    content = content.replace(
        '        self._check_world_exists()',
        '        self._check_world_exists()\n        self._check_telemetry()'
    )

with open(path, "w") as f:
    f.write(content)
print("PATCH T4 OK — validator: TL001-TL004 rules")
