"""
NOUS Import Resolver — Εισαγωγή (Eisagogi)
=============================================
Resolves import statements, merges multi-file projects.
Supports: relative paths, absolute paths, installed packages.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ast_nodes import (
    NousProgram, ImportNode, WorldNode, MessageNode, SoulNode,
    NervousSystemNode, EvolutionNode, PerceptionNode, TopologyNode,
    TestNode,
)

log = logging.getLogger("nous.import")

PACKAGES_DIR = Path(os.environ.get("NOUS_HOME", Path.home() / ".nous")) / "packages"


class ImportError(Exception):
    def __init__(self, path: str, reason: str, source_file: str = "") -> None:
        self.import_path = path
        self.reason = reason
        self.source_file = source_file
        loc = f" (from {source_file})" if source_file else ""
        super().__init__(f"Import error: {path}{loc} — {reason}")


class ImportResolver:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.cwd()
        self._resolved: dict[str, NousProgram] = {}
        self._resolving: set[str] = set()

    def resolve_program(self, program: NousProgram, source_path: Path | None = None) -> NousProgram:
        if not program.imports:
            return program

        base = source_path.parent if source_path else self.base_dir
        source_key = str(source_path) if source_path else "<inline>"

        for imp in program.imports:
            resolved_path = self._resolve_path(imp.path, base)
            if resolved_path is None:
                log.warning(f"Cannot resolve import: {imp.path} (from {source_key})")
                continue

            abs_key = str(resolved_path.resolve())

            if abs_key in self._resolving:
                log.warning(f"Circular import detected: {imp.path} (from {source_key})")
                continue

            if abs_key in self._resolved:
                imported = self._resolved[abs_key]
            else:
                self._resolving.add(abs_key)
                try:
                    imported = self._parse_and_resolve(resolved_path)
                    self._resolved[abs_key] = imported
                finally:
                    self._resolving.discard(abs_key)

            self._merge(program, imported, imp.path)

        program.imports = []
        return program

    def _resolve_path(self, import_path: str, base_dir: Path) -> Path | None:
        if import_path.endswith(".nous"):
            candidate = base_dir / import_path
            if candidate.exists():
                return candidate
            candidate = Path(import_path)
            if candidate.exists():
                return candidate
        else:
            candidate = base_dir / f"{import_path}.nous"
            if candidate.exists():
                return candidate
            candidate = base_dir / import_path / "main.nous"
            if candidate.exists():
                return candidate
            pkg_dir = PACKAGES_DIR / import_path
            if pkg_dir.exists():
                manifest = pkg_dir / "nous.toml"
                if manifest.exists():
                    import tomllib
                    with open(manifest, "rb") as f:
                        data = tomllib.load(f)
                    entry = data.get("package", {}).get("entry", "main.nous")
                    entry_path = pkg_dir / entry
                    if entry_path.exists():
                        return entry_path
                for f in sorted(pkg_dir.glob("*.nous")):
                    return f

        return None

    def _parse_and_resolve(self, path: Path) -> NousProgram:
        from parser import parse_nous_file
        program = parse_nous_file(path)
        return self.resolve_program(program, source_path=path)

    def _merge(self, target: NousProgram, source: NousProgram, import_path: str) -> None:
        existing_msg_names = {m.name for m in target.messages}
        for msg in source.messages:
            if msg.name not in existing_msg_names:
                target.messages.append(msg)
                existing_msg_names.add(msg.name)
            else:
                log.debug(f"Skipping duplicate message {msg.name} from {import_path}")

        existing_soul_names = {s.name for s in target.souls}
        for soul in source.souls:
            if soul.name not in existing_soul_names:
                target.souls.append(soul)
                existing_soul_names.add(soul.name)
            else:
                log.debug(f"Skipping duplicate soul {soul.name} from {import_path}")

        if source.nervous_system and not target.nervous_system:
            target.nervous_system = source.nervous_system
        elif source.nervous_system and target.nervous_system:
            target.nervous_system.routes.extend(source.nervous_system.routes)

        if source.evolution and not target.evolution:
            target.evolution = source.evolution

        if source.perception and not target.perception:
            target.perception = source.perception
        elif source.perception and target.perception:
            target.perception.rules.extend(source.perception.rules)

        if source.topology and not target.topology:
            target.topology = source.topology
        elif source.topology and target.topology:
            existing_servers = {s.name for s in target.topology.servers}
            for srv in source.topology.servers:
                if srv.name not in existing_servers:
                    target.topology.servers.append(srv)

        target.tests.extend(source.tests)

        log.info(f"Imported {import_path}: +{len(source.messages)} messages, +{len(source.souls)} souls")


def resolve_imports(program: NousProgram, source_path: Path | None = None) -> NousProgram:
    resolver = ImportResolver(base_dir=source_path.parent if source_path else None)
    return resolver.resolve_program(program, source_path)


def parse_project(entry_path: str) -> NousProgram:
    from parser import parse_nous_file
    path = Path(entry_path)
    program = parse_nous_file(path)
    return resolve_imports(program, source_path=path)
