"""
NOUS Test Suite — Distributed Runtime (P26)
=============================================
Tests: parser topology, codegen distributed, runtime bridge, TCP transport.
"""
from __future__ import annotations

import asyncio
import json
import py_compile
import tempfile
import os
import sys
import time

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        msg = f"  ✗ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def test_1_topology_parsing() -> None:
    print("\n═══ Test 1: Topology Parsing ═══")
    from parser import parse_nous_file
    p = parse_nous_file("test_distributed.nous")

    check("topology exists", p.topology is not None)
    check("2 servers", len(p.topology.servers) == 2)

    alpha = p.topology.servers[0]
    check("node_alpha name", alpha.name == "node_alpha")
    check("node_alpha host", alpha.host == "192.168.1.10")
    check("node_alpha port", alpha.port == 9100)
    check("node_alpha souls", alpha.souls == ["Scanner"])

    beta = p.topology.servers[1]
    check("node_beta name", beta.name == "node_beta")
    check("node_beta host", beta.host == "192.168.1.20")
    check("node_beta port", beta.port == 9100)
    check("node_beta souls", ["Analyzer", "Executor"] == beta.souls)


def test_2_codegen_distributed() -> None:
    print("\n═══ Test 2: CodeGen Distributed ═══")
    from parser import parse_nous_file
    from codegen import generate_python

    p = parse_nous_file("test_distributed.nous")
    code = generate_python(p)

    check("TOPOLOGY in code", "TOPOLOGY" in code)
    check("DistributedRuntime in code", "DistributedRuntime" in code)
    check("ROUTES in code", "ROUTES" in code)
    check("SPEAK_CHANNELS in code", "SPEAK_CHANNELS" in code)
    check("NOUS_NODE env var", "NOUS_NODE" in code)
    check("--node= argv parsing", '--node=' in code)
    check("set_route_map call", "set_route_map" in code)
    check("local_set filter", "local_set" in code)

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        check("py_compile PASS", True)
    except py_compile.PyCompileError as e:
        check("py_compile PASS", False, str(e))
    finally:
        os.unlink(tmp)


def test_3_no_topology_fallback() -> None:
    print("\n═══ Test 3: No-Topology Fallback ═══")
    from parser import parse_nous
    from codegen import generate_python

    source = '''
world LocalOnly {
    law cost_ceiling = $0.10 per cycle
    heartbeat = 5m
}

message Ping {
    ts: float = 0.0
}

soul Worker {
    mind: claude-sonnet @ Tier0A
    instinct {
        speak Ping(ts: now())
    }
}
'''
    p = parse_nous(source)
    code = generate_python(p)

    check("no TOPOLOGY in code", "TOPOLOGY" not in code)
    check("uses NousRuntime", "NousRuntime(" in code)
    check("no DistributedRuntime", "DistributedRuntime(" not in code)

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        check("py_compile PASS (local)", True)
    except py_compile.PyCompileError as e:
        check("py_compile PASS (local)", False, str(e))
    finally:
        os.unlink(tmp)


def test_4_distributed_channel_bridge() -> None:
    print("\n═══ Test 4: DistributedChannelBridge ═══")
    from runtime import DistributedChannelBridge, Channel

    class MockDistRegistry:
        def __init__(self) -> None:
            self._data: dict[str, list] = {}

        async def send(self, channel: str, message: object) -> None:
            self._data.setdefault(channel, []).append(message)

        async def receive(self, channel: str, timeout: float | None = None) -> object:
            lst = self._data.get(channel, [])
            if lst:
                return lst.pop(0)
            return None

    async def _run() -> None:
        mock = MockDistRegistry()
        bridge = DistributedChannelBridge(mock)

        ch = await bridge.get("test_ch")
        check("get returns Channel", isinstance(ch, Channel))

        await bridge.send("test_ch", {"msg": "hello"})
        check("send stores data", len(mock._data.get("test_ch", [])) == 1)

        result = await bridge.receive("test_ch")
        check("receive returns data", result == {"msg": "hello"})

        result2 = await bridge.receive("empty_ch")
        check("receive empty returns None", result2 is None)

    asyncio.run(_run())


def test_5_tcp_transport() -> None:
    print("\n═══ Test 5: TCP Transport ═══")
    from distributed import ChannelServer, RemoteChannelClient, DistributedChannelRegistry, NodeInfo, Envelope

    async def _run() -> None:
        registry = DistributedChannelRegistry(
            local_node="server_node",
            local_souls=["Analyzer"],
            topology=[
                NodeInfo(name="server_node", host="127.0.0.1", port=19100, souls=["Analyzer"]),
                NodeInfo(name="client_node", host="127.0.0.1", port=19101, souls=["Scanner"]),
            ],
        )
        await registry.start("127.0.0.1", 19100)
        check("server started", True)

        client = RemoteChannelClient("client_node", "server_node", "127.0.0.1", 19100)
        connected = await client.connect()
        check("client connected", connected)

        ok = await client.ping()
        check("ping-pong", ok)

        ok = await client.send("Scanner_Signal", {"source": "test", "data": "hello"})
        check("remote send", ok)

        await asyncio.sleep(0.1)

        msg = await registry.receive("Scanner_Signal", timeout=1.0)
        check("local receive after remote send", msg is not None)
        if msg:
            check("message data correct", msg.get("data") == "hello" if isinstance(msg, dict) else True)

        await client.close()
        await registry.stop()
        check("clean shutdown", True)

    asyncio.run(_run())


def test_6_envelope_serialization() -> None:
    print("\n═══ Test 6: Envelope Serialization ═══")
    from distributed import Envelope

    env = Envelope(op="send", channel="Scanner_Signal", data={"score": 0.95}, node="alpha")
    raw = env.to_bytes()
    check("to_bytes returns bytes", isinstance(raw, bytes))
    check("ends with newline", raw.endswith(b"\n"))

    parsed = Envelope.from_bytes(raw)
    check("round-trip op", parsed.op == "send")
    check("round-trip channel", parsed.channel == "Scanner_Signal")
    check("round-trip data", parsed.data == {"score": 0.95})
    check("round-trip node", parsed.node == "alpha")


def test_7_distributed_runtime_init() -> None:
    print("\n═══ Test 7: DistributedRuntime Init ═══")
    from runtime import DistributedRuntime

    rt = DistributedRuntime(
        world_name="TestWorld",
        node_name="node_alpha",
        node_host="0.0.0.0",
        node_port=9100,
        topology=[
            {"name": "node_alpha", "host": "192.168.1.10", "port": 9100, "souls": ["Scanner"]},
            {"name": "node_beta", "host": "192.168.1.20", "port": 9100, "souls": ["Analyzer"]},
        ],
        local_souls=["Scanner"],
    )
    check("world_name", rt.world_name == "TestWorld")
    check("node_name", rt.node_name == "node_alpha")
    check("node_port", rt.node_port == 9100)
    check("local_souls", rt._local_soul_names == ["Scanner"])
    check("topology count", len(rt._topology_nodes) == 2)


if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  NOUS P26 — Distributed Runtime Tests")
    print("═══════════════════════════════════════════")

    test_1_topology_parsing()
    test_2_codegen_distributed()
    test_3_no_topology_fallback()
    test_4_distributed_channel_bridge()
    test_5_tcp_transport()
    test_6_envelope_serialization()
    test_7_distributed_runtime_init()

    print(f"\n{'═' * 45}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed")
    if FAIL == 0:
        print("  Status: ALL PASS ✓")
    else:
        print(f"  Status: {FAIL} FAILED ✗")
    print(f"{'═' * 45}")
    sys.exit(0 if FAIL == 0 else 1)
