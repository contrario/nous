path = "/opt/aetherlang_agents/nous/codegen.py"
with open(path, "r") as f:
    content = f.read()

old_clone_factory = '''        self._emit("@classmethod")
        self._emit("def clone_factory(cls, clone_name: str, clone_tier: str | None, runtime: NousRuntime) -> 'Soul_" + soul.name + "':")
        self._indent()
        self._emit(f"clone = cls(runtime)")
        self._emit(f"clone.name = clone_name")
        if soul.mind:
            self._emit(f'clone.tier = clone_tier or "{soul.mind.tier.value}"')
        self._emit(f"return clone")
        self._dedent()'''

new_clone_factory = '''        if m.retire_trigger is not None:
            self._emit("def _retire_check(self, _metrics=None) -> bool:")
            self._indent()
            self._emit("metrics = {")
            self._indent()
            self._emit(f'"cycle_count": self.cycle_count,')
            self._emit(f'"queue_depth": getattr(self, "_queue_depth", 0),')
            self._emit(f'"latency": getattr(self, "_last_latency", 0.0),')
            self._emit(f'"error_count": getattr(self, "_error_count", 0),')
            if soul.memory:
                for f in soul.memory.fields:
                    self._emit(f'"{f.name}": self.{f.name},')
            self._dedent()
            self._emit("}")
            retire_code = self._expr_to_python(m.retire_trigger)
            retire_code = retire_code.replace("scan_count", 'metrics.get("scan_count", 0)')
            retire_code = retire_code.replace("queue_depth", 'metrics.get("queue_depth", 0)')
            retire_code = retire_code.replace("latency", 'metrics.get("latency", 0)')
            retire_code = retire_code.replace("error_count", 'metrics.get("error_count", 0)')
            retire_code = retire_code.replace("cycle_count", 'metrics.get("cycle_count", 0)')
            if soul.memory:
                for f in soul.memory.fields:
                    if f.name not in ("scan_count", "queue_depth", "latency", "error_count", "cycle_count"):
                        retire_code = retire_code.replace(f.name, f'metrics.get("{f.name}", 0)')
            self._emit(f"return {retire_code}")
            self._dedent()
            self._emit_blank()

        self._emit("@classmethod")
        self._emit("def clone_factory(cls, clone_name: str, clone_tier: str | None, runtime: NousRuntime) -> 'Soul_" + soul.name + "':")
        self._indent()
        self._emit(f"clone = cls(runtime)")
        self._emit(f"clone.name = clone_name")
        if soul.mind:
            self._emit(f'clone.tier = clone_tier or "{soul.mind.tier.value}"')
        self._emit(f"return clone")
        self._dedent()'''

if old_clone_factory in content:
    content = content.replace(old_clone_factory, new_clone_factory)

old_register = '''                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")
                    self._dedent()
                    self._emit(")")
            self._emit("rt._mitosis_engine = mitosis")'''

new_register = '''                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")'''

if old_register in content:
    content = content.replace(old_register, new_register)

    retire_block = '''                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")
                    if m.retire_trigger is not None:
                        listen_ch = f'"{soul.name}"' if soul.name in self._listeners else "None"
                        self._emit(f")")
                        retire_cd = self._duration_to_seconds(m.retire_cooldown)
                        self._emit(f"mitosis._configs[\\"{sn}\\"].retire_trigger_fn = _soul_{sn.lower()}._retire_check")
                        self._emit(f"mitosis._configs[\\"{sn}\\"].retire_cooldown_seconds = {retire_cd}")
                        self._emit(f"mitosis._configs[\\"{sn}\\"].min_clones = {m.min_clones}")
                    else:
                        self._emit(f")")
                    self._dedent()
            self._emit("rt._mitosis_engine = mitosis")'''

    content = content.replace(
        '''                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")''',
        retire_block,
        1
    )

with open(path, "w") as f:
    f.write(content)
print("PATCH 8 OK — codegen updated with retirement emit")
