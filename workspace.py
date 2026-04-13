"""
NOUS Workspace v1 — Χώρος Εργασίας (Choros Ergasias)
======================================================
Multi-file project support via nous.toml.
Auto-discovery, workspace-level validation, cross-file type checking.
"""
from __future__ import annotations

import fnmatch
import tomllib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, ImportNode


DEFAULT_TOML = """\
[package]
name = "{name}"
version = "0.1.0"
entry = "{entry}"

[workspace]
members = ["*.nous"]
exclude = ["*_test.nous"]

[build]
output_dir = "build"
"""


@dataclass
class WorkspaceConfig:
    root: Path
    name: str = ""
    version: str = "0.1.0"
    entry: str = "main.nous"
    members: list[str] = field(default_factory=lambda: ["*.nous"])
    exclude: list[str] = field(default_factory=lambda: ["*_test.nous"])
    output_dir: str = "build"
    dependencies: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceFile:
    path: Path
    relative: str
    program: Optional[NousProgram] = None
    parse_error: Optional[str] = None
    parse_time_ms: float = 0.0
    is_entry: bool = False
    is_test: bool = False


@dataclass
class WorkspaceError:
    code: str
    severity: str
    message: str
    file: str = ""

    def __str__(self) -> str:
        prefix = f"[{self.severity}] {self.code}"
        if self.file:
            prefix += f" @ {self.file}"
        return f"{prefix}: {self.message}"


@dataclass
class WorkspaceResult:
    config: WorkspaceConfig
    files: list[WorkspaceFile] = field(default_factory=list)
    merged: Optional[NousProgram] = None
    errors: list[WorkspaceError] = field(default_factory=list)
    warnings: list[WorkspaceError] = field(default_factory=list)
    total_parse_ms: float = 0.0
    total_validate_ms: float = 0.0
    total_typecheck_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return not any(e.severity == "ERROR" for e in self.errors)

    @property
    def source_files(self) -> list[WorkspaceFile]:
        return [f for f in self.files if not f.is_test and f.program is not None]

    @property
    def test_files(self) -> list[WorkspaceFile]:
        return [f for f in self.files if f.is_test and f.program is not None]


def find_workspace_root(start: Optional[Path] = None) -> Optional[Path]:
    current = (start or Path.cwd()).resolve()
    for _ in range(20):
        candidate = current / "nous.toml"
        if candidate.exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_config(toml_path: Path) -> WorkspaceConfig:
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    root = toml_path.parent
    pkg = data.get("package", {})
    ws = data.get("workspace", {})
    build = data.get("build", {})
    deps = data.get("dependencies", {})

    return WorkspaceConfig(
        root=root,
        name=pkg.get("name", root.name),
        version=pkg.get("version", "0.1.0"),
        entry=pkg.get("entry", "main.nous"),
        members=ws.get("members", ["*.nous"]),
        exclude=ws.get("exclude", ["*_test.nous"]),
        output_dir=build.get("output_dir", "build"),
        dependencies=deps,
        extra=data,
    )


def discover_files(config: WorkspaceConfig) -> list[Path]:
    root = config.root
    matched: set[Path] = set()
    for pattern in config.members:
        if "**" in pattern:
            for p in root.rglob(pattern.replace("**/", "")):
                if p.is_file() and p.suffix == ".nous":
                    matched.add(p.resolve())
        else:
            for p in root.glob(pattern):
                if p.is_file() and p.suffix == ".nous":
                    matched.add(p.resolve())

    excluded: set[Path] = set()
    for pattern in config.exclude:
        for p in root.glob(pattern):
            excluded.add(p.resolve())

    return sorted(matched - excluded)


def _is_test_file(path: Path, config: WorkspaceConfig) -> bool:
    name = path.name
    for pattern in config.exclude:
        if fnmatch.fnmatch(name, pattern):
            return True
    return "_test" in name or name.startswith("test_")


class Workspace:
    """Manages a NOUS multi-file workspace."""

    def __init__(self, config: WorkspaceConfig) -> None:
        self.config = config
        self.result = WorkspaceResult(config=config)

    def discover(self) -> WorkspaceResult:
        paths = discover_files(self.config)
        entry_path = (self.config.root / self.config.entry).resolve()

        if not paths:
            self.result.errors.append(WorkspaceError(
                "WS001", "ERROR",
                f"No .nous files found matching patterns: {self.config.members}",
            ))
            return self.result

        entry_found = False
        for p in paths:
            is_test = _is_test_file(p, self.config)
            is_entry = p == entry_path
            if is_entry:
                entry_found = True
                is_test = False
            wf = WorkspaceFile(
                path=p,
                relative=str(p.relative_to(self.config.root)),
                is_entry=is_entry,
                is_test=is_test,
            )
            self.result.files.append(wf)

        if not entry_found:
            all_nous = list(self.config.root.glob("*.nous"))
            for p in all_nous:
                if p.resolve() == entry_path:
                    entry_found = True
                    wf = WorkspaceFile(
                        path=p.resolve(),
                        relative=str(p.relative_to(self.config.root)),
                        is_entry=True,
                        is_test=False,
                    )
                    self.result.files.append(wf)
                    break

        if not entry_found:
            self.result.warnings.append(WorkspaceError(
                "WS002", "WARN",
                f"Entry file '{self.config.entry}' not found in workspace",
            ))

        return self.result

    def parse_all(self) -> WorkspaceResult:
        if not self.result.files:
            self.discover()

        from parser import parse_nous_file

        t0 = time.perf_counter()
        for wf in self.result.files:
            ft0 = time.perf_counter()
            try:
                wf.program = parse_nous_file(wf.path)
                wf.parse_time_ms = (time.perf_counter() - ft0) * 1000
            except Exception as e:
                wf.parse_error = str(e)
                wf.parse_time_ms = (time.perf_counter() - ft0) * 1000
                self.result.errors.append(WorkspaceError(
                    "WS003", "ERROR",
                    f"Parse error: {e}",
                    wf.relative,
                ))
        self.result.total_parse_ms = (time.perf_counter() - t0) * 1000
        return self.result

    def merge(self) -> WorkspaceResult:
        if not any(f.program for f in self.result.files):
            self.parse_all()

        source_files = self.result.source_files
        if not source_files:
            self.result.errors.append(WorkspaceError(
                "WS004", "ERROR", "No parseable source files in workspace",
            ))
            return self.result

        entry_file = next((f for f in source_files if f.is_entry), None)
        base = entry_file.program if entry_file else source_files[0].program

        merged = NousProgram(
            world=base.world,
            nervous_system=base.nervous_system,
            evolution=base.evolution,
            perception=base.perception,
            noesis=getattr(base, 'noesis', None),
        )

        seen_messages: set[str] = set()
        seen_souls: set[str] = set()

        programs_ordered: list[tuple[str, NousProgram]] = []
        if entry_file and entry_file.program:
            programs_ordered.append((entry_file.relative, entry_file.program))
        for f in source_files:
            if f.is_entry:
                continue
            if f.program:
                programs_ordered.append((f.relative, f.program))

        for rel_path, prog in programs_ordered:
            for msg in prog.messages:
                if msg.name in seen_messages:
                    if prog is not base:
                        self.result.warnings.append(WorkspaceError(
                            "WS005", "WARN",
                            f"Duplicate message '{msg.name}', skipped",
                            rel_path,
                        ))
                    continue
                seen_messages.add(msg.name)
                merged.messages.append(msg)

            for soul in prog.souls:
                if soul.name in seen_souls:
                    if prog is not base:
                        self.result.warnings.append(WorkspaceError(
                            "WS006", "WARN",
                            f"Duplicate soul '{soul.name}', skipped",
                            rel_path,
                        ))
                    continue
                seen_souls.add(soul.name)
                merged.souls.append(soul)

            if prog is not base:
                if prog.nervous_system and prog.nervous_system.routes:
                    if merged.nervous_system is None:
                        merged.nervous_system = prog.nervous_system
                    else:
                        merged.nervous_system.routes.extend(prog.nervous_system.routes)

            merged.imports.extend(prog.imports)
            merged.tests.extend(prog.tests)

        self.result.merged = merged
        return self.result

    def validate(self) -> WorkspaceResult:
        if self.result.merged is None:
            self.merge()
        if self.result.merged is None:
            return self.result

        from validator import validate_program
        t0 = time.perf_counter()
        vresult = validate_program(self.result.merged)
        self.result.total_validate_ms = (time.perf_counter() - t0) * 1000

        for e in vresult.errors:
            self.result.errors.append(WorkspaceError("WS-V", "ERROR", str(e)))
        for w in vresult.warnings:
            self.result.warnings.append(WorkspaceError("WS-V", "WARN", str(w)))

        return self.result

    def typecheck(self) -> WorkspaceResult:
        if self.result.merged is None:
            self.merge()
        if self.result.merged is None:
            return self.result

        from typechecker import typecheck_program
        t0 = time.perf_counter()
        tresult = typecheck_program(self.result.merged)
        self.result.total_typecheck_ms = (time.perf_counter() - t0) * 1000

        for e in tresult.errors:
            self.result.errors.append(WorkspaceError("WS-T", "ERROR", str(e)))
        for w in tresult.warnings:
            self.result.warnings.append(WorkspaceError("WS-T", "WARN", str(w)))

        return self.result

    def build(self) -> WorkspaceResult:
        self.discover()
        self.parse_all()
        self.merge()
        self.validate()
        self.typecheck()
        return self.result


def open_workspace(start: Optional[Path] = None) -> Optional[Workspace]:
    root = find_workspace_root(start)
    if root is None:
        return None
    config = load_config(root / "nous.toml")
    return Workspace(config)


def init_workspace(directory: Optional[Path] = None, name: Optional[str] = None, entry: Optional[str] = None) -> Path:
    target = (directory or Path.cwd()).resolve()
    target.mkdir(parents=True, exist_ok=True)

    ws_name = name or target.name
    ws_entry = entry or "main.nous"

    nous_files = list(target.glob("*.nous"))
    if nous_files and not entry:
        ws_entry = nous_files[0].name

    toml_content = DEFAULT_TOML.format(name=ws_name, entry=ws_entry)
    toml_path = target / "nous.toml"
    toml_path.write_text(toml_content, encoding="utf-8")
    return toml_path


def print_workspace_report(result: WorkspaceResult) -> None:
    cfg = result.config
    print(f"\n═══ NOUS Workspace — {cfg.name} v{cfg.version} ═══\n")
    print(f"  Root:    {cfg.root}")
    print(f"  Entry:   {cfg.entry}")
    print(f"  Output:  {cfg.output_dir}/")

    src = result.source_files
    tst = result.test_files
    err_files = [f for f in result.files if f.parse_error]

    print(f"\n  Files:   {len(result.files)} discovered")
    print(f"    Source:  {len(src)}")
    print(f"    Test:    {len(tst)}")
    if err_files:
        print(f"    Errors:  {len(err_files)}")

    for f in result.files:
        icon = "●" if f.is_entry else "○"
        tag = ""
        if f.is_test:
            tag = " [test]"
        if f.parse_error:
            tag = " [ERROR]"
        souls = len(f.program.souls) if f.program else 0
        msgs = len(f.program.messages) if f.program else 0
        print(f"    {icon} {f.relative}{tag}  ({souls} souls, {msgs} msgs, {f.parse_time_ms:.1f}ms)")

    if result.merged:
        m = result.merged
        print(f"\n  Merged program:")
        print(f"    World:    {m.world.name if m.world else 'None'}")
        print(f"    Souls:    {len(m.souls)}")
        print(f"    Messages: {len(m.messages)}")
        routes = len(m.nervous_system.routes) if m.nervous_system else 0
        print(f"    Routes:   {routes}")

    print(f"\n  Timing:")
    print(f"    Parse:     {result.total_parse_ms:.1f}ms")
    print(f"    Validate:  {result.total_validate_ms:.1f}ms")
    print(f"    Typecheck: {result.total_typecheck_ms:.1f}ms")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"    {e}")
    if result.warnings:
        print(f"\n  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    {w}")

    status = "✓ BUILD PASS" if result.ok else "✗ BUILD FAIL"
    print(f"\n  {status}")
