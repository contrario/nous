"""
NOUS Aevolver Live — Ζωντανή Εξέλιξη
======================================
Connects the Aevolver to live fitness data, scheduled evolution,
git commits, and Telegram notifications.

"While you sleep, I evolve."
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from ast_nodes import NousProgram, SoulNode
from parser import parse_nous_file
from validator import validate_program
from aevolver import Aevolver, EvolutionReport

log = logging.getLogger("nous.aevolver_live")

NOUS_DIR = Path("/opt/aetherlang_agents/nous")
PORTFOLIO_PATH = NOUS_DIR / "paper_portfolio.json"
EVOLUTION_LOG = NOUS_DIR / "evolution_history.json"


class LangfuseFitness:

    def __init__(self) -> None:
        self.public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
        self.host = os.environ.get("LANGFUSE_BASE_URL", os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"))
        self._available = bool(self.public_key and self.secret_key)
        if self._available:
            log.info(f"Langfuse connected: {self.host}")
        else:
            log.info("Langfuse not configured, using paper trading fitness")

    @property
    def available(self) -> bool:
        return self._available

    async def get_score(self, soul_name: str, metric: str = "quality_score", days: int = 7) -> Optional[float]:
        if not self._available:
            return None

        async with httpx.AsyncClient(timeout=15.0) as http:
            try:
                resp = await http.get(
                    f"{self.host}/api/public/scores",
                    params={"name": metric, "userId": soul_name.lower(), "limit": 50},
                    auth=(self.public_key, self.secret_key),
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning(f"Langfuse API error: {e}")
                return None

        scores = data.get("data", [])
        if not scores:
            log.info(f"No Langfuse scores for {soul_name}.{metric}")
            return None

        values = [s.get("value", 0) for s in scores if isinstance(s.get("value"), (int, float))]
        if not values:
            return None

        avg = sum(values) / len(values)
        log.info(f"Langfuse fitness {soul_name}.{metric}: {avg:.4f} ({len(values)} scores)")
        return avg

    async def log_evolution(self, soul_name: str, report: dict[str, Any]) -> None:
        if not self._available:
            return

        async with httpx.AsyncClient(timeout=10.0) as http:
            try:
                await http.post(
                    f"{self.host}/api/public/scores",
                    json={
                        "name": "evolution_fitness",
                        "value": report.get("child_fitness", 0),
                        "userId": soul_name.lower(),
                        "comment": report.get("reason", ""),
                    },
                    auth=(self.public_key, self.secret_key),
                )
            except Exception as e:
                log.warning(f"Langfuse log error: {e}")


class PaperTradingFitness:

    def __init__(self) -> None:
        self._portfolio_path = PORTFOLIO_PATH

    def get_score(self, soul_name: str) -> float:
        if not self._portfolio_path.exists():
            return 0.5

        try:
            portfolio = json.loads(self._portfolio_path.read_text())
        except (json.JSONDecodeError, OSError):
            return 0.5

        total_trades = portfolio.get("total_trades", 0)
        total_pnl = portfolio.get("total_pnl", 0.0)
        balance = portfolio.get("balance", 10000.0)
        closed = portfolio.get("closed_trades", [])

        if total_trades == 0:
            return 0.5

        wins = sum(1 for t in closed if t.get("close_price", 0) > t.get("entry_price", 0))
        win_rate = wins / max(len(closed), 1)
        roi = (balance - 10000.0) / 10000.0
        score = 0.3 + (win_rate * 0.4) + (min(max(roi, -0.5), 0.5) + 0.5) * 0.3
        return round(min(1.0, max(0.0, score)), 4)


class SourceRewriter:

    @staticmethod
    def update_dna(source_path: Path, soul_name: str, gene_updates: dict[str, Any]) -> bool:
        if not source_path.exists():
            return False

        text = source_path.read_text(encoding="utf-8")
        modified = False

        for gene_name, new_value in gene_updates.items():
            pattern = re.compile(
                rf'(soul\s+{re.escape(soul_name)}\s*\{{.*?dna\s*\{{[^}}]*?)'
                rf'({re.escape(gene_name)}\s*:\s*)([\d.]+)(\s*~)',
                re.DOTALL,
            )
            match = pattern.search(text)
            if match:
                formatted = str(new_value) if isinstance(new_value, int) else f"{new_value:.4f}" if isinstance(new_value, float) else str(new_value)
                text = text[:match.start(3)] + formatted + text[match.end(3):]
                modified = True
                log.info(f"Rewrote {soul_name}.dna.{gene_name} = {formatted} in {source_path.name}")

        if modified:
            source_path.write_text(text, encoding="utf-8")

        return modified


class GitCommitter:

    def __init__(self, repo_dir: Path) -> None:
        self.repo_dir = repo_dir
        self._git_available = self._check_git()

    def _check_git(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def init_if_needed(self) -> None:
        if self._git_available:
            return
        try:
            subprocess.run(["git", "init"], cwd=str(self.repo_dir), capture_output=True, timeout=5)
            subprocess.run(["git", "add", "."], cwd=str(self.repo_dir), capture_output=True, timeout=5)
            subprocess.run(
                ["git", "commit", "-m", "NOUS: initial commit"],
                cwd=str(self.repo_dir), capture_output=True, timeout=10,
            )
            self._git_available = True
            log.info("Git repo initialized")
        except Exception as e:
            log.warning(f"Git init failed: {e}")

    def commit(self, message: str, files: list[str] | None = None) -> bool:
        if not self._git_available:
            return False

        try:
            if files:
                for f in files:
                    subprocess.run(
                        ["git", "add", f],
                        cwd=str(self.repo_dir), capture_output=True, timeout=5,
                    )
            else:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(self.repo_dir), capture_output=True, timeout=5,
                )

            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.repo_dir), capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                log.info(f"Git commit: {message}")
                return True
            else:
                log.debug(f"Git commit skipped (no changes): {result.stderr.strip()}")
                return False
        except Exception as e:
            log.warning(f"Git commit failed: {e}")
            return False


class TelegramNotifier:

    def __init__(self) -> None:
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    async def notify(self, message: str) -> None:
        if not self.token or not self.chat_id:
            log.info(f"[TELEGRAM] {message}")
            return

        async with httpx.AsyncClient(timeout=10.0) as http:
            try:
                await http.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
                )
            except Exception as e:
                log.warning(f"Telegram notify failed: {e}")


class AevolverLive:

    def __init__(
        self,
        source_path: Path,
        program: NousProgram,
    ) -> None:
        self.source_path = source_path
        self.program = program
        self.langfuse = LangfuseFitness()
        self.paper = PaperTradingFitness()
        self.rewriter = SourceRewriter()
        self.git = GitCommitter(NOUS_DIR)
        self.telegram = TelegramNotifier()

    async def _fitness_fn(self, soul: SoulNode) -> float:
        if self.langfuse.available:
            score = await self.langfuse.get_score(soul.name)
            if score is not None:
                return score

        return self.paper.get_score(soul.name)

    def _sync_fitness(self, soul: SoulNode) -> float:
        return asyncio.get_event_loop().run_until_complete(self._fitness_fn(soul))

    async def evolve(self) -> EvolutionReport:
        log.info("═══ NOUS Evolution Cycle Starting ═══")

        fitness_cache: dict[str, float] = {}
        for soul in self.program.souls:
            fitness_cache[soul.name] = await self._fitness_fn(soul)
            log.info(f"  {soul.name} fitness: {fitness_cache[soul.name]:.4f}")

        def cached_fitness(soul: SoulNode) -> float:
            return fitness_cache.get(soul.name, 0.5)

        aevolver = Aevolver(self.program, fitness_fn=cached_fitness)
        report = aevolver.evolve()

        for cycle in report.cycles:
            if cycle.accepted and cycle.mutations:
                gene_updates = {m.gene_name: m.new_value for m in cycle.mutations}
                self.rewriter.update_dna(self.source_path, cycle.soul_name, gene_updates)

                commit_msg = (
                    f"NOUS evolution: {cycle.soul_name} "
                    f"fitness {cycle.parent_fitness:.3f}→{cycle.child_fitness:.3f}\n\n"
                    + "\n".join(f"  {m.gene_name}: {m.old_value} → {m.new_value}" for m in cycle.mutations)
                )
                self.git.commit(commit_msg, [str(self.source_path)])

                if self.langfuse.available:
                    await self.langfuse.log_evolution(cycle.soul_name, {
                        "child_fitness": cycle.child_fitness,
                        "reason": cycle.reason,
                    })

        self._save_history(report)

        summary = self._build_summary(report)
        await self.telegram.notify(summary)

        log.info("═══ Evolution Cycle Complete ═══")
        return report

    def _build_summary(self, report: EvolutionReport) -> str:
        lines = ["🧬 <b>NOUS Evolution Report</b>"]
        lines.append(f"⏰ {time.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        for c in report.cycles:
            icon = "✅" if c.accepted else "❌"
            lines.append(f"{icon} <b>{c.soul_name}</b>")
            lines.append(f"  Fitness: {c.parent_fitness:.3f} → {c.child_fitness:.3f}")
            for m in c.mutations:
                lines.append(f"  • {m.gene_name}: {m.old_value} → {m.new_value}")
            lines.append(f"  {c.reason}")
            lines.append("")

        lines.append(f"Total: {report.total_mutations} mutations, {report.accepted_count}/{len(report.cycles)} accepted")
        return "\n".join(lines)

    def _save_history(self, report: EvolutionReport) -> None:
        history: list[dict[str, Any]] = []
        if EVOLUTION_LOG.exists():
            try:
                history = json.loads(EVOLUTION_LOG.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        entry = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cycles": [],
        }
        for c in report.cycles:
            entry["cycles"].append({
                "soul": c.soul_name,
                "accepted": c.accepted,
                "parent_fitness": c.parent_fitness,
                "child_fitness": c.child_fitness,
                "reason": c.reason,
                "mutations": [
                    {"gene": m.gene_name, "old": m.old_value, "new": m.new_value}
                    for m in c.mutations
                ],
            })

        history.append(entry)
        try:
            EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
            EVOLUTION_LOG.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
        except OSError as e:
            log_path = Path(self.source_path).with_suffix(".evolution.json")
            log_path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
            log.info(f"Evolution history saved to {log_path}")


class EvolutionScheduler:

    def __init__(self, source_path: Path, schedule_hour: int = 3, schedule_minute: int = 0) -> None:
        self.source_path = source_path
        self.schedule_hour = schedule_hour
        self.schedule_minute = schedule_minute
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info(f"Evolution scheduler started: daily at {self.schedule_hour:02d}:{self.schedule_minute:02d}")

    async def _loop(self) -> None:
        while self._running:
            now = time.localtime()
            target_today = time.mktime(time.struct_time((
                now.tm_year, now.tm_mon, now.tm_mday,
                self.schedule_hour, self.schedule_minute, 0,
                now.tm_wday, now.tm_yday, now.tm_isdst,
            )))

            current = time.time()
            if current >= target_today:
                target_today += 86400

            wait_seconds = target_today - current
            log.info(f"Next evolution in {wait_seconds / 3600:.1f} hours")

            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                break

            if not self._running:
                break

            await self._run_evolution()

    async def _run_evolution(self) -> None:
        log.info("Scheduled evolution triggered")
        try:
            program = parse_nous_file(self.source_path)
            result = validate_program(program)
            if not result.ok:
                log.error(f"Validation failed before evolution: {result.errors}")
                return

            live = AevolverLive(self.source_path, program)
            await live.evolve()
        except Exception as e:
            log.error(f"Evolution cycle failed: {e}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


async def run_evolution_now(source_path: str | Path) -> EvolutionReport:
    path = Path(source_path)
    program = parse_nous_file(path)
    result = validate_program(program)
    if not result.ok:
        log.error(f"Validation failed: {result.errors}")
        return EvolutionReport()

    live = AevolverLive(path, program)
    return await live.evolve()


def main() -> None:
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    source = sys.argv[1] if len(sys.argv) > 1 else "gate_alpha.nous"
    mode = sys.argv[2] if len(sys.argv) > 2 else "now"

    if mode == "now":
        report = asyncio.run(run_evolution_now(source))
        print(report.summary())
    elif mode == "daemon":
        async def run_daemon() -> None:
            scheduler = EvolutionScheduler(Path(source))
            await scheduler.start()
            try:
                while True:
                    await asyncio.sleep(3600)
            except KeyboardInterrupt:
                await scheduler.stop()
        asyncio.run(run_daemon())
    else:
        print(f"Usage: python3 aevolver_live.py <file.nous> [now|daemon]")


if __name__ == "__main__":
    main()
