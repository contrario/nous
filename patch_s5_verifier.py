path = "/opt/aetherlang_agents/nous/verifier.py"
with open(path, "r") as f:
    content = f.read()

old = '''        self._verify_telemetry()
        self._verify_mitosis()'''
new = '''        self._verify_telemetry()
        self._verify_symbiosis()
        self._verify_mitosis()'''
if old in content:
    content = content.replace(old, new)

old_cats = '"telemetry", "mitosis"'
new_cats = '"telemetry", "symbiosis", "mitosis"'
if old_cats in content:
    content = content.replace(old_cats, new_cats)

old_verify_mitosis = '    def _verify_mitosis(self) -> None:'
new_verify_symbiosis = '''    def _verify_symbiosis(self) -> None:
        sym_souls = [s for s in self.program.souls if s.symbiosis is not None]
        if not sym_souls:
            return

        bonds: dict[str, list[str]] = {}
        for soul in sym_souls:
            bonds[soul.name] = list(soul.symbiosis.bond_with)

        for soul in sym_souls:
            sym = soul.symbiosis
            loc = f"soul {soul.name}"

            mutual = []
            for bond_name in sym.bond_with:
                if bond_name in bonds and soul.name in bonds[bond_name]:
                    mutual.append(bond_name)

            if mutual:
                self.result.prove(
                    "VSY001", "symbiosis",
                    f"Soul {soul.name} has mutual bonds with: {', '.join(mutual)}",
                    loc,
                )
            else:
                self.result.warning(
                    "VSY001", "symbiosis",
                    f"Soul {soul.name} bonds are one-directional (no mutual bond found)",
                    loc,
                )

            if sym.shared_memory:
                self.result.prove(
                    "VSY002", "symbiosis",
                    f"Soul {soul.name} shares {len(sym.shared_memory)} field(s): {', '.join(sym.shared_memory)}",
                    loc,
                )

            if sym.evolve_together:
                has_dna = soul.dna is not None
                bond_dna = all(
                    next((s for s in self.program.souls if s.name == b), None) is not None
                    and next((s for s in self.program.souls if s.name == b), None).dna is not None
                    for b in sym.bond_with
                )
                if has_dna and bond_dna:
                    self.result.prove(
                        "VSY003", "symbiosis",
                        f"Soul {soul.name} co-evolution viable: self + bonds all have dna",
                        loc,
                    )
                else:
                    missing = []
                    if not has_dna:
                        missing.append(soul.name)
                    for b in sym.bond_with:
                        bs = next((s for s in self.program.souls if s.name == b), None)
                        if bs and not bs.dna:
                            missing.append(b)
                    self.result.warning(
                        "VSY003", "symbiosis",
                        f"Co-evolution incomplete: missing dna in {', '.join(missing)}",
                        loc,
                    )

        cluster_count = 0
        visited: set[str] = set()
        for soul_name in bonds:
            if soul_name not in visited:
                cluster: set[str] = set()
                stack = [soul_name]
                while stack:
                    n = stack.pop()
                    if n in visited:
                        continue
                    visited.add(n)
                    cluster.add(n)
                    for neighbor in bonds.get(n, []):
                        if neighbor in bonds:
                            stack.append(neighbor)
                cluster_count += 1

        total = len(sym_souls)
        self.result.prove(
            "VSY004", "symbiosis",
            f"Symbiosis coverage: {total} soul(s) in {cluster_count} cluster(s)",
        )

    def _verify_mitosis(self) -> None:'''

if old_verify_mitosis in content and '_verify_symbiosis' not in content:
    content = content.replace(old_verify_mitosis, new_verify_symbiosis)

with open(path, "w") as f:
    f.write(content)
print("PATCH S5 OK — verifier: VSY001-VSY004")
