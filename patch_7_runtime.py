path = "/opt/aetherlang_agents/nous/runtime.py"
with open(path, "r") as f:
    content = f.read()

old_add_soul = '''    def add_soul(self, runner: SoulRunner) -> None:
        runner.set_shutdown_event(self._shutdown)
        runner._cost_tracker = self.cost_tracker
        runner._sense_cache = self.sense_cache
        runner._immune_engine = self._immune_engine
        self._runners.append(runner)'''

new_add_soul = '''    def add_soul(self, runner: SoulRunner) -> None:
        runner.set_shutdown_event(self._shutdown)
        runner._cost_tracker = self.cost_tracker
        runner._sense_cache = self.sense_cache
        runner._immune_engine = self._immune_engine
        self._runners.append(runner)

    def remove_soul(self, name: str) -> bool:
        for i, runner in enumerate(self._runners):
            if runner.name == name:
                runner.stop()
                self._runners.pop(i)
                log.info(f"Soul [{name}]: removed from runtime ({len(self._runners)} remaining)")
                return True
        log.warning(f"Soul [{name}]: not found in runtime for removal")
        return False'''

if old_add_soul in content:
    content = content.replace(old_add_soul, new_add_soul)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 7 OK — runtime updated with remove_soul()")
else:
    print("PATCH 7 SKIP — pattern not found")
