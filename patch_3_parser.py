path = "/opt/aetherlang_agents/nous/parser.py"
with open(path, "r") as f:
    content = f.read()

old = '''    def mitosis_verify(self, items: list) -> dict:
        val = items[0]
        return {"verify": val if isinstance(val, bool) else str(val).lower() == "true"}'''

new = '''    def mitosis_verify(self, items: list) -> dict:
        val = items[0]
        return {"verify": val if isinstance(val, bool) else str(val).lower() == "true"}

    def mitosis_retire_trigger(self, items: list) -> dict:
        return {"retire_trigger": items[0]}

    def mitosis_retire_cooldown(self, items: list) -> dict:
        return {"retire_cooldown": str(items[0])}

    def mitosis_min_clones(self, items: list) -> dict:
        return {"min_clones": int(items[0])}'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 3 OK — parser updated with retire transformers")
else:
    print("PATCH 3 SKIP — pattern not found")
