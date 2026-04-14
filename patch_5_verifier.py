path = "/opt/aetherlang_agents/nous/verifier.py"
with open(path, "r") as f:
    content = f.read()

old_verify_call = '''        self._verify_mitosis()
        self._verify_immune()'''

new_verify_call = '''        self._verify_mitosis()
        self._verify_retirement()
        self._verify_immune()'''

if old_verify_call in content:
    content = content.replace(old_verify_call, new_verify_call)

old_capacity = '''        total_max_clones = sum(s.mitosis.max_clones for s in mitosis_souls)
        total_souls = len(self.program.souls) + total_max_clones
        self.result.info(
            "VMI005", "mitosis",
            f"Mitosis capacity: {len(mitosis_souls)} soul(s) can spawn up to {total_max_clones} clones (max {total_souls} total)",
        )'''

new_capacity = '''        total_max_clones = sum(s.mitosis.max_clones for s in mitosis_souls)
        total_souls = len(self.program.souls) + total_max_clones
        self.result.info(
            "VMI005", "mitosis",
            f"Mitosis capacity: {len(mitosis_souls)} soul(s) can spawn up to {total_max_clones} clones (max {total_souls} total)",
        )

    def _verify_retirement(self) -> None:
        mitosis_souls = [s for s in self.program.souls if s.mitosis is not None]
        if not mitosis_souls:
            return

        retire_souls = [s for s in mitosis_souls if s.mitosis.retire_trigger is not None]

        for soul in retire_souls:
            m = soul.mitosis
            loc = f"soul {soul.name}"

            retire_window = m.max_clones - m.min_clones
            self.result.prove(
                "VRT001", "retirement",
                f"Soul {soul.name} retirement policy: min_clones={m.min_clones}, "
                f"max_clones={m.max_clones}, retire window={retire_window}",
                loc,
            )

            if m.min_clones < m.max_clones:
                self.result.prove(
                    "VRT002", "retirement",
                    f"Soul {soul.name} retirement feasible: min_clones ({m.min_clones}) < max_clones ({m.max_clones})",
                    loc,
                )
            else:
                self.result.warning(
                    "VRT002", "retirement",
                    f"Soul {soul.name} retirement impossible: min_clones ({m.min_clones}) >= max_clones ({m.max_clones})",
                    loc,
                )

        if mitosis_souls:
            coverage = len(retire_souls)
            total = len(mitosis_souls)
            if coverage == total:
                self.result.prove(
                    "VRT003", "retirement",
                    f"Retirement coverage: {coverage}/{total} mitosis souls have retirement policy",
                )
            else:
                without = [s.name for s in mitosis_souls if s.mitosis.retire_trigger is None]
                self.result.warning(
                    "VRT003", "retirement",
                    f"Retirement coverage: {coverage}/{total} — souls without retirement: {', '.join(without)}",
                )'''

if old_capacity in content:
    content = content.replace(old_capacity, new_capacity)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 5 OK — verifier updated with VRT001-VRT003")
else:
    print("PATCH 5 SKIP — pattern not found")
