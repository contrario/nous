path = "/opt/aetherlang_agents/nous/runtime.py"
with open(path, "r") as f:
    content = f.read()

old_runtime_init_engines = '''        self._mitosis_engine: Optional[Any] = None
        self._immune_engine: Optional[Any] = None
        self._dream_engine: Optional[Any] = None'''

new_runtime_init_engines = '''        self._mitosis_engine: Optional[Any] = None
        self._immune_engine: Optional[Any] = None
        self._dream_engine: Optional[Any] = None
        self._telemetry_engine: Optional[Any] = None'''

if old_runtime_init_engines in content:
    content = content.replace(old_runtime_init_engines, new_runtime_init_engines)

old_tg_dream = '''                if self._dream_engine:
                    tg.create_task(self._dream_engine.run())'''

new_tg_dream = '''                if self._dream_engine:
                    tg.create_task(self._dream_engine.run())
                if self._telemetry_engine:
                    tg.create_task(self._telemetry_engine.run())'''

if old_tg_dream in content:
    content = content.replace(old_tg_dream, new_tg_dream)

old_shutdown_dream = '''        if self._dream_engine:
            self._dream_engine.stop()'''

new_shutdown_dream = '''        if self._dream_engine:
            self._dream_engine.stop()
        if self._telemetry_engine:
            self._telemetry_engine.stop()'''

if old_shutdown_dream in content:
    content = content.replace(old_shutdown_dream, new_shutdown_dream)

old_heartbeat_log = '''        log.info(f"Soul [{self.name}]: cycle {self._cycle_count} complete ({_latency_ms:.0f}ms)")'''

new_heartbeat_log = '''        log.info(f"Soul [{self.name}]: cycle {self._cycle_count} complete ({_latency_ms:.0f}ms)")
        if hasattr(self, '_telemetry_engine') and self._telemetry_engine and self._telemetry_engine.enabled:
            _tspan = self._telemetry_engine.start_span(
                kind=__import__('telemetry_engine').SpanKind.CYCLE,
                soul_name=self.name,
                cycle_count=self._cycle_count,
                latency_ms=round(_latency_ms, 2),
                wake_strategy=self.wake_strategy,
            )
            _tspan.end_time = time.time()
            _tspan.start_time = _t0
            import asyncio as _aio
            _aio.ensure_future(self._telemetry_engine.record(_tspan))'''

if old_heartbeat_log in content:
    content = content.replace(old_heartbeat_log, new_heartbeat_log, 1)

old_soul_runner_init_end = '''        self._immune_engine: Optional[Any] = None
        self._dream_engine: Optional[Any] = None
        self._shutdown_event: Optional[asyncio.Event] = None'''

new_soul_runner_init_end = '''        self._immune_engine: Optional[Any] = None
        self._dream_engine: Optional[Any] = None
        self._telemetry_engine: Optional[Any] = None
        self._shutdown_event: Optional[asyncio.Event] = None'''

if old_soul_runner_init_end in content:
    content = content.replace(old_soul_runner_init_end, new_soul_runner_init_end)

old_add_soul_append = '''        runner._immune_engine = self._immune_engine
        self._runners.append(runner)'''

new_add_soul_append = '''        runner._immune_engine = self._immune_engine
        runner._telemetry_engine = self._telemetry_engine
        self._runners.append(runner)'''

if old_add_soul_append in content:
    content = content.replace(old_add_soul_append, new_add_soul_append)

with open(path, "w") as f:
    f.write(content)
print("PATCH T8 OK — runtime: telemetry engine integration")
