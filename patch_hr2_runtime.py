path = "/opt/aetherlang_agents/nous/runtime.py"
with open(path, "r") as f:
    content = f.read()

old = '        self._telemetry_engine: Optional[Any] = None'
new = '        self._telemetry_engine: Optional[Any] = None\n        self._hot_reload_engine: Optional[Any] = None'
if old in content and '_hot_reload_engine' not in content:
    content = content.replace(old, new, 1)

old_tg = '''                if self._telemetry_engine:
                    tg.create_task(self._telemetry_engine.run())'''
new_tg = '''                if self._telemetry_engine:
                    tg.create_task(self._telemetry_engine.run())
                if self._hot_reload_engine:
                    tg.create_task(self._hot_reload_engine.run())'''
if old_tg in content:
    content = content.replace(old_tg, new_tg)

old_shutdown = '''        if self._telemetry_engine:
            self._telemetry_engine.stop()'''
new_shutdown = '''        if self._telemetry_engine:
            self._telemetry_engine.stop()
        if self._hot_reload_engine:
            self._hot_reload_engine.stop()'''
if old_shutdown in content:
    content = content.replace(old_shutdown, new_shutdown)

with open(path, "w") as f:
    f.write(content)
print("PATCH HR2 OK — runtime: hot reload engine lifecycle")
