path = "/opt/aetherlang_agents/nous/codegen.py"
with open(path, "r") as f:
    content = f.read()

old_imports_dream = '''        has_dream = any(s.dream_system for s in self.program.souls)
        if has_dream:
            self._emit("from dream_engine import DreamEngine, DreamConfig")'''

new_imports_dream = '''        has_telemetry = self.program.world and self.program.world.telemetry and self.program.world.telemetry.enabled
        if has_telemetry:
            self._emit("from telemetry_engine import TelemetryEngine, TelemetryConfig, SpanKind, SpanStatus")
        has_dream = any(s.dream_system for s in self.program.souls)
        if has_dream:
            self._emit("from dream_engine import DreamEngine, DreamConfig")'''

if old_imports_dream in content:
    content = content.replace(old_imports_dream, new_imports_dream)

old_rt_create = '''        self._emit(f"rt = NousRuntime(")
        self._indent()
        self._emit(f'world_name="{world_name}",')
        self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
        self._emit(f"cost_ceiling=COST_CEILING,")
        self._dedent()
        self._emit(")")'''

new_rt_create = '''        self._emit(f"rt = NousRuntime(")
        self._indent()
        self._emit(f'world_name="{world_name}",')
        self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
        self._emit(f"cost_ceiling=COST_CEILING,")
        self._dedent()
        self._emit(")")'''

has_telemetry_block = '''
        has_telemetry = self.program.world and self.program.world.telemetry and self.program.world.telemetry.enabled
        if has_telemetry:
            t = self.program.world.telemetry'''

if old_rt_create in content and "# ═══ Telemetry Engine ═══" not in content:
    insert_point = old_rt_create + "\n        self._emit_blank()"
    telemetry_emit = old_rt_create + '''
        if has_telemetry:
            t = self.program.world.telemetry
            self._emit_blank()
            self._emit("# ═══ Telemetry Engine ═══")
            endpoint_str = f'"{t.endpoint}"' if t.endpoint else "None"
            self._emit(f"_telemetry = TelemetryEngine(TelemetryConfig(")
            self._indent()
            self._emit(f"enabled=True,")
            self._emit(f'exporter="{t.exporter}",')
            self._emit(f"endpoint={endpoint_str},")
            self._emit(f"sample_rate={t.sample_rate},")
            self._emit(f"trace_senses={t.trace_senses},")
            self._emit(f"trace_llm={t.trace_llm},")
            self._emit(f"buffer_size={t.buffer_size},")
            self._dedent()
            self._emit(f"))")
            self._emit(f"rt._telemetry_engine = _telemetry")'''

    content = content.replace(old_rt_create, telemetry_emit)

with open(path, "w") as f:
    f.write(content)
print("PATCH T7 OK — codegen: telemetry engine wiring")
