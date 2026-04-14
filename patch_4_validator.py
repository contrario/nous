path = "/opt/aetherlang_agents/nous/validator.py"
with open(path, "r") as f:
    content = f.read()

old = '''        if m.clone_tier:
            valid_tiers = {"Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3", "Groq", "Together", "Fireworks", "Cerebras"}'''

new = '''        if m.min_clones < 0:
            self.result.error("RT001", f"Mitosis min_clones must be >= 0, got {m.min_clones}", loc)

        if m.min_clones >= m.max_clones:
            self.result.error("RT002", f"Mitosis min_clones ({m.min_clones}) must be < max_clones ({m.max_clones})", loc)

        if m.retire_trigger is not None and m.trigger is None:
            self.result.warn("RT003", f"Soul {soul.name} has retire_trigger but no spawn trigger. Clones never spawn.", loc)

        if m.trigger is not None and m.retire_trigger is None:
            self.result.warn("RT004", f"Soul {soul.name} has mitosis but no retire_trigger. Clones never die — potential resource leak.", loc)

        if m.clone_tier:
            valid_tiers = {"Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3", "Groq", "Together", "Fireworks", "Cerebras"}'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 4 OK — validator updated with RT001-RT004")
else:
    print("PATCH 4 SKIP — pattern not found")
