"""
NOUS Package Registry — Μητρώο (Mitroo)
==========================================
Local package registry for publish, download, and dependency resolution.
Registry location: /var/nous_registry/
Structure: /var/nous_registry/{name}/{version}/package.tar.gz + manifest.json
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


REGISTRY_DIR = Path("/var/nous_registry")
PACKAGES_DIR = Path.home() / ".nous" / "packages"


@dataclass
class PackageManifest:
    name: str
    version: str
    description: str = ""
    entry: str = "main.nous"
    author: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "entry": self.entry,
            "author": self.author,
            "dependencies": self.dependencies,
            "files": self.files,
            "checksum": self.checksum,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> PackageManifest:
        return PackageManifest(
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            entry=data.get("entry", "main.nous"),
            author=data.get("author", ""),
            dependencies=data.get("dependencies", {}),
            files=data.get("files", []),
            checksum=data.get("checksum", ""),
        )


@dataclass
class ResolveResult:
    packages: list[PackageManifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def _read_project_toml(project_dir: Path) -> Optional[dict[str, Any]]:
    toml_path = project_dir / "nous.toml"
    if not toml_path.exists():
        return None
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def publish(project_dir: Path, registry_dir: Optional[Path] = None) -> tuple[bool, str]:
    reg = registry_dir or REGISTRY_DIR
    data = _read_project_toml(project_dir)
    if data is None:
        return False, "No nous.toml found in project directory"

    pkg = data.get("package", {})
    name = pkg.get("name", "")
    version = pkg.get("version", "")
    if not name:
        return False, "Package name is required in [package]"
    if not version:
        return False, "Package version is required in [package]"

    entry = pkg.get("entry", "main.nous")
    entry_path = project_dir / entry
    if not entry_path.exists():
        return False, f"Entry file not found: {entry}"

    nous_files = sorted(project_dir.glob("*.nous"))
    if not nous_files:
        return False, "No .nous files found in project"

    all_files = [str(f.relative_to(project_dir)) for f in nous_files]
    all_files.append("nous.toml")

    pkg_dir = reg / name / version
    pkg_dir.mkdir(parents=True, exist_ok=True)

    tarball_path = pkg_dir / "package.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        for rel in all_files:
            full = project_dir / rel
            if full.exists():
                tar.add(full, arcname=rel)

    deps = data.get("dependencies", {})
    manifest = PackageManifest(
        name=name,
        version=version,
        description=pkg.get("description", ""),
        entry=entry,
        author=pkg.get("author", ""),
        dependencies=deps,
        files=all_files,
        checksum=_file_checksum(tarball_path),
    )

    manifest_path = pkg_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    versions_path = reg / name / "versions.json"
    versions: list[str] = []
    if versions_path.exists():
        versions = json.loads(versions_path.read_text(encoding="utf-8"))
    if version not in versions:
        versions.append(version)
        versions.sort(key=_version_tuple)
    versions_path.write_text(json.dumps(versions, indent=2), encoding="utf-8")

    return True, f"Published {name}@{version} to {pkg_dir}"


def _version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def list_registry(registry_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    reg = registry_dir or REGISTRY_DIR
    if not reg.exists():
        return []
    result: list[dict[str, Any]] = []
    for pkg_dir in sorted(reg.iterdir()):
        if not pkg_dir.is_dir():
            continue
        versions_path = pkg_dir / "versions.json"
        if not versions_path.exists():
            continue
        versions = json.loads(versions_path.read_text(encoding="utf-8"))
        latest = versions[-1] if versions else "0.0.0"
        manifest_path = pkg_dir / latest / "manifest.json"
        desc = ""
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            desc = m.get("description", "")
        result.append({
            "name": pkg_dir.name,
            "versions": versions,
            "latest": latest,
            "description": desc,
        })
    return result


def resolve_version(name: str, spec: str, registry_dir: Optional[Path] = None) -> Optional[str]:
    reg = registry_dir or REGISTRY_DIR
    versions_path = reg / name / "versions.json"
    if not versions_path.exists():
        return None
    versions: list[str] = json.loads(versions_path.read_text(encoding="utf-8"))
    if not versions:
        return None
    if spec == "latest" or spec == "*":
        return versions[-1]
    if spec in versions:
        return spec
    for v in reversed(versions):
        if v.startswith(spec):
            return v
    return None


def download(name: str, version: str, registry_dir: Optional[Path] = None,
             packages_dir: Optional[Path] = None) -> tuple[bool, str]:
    reg = registry_dir or REGISTRY_DIR
    pkgs = packages_dir or PACKAGES_DIR

    tarball_path = reg / name / version / "package.tar.gz"
    if not tarball_path.exists():
        return False, f"Package not found: {name}@{version}"

    dst = pkgs / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tarball_path, "r:gz") as tar:
        tar.extractall(path=dst)

    return True, f"Installed {name}@{version} to {dst}"


def resolve_dependencies(deps: dict[str, str], registry_dir: Optional[Path] = None,
                         _visited: Optional[set[str]] = None) -> ResolveResult:
    reg = registry_dir or REGISTRY_DIR
    result = ResolveResult()
    visited = _visited or set()

    for name, spec in deps.items():
        if name in visited:
            continue
        visited.add(name)

        version = resolve_version(name, spec, reg)
        if version is None:
            result.errors.append(f"Cannot resolve {name}@{spec} — not found in registry")
            continue

        manifest_path = reg / name / version / "manifest.json"
        if not manifest_path.exists():
            result.errors.append(f"Manifest missing for {name}@{version}")
            continue

        manifest = PackageManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        result.packages.append(manifest)

        if manifest.dependencies:
            sub = resolve_dependencies(manifest.dependencies, reg, visited)
            result.packages.extend(sub.packages)
            result.errors.extend(sub.errors)

    return result


def install_from_toml(project_dir: Path, registry_dir: Optional[Path] = None,
                      packages_dir: Optional[Path] = None) -> tuple[bool, list[str]]:
    data = _read_project_toml(project_dir)
    if data is None:
        return False, ["No nous.toml found"]

    deps = data.get("dependencies", {})
    if not deps:
        return True, ["No dependencies declared"]

    resolved = resolve_dependencies(deps, registry_dir)
    if not resolved.ok:
        return False, resolved.errors

    installed: list[str] = []
    errors: list[str] = []
    for manifest in resolved.packages:
        ok, msg = download(manifest.name, manifest.version, registry_dir, packages_dir)
        if ok:
            installed.append(f"{manifest.name}@{manifest.version}")
        else:
            errors.append(msg)

    if errors:
        return False, errors
    return True, installed
