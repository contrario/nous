path = "/opt/aetherlang_agents/nous/verifier.py"
with open(path, "r") as f:
    content = f.read()

old_verify_call = '''        self._verify_mitosis()
        self._verify_retirement()'''

new_verify_call = '''        self._verify_telemetry()
        self._verify_mitosis()
        self._verify_retirement()'''

if old_verify_call in content:
    content = content.replace(old_verify_call, new_verify_call)

old_verify_mitosis_def = '''    def _verify_mitosis(self) -> None:'''

new_verify_telemetry = '''    def _verify_telemetry(self) -> None:
        if not self.program.world or not self.program.world.telemetry:
            return

        t = self.program.world.telemetry
        loc = "world > telemetry"

        if not t.enabled:
            self.result.info("VTL001", "telemetry", "Telemetry declared but disabled", loc)
            return

        self.result.prove(
            "VTL001", "telemetry",
            f"Telemetry enabled: exporter={t.exporter}, sample_rate={t.sample_rate}",
            loc,
        )

        if t.trace_senses and t.trace_llm:
            self.result.prove(
                "VTL002", "telemetry",
                "Full observability: senses and LLM calls traced",
                loc,
            )
        elif t.trace_senses:
            self.result.info(
                "VTL002", "telemetry",
                "Partial observability: senses traced, LLM calls not traced",
                loc,
            )
        elif t.trace_llm:
            self.result.info(
                "VTL002", "telemetry",
                "Partial observability: LLM calls traced, senses not traced",
                loc,
            )
        else:
            self.result.warning(
                "VTL002", "telemetry",
                "Telemetry enabled but neither senses nor LLM calls are traced",
                loc,
            )

        soul_count = len(self.program.souls)
        has_mitosis = any(s.mitosis for s in self.program.souls)
        has_immune = any(s.immune_system for s in self.program.souls)
        has_dream = any(s.dream_system for s in self.program.souls)
        subsystems = []
        if has_mitosis:
            subsystems.append("mitosis")
        if has_immune:
            subsystems.append("immune")
        if has_dream:
            subsystems.append("dream")
        sub_str = ", ".join(subsystems) if subsystems else "none"
        self.result.prove(
            "VTL003", "telemetry",
            f"Telemetry covers {soul_count} soul(s), subsystems: {sub_str}",
            loc,
        )

    def _verify_mitosis(self) -> None:'''

if old_verify_mitosis_def in content:
    content = content.replace(old_verify_mitosis_def, new_verify_telemetry)

old_cats = '"mitosis", "retirement", "immune", "dream"'
new_cats = '"telemetry", "mitosis", "retirement", "immune", "dream"'
if old_cats in content:
    content = content.replace(old_cats, new_cats)

with open(path, "w") as f:
    f.write(content)
print("PATCH T5 OK — verifier: VTL001-VTL003 proofs + telemetry category")
