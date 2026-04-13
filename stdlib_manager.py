"""
NOUS Standard Library Manager — Βιβλιοθήκη (Bibliothiki)
=========================================================
Installs, lists, and manages stdlib and user packages.
Package location: ~/.nous/packages/{name}/
"""
from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


STDLIB_DIR = Path(__file__).parent / "stdlib"
PACKAGES_DIR = Path.home() / ".nous" / "packages"

STDLIB_PACKAGES = ["watcher", "scheduler", "aggregator", "router", "logger"]


@dataclass
class PackageInfo:
    name: str
    version: str
    description: str
    entry: str
    author: str
    path: Path
    installed: bool = False


def _read_manifest(pkg_dir: Path) -> Optional[PackageInfo]:
    toml_path = pkg_dir / "nous.toml"
    if not toml_path.exists():
        return None
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    pkg = data.get("package", {})
    return PackageInfo(
        name=pkg.get("name", pkg_dir.name),
        version=pkg.get("version", "0.0.0"),
        description=pkg.get("description", ""),
        entry=pkg.get("entry", "main.nous"),
        author=pkg.get("author", "unknown"),
        path=pkg_dir,
        installed=True,
    )


def install_stdlib() -> list[str]:
    installed: list[str] = []
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    for pkg_name in STDLIB_PACKAGES:
        src = STDLIB_DIR / pkg_name
        if not src.exists():
            continue
        dst = PACKAGES_DIR / pkg_name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        installed.append(pkg_name)
    return installed


def install_package(source: Path) -> Optional[str]:
    if not source.exists():
        return None
    toml_path = source / "nous.toml"
    if not toml_path.exists():
        return None
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    name = data.get("package", {}).get("name", source.name)
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    dst = PACKAGES_DIR / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(source, dst)
    return name


def uninstall_package(name: str) -> bool:
    pkg_dir = PACKAGES_DIR / name
    if not pkg_dir.exists():
        return False
    shutil.rmtree(pkg_dir)
    return True


def list_packages() -> list[PackageInfo]:
    packages: list[PackageInfo] = []
    if not PACKAGES_DIR.exists():
        return packages
    for d in sorted(PACKAGES_DIR.iterdir()):
        if d.is_dir():
            info = _read_manifest(d)
            if info:
                packages.append(info)
    return packages


def get_package(name: str) -> Optional[PackageInfo]:
    pkg_dir = PACKAGES_DIR / name
    if not pkg_dir.exists():
        return None
    return _read_manifest(pkg_dir)


def get_package_entry(name: str) -> Optional[Path]:
    info = get_package(name)
    if info is None:
        return None
    return info.path / info.entry


def cmd_pkg(args: list[str]) -> int:
    if not args:
        print("Usage: nous pkg [install|list|init|uninstall|publish|registry]")
        return 1

    subcmd = args[0]

    if subcmd == "install":
        if len(args) > 1:
            source = Path(args[1])
            name = install_package(source)
            if name:
                print(f"Installed: {name}")
                return 0
            else:
                print(f"Error: invalid package at {source}")
                return 1
        else:
            from registry import install_from_toml
            toml_path = Path("nous.toml")
            if toml_path.exists():
                ok, msgs = install_from_toml(Path.cwd())
                if ok:
                    if msgs and msgs[0] == "No dependencies declared":
                        print("No dependencies in nous.toml. Installing stdlib...")
                        installed = install_stdlib()
                        print(f"Installed {len(installed)} stdlib packages:")
                        for name in installed:
                            print(f"  ✓ {name}")
                    else:
                        print(f"Installed {len(msgs)} packages from nous.toml:")
                        for m in msgs:
                            print(f"  ✓ {m}")
                else:
                    print("Dependency resolution failed:")
                    for m in msgs:
                        print(f"  ✗ {m}")
                    return 1
                return 0
            else:
                installed = install_stdlib()
                print(f"Installed {len(installed)} stdlib packages:")
                for name in installed:
                    print(f"  ✓ {name}")
                return 0

    elif subcmd == "list":
        packages = list_packages()
        if not packages:
            print("No packages installed. Run: nous pkg install")
            return 0
        print(f"Installed packages ({len(packages)}):")
        for pkg in packages:
            print(f"  {pkg.name} v{pkg.version} — {pkg.description}")
        return 0

    elif subcmd == "uninstall":
        if len(args) < 2:
            print("Usage: nous pkg uninstall <name>")
            return 1
        name = args[1]
        if uninstall_package(name):
            print(f"Uninstalled: {name}")
            return 0
        else:
            print(f"Package not found: {name}")
            return 1

    elif subcmd == "init":
        toml_path = Path("nous.toml")
        if toml_path.exists():
            print("nous.toml already exists")
            return 1
        content = """[package]
name = "my_project"
version = "0.1.0"
description = ""
entry = "main.nous"
author = ""

[dependencies]
"""
        toml_path.write_text(content, encoding="utf-8")
        print("Created nous.toml")
        return 0

    elif subcmd == "publish":
        from registry import publish
        project_dir = Path(args[1]) if len(args) > 1 else Path.cwd()
        ok, msg = publish(project_dir)
        if ok:
            print(f"✓ {msg}")
            return 0
        else:
            print(f"✗ {msg}")
            return 1

    elif subcmd == "registry":
        from registry import list_registry
        packages = list_registry()
        if not packages:
            print("Registry is empty. Publish packages with: nous pkg publish")
            return 0
        print(f"Registry ({len(packages)} packages):")
        for p in packages:
            print(f"  {p['name']} v{p['latest']} ({len(p['versions'])} versions) — {p['description']}")
        return 0

    else:
        print(f"Unknown subcommand: {subcmd}")
        return 1
