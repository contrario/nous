path = "/opt/aetherlang_agents/nous/codegen.py"
with open(path, "r") as f:
    content = f.read()

old_imports = '''        has_dream = any(s.dream_system for s in self.program.souls)
        if has_dream:
            self._emit("from dream_engine import DreamEngine, DreamConfig")'''
new_imports = '''        has_symbiosis = any(s.symbiosis for s in self.program.souls)
        if has_symbiosis:
            self._emit("from symbiosis_engine import SymbiosisEngine, BondConfig")
        has_dream = any(s.dream_system for s in self.program.souls)
        if has_dream:
            self._emit("from dream_engine import DreamEngine, DreamConfig")'''
if old_imports in content:
    content = content.replace(old_imports, new_imports)

old_rt_mitosis = '''        self._emit("rt._mitosis_engine = mitosis")
            self._emit_blank()'''

# Find where to insert symbiosis engine wiring - after return rt
old_return = '''    return rt'''
# Actually, let's insert before the return
old_emit_return = '''        self._emit("return rt")'''

# Find the build_runtime's return statement
# Insert symbiosis engine before the final return
import re
# Find "rt._mitosis_engine = mitosis" line and the section after all engines
# Better approach: add after dream engine section, before return

old_return_emit = '        self._emit("return rt")'
if old_return_emit in content and 'SymbiosisEngine' not in content:
    sym_block = '''
        has_symbiosis = any(s.symbiosis for s in self.program.souls)
        if has_symbiosis:
            self._emit_blank()
            self._emit("# ═══ Symbiosis Engine ═══")
            self._emit("symbiosis = SymbiosisEngine(rt)")
            for soul in self.program.souls:
                if soul.symbiosis:
                    sym = soul.symbiosis
                    sn = soul.name
                    bond_list = "[" + ", ".join(f'"{b}"' for b in sym.bond_with) + "]"
                    shared_list = "[" + ", ".join(f'"{f}"' for f in sym.shared_memory) + "]"
                    sync_s = self._duration_to_seconds(sym.sync_interval)
                    self._emit(f"symbiosis.register(BondConfig(")
                    self._indent()
                    self._emit(f'soul_name="{sn}",')
                    self._emit(f"bond_with={bond_list},")
                    self._emit(f"shared_fields={shared_list},")
                    self._emit(f"sync_interval_seconds={sync_s},")
                    self._emit(f"evolve_together={sym.evolve_together},")
                    self._dedent()
                    self._emit(f"))")
            self._emit("rt._symbiosis_engine = symbiosis")
            self._emit_blank()

''' + '        self._emit("return rt")'
    content = content.replace(old_return_emit, sym_block, 1)

with open(path, "w") as f:
    f.write(content)
print("PATCH S7 OK — codegen: symbiosis engine wiring")
