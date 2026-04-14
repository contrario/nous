path = "/opt/aetherlang_agents/nous/parser.py"
with open(path, "r") as f:
    content = f.read()

if "from ast_nodes import" in content and "TelemetryNode" not in content:
    content = content.replace(
        "from ast_nodes import",
        "from ast_nodes import TelemetryNode,\n    "
    )
    # Fix double import line if needed
    content = content.replace(
        "from ast_nodes import TelemetryNode,\n    from ast_nodes import",
        "from ast_nodes import TelemetryNode,"
    )

old_heartbeat = '''    # ── World ──
    def heartbeat_decl(self, items: list) -> dict:
        return {"heartbeat": items[0]}'''

new_heartbeat = '''    # ── Telemetry ──
    def telemetry_enabled(self, items: list) -> dict:
        return {"enabled": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def telemetry_exporter(self, items: list) -> dict:
        return {"exporter": str(items[0])}

    def telemetry_endpoint(self, items: list) -> dict:
        return {"endpoint": str(items[0])}

    def telemetry_sample_rate(self, items: list) -> dict:
        return {"sample_rate": float(items[0])}

    def telemetry_trace_senses(self, items: list) -> dict:
        return {"trace_senses": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def telemetry_trace_llm(self, items: list) -> dict:
        return {"trace_llm": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def telemetry_buffer_size(self, items: list) -> dict:
        return {"buffer_size": int(items[0])}

    def telemetry_field(self, items: list) -> Any:
        return items[0]

    def telemetry_block(self, items: list) -> dict:
        s = self._strip(items)
        node = TelemetryNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return {"telemetry": node}

    # ── World ──
    def heartbeat_decl(self, items: list) -> dict:
        return {"heartbeat": items[0]}'''

if old_heartbeat in content:
    content = content.replace(old_heartbeat, new_heartbeat)

old_world_decl_config = '''                elif "config" in item:
                    k, v = item["config"]
                    node.config[k] = v'''

new_world_decl_config = '''                elif "telemetry" in item:
                    node.telemetry = item["telemetry"]
                elif "config" in item:
                    k, v = item["config"]
                    node.config[k] = v'''

if old_world_decl_config in content:
    content = content.replace(old_world_decl_config, new_world_decl_config)

with open(path, "w") as f:
    f.write(content)
print("PATCH T3 OK — parser: telemetry transformer methods + world_decl integration")
