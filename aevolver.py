"""
NOUS Aevolver — Εξέλιξη (Evolution)
=====================================
Operates directly on the Living AST to mutate DNA genes.
Shadow-tests mutations, measures fitness, commits or rolls back atomically.

"While you sleep, I evolve."
"""
from __future__ import annotations

import copy
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ast_nodes import (
    NousProgram, SoulNode, DnaNode, GeneNode, EvolutionNode,
    MutateBlockNode,
)
from validator import validate_program, ValidationResult

log = logging.getLogger("nous.aevolver")


@dataclass
class MutationRecord:
    soul_name: str
    gene_name: str
    old_value: Any
    new_value: Any
    timestamp: float = field(default_factory=time.time)


@dataclass
class EvolutionCycleResult:
    soul_name: str
    mutations: list[MutationRecord] = field(default_factory=list)
    parent_fitness: float = 0.0
    child_fitness: float = 0.0
    accepted: bool = False
    rolled_back: bool = False
    reason: str = ""
    duration_s: float = 0.0


@dataclass
class EvolutionReport:
    timestamp: float = field(default_factory=time.time)
    cycles: list[EvolutionCycleResult] = field(default_factory=list)

    @property
    def total_mutations(self) -> int:
        return sum(len(c.mutations) for c in self.cycles)

    @property
    def accepted_count(self) -> int:
        return sum(1 for c in self.cycles if c.accepted)

    def summary(self) -> str:
        lines = ["═══ NOUS Evolution Report ═══"]
        for c in self.cycles:
            status = "✓ ACCEPTED" if c.accepted else "✗ ROLLED BACK"
            lines.append(f"\n  Soul: {c.soul_name} [{status}]")
            lines.append(f"  Fitness: {c.parent_fitness:.3f} → {c.child_fitness:.3f}")
            lines.append(f"  Reason: {c.reason}")
            for m in c.mutations:
                lines.append(f"    Gene {m.gene_name}: {m.old_value} → {m.new_value}")
        lines.append(f"\nTotal: {self.total_mutations} mutations, {self.accepted_count}/{len(self.cycles)} accepted")
        return "\n".join(lines)


class Aevolver:
    """
    Mutates DNA genes on the Living AST.
    Never modifies the live AST directly — always works on shadow copies.
    """

    def __init__(
        self,
        program: NousProgram,
        fitness_fn: Optional[Callable[[SoulNode], float]] = None,
    ) -> None:
        self.program = program
        self.fitness_fn = fitness_fn or self._default_fitness
        self.history: list[EvolutionReport] = []

    def evolve(self) -> EvolutionReport:
        report = EvolutionReport()

        evo = self.program.evolution
        if evo is None:
            log.warning("No evolution block in program")
            return report

        for mutate_block in evo.mutations:
            result = self._evolve_target(mutate_block)
            report.cycles.append(result)

        self.history.append(report)
        log.info(report.summary())
        return report

    def mutate_soul_dna(self, soul_name: str) -> EvolutionCycleResult:
        soul = self._find_soul(soul_name)
        if soul is None:
            return EvolutionCycleResult(soul_name=soul_name, reason=f"Soul {soul_name} not found")
        if soul.dna is None:
            return EvolutionCycleResult(soul_name=soul_name, reason=f"Soul {soul_name} has no DNA")

        mutate_block = MutateBlockNode(target=f"{soul_name}.dna")
        return self._evolve_target(mutate_block)

    def _evolve_target(self, mutate_block: MutateBlockNode) -> EvolutionCycleResult:
        t0 = time.perf_counter()
        parts = mutate_block.target.split(".")
        soul_name = parts[0]

        soul = self._find_soul(soul_name)
        if soul is None:
            return EvolutionCycleResult(
                soul_name=soul_name,
                reason=f"Soul {soul_name} not found",
                duration_s=time.perf_counter() - t0,
            )

        if soul.dna is None:
            return EvolutionCycleResult(
                soul_name=soul_name,
                reason=f"Soul {soul_name} has no DNA block",
                duration_s=time.perf_counter() - t0,
            )

        parent_fitness = self.fitness_fn(soul)

        shadow_program = copy.deepcopy(self.program)
        shadow_soul = self._find_soul_in(soul_name, shadow_program)
        if shadow_soul is None or shadow_soul.dna is None:
            return EvolutionCycleResult(
                soul_name=soul_name,
                reason="Shadow copy failed",
                duration_s=time.perf_counter() - t0,
            )

        mutations = self._mutate_genes(shadow_soul.dna)

        validation = validate_program(shadow_program)
        if not validation.ok:
            return EvolutionCycleResult(
                soul_name=soul_name,
                mutations=mutations,
                parent_fitness=parent_fitness,
                child_fitness=0.0,
                accepted=False,
                rolled_back=True,
                reason=f"Law violation: {validation.errors[0]}",
                duration_s=time.perf_counter() - t0,
            )

        child_fitness = self.fitness_fn(shadow_soul)

        if child_fitness > parent_fitness:
            self._apply_mutations(soul, mutations)
            return EvolutionCycleResult(
                soul_name=soul_name,
                mutations=mutations,
                parent_fitness=parent_fitness,
                child_fitness=child_fitness,
                accepted=True,
                reason=f"Fitness improved: {parent_fitness:.3f} → {child_fitness:.3f}",
                duration_s=time.perf_counter() - t0,
            )
        else:
            return EvolutionCycleResult(
                soul_name=soul_name,
                mutations=mutations,
                parent_fitness=parent_fitness,
                child_fitness=child_fitness,
                accepted=False,
                rolled_back=True,
                reason=f"Fitness did not improve: {parent_fitness:.3f} → {child_fitness:.3f}",
                duration_s=time.perf_counter() - t0,
            )

    def _mutate_genes(self, dna: DnaNode) -> list[MutationRecord]:
        mutations = []
        for gene in dna.genes:
            old_value = gene.value
            new_value = self._mutate_gene(gene)
            if new_value != old_value:
                gene.value = new_value
                mutations.append(MutationRecord(
                    soul_name="",
                    gene_name=gene.name,
                    old_value=old_value,
                    new_value=new_value,
                ))
        return mutations

    def _mutate_gene(self, gene: GeneNode) -> Any:
        if not gene.range or len(gene.range) < 2:
            return gene.value

        all_numeric = all(isinstance(v, (int, float)) for v in gene.range)

        if all_numeric:
            min_val = min(gene.range)
            max_val = max(gene.range)
            if isinstance(gene.value, int) and all(isinstance(v, int) for v in gene.range):
                return random.randint(int(min_val), int(max_val))
            else:
                return round(random.uniform(float(min_val), float(max_val)), 4)
        else:
            return random.choice(gene.range)

    def _apply_mutations(self, soul: SoulNode, mutations: list[MutationRecord]) -> None:
        if soul.dna is None:
            return
        gene_map = {g.name: g for g in soul.dna.genes}
        for m in mutations:
            if m.gene_name in gene_map:
                gene_map[m.gene_name].value = m.new_value
                log.info(f"Applied mutation: {soul.name}.{m.gene_name} = {m.new_value}")

    def _find_soul(self, name: str) -> Optional[SoulNode]:
        return self._find_soul_in(name, self.program)

    def _find_soul_in(self, name: str, program: NousProgram) -> Optional[SoulNode]:
        for soul in program.souls:
            if soul.name == name:
                return soul
        return None

    def _default_fitness(self, soul: SoulNode) -> float:
        if soul.dna is None:
            return 0.5
        score = 0.5
        for gene in soul.dna.genes:
            if isinstance(gene.value, (int, float)) and gene.range:
                all_numeric = all(isinstance(v, (int, float)) for v in gene.range)
                if all_numeric:
                    min_val = min(gene.range)
                    max_val = max(gene.range)
                    mid = (min_val + max_val) / 2
                    dist = abs(gene.value - mid) / max(max_val - min_val, 0.001)
                    score += (1 - dist) * 0.1
        return min(1.0, score)

    def get_dna_snapshot(self, soul_name: str) -> Optional[dict[str, Any]]:
        soul = self._find_soul(soul_name)
        if soul is None or soul.dna is None:
            return None
        return {g.name: {"value": g.value, "range": g.range} for g in soul.dna.genes}

    def export_history(self, path: str | Path) -> None:
        data = []
        for report in self.history:
            cycles = []
            for c in report.cycles:
                cycles.append({
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
            data.append({"timestamp": report.timestamp, "cycles": cycles})
        Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
