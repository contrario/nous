path = "/opt/aetherlang_agents/nous/ast_nodes.py"
with open(path, "r") as f:
    content = f.read()

old = '''class MitosisNode(NousNode):'''
new = '''class SymbiosisNode(NousNode):
    bond_with: list[str] = Field(default_factory=list)
    shared_memory: list[str] = Field(default_factory=list)
    sync_interval: str = "10s"
    evolve_together: bool = False


class MitosisNode(NousNode):'''

if old in content and 'SymbiosisNode' not in content:
    content = content.replace(old, new)

old_soul = '''    dream_system: Optional[DreamSystemNode] = None'''
new_soul = '''    dream_system: Optional[DreamSystemNode] = None
    symbiosis: Optional[SymbiosisNode] = None'''

if old_soul in content and 'symbiosis' not in content:
    content = content.replace(old_soul, new_soul)

with open(path, "w") as f:
    f.write(content)
print("PATCH S2 OK — AST: SymbiosisNode + SoulNode.symbiosis")
