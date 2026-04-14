path = "/opt/aetherlang_agents/nous/ast_nodes.py"
with open(path, "r") as f:
    content = f.read()

old = '''class MitosisNode(NousNode):
    trigger: Any = None
    max_clones: int = 3
    cooldown: str = "60s"
    clone_tier: Optional[str] = None
    verify: bool = True'''

new = '''class MitosisNode(NousNode):
    trigger: Any = None
    max_clones: int = 3
    cooldown: str = "60s"
    clone_tier: Optional[str] = None
    verify: bool = True
    retire_trigger: Any = None
    retire_cooldown: str = "120s"
    min_clones: int = 0'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 2 OK — MitosisNode updated with retire fields")
else:
    print("PATCH 2 SKIP — pattern not found")
