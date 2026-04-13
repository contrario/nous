"""
NOUS Import Resolver v2 — Εισαγωγή (Eisagogi)
=================================================
Resolves imports, detects cycles, merges programs,
runs cross-file type checking.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, ImportNode, MessageNode, SoulNode


PACKAGES_DIR = Path.home() / ".nous" / "packages"


@dataclass
class ImportError:
    code: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        prefix = f"[IMPORT] {self.code}"
        if self.location:
            prefix += f" @ {self.location}"
        return f"{prefix}: {self.message}"


@dataclass
class ImportResult:
    program: NousProgram
    resolved_files: list[str] = field(default_factory=list)
    errors: list[ImportError] = field(default_factory=list)
    warnings: list[ImportError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class ImportResolver:
    """Resolves and merges imports for a NOUS program."""

    def __init__(self, base_dir: Path, packages_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir
        self.packages_dir = packages_dir or PACKAGES_DIR
        self._resolved: dict[str, NousProgram] = {}
        self._resolving: set[str] = set()
        self.errors: list[ImportError] = []
        self.warnings: list[ImportError] = []

    def resolve(self, program: NousProgram, source_path: Optional[Path] = None) -> ImportResult:
        source_key = str(source_path) if source_path else "<main>"
        self._resolved[source_key] = program

        for imp in program.imports:
            self._resolve_import(imp, source_path or self.base_dir / "main.nous")

        merged = self._merge_all(program)
        return ImportResult(
            program=merged,
            resolved_files=list(self._resolved.keys()),
            errors=list(self.errors),
            warnings=list(self.warnings),
        )

    def _resolve_import(self, imp: ImportNode, from_file: Path) -> None:
        resolved_path = self._find_import(imp, from_file)
        if resolved_path is None:
            self.errors.append(ImportError(
                "IM001",
                f"Cannot resolve import: {imp.path}",
                str(from_file),
            ))
            return

        path_key = str(resolved_path)

        if path_key in self._resolving:
            self.errors.append(ImportError(
                "IM002",
                f"Circular import detected: {imp.path}",
                str(from_file),
            ))
            return

        if path_key in self._resolved:
            return

        self._resolving.add(path_key)
        try:
            imported_program = self._parse_file(resolved_path)
            if imported_program is None:
                return
            self._resolved[path_key] = imported_program

            for sub_imp in imported_program.imports:
                self._resolve_import(sub_imp, resolved_path)
        finally:
            self._resolving.discard(path_key)

    def _find_import(self, imp: ImportNode, from_file: Path) -> Optional[Path]:
        if imp.package:
            return self._find_package(imp.package)
        if imp.path:
            found = self._find_file(imp.path, from_file.parent)
            if found:
                return found
            stem = Path(imp.path).stem
            return self._find_package(stem)
        return None

    def _find_file(self, path_str: str, rel_dir: Path) -> Optional[Path]:
        candidate = rel_dir / path_str
        if candidate.exists():
            return candidate.resolve()
        candidate = self.base_dir / path_str
        if candidate.exists():
            return candidate.resolve()
        if not path_str.endswith(".nous"):
            candidate = rel_dir / f"{path_str}.nous"
            if candidate.exists():
                return candidate.resolve()
        return None

    def _find_package(self, name: str) -> Optional[Path]:
        pkg_dir = self.packages_dir / name
        if not pkg_dir.exists():
            return None
        toml_path = pkg_dir / "nous.toml"
        if toml_path.exists():
            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
                entry = data.get("package", {}).get("entry", "main.nous")
                entry_path = pkg_dir / entry
                if entry_path.exists():
                    return entry_path.resolve()
            except Exception:
                pass
        main_path = pkg_dir / "main.nous"
        if main_path.exists():
            return main_path.resolve()
        return None

    def _parse_file(self, path: Path) -> Optional[NousProgram]:
        try:
            from parser import parse_nous_file
            return parse_nous_file(path)
        except Exception as e:
            self.errors.append(ImportError(
                "IM003",
                f"Parse error in imported file {path.name}: {e}",
                str(path),
            ))
            return None

    def _merge_all(self, main_program: NousProgram) -> NousProgram:
        merged = NousProgram(
            world=main_program.world,
            nervous_system=main_program.nervous_system,
            evolution=main_program.evolution,
            perception=main_program.perception,
            tests=list(main_program.tests),
            imports=list(main_program.imports),
        )
        seen_messages: set[str] = set()
        seen_souls: set[str] = set()

        for msg in main_program.messages:
            seen_messages.add(msg.name)
            merged.messages.append(msg)
        for soul in main_program.souls:
            seen_souls.add(soul.name)
            merged.souls.append(soul)

        for path_key, imported in self._resolved.items():
            if path_key == str(self.base_dir / "main.nous") or imported is main_program:
                continue
            for msg in imported.messages:
                if msg.name in seen_messages:
                    self.warnings.append(ImportError(
                        "IM004",
                        f"Duplicate message '{msg.name}' from import, skipped",
                        path_key,
                    ))
                    continue
                seen_messages.add(msg.name)
                merged.messages.append(msg)

            for soul in imported.souls:
                if soul.name in seen_souls:
                    self.warnings.append(ImportError(
                        "IM005",
                        f"Duplicate soul '{soul.name}' from import, skipped",
                        path_key,
                    ))
                    continue
                seen_souls.add(soul.name)
                merged.souls.append(soul)

        return merged


def resolve_imports(program: NousProgram, source_path: Path) -> ImportResult:
    resolver = ImportResolver(base_dir=source_path.parent)
    return resolver.resolve(program, source_path)


def parse_project(path: Path) -> ImportResult:
    from parser import parse_nous_file
    program = parse_nous_file(path)
    if not program.imports:
        return ImportResult(
            program=program,
            resolved_files=[str(path)],
        )
    return resolve_imports(program, path)


def cross_file_typecheck(result: ImportResult) -> list[str]:
    if not result.ok:
        return [str(e) for e in result.errors]
    issues: list[str] = []
    try:
        from typechecker import typecheck_program
        tc = typecheck_program(result.program)
        for e in tc.errors:
            issues.append(f"[TYPE] {e}")
        for w in tc.warnings:
            issues.append(f"[TYPE] {w}")
    except Exception as e:
        issues.append(f"[TYPE] Error: {e}")
    return issues
