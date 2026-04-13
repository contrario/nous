#!/usr/bin/env python3
"""
NOUS Cross-World Communication Patch
Applies changes to: nous.lark, ast_nodes.py, parser.py, codegen.py, multiworld.py
"""
import re
import sys
from pathlib import Path

BASE = Path("/opt/aetherlang_agents/nous")


def patch_file(path: Path, old: str, new: str, label: str) -> bool:
    content = path.read_text()
    if old not in content:
        print(f"  [SKIP] {label} — pattern not found (maybe already patched?)")
        return False
    content = content.replace(old, new, 1)
    path.write_text(content)
    print(f"  [OK]   {label}")
    return True


def patch_grammar() -> None:
    print("\n=== 1. Patching nous.lark ===")
    p = BASE / "nous.lark"

    patch_file(p,
        'speak_stmt: SPEAK message_construct',
        'speak_stmt: SPEAK message_construct                      -> speak_local\n'
        '          | SPEAK cross_target message_construct          -> speak_cross\n'
        '\n'
        'cross_target: "@" NAME "::"',
        "speak_stmt → speak_local/speak_cross + cross_target"
    )

    patch_file(p,
        'listen_expr: "let" NAME "=" LISTEN soul_ref "::" NAME',
        'listen_expr: "let" NAME "=" LISTEN soul_ref "::" NAME          -> listen_local\n'
        '           | "let" NAME "=" LISTEN cross_target NAME            -> listen_cross',
        "listen_expr → listen_local/listen_cross"
    )


def patch_ast_nodes() -> None:
    print("\n=== 2. Patching ast_nodes.py ===")
    p = BASE / "ast_nodes.py"

    patch_file(p,
        'class SpeakNode(NousNode):\n'
        '    message_type: str\n'
        '    args: dict[str, Any] = Field(default_factory=dict)',
        'class SpeakNode(NousNode):\n'
        '    message_type: str\n'
        '    args: dict[str, Any] = Field(default_factory=dict)\n'
        '    target_world: str | None = None',
        "SpeakNode.target_world"
    )

    patch_file(p,
        'class ListenNode(NousNode):\n'
        '    target_soul: str\n'
        '    message_type: str\n'
        '    bind_name: str',
        'class ListenNode(NousNode):\n'
        '    target_soul: str\n'
        '    message_type: str\n'
        '    bind_name: str\n'
        '    target_world: str | None = None',
        "ListenNode.target_world"
    )


def patch_parser() -> None:
    print("\n=== 3. Patching parser.py ===")
    p = BASE / "parser.py"
    content = p.read_text()

    old_speak = None
    for pattern in [
        'def speak_stmt(self, items: list) -> SpeakNode:',
        'def speak_stmt(self, items):',
    ]:
        if pattern in content:
            old_speak = pattern
            break

    if old_speak:
        start = content.index(old_speak)
        next_def = content.index('\n    def ', start + 10)
        old_block = content[start:next_def]

        new_block = '''def cross_target(self, items: list) -> str:
        for item in items:
            if isinstance(item, Token):
                return str(item)
        return ""

    def speak_local(self, items: list) -> SpeakNode:
        items = [i for i in items if i is not None]
        msg = items[-1]
        if isinstance(msg, dict) and msg.get("kind") == "message_construct":
            return SpeakNode(message_type=msg["type"], args=msg.get("args", {}))
        return SpeakNode(message_type=str(msg))

    def speak_cross(self, items: list) -> SpeakNode:
        items = [i for i in items if i is not None]
        world_name = items[0] if isinstance(items[0], str) else str(items[0])
        msg = items[-1]
        if isinstance(msg, dict) and msg.get("kind") == "message_construct":
            return SpeakNode(message_type=msg["type"], args=msg.get("args", {}), target_world=world_name)
        return SpeakNode(message_type=str(msg), target_world=world_name)

'''
        content = content[:start] + new_block + content[next_def:]
        print("  [OK]   speak_stmt → speak_local/speak_cross + cross_target")
    else:
        print("  [SKIP] speak_stmt — not found")

    old_listen = None
    for pattern in [
        'def listen_expr(self, items: list) -> LetNode:',
        'def listen_expr(self, items):',
    ]:
        if pattern in content:
            old_listen = pattern
            break

    if old_listen:
        start = content.index(old_listen)
        next_def = content.index('\n    def ', start + 10)
        old_block = content[start:next_def]

        new_block = '''def listen_local(self, items: list) -> LetNode:
        items = [i for i in items if i is not None]
        names = [i for i in items if isinstance(i, str)]
        bind_name = names[0]
        soul = names[1] if len(names) > 2 else names[0]
        msg_type = names[-1]
        return LetNode(name=bind_name, value={"kind": "listen", "soul": soul, "type": msg_type})

    def listen_cross(self, items: list) -> LetNode:
        items = [i for i in items if i is not None]
        names = [i for i in items if isinstance(i, str)]
        bind_name = names[0]
        world_name = names[1]
        msg_type = names[2]
        return LetNode(name=bind_name, value={"kind": "listen_cross", "world": world_name, "type": msg_type})

'''
        content = content[:start] + new_block + content[next_def:]
        print("  [OK]   listen_expr → listen_local/listen_cross")
    else:
        print("  [SKIP] listen_expr — not found")

    p.write_text(content)


def patch_codegen() -> None:
    print("\n=== 4. Patching codegen.py ===")
    p = BASE / "codegen.py"
    content = p.read_text()

    old_speak_code = None
    for pattern in [
        '        elif isinstance(stmt, SpeakNode):\n'
        '            channel = f"{soul_name}_{stmt.message_type}"\n'
        '            args_str = self._kv_to_python(stmt.args)\n'
        '            self._emit(f"await channels.send(\\"{channel}\\", {stmt.message_type}({args_str}))")',
    ]:
        if pattern in content:
            old_speak_code = pattern
            break

    if not old_speak_code:
        for pattern in [
            'isinstance(stmt, SpeakNode):',
        ]:
            if pattern in content:
                idx = content.index(pattern)
                line_start = content.rfind('\n', 0, idx) + 1
                next_elif = content.find('\n        elif ', idx + 10)
                if next_elif == -1:
                    next_elif = content.find('\n        else:', idx + 10)
                old_speak_code = content[line_start:next_elif]
                break

    new_speak_code = (
        '        elif isinstance(stmt, SpeakNode):\n'
        '            args_str = self._kv_to_python(stmt.args)\n'
        '            if stmt.target_world:\n'
        '                self._emit(f\'await cross_bus.publish("{stmt.target_world}", "{stmt.message_type}", {stmt.message_type}({args_str}))\')\n'
        '            else:\n'
        '                channel = f"{soul_name}_{stmt.message_type}"\n'
        '                self._emit(f\'await channels.send("{channel}", {stmt.message_type}({args_str}))\')'
    )

    if old_speak_code and old_speak_code in content:
        content = content.replace(old_speak_code, new_speak_code, 1)
        print("  [OK]   SpeakNode codegen → cross_bus.publish support")
    else:
        print("  [SKIP] SpeakNode codegen — exact pattern not found, manual patch needed")

    listen_cross_handler = '''
            elif kind == "listen_cross":
                world = val["world"]
                msg_type = val["type"]
                self._emit(f'{stmt.name} = await cross_bus.subscribe("{world}", "{msg_type}")')
'''
    if 'listen_cross' not in content:
        listen_marker = 'kind == "listen"'
        if listen_marker in content:
            idx = content.index(listen_marker)
            block_end = content.find('\n            elif ', idx + 10)
            if block_end == -1:
                block_end = content.find('\n            else:', idx + 10)
            if block_end != -1:
                content = content[:block_end] + listen_cross_handler + content[block_end:]
                print("  [OK]   listen_cross codegen handler added")
            else:
                print("  [SKIP] listen_cross — couldn't find insertion point")
        else:
            print("  [SKIP] listen_cross — 'listen' kind not found in codegen")
    else:
        print("  [SKIP] listen_cross — already exists")

    cross_bus_init = '\ncross_bus = None  # Set by MultiWorldRunner\n'
    if 'cross_bus = None' not in content:
        channels_marker = 'channels = None'
        if channels_marker in content:
            idx = content.index(channels_marker)
            line_end = content.find('\n', idx)
            content = content[:line_end + 1] + cross_bus_init + content[line_end + 1:]
            print("  [OK]   cross_bus global variable added")
        else:
            print("  [SKIP] cross_bus global — 'channels = None' not found")
    else:
        print("  [SKIP] cross_bus global — already exists")

    p.write_text(content)


def create_multiworld() -> None:
    print("\n=== 5. Updating multiworld.py ===")
    p = BASE / "multiworld.py"
    content = p.read_text() if p.exists() else ""

    if 'async def publish' in content and 'async def subscribe' in content:
        print("  [SKIP] SharedChannelBus already has publish/subscribe")
        return

    new_content = '''"""
NOUS Multi-World Runner with Cross-World Communication
=======================================================
Concurrent world execution via asyncio.TaskGroup.
SharedChannelBus enables cross-world messaging.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("nous.multiworld")


class SharedChannelBus:
    """Cross-world publish/subscribe message bus."""

    def __init__(self) -> None:
        self._channels: dict[str, asyncio.Queue[Any]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[Any]]] = {}
        self._lock = asyncio.Lock()

    def _key(self, world: str, msg_type: str) -> str:
        return f"{world}::{msg_type}"

    async def publish(self, target_world: str, msg_type: str, message: Any) -> None:
        key = self._key(target_world, msg_type)
        async with self._lock:
            queues = self._subscribers.get(key, [])
        for q in queues:
            await q.put(message)
        logger.info(f"[CrossBus] Published {msg_type} → @{target_world} ({len(queues)} subscribers)")

    async def subscribe(self, world: str, msg_type: str) -> Any:
        key = self._key(world, msg_type)
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = []
            self._subscribers[key].append(q)
        logger.info(f"[CrossBus] Subscribed to {world}::{msg_type}")
        return await q.get()

    async def subscribe_nowait(self, world: str, msg_type: str) -> Any | None:
        key = self._key(world, msg_type)
        async with self._lock:
            queues = self._subscribers.get(key, [])
        for q in queues:
            try:
                return q.get_nowait()
            except asyncio.QueueEmpty:
                return None
        return None

    def stats(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._subscribers.items()}


@dataclass
class WorldInstance:
    name: str
    source_path: Path
    compiled_path: Path | None = None
    module: Any = None

    def load(self) -> None:
        if self.compiled_path is None:
            raise ValueError(f"World {self.name} not compiled")
        spec = importlib.util.spec_from_file_location(
            f"nous_world_{self.name}", str(self.compiled_path)
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {self.compiled_path}")
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[f"nous_world_{self.name}"] = self.module
        spec.loader.exec_module(self.module)

    async def run(self, bus: SharedChannelBus) -> None:
        if self.module is None:
            self.load()
        if hasattr(self.module, "cross_bus"):
            self.module.cross_bus = bus
        run_fn = getattr(self.module, "run_world", None)
        if run_fn is None:
            raise AttributeError(f"World {self.name} has no run_world()")
        logger.info(f"[{self.name}] Starting...")
        await run_fn()
        logger.info(f"[{self.name}] Finished.")


class MultiWorldRunner:
    """Runs multiple worlds concurrently with shared cross-world bus."""

    def __init__(self) -> None:
        self.worlds: list[WorldInstance] = []
        self.bus = SharedChannelBus()

    def add_world(self, name: str, source: Path, compiled: Path) -> None:
        self.worlds.append(WorldInstance(
            name=name, source_path=source, compiled_path=compiled
        ))

    async def run_all(self) -> None:
        if not self.worlds:
            logger.warning("No worlds to run")
            return

        print(f"NOUS Multi-World: {len(self.worlds)} worlds (cross-bus enabled)")
        for w in self.worlds:
            print(f"  → {w.source_path.name}")
            w.load()
            if hasattr(w.module, "cross_bus"):
                w.module.cross_bus = self.bus

        async with asyncio.TaskGroup() as tg:
            for w in self.worlds:
                tg.create_task(w.run(self.bus))

        stats = self.bus.stats()
        if stats:
            print(f"Cross-bus stats: {stats}")


async def run_multi(compiled_worlds: list[tuple[str, Path, Path]]) -> None:
    runner = MultiWorldRunner()
    for name, source, compiled in compiled_worlds:
        runner.add_world(name, source, compiled)
    await runner.run_all()
'''
    p.write_text(new_content)
    print("  [OK]   multiworld.py updated with publish/subscribe bus")


def create_test_file() -> None:
    print("\n=== 6. Creating cross_world_test.nous ===")
    p = BASE / "cross_world_test.nous"
    p.write_text('''// cross_world_test.nous — Cross-World Communication Test
// Two worlds: Radar sends alerts, Command receives them

world Radar {
    law CostCeiling = $0.10 per cycle
    heartbeat = 5m
}

message Alert {
    level: string
    detail: string
    source: SoulRef
}

soul Watcher {
    mind: deepseek-r1 @ Tier1
    senses: [check_health]

    memory {
        alert_count: int = 0
    }

    instinct {
        let status = sense check_health()
        if status.is_critical {
            speak @Command::Alert(level: "critical", detail: status.message, source: self)
            remember alert_count += 1
        }
    }

    heal {
        on timeout => retry(3, exponential)
    }
}
''')
    print("  [OK]   cross_world_test.nous created")

    p2 = BASE / "cross_world_command.nous"
    p2.write_text('''// cross_world_command.nous — Receives cross-world alerts from Radar

world Command {
    law CostCeiling = $0.10 per cycle
    heartbeat = 5m
}

message Alert {
    level: string
    detail: string
    source: SoulRef
}

message Response {
    action: string
    target: string
}

soul Dispatcher {
    mind: deepseek-r1 @ Tier1
    senses: [send_telegram]

    memory {
        handled: int = 0
    }

    instinct {
        let alert = listen @Radar::Alert as incoming
        if alert.level == "critical" {
            speak Response(action: "escalate", target: alert.source)
            remember handled += 1
        }
    }

    heal {
        on timeout => retry(3, exponential)
    }
}

nervous_system {
    Dispatcher -> Logger
}

soul Logger {
    mind: deepseek-r1 @ Tier2
    senses: [write_log]

    instinct {
        let resp = listen Dispatcher::Response
        sense write_log(entry: resp.action)
    }

    heal {
        on timeout => retry(2, exponential)
    }
}
''')
    print("  [OK]   cross_world_command.nous created")


def clear_parser_cache() -> None:
    print("\n=== 7. Clearing parser cache ===")
    p = BASE / "parser.py"
    content = p.read_text()
    if "_PARSER_CACHE" in content:
        print("  [INFO] Parser cache will refresh on next run (grammar changed)")
    else:
        print("  [INFO] No cache variable found")


def main() -> None:
    print("NOUS Cross-World Communication Patch")
    print("=" * 50)

    if not BASE.exists():
        print(f"ERROR: {BASE} not found")
        sys.exit(1)

    patch_grammar()
    patch_ast_nodes()
    patch_parser()
    patch_codegen()
    create_multiworld()
    create_test_file()
    clear_parser_cache()

    print("\n" + "=" * 50)
    print("PATCH COMPLETE")
    print("")
    print("Test with:")
    print("  nous compile cross_world_test.nous")
    print("  nous compile cross_world_command.nous")
    print("  nous run cross_world_test.nous cross_world_command.nous")
    print("")
    print("New grammar:")
    print("  speak @Command::Alert(level: \"critical\", ...)")
    print("  let alert = listen @Radar::Alert as incoming")


if __name__ == "__main__":
    main()
