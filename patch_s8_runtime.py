path = "/opt/aetherlang_agents/nous/runtime.py"
with open(path, "r") as f:
    content = f.read()

old = '        self._hot_reload_engine: Optional[Any] = None'
new = '        self._hot_reload_engine: Optional[Any] = None\n        self._symbiosis_engine: Optional[Any] = None'
if old in content and '_symbiosis_engine' not in content:
    content = content.replace(old, new)

old_tg = '''                if self._hot_reload_engine:
                    tg.create_task(self._hot_reload_engine.run())'''
new_tg = '''                if self._symbiosis_engine:
                    tg.create_task(self._symbiosis_engine.run())
                if self._hot_reload_engine:
                    tg.create_task(self._hot_reload_engine.run())'''
if old_tg in content:
    content = content.replace(old_tg, new_tg)

old_shutdown = '''        if self._hot_reload_engine:
            self._hot_reload_engine.stop()'''
new_shutdown = '''        if self._symbiosis_engine:
            self._symbiosis_engine.stop()
        if self._hot_reload_engine:
            self._hot_reload_engine.stop()'''
if old_shutdown in content:
    content = content.replace(old_shutdown, new_shutdown)

with open(path, "w") as f:
    f.write(content)
print("PATCH S8 OK — runtime: symbiosis engine lifecycle")
