"""
NOUS Package Manager — Πακέτο (Paketo)
========================================
Install, publish, and manage .nous packages from GitHub.
Registry: GitHub repos with nous.toml manifests.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("nous.pkg")

NOUS_HOME = Path(os.environ.get("NOUS_HOME", Path.home() / ".nous"))
PACKAGES_DIR = NOUS_HOME / "packages"
REGISTRY_URL = "https://raw.githubusercontent.com/contrario/nous-registry/main/registry.json"


@dataclass
class PackageManifest:
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    repository: str = ""
    entry: str = "main.nous"
    dependencies: dict[str, str] = field(default_factory=dict)
    souls: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, path: Path) -> PackageManifest:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        pkg = data.get("package", {})
        return cls(
            name=pkg.get("name", ""),
            version=pkg.get("version", "0.0.0"),
            description=pkg.get("description", ""),
            author=pkg.get("author", ""),
            license=pkg.get("license", "MIT"),
            repository=pkg.get("repository", ""),
            entry=pkg.get("entry", "main.nous"),
            dependencies=data.get("dependencies", {}),
            souls=data.get("exports", {}).get("souls", []),
            messages=data.get("exports", {}).get("messages", []),
            tools=data.get("exports", {}).get("tools", []),
        )

    def to_toml(self) -> str:
        lines = [
            "[package]",
            f'name = "{self.name}"',
            f'version = "{self.version}"',
            f'description = "{self.description}"',
            f'author = "{self.author}"',
            f'license = "{self.license}"',
            f'repository = "{self.repository}"',
            f'entry = "{self.entry}"',
            "",
        ]
        if self.dependencies:
            lines.append("[dependencies]")
            for name, version in self.dependencies.items():
                lines.append(f'{name} = "{version}"')
            lines.append("")
        if self.souls or self.messages or self.tools:
            lines.append("[exports]")
            if self.souls:
                lines.append(f'souls = [{", ".join(f"{s!r}" for s in self.souls)}]')
            if self.messages:
                lines.append(f'messages = [{", ".join(f"{m!r}" for m in self.messages)}]')
            if self.tools:
                lines.append(f'tools = [{", ".join(f"{t!r}" for t in self.tools)}]')
        return "\n".join(lines) + "\n"


@dataclass
class RegistryEntry:
    name: str
    version: str
    description: str
    repository: str
    author: str = ""


@dataclass
class InstallResult:
    name: str
    version: str
    success: bool
    message: str
    path: str = ""


class PackageRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, RegistryEntry] = {}
        self._local_cache_file = NOUS_HOME / "registry_cache.json"

    def search(self, query: str) -> list[RegistryEntry]:
        entries = self._load_entries()
        if not query:
            return entries
        q = query.lower()
        return [e for e in entries if q in e.name.lower() or q in e.description.lower()]

    def get(self, name: str) -> RegistryEntry | None:
        entries = self._load_entries()
        for e in entries:
            if e.name == name:
                return e
        return None

    def _load_entries(self) -> list[RegistryEntry]:
        if self._cache:
            return list(self._cache.values())

        if self._local_cache_file.exists():
            try:
                data = json.loads(self._local_cache_file.read_text())
                entries = [RegistryEntry(**e) for e in data.get("packages", [])]
                self._cache = {e.name: e for e in entries}
                return entries
            except Exception:
                pass

        return self._fetch_remote()

    def _fetch_remote(self) -> list[RegistryEntry]:
        try:
            import urllib.request
            with urllib.request.urlopen(REGISTRY_URL, timeout=10) as resp:
                data = json.loads(resp.read())
            entries = [RegistryEntry(**e) for e in data.get("packages", [])]
            self._cache = {e.name: e for e in entries}
            NOUS_HOME.mkdir(parents=True, exist_ok=True)
            self._local_cache_file.write_text(json.dumps(data))
            return entries
        except Exception as e:
            log.warning(f"Cannot fetch registry: {e}")
            return []


class PackageManager:
    def __init__(self, project_dir: Path | None = None) -> None:
        self.project_dir = project_dir or Path.cwd()
        self.registry = PackageRegistry()
        PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    def install(self, name: str, version: str = "latest") -> InstallResult:
        entry = self.registry.get(name)
        if entry and entry.repository:
            return self._install_from_git(name, entry.repository, version)
        if "/" in name:
            return self._install_from_git(name.split("/")[-1], f"https://github.com/{name}.git", version)
        if name.startswith("http"):
            pkg_name = name.rstrip("/").split("/")[-1].replace(".git", "")
            return self._install_from_git(pkg_name, name, version)
        return InstallResult(name=name, version="", success=False, message=f"Package not found: {name}")

    def _install_from_git(self, name: str, repo_url: str, version: str) -> InstallResult:
        pkg_dir = PACKAGES_DIR / name
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)

        cmd = ["git", "clone", "--depth", "1"]
        if version != "latest":
            cmd.extend(["--branch", version])
        cmd.extend([repo_url, str(pkg_dir)])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                return InstallResult(name=name, version=version, success=False,
                                     message=f"Git clone failed: {proc.stderr.strip()}")
        except subprocess.TimeoutExpired:
            return InstallResult(name=name, version=version, success=False, message="Git clone timeout")
        except FileNotFoundError:
            return InstallResult(name=name, version=version, success=False, message="git not found")

        manifest_path = pkg_dir / "nous.toml"
        if manifest_path.exists():
            manifest = PackageManifest.from_toml(manifest_path)
            actual_version = manifest.version

            for dep_name, dep_ver in manifest.dependencies.items():
                dep_result = self.install(dep_name, dep_ver)
                if not dep_result.success:
                    log.warning(f"Dependency {dep_name} failed: {dep_result.message}")
        else:
            actual_version = version

        return InstallResult(
            name=name, version=actual_version, success=True,
            message="Installed", path=str(pkg_dir),
        )

    def uninstall(self, name: str) -> InstallResult:
        pkg_dir = PACKAGES_DIR / name
        if not pkg_dir.exists():
            return InstallResult(name=name, version="", success=False, message="Not installed")
        shutil.rmtree(pkg_dir)
        return InstallResult(name=name, version="", success=True, message="Uninstalled")

    def list_installed(self) -> list[PackageManifest]:
        results: list[PackageManifest] = []
        if not PACKAGES_DIR.exists():
            return results
        for pkg_dir in sorted(PACKAGES_DIR.iterdir()):
            if pkg_dir.is_dir():
                manifest_path = pkg_dir / "nous.toml"
                if manifest_path.exists():
                    try:
                        results.append(PackageManifest.from_toml(manifest_path))
                    except Exception:
                        results.append(PackageManifest(name=pkg_dir.name, version="unknown"))
                else:
                    nous_files = list(pkg_dir.glob("*.nous"))
                    results.append(PackageManifest(
                        name=pkg_dir.name, version="unknown",
                        entry=nous_files[0].name if nous_files else "",
                    ))
        return results

    def init(self, name: str | None = None) -> Path:
        if name is None:
            name = self.project_dir.name
        manifest = PackageManifest(name=name, version="0.1.0", author="", description="")

        from parser import parse_nous_file
        nous_files = list(self.project_dir.glob("*.nous"))
        if nous_files:
            manifest.entry = nous_files[0].name
            try:
                program = parse_nous_file(nous_files[0])
                manifest.souls = [s.name for s in program.souls]
                manifest.messages = [m.name for m in program.messages]
                tools: set[str] = set()
                for s in program.souls:
                    tools.update(s.senses)
                manifest.tools = sorted(tools)
            except Exception:
                pass

        toml_path = self.project_dir / "nous.toml"
        toml_path.write_text(manifest.to_toml(), encoding="utf-8")
        return toml_path

    def resolve_import(self, package_name: str) -> Path | None:
        pkg_dir = PACKAGES_DIR / package_name
        if not pkg_dir.exists():
            return None
        manifest_path = pkg_dir / "nous.toml"
        if manifest_path.exists():
            manifest = PackageManifest.from_toml(manifest_path)
            entry = pkg_dir / manifest.entry
            if entry.exists():
                return entry
        nous_files = list(pkg_dir.glob("*.nous"))
        return nous_files[0] if nous_files else None

    def search(self, query: str) -> list[RegistryEntry]:
        return self.registry.search(query)


def cmd_install(name: str, version: str = "latest") -> int:
    mgr = PackageManager()
    result = mgr.install(name, version)
    if result.success:
        print(f"  ✓ {result.name}@{result.version} installed → {result.path}")
        return 0
    print(f"  ✗ {result.name}: {result.message}", file=sys.stderr)
    return 1


def cmd_uninstall(name: str) -> int:
    mgr = PackageManager()
    result = mgr.uninstall(name)
    if result.success:
        print(f"  ✓ {name} uninstalled")
        return 0
    print(f"  ✗ {result.message}", file=sys.stderr)
    return 1


def cmd_list() -> int:
    mgr = PackageManager()
    packages = mgr.list_installed()
    if not packages:
        print("  No packages installed")
        return 0
    print(f"\n  Installed packages ({len(packages)}):")
    for p in packages:
        print(f"  {p.name}@{p.version} — {p.description or p.entry}")
    print()
    return 0


def cmd_init(name: str | None = None) -> int:
    mgr = PackageManager()
    path = mgr.init(name)
    print(f"  ✓ Created {path}")
    return 0


def cmd_search(query: str) -> int:
    mgr = PackageManager()
    results = mgr.search(query)
    if not results:
        print("  No packages found")
        return 0
    print(f"\n  Registry ({len(results)} packages):")
    for r in results:
        print(f"  {r.name}@{r.version} — {r.description}")
        if r.repository:
            print(f"    {r.repository}")
    print()
    return 0
