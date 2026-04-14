"""
NOUS Distributed Runtime — Δίκτυο (Diktyo)
=============================================
TCP-based channel transport for multi-machine soul execution.
JSON-line protocol. Async streams. Auto-reconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("nous.distributed")

DEFAULT_PORT = 9100
RECONNECT_DELAY = 2.0
MAX_RECONNECT_ATTEMPTS = 10


@dataclass
class NodeInfo:
    name: str
    host: str
    port: int = DEFAULT_PORT
    souls: list[str] = field(default_factory=list)


class ProtocolError(Exception):
    pass


@dataclass
class Envelope:
    op: str
    channel: str = ""
    data: Any = None
    node: str = ""
    timestamp: float = 0.0

    def to_bytes(self) -> bytes:
        obj = {
            "op": self.op,
            "channel": self.channel,
            "data": self.data,
            "node": self.node,
            "ts": self.timestamp or time.time(),
        }
        return json.dumps(obj, default=str).encode("utf-8") + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Envelope":
        obj = json.loads(raw.decode("utf-8").strip())
        return cls(
            op=obj["op"],
            channel=obj.get("channel", ""),
            data=obj.get("data"),
            node=obj.get("node", ""),
            timestamp=obj.get("ts", 0.0),
        )


class ChannelServer:
    def __init__(
        self,
        node_name: str,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        registry: Optional["DistributedChannelRegistry"] = None,
    ) -> None:
        self.node_name = node_name
        self.host = host
        self.port = port
        self._registry = registry
        self._server: Optional[asyncio.Server] = None
        self._clients: dict[str, asyncio.StreamWriter] = {}
        self._running = False

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self._running = True
        addr = self._server.sockets[0].getsockname() if self._server.sockets else (self.host, self.port)
        log.info(f"ChannelServer [{self.node_name}] listening on {addr[0]}:{addr[1]}")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        log.info(f"ChannelServer [{self.node_name}]: connection from {peer}")
        client_node = ""
        try:
            while self._running:
                line = await reader.readline()
                if not line:
                    break
                try:
                    env = Envelope.from_bytes(line)
                except (json.JSONDecodeError, KeyError) as e:
                    log.warning(f"ChannelServer: malformed message from {peer}: {e}")
                    continue

                if env.op == "register":
                    client_node = env.node
                    self._clients[client_node] = writer
                    log.info(f"ChannelServer: node '{client_node}' registered")
                    ack = Envelope(op="ack", node=self.node_name)
                    writer.write(ack.to_bytes())
                    await writer.drain()

                elif env.op == "send":
                    if self._registry:
                        await self._registry.deliver_local(env.channel, env.data)
                    ack = Envelope(op="ack", channel=env.channel, node=self.node_name)
                    writer.write(ack.to_bytes())
                    await writer.drain()

                elif env.op == "ping":
                    pong = Envelope(op="pong", node=self.node_name)
                    writer.write(pong.to_bytes())
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"ChannelServer: client handler error: {e}")
        finally:
            if client_node and client_node in self._clients:
                del self._clients[client_node]
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            log.info(f"ChannelServer: {peer} disconnected")

    async def push_to_node(self, node_name: str, envelope: Envelope) -> bool:
        writer = self._clients.get(node_name)
        if not writer or writer.is_closing():
            return False
        try:
            writer.write(envelope.to_bytes())
            await writer.drain()
            return True
        except Exception as e:
            log.warning(f"ChannelServer: push to {node_name} failed: {e}")
            return False

    async def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for name, writer in self._clients.items():
            writer.close()
        self._clients.clear()
        log.info(f"ChannelServer [{self.node_name}]: stopped")


class RemoteChannelClient:
    def __init__(self, local_node: str, remote_node: str, host: str, port: int = DEFAULT_PORT) -> None:
        self.local_node = local_node
        self.remote_node = remote_node
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=5.0,
                )
                reg = Envelope(op="register", node=self.local_node)
                self._writer.write(reg.to_bytes())
                await self._writer.drain()
                line = await asyncio.wait_for(self._reader.readline(), timeout=5.0)
                ack = Envelope.from_bytes(line)
                if ack.op == "ack":
                    self._connected = True
                    log.info(f"RemoteClient [{self.local_node}]: connected to {self.remote_node} @ {self.host}:{self.port}")
                    return True
            except (OSError, asyncio.TimeoutError) as e:
                log.warning(f"RemoteClient: connect to {self.remote_node} attempt {attempt+1} failed: {e}")
                await asyncio.sleep(RECONNECT_DELAY * (attempt + 1))
        log.error(f"RemoteClient: failed to connect to {self.remote_node} after {MAX_RECONNECT_ATTEMPTS} attempts")
        return False

    async def send(self, channel: str, data: Any, timeout: float = 5.0) -> bool:
        async with self._lock:
            if not self._connected or not self._writer or self._writer.is_closing():
                reconnected = await self.connect()
                if not reconnected:
                    return False
            try:
                env = Envelope(op="send", channel=channel, data=data, node=self.local_node)
                self._writer.write(env.to_bytes())
                await self._writer.drain()
                line = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
                ack = Envelope.from_bytes(line)
                return ack.op == "ack"
            except (OSError, asyncio.TimeoutError) as e:
                log.warning(f"RemoteClient: send to {self.remote_node} failed: {e}")
                self._connected = False
                return False

    async def ping(self) -> bool:
        async with self._lock:
            if not self._connected:
                return False
            try:
                env = Envelope(op="ping", node=self.local_node)
                self._writer.write(env.to_bytes())
                await self._writer.drain()
                line = await asyncio.wait_for(self._reader.readline(), timeout=3.0)
                pong = Envelope.from_bytes(line)
                return pong.op == "pong"
            except Exception:
                self._connected = False
                return False

    async def close(self) -> None:
        self._connected = False
        if self._writer and not self._writer.is_closing():
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass


class DistributedChannelRegistry:
    def __init__(
        self,
        local_node: str,
        local_souls: list[str],
        topology: list[NodeInfo],
    ) -> None:
        self.local_node = local_node
        self.local_souls = set(local_souls)
        self._topology = {n.name: n for n in topology}
        self._soul_to_node: dict[str, str] = {}
        self._channel_to_target: dict[str, str] = {}
        self._local_queues: dict[str, asyncio.Queue[Any]] = {}
        self._remote_clients: dict[str, RemoteChannelClient] = {}
        self._server: Optional[ChannelServer] = None
        self._lock = asyncio.Lock()

        for node in topology:
            for soul in node.souls:
                self._soul_to_node[soul] = node.name

    def set_route_map(self, routes: list[tuple[str, str]], speak_channels: dict[str, str]) -> None:
        for src, tgt in routes:
            channel_name = speak_channels.get(src, f"{src}_msg")
            target_node = self._soul_to_node.get(tgt, self.local_node)
            self._channel_to_target[channel_name] = target_node

    async def start(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> None:
        self._server = ChannelServer(self.local_node, host, port, registry=self)
        await self._server.start()
        for name, node in self._topology.items():
            if name != self.local_node:
                client = RemoteChannelClient(self.local_node, name, node.host, node.port)
                self._remote_clients[name] = client

    async def connect_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, client in self._remote_clients.items():
            ok = await client.connect()
            results[name] = ok
        return results

    async def get_local_queue(self, name: str) -> asyncio.Queue[Any]:
        async with self._lock:
            if name not in self._local_queues:
                self._local_queues[name] = asyncio.Queue(maxsize=100)
            return self._local_queues[name]

    async def send(self, channel: str, message: Any) -> None:
        target_node = self._channel_to_target.get(channel, self.local_node)
        if target_node != self.local_node:
            client = self._remote_clients.get(target_node)
            if client:
                data = self._serialize(message)
                ok = await client.send(channel, data)
                if not ok:
                    log.error(f"Distributed send to {target_node}:{channel} failed")
                return
            else:
                log.error(f"No remote client for node {target_node}")
                return
        await self.deliver_local(channel, message)

    async def receive(self, channel: str, timeout: Optional[float] = None) -> Any:
        q = await self.get_local_queue(channel)
        try:
            if timeout is not None:
                return await asyncio.wait_for(q.get(), timeout=timeout)
            return await q.get()
        except asyncio.TimeoutError:
            return None

    async def deliver_local(self, channel: str, data: Any) -> None:
        q = await self.get_local_queue(channel)
        try:
            q.put_nowait(data)
            log.debug(f"Distributed: delivered to local [{channel}]")
        except asyncio.QueueFull:
            log.warning(f"Distributed: channel [{channel}] full, dropping")

    def _serialize(self, message: Any) -> Any:
        if hasattr(message, "model_dump"):
            return message.model_dump()
        if hasattr(message, "__dict__"):
            return message.__dict__
        return message

    async def stop(self) -> None:
        for client in self._remote_clients.values():
            await client.close()
        if self._server:
            await self._server.stop()
        log.info(f"DistributedRegistry [{self.local_node}]: stopped")

    async def health(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "node": self.local_node,
            "local_souls": sorted(self.local_souls),
            "local_channels": sorted(self._local_queues.keys()),
            "remote_nodes": {},
        }
        for name, client in self._remote_clients.items():
            ok = await client.ping()
            status["remote_nodes"][name] = "connected" if ok else "disconnected"
        return status


async def cluster_health(nodes: list[NodeInfo]) -> dict[str, str]:
    results: dict[str, str] = {}
    for node in nodes:
        client = RemoteChannelClient("health_check", node.name, node.host, node.port)
        try:
            connected = await client.connect()
            if connected:
                ok = await client.ping()
                results[node.name] = "healthy" if ok else "unhealthy"
            else:
                results[node.name] = "unreachable"
        except Exception:
            results[node.name] = "error"
        finally:
            await client.close()
    return results
