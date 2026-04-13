"""
NOUS Cross-World v2.0 — Multi-world type checking
===================================================
nous crossworld world1.nous world2.nous
Validates message types and fields across world boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ast_nodes import (
    NousProgram, SoulNode, MessageNode, SpeakNode,
    LetNode, IfNode, ForNode, InstinctNode,
)
from parser import parse_nous_file


@dataclass
class CrossWorldError:
    code: str
    severity: str
    world: str
    soul: str
    message: str


@dataclass
class CrossWorldResult:
    errors: list[CrossWorldError] = field(default_factory=list)
    warnings: list[CrossWorldError] = field(default_factory=list)
    worlds: int = 0
    cross_speaks: int = 0
    cross_listens: int = 0

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class CrossWorldChecker:

    def __init__(self) -> None:
        self.worlds: dict[str, NousProgram] = {}
        self.world_files: dict[str, str] = {}

    def add_file(self, path: str | Path) -> str | None:
        p = Path(path)
        try:
            program = parse_nous_file(p)
        except Exception as e:
            return f"Parse error in {p.name}: {e}"
        if not program.world:
            return f"{p.name}: no world declaration found"
        name = program.world.name
        if name in self.worlds:
            return f"Duplicate world name: {name}"
        self.worlds[name] = program
        self.world_files[name] = str(p)
        return None

    def check(self) -> CrossWorldResult:
        result = CrossWorldResult(worlds=len(self.worlds))

        all_messages: dict[str, dict[str, MessageNode]] = {}
        for world_name, program in self.worlds.items():
            all_messages[world_name] = {m.name: m for m in program.messages}

        for world_name, program in self.worlds.items():
            for soul in program.souls:
                if soul.instinct:
                    self._check_statements(
                        soul.instinct.statements,
                        world_name, soul.name,
                        all_messages, result,
                    )

        return result

    def _check_statements(
        self,
        stmts: list[Any],
        world_name: str,
        soul_name: str,
        all_messages: dict[str, dict[str, MessageNode]],
        result: CrossWorldResult,
    ) -> None:
        for stmt in stmts:
            if isinstance(stmt, SpeakNode) and stmt.target_world:
                result.cross_speaks += 1
                self._check_cross_speak(stmt, world_name, soul_name, all_messages, result)
            elif isinstance(stmt, LetNode) and isinstance(stmt.value, dict):
                kind = stmt.value.get("kind", "")
                if kind == "listen" and "world" in stmt.value:
                    result.cross_listens += 1
                    self._check_cross_listen(stmt.value, world_name, soul_name, all_messages, result)
            elif isinstance(stmt, IfNode):
                self._check_statements(stmt.then_body, world_name, soul_name, all_messages, result)
                self._check_statements(stmt.else_body, world_name, soul_name, all_messages, result)
            elif isinstance(stmt, ForNode):
                self._check_statements(stmt.body, world_name, soul_name, all_messages, result)

    def _check_cross_speak(
        self,
        node: SpeakNode,
        world_name: str,
        soul_name: str,
        all_messages: dict[str, dict[str, MessageNode]],
        result: CrossWorldResult,
    ) -> None:
        target = node.target_world
        assert target is not None

        if target == world_name:
            result.warnings.append(CrossWorldError(
                code="CW001",
                severity="WARN",
                world=world_name,
                soul=soul_name,
                message=f"Cross-world speak to own world '{target}' — use local speak instead",
            ))

        if target not in self.worlds:
            result.errors.append(CrossWorldError(
                code="CW002",
                severity="ERROR",
                world=world_name,
                soul=soul_name,
                message=f"Target world '{target}' not found in project",
            ))
            return

        target_msgs = all_messages.get(target, {})
        if node.message_type not in target_msgs:
            result.errors.append(CrossWorldError(
                code="CW003",
                severity="ERROR",
                world=world_name,
                soul=soul_name,
                message=f"Message '{node.message_type}' not defined in world '{target}'",
            ))
            return

        msg_def = target_msgs[node.message_type]
        defined_fields = {f.name for f in msg_def.fields}
        required_fields = {f.name for f in msg_def.fields if f.default is None}
        sent_fields = {k for k in node.args.keys() if not k.startswith("_pos_")}

        missing = required_fields - sent_fields
        if missing:
            result.errors.append(CrossWorldError(
                code="CW004",
                severity="ERROR",
                world=world_name,
                soul=soul_name,
                message=f"Missing required fields in cross-world speak {node.message_type}: {', '.join(sorted(missing))}",
            ))

        unknown = sent_fields - defined_fields
        if unknown:
            result.warnings.append(CrossWorldError(
                code="CW005",
                severity="WARN",
                world=world_name,
                soul=soul_name,
                message=f"Unknown fields in cross-world speak {node.message_type}: {', '.join(sorted(unknown))}",
            ))

    def _check_cross_listen(
        self,
        val: dict[str, Any],
        world_name: str,
        soul_name: str,
        all_messages: dict[str, dict[str, MessageNode]],
        result: CrossWorldResult,
    ) -> None:
        target_world = val.get("world", "")
        target_soul = val.get("soul", "")
        msg_type = val.get("type", "")

        if target_world not in self.worlds:
            result.errors.append(CrossWorldError(
                code="CW006",
                severity="ERROR",
                world=world_name,
                soul=soul_name,
                message=f"Listen target world '{target_world}' not found",
            ))
            return

        target_program = self.worlds[target_world]
        soul_names = [s.name for s in target_program.souls]
        if target_soul not in soul_names:
            result.warnings.append(CrossWorldError(
                code="CW007",
                severity="WARN",
                world=world_name,
                soul=soul_name,
                message=f"Listen target soul '{target_soul}' not found in world '{target_world}'",
            ))

        target_msgs = all_messages.get(target_world, {})
        if msg_type not in target_msgs:
            result.errors.append(CrossWorldError(
                code="CW008",
                severity="ERROR",
                world=world_name,
                soul=soul_name,
                message=f"Message '{msg_type}' not defined in world '{target_world}'",
            ))


def check_cross_world(paths: list[str]) -> CrossWorldResult:
    checker = CrossWorldChecker()
    for p in paths:
        err = checker.add_file(p)
        if err:
            result = CrossWorldResult()
            result.errors.append(CrossWorldError(
                code="CW000", severity="ERROR", world="", soul="", message=err,
            ))
            return result
    return checker.check()


def print_cross_world_report(result: CrossWorldResult) -> None:
    print(f"Cross-World Check — {result.worlds} worlds")
    print(f"{'=' * 55}")
    print(f"  Cross-speaks: {result.cross_speaks} | Cross-listens: {result.cross_listens}")
    print()

    if result.errors:
        print(f"  \033[31mERRORS ({len(result.errors)}):\033[0m")
        for e in result.errors:
            ctx = f"{e.world}::{e.soul}" if e.world else ""
            print(f"    [{e.code}] {ctx}: {e.message}")
        print()

    if result.warnings:
        print(f"  \033[33mWARNINGS ({len(result.warnings)}):\033[0m")
        for w in result.warnings:
            ctx = f"{w.world}::{w.soul}" if w.world else ""
            print(f"    [{w.code}] {ctx}: {w.message}")
        print()

    if result.ok:
        print(f"  \033[32m✓ CROSS-WORLD PASS\033[0m")
    else:
        print(f"  \033[31m✗ CROSS-WORLD FAIL\033[0m")
