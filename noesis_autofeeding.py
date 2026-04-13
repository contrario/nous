"""
Noesis Phase 5: Auto-Feeding Engine
Curiosity engine, oracle weaning schedule, topic discovery.

- CuriosityEngine: tracks low-score queries, auto-feeds gaps
- OracleWeaner: raises threshold as lattice grows and autonomy improves
- TopicDiscovery: analyzes lattice coverage, finds weak/strong topics
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger("noesis.autofeeding")


class CuriosityEntry:
    __slots__ = ("query", "best_score", "timestamp", "attempts", "resolved")

    def __init__(self, query: str, best_score: float) -> None:
        self.query = query
        self.best_score = best_score
        self.timestamp = time.time()
        self.attempts = 0
        self.resolved = False


class CuriosityEngine:

    def __init__(
        self,
        gap_threshold: float = 0.5,
        max_gaps: int = 100,
        cooldown_hours: float = 24.0,
    ) -> None:
        self.gap_threshold = gap_threshold
        self.max_gaps = max_gaps
        self.cooldown_seconds = cooldown_hours * 3600
        self.gaps: dict[str, CuriosityEntry] = {}

    def record_query(self, query: str, best_score: float) -> bool:
        query_key = query.strip().lower()[:200]

        if query_key in self.gaps:
            existing = self.gaps[query_key]
            existing.best_score = max(existing.best_score, best_score)
            if existing.best_score >= self.gap_threshold:
                existing.resolved = True
            return False

        if best_score < self.gap_threshold:
            if len(self.gaps) >= self.max_gaps:
                self._evict_oldest()
            self.gaps[query_key] = CuriosityEntry(query, best_score)
            return True

        return False

    def get_unresolved(self, limit: int = 10) -> list[dict[str, Any]]:
        now = time.time()
        candidates: list[tuple[str, CuriosityEntry]] = []

        for key, entry in self.gaps.items():
            if entry.resolved:
                continue
            if entry.attempts > 0 and (now - entry.timestamp) < self.cooldown_seconds:
                continue
            candidates.append((key, entry))

        candidates.sort(key=lambda x: x[1].best_score)

        result: list[dict[str, Any]] = []
        for key, entry in candidates[:limit]:
            result.append({
                "query": entry.query,
                "best_score": entry.best_score,
                "age_hours": round((now - entry.timestamp) / 3600, 1),
                "attempts": entry.attempts,
            })
        return result

    def mark_attempted(self, query: str) -> None:
        key = query.strip().lower()[:200]
        if key in self.gaps:
            self.gaps[key].attempts += 1
            self.gaps[key].timestamp = time.time()

    def mark_resolved(self, query: str) -> None:
        key = query.strip().lower()[:200]
        if key in self.gaps:
            self.gaps[key].resolved = True

    def _evict_oldest(self) -> None:
        resolved = [k for k, v in self.gaps.items() if v.resolved]
        for k in resolved:
            del self.gaps[k]
            if len(self.gaps) < self.max_gaps:
                return

        if self.gaps:
            oldest_key = min(self.gaps, key=lambda k: self.gaps[k].timestamp)
            del self.gaps[oldest_key]

    @property
    def gap_count(self) -> int:
        return sum(1 for v in self.gaps.values() if not v.resolved)

    def stats(self) -> dict[str, Any]:
        total = len(self.gaps)
        resolved = sum(1 for v in self.gaps.values() if v.resolved)
        unresolved = total - resolved
        avg_score = 0.0
        if unresolved > 0:
            scores = [v.best_score for v in self.gaps.values() if not v.resolved]
            avg_score = sum(scores) / len(scores)
        return {
            "total_gaps": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "avg_gap_score": round(avg_score, 3),
        }

    def save(self, path: Path) -> None:
        data = []
        for key, entry in self.gaps.items():
            data.append({
                "query": entry.query,
                "best_score": entry.best_score,
                "timestamp": entry.timestamp,
                "attempts": entry.attempts,
                "resolved": entry.resolved,
            })
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path: Path) -> int:
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for item in data:
            entry = CuriosityEntry(item["query"], item["best_score"])
            entry.timestamp = item.get("timestamp", time.time())
            entry.attempts = item.get("attempts", 0)
            entry.resolved = item.get("resolved", False)
            key = entry.query.strip().lower()[:200]
            self.gaps[key] = entry
            count += 1
        return count


class OracleWeaner:

    SCHEDULE = [
        (100, 0.30),
        (500, 0.35),
        (1000, 0.40),
        (2500, 0.45),
        (5000, 0.50),
        (10000, 0.55),
        (25000, 0.60),
    ]

    def __init__(
        self,
        base_threshold: float = 0.30,
        autonomy_boost: bool = True,
    ) -> None:
        self.base_threshold = base_threshold
        self.autonomy_boost = autonomy_boost
        self.current_threshold = base_threshold

    def compute_threshold(
        self,
        atom_count: int,
        autonomy_pct: float = 0.0,
    ) -> float:
        threshold = self.base_threshold

        for min_atoms, new_threshold in self.SCHEDULE:
            if atom_count >= min_atoms:
                threshold = new_threshold
            else:
                break

        if self.autonomy_boost and autonomy_pct >= 80.0:
            bonus = (autonomy_pct - 80.0) / 200.0
            threshold = min(0.70, threshold + bonus)

        self.current_threshold = round(threshold, 3)
        return self.current_threshold

    def apply(self, oracle: Any, atom_count: int, autonomy_pct: float = 0.0) -> float:
        new_threshold = self.compute_threshold(atom_count, autonomy_pct)
        if hasattr(oracle, "confidence_threshold"):
            old = oracle.confidence_threshold
            oracle.confidence_threshold = new_threshold
            if old != new_threshold:
                log.info(f"Oracle threshold: {old:.2f} → {new_threshold:.2f} ({atom_count} atoms, {autonomy_pct:.0f}% autonomy)")
        return new_threshold

    def status(self, atom_count: int, autonomy_pct: float = 0.0) -> dict[str, Any]:
        current = self.compute_threshold(atom_count, autonomy_pct)
        next_level = None
        for min_atoms, new_threshold in self.SCHEDULE:
            if atom_count < min_atoms:
                next_level = {"atoms_needed": min_atoms, "threshold": new_threshold}
                break
        return {
            "current_threshold": current,
            "atom_count": atom_count,
            "autonomy_pct": round(autonomy_pct, 1),
            "next_level": next_level,
        }


class TopicDiscovery:

    def __init__(self, min_atoms_per_topic: int = 3) -> None:
        self.min_atoms = min_atoms_per_topic

    def analyze(self, lattice: Any) -> dict[str, Any]:
        tag_counts: Counter[str] = Counter()
        tag_scores: defaultdict[str, list[float]] = defaultdict(list)
        tag_usage: defaultdict[str, int] = defaultdict(int)

        for atom in lattice.atoms.values():
            tags = getattr(atom, "tags", set())
            for tag in tags:
                if tag.startswith("type:"):
                    continue
                tag_counts[tag] += 1
                tag_scores[tag].append(getattr(atom, "confidence", 0.5))
                tag_usage[tag] += getattr(atom, "usage_count", 0)

        pattern_counts: Counter[str] = Counter()
        for atom in lattice.atoms.values():
            for p in getattr(atom, "patterns", []):
                if len(p) > 3:
                    pattern_counts[p] += 1

        topics: list[dict[str, Any]] = []
        for tag, count in tag_counts.most_common(50):
            if count < self.min_atoms:
                continue
            scores = tag_scores[tag]
            avg_conf = sum(scores) / len(scores) if scores else 0
            usage = tag_usage[tag]
            topics.append({
                "topic": tag,
                "atoms": count,
                "avg_confidence": round(avg_conf, 3),
                "total_usage": usage,
                "strength": round(count * avg_conf, 2),
            })

        topics.sort(key=lambda t: t["strength"], reverse=True)

        strong = [t for t in topics if t["strength"] >= 5.0]
        weak = [t for t in topics if t["strength"] < 2.0 and t["atoms"] >= self.min_atoms]

        top_patterns = pattern_counts.most_common(20)
        rare_patterns = [(p, c) for p, c in pattern_counts.items() if c == 1]

        source_counts: Counter[str] = Counter()
        for atom in lattice.atoms.values():
            source_counts[getattr(atom, "source", "unknown")] += 1

        return {
            "total_atoms": len(lattice.atoms),
            "total_topics": len(topics),
            "strong_topics": strong[:10],
            "weak_topics": weak[:10],
            "top_patterns": top_patterns,
            "rare_pattern_count": len(rare_patterns),
            "sources": dict(source_counts.most_common(10)),
            "all_topics": topics,
        }

    def suggest_feeds(self, analysis: dict[str, Any], max_suggestions: int = 5) -> list[dict[str, str]]:
        suggestions: list[dict[str, str]] = []

        for topic in analysis.get("weak_topics", [])[:max_suggestions]:
            suggestions.append({
                "topic": topic["topic"],
                "reason": f"Weak coverage: {topic['atoms']} atoms, strength {topic['strength']}",
                "action": f"--wiki \"{topic['topic']}\" or --arxiv \"{topic['topic']}\"",
            })

        if len(suggestions) < max_suggestions:
            strong = analysis.get("strong_topics", [])
            if strong:
                for t in strong[:2]:
                    suggestions.append({
                        "topic": t["topic"] + " advanced",
                        "reason": f"Deepen strong topic: {t['atoms']} atoms, strength {t['strength']}",
                        "action": f"--arxiv \"{t['topic']}\" or --nasa-ads \"{t['topic']}\"",
                    })

        return suggestions[:max_suggestions]
