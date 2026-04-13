"""
NOUS Distributed Topology — Τοπολογία (Topologia)
===================================================
SSH deployment, cross-server TCP channels, health monitoring.
Zero external dependencies: asyncio.subprocess for SSH, raw TCP for messaging.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, TopologyNode, TopologyServerNode

log = logging.getLogger("nous.topology")

DEFAULT_BRIDGE_PORT = 9100
SSH_TIMEOUT = 30
HEALTH_INTERVAL = 15
DEPLOY_DIR = "/opt/nous_remote"


@dataclass
class ServerSpec:
    name: str
    host: str
    port: int = DEFAULT_BRIDGE_PORT
    ssh_port: int = 22
    ssh_key: str = ""
    ssh_user: str = "root"
    python: str = "python3"
    souls: list[str] = field(default_factory=list)
    env_file: str = ""

    @classmethod
    def from_ast(cls, node: TopologyServerNode) -> ServerSpec:
        cfg = node.config
        souls_raw = cfg.get("souls", [])
        souls: list[str] = []
        if isinstance(souls_raw, list):
            souls = [str(s) for s in souls_raw]
        return cls(
            name=node.name,
            host=node.host,
            port=int(cfg.get("port", DEFAULT_BRIDGE_PORT)),
            ssh_port=int(cfg.get("ssh_port", 22)),
            ssh_key=str(cfg.get("ssh_key", "")),
            ssh_user=str(cfg.get("ssh_user", "root")),
            python=str(cfg.get("python", "python3")),
            souls=souls,
            env_file=str(cfg.get("env_file", "")),
        )


@dataclass
class DeployResult:
    server: str
    host: str
    success: bool
    message: str
    pid: int = 0
    elapsed: float = 0.0


@dataclass
class HealthStatus:
    server: str
    host: str
    alive: bool
    pid: int = 0
    uptime: float = 0.0
    souls_running: list[str] = field(default_factory=list)
    last_check: float = 0.0
    error: str = ""


class SSHRunner:
    """Execute commands on remote servers via SSH subprocess."""

    def __init__(self, spec: ServerSpec) -> None:
        self.spec = spec

    def _ssh_base(self) -> list[str]:
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            "-p", str(self.spec.ssh_port),
        ]
        if self.spec.ssh_key:
            key_path = os.path.expanduser(self.spec.ssh_key)
            cmd.extend(["-i", key_path])
        cmd.append(f"{self.spec.ssh_user}@{self.spec.host}")
        return cmd

    def _scp_base(self) -> list[str]:
        cmd = [
            "scp",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            "-P", str(self.spec.ssh_port),
        ]
        if self.spec.ssh_key:
            key_path = os.path.expanduser(self.spec.ssh_key)
            cmd.extend(["-i", key_path])
        return cmd

    async def run_command(self, command: str, timeout: float = SSH_TIMEOUT) -> tuple[int, str, str]:
        ssh_cmd = self._ssh_base() + [command]
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
            )
        except asyncio.TimeoutError:
            return -1, "", f"SSH timeout after {timeout}s"
        except Exception as e:
            return -1, "", str(e)

    async def upload_file(self, local_path: str, remote_path: str) -> tuple[bool, str]:
        scp_cmd = self._scp_base() + [
            local_path,
            f"{self.spec.ssh_user}@{self.spec.host}:{remote_path}",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *scp_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=SSH_TIMEOUT)
            if proc.returncode == 0:
                return True, ""
            return False, stderr.decode("utf-8", errors="replace").strip()
        except asyncio.TimeoutError:
            return False, f"SCP timeout after {SSH_TIMEOUT}s"
        except Exception as e:
            return False, str(e)

    async def check_alive(self) -> bool:
        code, _, _ = await self.run_command("echo ok", timeout=10)
        return code == 0


class SSHDeployer:
    """Deploy compiled .nous worlds to remote servers via SSH."""

    def __init__(self, program: NousProgram, compiled_code: str) -> None:
        self.program = program
        self.compiled_code = compiled_code
        self.servers: list[ServerSpec] = []
        if program.topology:
            self.servers = [ServerSpec.from_ast(s) for s in program.topology.servers]

    async def deploy_all(self) -> list[DeployResult]:
        results: list[DeployResult] = []
        tasks = [self._deploy_one(spec) for spec in self.servers]
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        for item in completed:
            if isinstance(item, Exception):
                results.append(DeployResult(
                    server="unknown", host="unknown", success=False,
                    message=str(item),
                ))
            else:
                results.append(item)
        return results

    async def _deploy_one(self, spec: ServerSpec) -> DeployResult:
        t0 = time.perf_counter()
        runner = SSHRunner(spec)
        log.info(f"Deploying to {spec.name} ({spec.host})...")

        alive = await runner.check_alive()
        if not alive:
            return DeployResult(
                server=spec.name, host=spec.host, success=False,
                message="SSH connection failed", elapsed=time.perf_counter() - t0,
            )

        code, _, err = await runner.run_command(f"mkdir -p {DEPLOY_DIR}")
        if code != 0:
            return DeployResult(
                server=spec.name, host=spec.host, success=False,
                message=f"Cannot create deploy dir: {err}",
                elapsed=time.perf_counter() - t0,
            )

        filtered_code = self._filter_souls(spec.souls)
        world_name = self.program.world.name if self.program.world else "nous_world"
        remote_file = f"{DEPLOY_DIR}/{world_name}_{spec.name}.py"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(filtered_code)
            local_tmp = f.name

        try:
            ok, err = await runner.upload_file(local_tmp, remote_file)
            if not ok:
                return DeployResult(
                    server=spec.name, host=spec.host, success=False,
                    message=f"Upload failed: {err}",
                    elapsed=time.perf_counter() - t0,
                )
        finally:
            os.unlink(local_tmp)

        if spec.env_file:
            ok, err = await runner.upload_file(
                os.path.expanduser(spec.env_file),
                f"{DEPLOY_DIR}/.env",
            )
            if not ok:
                log.warning(f"Env file upload failed for {spec.name}: {err}")

        stop_cmd = f"pkill -f '{world_name}_{spec.name}.py' 2>/dev/null; sleep 1"
        await runner.run_command(stop_cmd)

        bridge_env = f"NOUS_BRIDGE_PORT={spec.port} NOUS_SERVER_NAME={spec.name}"
        start_cmd = (
            f"cd {DEPLOY_DIR} && "
            f"nohup {bridge_env} {spec.python} {remote_file} "
            f"> /var/log/nous_{spec.name}.log 2>&1 & echo $!"
        )
        code, stdout, err = await runner.run_command(start_cmd)
        if code != 0:
            return DeployResult(
                server=spec.name, host=spec.host, success=False,
                message=f"Start failed: {err}",
                elapsed=time.perf_counter() - t0,
            )

        pid = 0
        try:
            pid = int(stdout.strip())
        except ValueError:
            pass

        elapsed = time.perf_counter() - t0
        log.info(f"Deployed {spec.name} ({spec.host}) — PID {pid}, {elapsed:.2f}s")
        return DeployResult(
            server=spec.name, host=spec.host, success=True,
            message=f"Running (PID {pid})", pid=pid, elapsed=elapsed,
        )

    def _filter_souls(self, soul_names: list[str]) -> str:
        if not soul_names:
            return self.compiled_code
        lines = self.compiled_code.split("\n")
        result: list[str] = []
        all_soul_classes = {f"Soul_{s.name}" for s in self.program.souls}
        target_classes = {f"Soul_{name}" for name in soul_names}
        skip_classes = all_soul_classes - target_classes

        skipping = False
        skip_indent = 0
        for line in lines:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)

            if skipping and current_indent <= skip_indent and stripped:
                skipping = False

            if any(stripped.startswith(f"class {cls}") for cls in skip_classes):
                skipping = True
                skip_indent = current_indent
                continue

            if not skipping:
                if 'souls["' in stripped:
                    soul_in_line = None
                    for s in self.program.souls:
                        if f'souls["{s.name}"]' in stripped:
                            soul_in_line = s.name
                            break
                    if soul_in_line and soul_in_line not in soul_names:
                        continue

                if "tg.create_task" in stripped:
                    task_soul = None
                    for s in self.program.souls:
                        if f'souls["{s.name}"]' in stripped:
                            task_soul = s.name
                            break
                    if task_soul and task_soul not in soul_names:
                        continue

                result.append(line)

        return "\n".join(result)

    async def stop_all(self) -> list[DeployResult]:
        results: list[DeployResult] = []
        world_name = self.program.world.name if self.program.world else "nous_world"
        for spec in self.servers:
            runner = SSHRunner(spec)
            cmd = f"pkill -f '{world_name}_{spec.name}.py' 2>/dev/null"
            code, _, err = await runner.run_command(cmd)
            results.append(DeployResult(
                server=spec.name, host=spec.host,
                success=code == 0 or code == 1,
                message="Stopped" if code != -1 else err,
            ))
        return results


class TCPBridgeMessage:
    """Length-prefixed JSON message for cross-server communication."""

    @staticmethod
    def encode(msg: dict[str, Any]) -> bytes:
        payload = json.dumps(msg, default=str).encode("utf-8")
        return struct.pack("!I", len(payload)) + payload

    @staticmethod
    async def decode(reader: asyncio.StreamReader) -> dict[str, Any] | None:
        header = await reader.readexactly(4)
        length = struct.unpack("!I", header)[0]
        if length > 10 * 1024 * 1024:
            raise ValueError(f"Message too large: {length}")
        payload = await reader.readexactly(length)
        return json.loads(payload.decode("utf-8"))


class TCPBridgeServer:
    """TCP server for receiving cross-server messages."""

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_BRIDGE_PORT) -> None:
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._handlers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._connections: list[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = []

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port,
        )
        log.info(f"TCP bridge listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        for _, writer in self._connections:
            writer.close()
        self._connections.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def subscribe(self, msg_type: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._handlers.setdefault(msg_type, []).append(q)
        return q

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        log.info(f"Bridge connection from {peer}")
        self._connections.append((reader, writer))
        try:
            while True:
                msg = await TCPBridgeMessage.decode(reader)
                if msg is None:
                    break
                msg_type = msg.get("type", "")
                log.debug(f"Bridge received: {msg_type} from {msg.get('source', '?')}")
                for q in self._handlers.get(msg_type, []):
                    try:
                        q.put_nowait(msg)
                    except asyncio.QueueFull:
                        log.warning(f"Bridge queue full for {msg_type}")
        except (asyncio.IncompleteReadError, ConnectionError):
            log.info(f"Bridge connection closed: {peer}")
        except Exception as e:
            log.error(f"Bridge error from {peer}: {e}")
        finally:
            writer.close()
            if (reader, writer) in self._connections:
                self._connections.remove((reader, writer))


class TCPBridgeClient:
    """TCP client for sending messages to remote servers."""

    def __init__(self) -> None:
        self._connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, server_name: str, host: str, port: int) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10,
            )
            self._connections[server_name] = (reader, writer)
            log.info(f"Bridge connected to {server_name} ({host}:{port})")
            return True
        except Exception as e:
            log.error(f"Bridge connect failed to {server_name} ({host}:{port}): {e}")
            return False

    async def send(self, server_name: str, msg: dict[str, Any]) -> bool:
        conn = self._connections.get(server_name)
        if not conn:
            log.error(f"No bridge connection to {server_name}")
            return False
        reader, writer = conn
        try:
            async with self._lock:
                data = TCPBridgeMessage.encode(msg)
                writer.write(data)
                await writer.drain()
            return True
        except Exception as e:
            log.error(f"Bridge send to {server_name} failed: {e}")
            del self._connections[server_name]
            return False

    async def close_all(self) -> None:
        for name, (_, writer) in self._connections.items():
            try:
                writer.close()
            except Exception:
                pass
        self._connections.clear()


class CrossServerBus:
    """Unified cross-server messaging: local bridge server + remote clients."""

    def __init__(self, local_name: str, port: int = DEFAULT_BRIDGE_PORT) -> None:
        self.local_name = local_name
        self.server = TCPBridgeServer(port=port)
        self.client = TCPBridgeClient()
        self._peers: dict[str, ServerSpec] = {}

    async def start(self) -> None:
        await self.server.start()

    async def connect_peers(self, servers: list[ServerSpec]) -> None:
        for spec in servers:
            if spec.name == self.local_name:
                continue
            self._peers[spec.name] = spec
            ok = await self.client.connect(spec.name, spec.host, spec.port)
            if not ok:
                log.warning(f"Could not connect to peer {spec.name} — will retry")

    async def publish(self, target_server: str, msg_type: str, payload: dict[str, Any]) -> bool:
        msg = {
            "type": msg_type,
            "source": self.local_name,
            "target": target_server,
            "payload": payload,
            "timestamp": time.time(),
        }
        if target_server == self.local_name:
            for q in self.server._handlers.get(msg_type, []):
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    pass
            return True
        return await self.client.send(target_server, msg)

    async def subscribe(self, msg_type: str) -> asyncio.Queue[dict[str, Any]]:
        return self.server.subscribe(msg_type)

    async def stop(self) -> None:
        await self.client.close_all()
        await self.server.stop()


class HealthMonitor:
    """Periodic health checks on deployed servers."""

    def __init__(self, servers: list[ServerSpec], interval: float = HEALTH_INTERVAL) -> None:
        self.servers = servers
        self.interval = interval
        self._status: dict[str, HealthStatus] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info(f"Health monitor started ({self.interval}s interval, {len(self.servers)} servers)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def get_status(self) -> dict[str, HealthStatus]:
        return dict(self._status)

    async def check_all(self) -> dict[str, HealthStatus]:
        tasks = [self._check_one(spec) for spec in self.servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            name = self.servers[i].name
            if isinstance(result, Exception):
                self._status[name] = HealthStatus(
                    server=name, host=self.servers[i].host,
                    alive=False, error=str(result),
                    last_check=time.time(),
                )
            else:
                self._status[name] = result
        return dict(self._status)

    async def _check_one(self, spec: ServerSpec) -> HealthStatus:
        runner = SSHRunner(spec)
        world_name = "nous"
        check_cmd = (
            f"pgrep -f '{world_name}.*{spec.name}.py' 2>/dev/null && "
            f"cat /proc/$(pgrep -f '{world_name}.*{spec.name}.py' | head -1)/stat 2>/dev/null | awk '{{print $22}}'"
        )
        code, stdout, err = await runner.run_command(check_cmd, timeout=15)
        alive = code == 0 and stdout.strip() != ""

        pid = 0
        uptime = 0.0
        if alive:
            lines = stdout.strip().split("\n")
            try:
                pid = int(lines[0])
            except (ValueError, IndexError):
                pass
            if len(lines) > 1:
                try:
                    start_ticks = int(lines[-1])
                    boot_code, boot_out, _ = await runner.run_command(
                        "cat /proc/stat | grep btime | awk '{print $2}'", timeout=5,
                    )
                    if boot_code == 0 and boot_out:
                        boot_time = int(boot_out)
                        hz_code, hz_out, _ = await runner.run_command(
                            "getconf CLK_TCK", timeout=5,
                        )
                        hz = int(hz_out) if hz_code == 0 and hz_out else 100
                        start_time = boot_time + (start_ticks / hz)
                        uptime = time.time() - start_time
                except (ValueError, ZeroDivisionError):
                    pass

        return HealthStatus(
            server=spec.name,
            host=spec.host,
            alive=alive,
            pid=pid,
            uptime=uptime,
            souls_running=spec.souls if alive else [],
            last_check=time.time(),
            error="" if alive else (err or "Process not found"),
        )

    async def _loop(self) -> None:
        while self._running:
            try:
                status = await self.check_all()
                for name, s in status.items():
                    if s.alive:
                        log.debug(f"Health {name}: alive (PID {s.pid}, uptime {s.uptime:.0f}s)")
                    else:
                        log.warning(f"Health {name}: DOWN — {s.error}")
            except Exception as e:
                log.error(f"Health check error: {e}")
            await asyncio.sleep(self.interval)


class TopologyManager:
    """Orchestrates deployment, bridge, and health for a topology."""

    def __init__(self, program: NousProgram, compiled_code: str) -> None:
        self.program = program
        self.compiled_code = compiled_code
        self.servers: list[ServerSpec] = []
        if program.topology:
            self.servers = [ServerSpec.from_ast(s) for s in program.topology.servers]
        self.deployer = SSHDeployer(program, compiled_code)
        self.monitor = HealthMonitor(self.servers)
        self.bus: CrossServerBus | None = None

    async def deploy(self) -> list[DeployResult]:
        results = await self.deployer.deploy_all()
        for r in results:
            status = "✓" if r.success else "✗"
            log.info(f"  {status} {r.server} ({r.host}): {r.message} [{r.elapsed:.2f}s]")
        return results

    async def start_bridge(self, local_name: str, port: int = DEFAULT_BRIDGE_PORT) -> None:
        self.bus = CrossServerBus(local_name, port)
        await self.bus.start()
        await self.bus.connect_peers(self.servers)

    async def start_monitoring(self) -> None:
        await self.monitor.start()

    async def stop(self) -> None:
        await self.monitor.stop()
        if self.bus:
            await self.bus.stop()

    async def status(self) -> dict[str, HealthStatus]:
        return await self.monitor.check_all()

    async def stop_all(self) -> list[DeployResult]:
        return await self.deployer.stop_all()


def extract_topology(program: NousProgram) -> list[ServerSpec]:
    if not program.topology:
        return []
    return [ServerSpec.from_ast(s) for s in program.topology.servers]


async def deploy_topology(
    program: NousProgram,
    compiled_code: str,
    monitor: bool = True,
) -> TopologyManager:
    mgr = TopologyManager(program, compiled_code)
    results = await mgr.deploy()
    successes = sum(1 for r in results if r.success)
    failures = sum(1 for r in results if not r.success)
    log.info(f"Deployment: {successes} succeeded, {failures} failed")

    if monitor and successes > 0:
        await mgr.start_monitoring()

    return mgr
