path = "/opt/aetherlang_agents/nous/codegen.py"
with open(path, "r") as f:
    content = f.read()

old = '''                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")
                    if m.retire_trigger is not None:
                        listen_ch = f\'"{soul.name}"\' if soul.name in self._listeners else "None"
                        self._emit(f")")
                        retire_cd = self._duration_to_seconds(m.retire_cooldown)
                        self._emit(f"mitosis._configs[\\"{sn}\\"].retire_trigger_fn = _soul_{sn.lower()}._retire_check")
                        self._emit(f"mitosis._configs[\\"{sn}\\"].retire_cooldown_seconds = {retire_cd}")
                        self._emit(f"mitosis._configs[\\"{sn}\\"].min_clones = {m.min_clones}")
                    else:
                        self._emit(f")")
                    self._dedent()'''

new = '''                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")
                    self._dedent()
                    self._emit(f")")
                    if m.retire_trigger is not None:
                        retire_cd = self._duration_to_seconds(m.retire_cooldown)
                        self._emit(f"mitosis._configs[\\"{sn}\\"].retire_trigger_fn = _soul_{sn.lower()}._retire_check")
                        self._emit(f"mitosis._configs[\\"{sn}\\"].retire_cooldown_seconds = {retire_cd}")
                        self._emit(f"mitosis._configs[\\"{sn}\\"].min_clones = {m.min_clones}")'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 8b OK — codegen indentation fixed")
else:
    print("PATCH 8b SKIP — pattern not found")
