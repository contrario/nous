#!/usr/bin/env python3
"""
Noesis Lattice Merge — Standalone script for cron.
Merges remote lattice into local, resolves conflicts by fitness.

Usage:
    python3 noesis_merge.py                          # auto-detect paths
    python3 noesis_merge.py --local X --remote Y     # explicit paths
    python3 noesis_merge.py --dry-run                # show stats only

Designed for cron after the existing scp sync:
    35 4 * * * scp root@B:/path/noesis_lattice.json /path/noesis_lattice_B.json
    40 4 * * * cd /path && python3 noesis_merge.py >> /var/log/noesis_merge.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from noesis_scaling import LatticeMerger, BackupManager


def detect_paths() -> tuple[Path, Path]:
    candidates = [
        (
            Path("/opt/aetherlang_agents/nous/noesis_lattice.json"),
            Path("/opt/aetherlang_agents/nous/noesis_lattice_B.json"),
        ),
        (
            Path("/opt/neuroaether/nous/noesis_lattice.json"),
            Path("/opt/neuroaether/nous/noesis_lattice_A.json"),
        ),
    ]
    for local, remote in candidates:
        if local.exists() and remote.exists():
            return local, remote
    print("ERROR: Cannot find lattice files.")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Noesis lattices")
    parser.add_argument("--local", type=str, help="Local lattice path")
    parser.add_argument("--remote", type=str, help="Remote lattice path")
    parser.add_argument("--dry-run", action="store_true", help="Show stats only")
    args = parser.parse_args()

    if args.local and args.remote:
        local_path = Path(args.local)
        remote_path = Path(args.remote)
    else:
        local_path, remote_path = detect_paths()

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Noesis Lattice Merge")
    print(f"  Local:  {local_path}")
    print(f"  Remote: {remote_path}")

    local_data = json.loads(local_path.read_text(encoding="utf-8"))
    remote_data = json.loads(remote_path.read_text(encoding="utf-8"))
    local_count = len(local_data.get("atoms", []))
    remote_count = len(remote_data.get("atoms", []))
    print(f"  Local atoms:  {local_count}")
    print(f"  Remote atoms: {remote_count}")

    if args.dry_run:
        atoms_a = {a["id"]: a for a in local_data.get("atoms", [])}
        atoms_b = {a["id"]: a for a in remote_data.get("atoms", [])}
        only_a = len(set(atoms_a.keys()) - set(atoms_b.keys()))
        only_b = len(set(atoms_b.keys()) - set(atoms_a.keys()))
        both = len(set(atoms_a.keys()) & set(atoms_b.keys()))
        print(f"\n  DRY RUN:")
        print(f"    Only in local:  {only_a}")
        print(f"    Only in remote: {only_b}")
        print(f"    In both:        {both}")
        print(f"    Total after:    {only_a + only_b + both}")
        return

    backup_dir = local_path.parent / "backups"
    mgr = BackupManager(backup_dir, max_backups=7)
    backup = mgr.create_backup(local_path)
    if backup:
        print(f"  Backup: {backup}")

    stats = LatticeMerger.merge(local_path, remote_path, output_path=local_path)

    if "error" in stats:
        print(f"  ERROR: {stats['error']}")
        sys.exit(1)

    print(f"\n  Results:")
    print(f"    Only from local:  {stats['a_only']}")
    print(f"    Only from remote: {stats['b_only']}")
    print(f"    Both (local won): {stats['both_a_wins']}")
    print(f"    Both (remote won):{stats['both_b_wins']}")
    print(f"    Total merged:     {stats['total']}")
    print(f"  ✓ Merged lattice saved to {local_path}")


if __name__ == "__main__":
    main()
