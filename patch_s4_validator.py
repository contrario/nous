path = "/opt/aetherlang_agents/nous/validator.py"
with open(path, "r") as f:
    content = f.read()

old = '''            if soul.mitosis:
                self._check_mitosis(soul)'''
new = '''            if soul.symbiosis:
                self._check_symbiosis(soul)
            if soul.mitosis:
                self._check_mitosis(soul)'''
if old in content and '_check_symbiosis' not in content:
    content = content.replace(old, new)

old_check_mitosis = '''    def _check_mitosis(self, soul: SoulNode) -> None:'''
new_check_symbiosis = '''    def _check_symbiosis(self, soul: SoulNode) -> None:
        loc = f"soul {soul.name} > symbiosis"
        sym = soul.symbiosis
        soul_names = {s.name for s in self.program.souls}

        if not sym.bond_with:
            self.result.error("SY001", f"Symbiosis bond_with is empty. Must bond with at least one soul.", loc)

        for bond_name in sym.bond_with:
            if bond_name not in soul_names:
                self.result.error("SY002", f"Bond target '{bond_name}' does not exist.", loc)
            if bond_name == soul.name:
                self.result.error("SY003", f"Soul cannot bond with itself.", loc)

        if sym.shared_memory:
            if soul.memory is None:
                self.result.error("SY004", f"Shared memory fields declared but soul has no memory block.", loc)
            else:
                mem_fields = {f.name for f in soul.memory.fields}
                for field_name in sym.shared_memory:
                    if field_name not in mem_fields:
                        self.result.error("SY005", f"Shared field '{field_name}' not found in soul memory.", loc)

        for bond_name in sym.bond_with:
            bond_soul = next((s for s in self.program.souls if s.name == bond_name), None)
            if bond_soul and sym.shared_memory:
                if bond_soul.memory is None:
                    self.result.warn("SY006", f"Bond target '{bond_name}' has no memory block. Shared fields will be injected at runtime.", loc)

        if sym.evolve_together and soul.dna is None:
            self.result.warn("SY007", f"evolve_together=true but soul has no dna block.", loc)

        import re
        m = re.match(r"(\d+)(ms|s|m|h)", sym.sync_interval)
        if m:
            val, unit = int(m.group(1)), m.group(2)
            seconds = {"ms": val/1000, "s": val, "m": val*60, "h": val*3600}[unit]
            if seconds < 1:
                self.result.warn("SY008", f"sync_interval {sym.sync_interval} is very fast. May cause overhead.", loc)

    def _check_mitosis(self, soul: SoulNode) -> None:'''

if old_check_mitosis in content and '_check_symbiosis' not in content:
    content = content.replace(old_check_mitosis, new_check_symbiosis)

with open(path, "w") as f:
    f.write(content)
print("PATCH S4 OK — validator: SY001-SY008")
