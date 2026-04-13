"""
Noesis Phase 4: Scaling Engine
Incremental save (WAL + compaction), lattice merge, backup rotation.

WAL format (append-only, one JSON per line):
    {"op": "add", "atom": {...}, "ts": 1234567890.0}
    {"op": "remove", "atom_id": "abc123", "ts": 1234567890.0}
    {"op": "update", "atom_id": "abc123", "fields": {"confidence": 0.9}, "ts": 1234567890.0}

Usage:
    from noesis_scaling import WAL, LatticeMerger, BackupManager
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("noesis.scaling")


class WAL:

    def __init__(self, wal_path: Path) -> None:
        self.path = wal_path
        self._fd: Any = None

    def open(self) -> None:
        self._fd = open(self.path, "a", encoding="utf-8")

    def close(self) -> None:
        if self._fd:
            self._fd.flush()
            self._fd.close()
            self._fd = None

    def log_add(self, atom_dict: dict[str, Any]) -> None:
        self._write({"op": "add", "atom": atom_dict, "ts": time.time()})

    def log_remove(self, atom_id: str) -> None:
        self._write({"op": "remove", "atom_id": atom_id, "ts": time.time()})

    def log_update(self, atom_id: str, fields: dict[str, Any]) -> None:
        self._write({"op": "update", "atom_id": atom_id, "fields": fields, "ts": time.time()})

    def _write(self, entry: dict[str, Any]) -> None:
        if self._fd is None:
            self.open()
        line = json.dumps(entry, default=str)
        self._fd.write(line + "\n")
        self._fd.flush()

    def replay(self, lattice: Any) -> int:
        if not self.path.exists():
            return 0

        count = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    op = entry.get("op")

                    if op == "add":
                        atom_dict = entry["atom"]
                        from noesis_engine import Atom
                        atom = Atom.from_dict(atom_dict)
                        if atom.id not in lattice.atoms:
                            lattice.add(atom)
                            count += 1

                    elif op == "remove":
                        atom_id = entry["atom_id"]
                        if atom_id in lattice.atoms:
                            lattice.remove(atom_id)
                            count += 1

                    elif op == "update":
                        atom_id = entry["atom_id"]
                        fields = entry.get("fields", {})
                        if atom_id in lattice.atoms:
                            atom = lattice.atoms[atom_id]
                            for k, v in fields.items():
                                if hasattr(atom, k):
                                    setattr(atom, k, v)
                            count += 1

                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    log.warning(f"WAL replay error line {line_num}: {e}")
                    continue

        return count

    def compact(self, lattice_path: Path, lattice: Any) -> None:
        lattice.save(lattice_path)
        if self.path.exists():
            self.close()
            self.path.unlink()
            self.open()
        log.info(f"WAL compacted: {lattice_path} ({lattice.size} atoms)")

    @property
    def entry_count(self) -> int:
        if not self.path.exists():
            return 0
        count = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count


class LatticeMerger:

    @staticmethod
    def merge(
        lattice_a_path: Path,
        lattice_b_path: Path,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        if not lattice_a_path.exists():
            return {"error": f"Not found: {lattice_a_path}"}
        if not lattice_b_path.exists():
            return {"error": f"Not found: {lattice_b_path}"}

        data_a = json.loads(lattice_a_path.read_text(encoding="utf-8"))
        data_b = json.loads(lattice_b_path.read_text(encoding="utf-8"))

        atoms_a = {a["id"]: a for a in data_a.get("atoms", [])}
        atoms_b = {a["id"]: a for a in data_b.get("atoms", [])}

        merged: dict[str, dict[str, Any]] = {}
        stats = {
            "a_only": 0,
            "b_only": 0,
            "both_a_wins": 0,
            "both_b_wins": 0,
            "total": 0,
        }

        all_ids = set(atoms_a.keys()) | set(atoms_b.keys())

        for atom_id in all_ids:
            in_a = atom_id in atoms_a
            in_b = atom_id in atoms_b

            if in_a and not in_b:
                merged[atom_id] = atoms_a[atom_id]
                stats["a_only"] += 1
            elif in_b and not in_a:
                merged[atom_id] = atoms_b[atom_id]
                stats["b_only"] += 1
            else:
                winner = LatticeMerger._pick_winner(atoms_a[atom_id], atoms_b[atom_id])
                merged[atom_id] = winner
                if winner is atoms_a[atom_id]:
                    stats["both_a_wins"] += 1
                else:
                    stats["both_b_wins"] += 1

        stats["total"] = len(merged)

        if output_path:
            out_data = {
                "version": "noesis-1.0",
                "timestamp": time.time(),
                "atom_count": len(merged),
                "merge_source_a": str(lattice_a_path),
                "merge_source_b": str(lattice_b_path),
                "atoms": list(merged.values()),
            }
            output_path.write_text(json.dumps(out_data, indent=2, default=str), encoding="utf-8")

        log.info(f"Merge: A={len(atoms_a)}, B={len(atoms_b)} → {len(merged)} atoms")
        return stats

    @staticmethod
    def _pick_winner(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        fitness_a = LatticeMerger._calc_fitness(a)
        fitness_b = LatticeMerger._calc_fitness(b)

        if fitness_a > fitness_b:
            return a
        elif fitness_b > fitness_a:
            return b

        birth_a = a.get("birth", 0)
        birth_b = b.get("birth", 0)
        return a if birth_a >= birth_b else b

    @staticmethod
    def _calc_fitness(atom_dict: dict[str, Any]) -> float:
        confidence = atom_dict.get("confidence", 0.5)
        usage = atom_dict.get("usage_count", 0)
        success = atom_dict.get("success_count", 0)
        if usage == 0:
            return confidence * 0.5
        success_rate = success / max(usage, 1)
        return confidence * 0.4 + success_rate * 0.4 + 0.2

    @staticmethod
    def merge_into_lattice(lattice: Any, other_path: Path) -> dict[str, int]:
        if not other_path.exists():
            return {"error": 1, "added": 0, "updated": 0}

        data = json.loads(other_path.read_text(encoding="utf-8"))
        added = 0
        updated = 0

        for atom_dict in data.get("atoms", []):
            atom_id = atom_dict.get("id")
            if not atom_id:
                continue

            if atom_id not in lattice.atoms:
                from noesis_engine import Atom
                atom = Atom.from_dict(atom_dict)
                lattice.add(atom)
                added += 1
            else:
                existing = lattice.atoms[atom_id]
                incoming_fitness = LatticeMerger._calc_fitness(atom_dict)
                existing_fitness = existing.fitness

                if incoming_fitness > existing_fitness:
                    existing.confidence = atom_dict.get("confidence", existing.confidence)
                    existing.usage_count = max(existing.usage_count, atom_dict.get("usage_count", 0))
                    existing.success_count = max(existing.success_count, atom_dict.get("success_count", 0))
                    updated += 1

        log.info(f"Merge into lattice: added={added}, updated={updated}")
        return {"added": added, "updated": updated}


class BackupManager:

    def __init__(self, backup_dir: Path, max_backups: int = 7) -> None:
        self.backup_dir = backup_dir
        self.max_backups = max_backups
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, lattice_path: Path) -> Path | None:
        if not lattice_path.exists():
            return None

        timestamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        backup_name = f"noesis_lattice_{timestamp}.json"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(lattice_path, backup_path)
        log.info(f"Backup created: {backup_path}")

        self._rotate()
        return backup_path

    def _rotate(self) -> None:
        backups = sorted(
            self.backup_dir.glob("noesis_lattice_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old_backup in backups[self.max_backups:]:
            old_backup.unlink()
            log.info(f"Rotated out: {old_backup.name}")

    def list_backups(self) -> list[dict[str, Any]]:
        backups = sorted(
            self.backup_dir.glob("noesis_lattice_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        result: list[dict[str, Any]] = []
        for bp in backups:
            try:
                data = json.loads(bp.read_text(encoding="utf-8"))
                atom_count = data.get("atom_count", len(data.get("atoms", [])))
            except (json.JSONDecodeError, IOError):
                atom_count = -1
            result.append({
                "name": bp.name,
                "path": str(bp),
                "size_kb": round(bp.stat().st_size / 1024, 1),
                "atoms": atom_count,
                "modified": time.ctime(bp.stat().st_mtime),
            })
        return result

    def restore(self, backup_path: Path, target_path: Path) -> bool:
        if not backup_path.exists():
            return False
        shutil.copy2(backup_path, target_path)
        log.info(f"Restored: {backup_path} → {target_path}")
        return True
