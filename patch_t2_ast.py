path = "/opt/aetherlang_agents/nous/ast_nodes.py"
with open(path, "r") as f:
    content = f.read()

old_world = '''class WorldNode(NousNode):
    name: str
    laws: list[LawNode] = Field(default_factory=list)
    heartbeat: Optional[str] = None
    timezone: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)'''

new_world = '''class TelemetryNode(NousNode):
    enabled: bool = True
    exporter: str = "console"
    endpoint: Optional[str] = None
    sample_rate: float = 1.0
    trace_senses: bool = True
    trace_llm: bool = True
    buffer_size: int = 1000


class WorldNode(NousNode):
    name: str
    laws: list[LawNode] = Field(default_factory=list)
    heartbeat: Optional[str] = None
    timezone: Optional[str] = None
    telemetry: Optional[TelemetryNode] = None
    config: dict[str, Any] = Field(default_factory=dict)'''

if old_world in content:
    content = content.replace(old_world, new_world)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH T2 OK — AST: TelemetryNode + WorldNode.telemetry field")
else:
    print("PATCH T2 SKIP — pattern not found")
