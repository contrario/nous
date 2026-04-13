"""
Νόηση Benchmark — Performance & Quality Metrics
=================================================
Tests: throughput, accuracy, compression ratio, scaling, memory.
"""
from __future__ import annotations

import sys
import time
import resource
from pathlib import Path
from noesis_engine import NoesisEngine


QA_PAIRS: list[tuple[str, list[str]]] = [
    ("What is the Sun?", ["star", "solar"]),
    ("Tell me about Socrates", ["philosopher", "athens"]),
    ("What did Turing do?", ["turing", "computing"]),
    ("What is NOUS?", ["language", "agent"]),
    ("Maillard reaction", ["browning", "amino"]),
    ("Who is Plato?", ["academy", "forms"]),
    ("Mars facts", ["planet", "red"]),
    ("Moon orbit", ["satellite", "earth"]),
    ("Shannon information", ["shannon", "information"]),
    ("Aristotle logic", ["aristotle", "logic"]),
    ("Greek food", ["olive", "cuisine"]),
    ("What is Noesis?", ["symbolic", "engine"]),
]

CORPUS: list[str] = [
    "The Sun is a G-type main-sequence star at the center of the Solar System. It contains 99.86% of the total mass of the Solar System.",
    "The Moon is Earth's only natural satellite. It orbits Earth at an average distance of 384,400 kilometers.",
    "Mars is the fourth planet from the Sun. Mars is often called the Red Planet because of iron oxide on its surface.",
    "Socrates was an ancient Greek philosopher from Athens, born around 470 BC. Socrates developed the Socratic method of questioning.",
    "Plato was a student of Socrates and founded the Academy in Athens. Plato proposed the Theory of Forms.",
    "Aristotle studied at Plato's Academy for twenty years. Aristotle created formal logic and the syllogism.",
    "Alan Turing proposed the concept of a universal computing machine in 1936. Turing played a crucial role in breaking the Enigma code.",
    "Claude Shannon founded information theory with his 1948 paper. Shannon proved that information can be quantified in bits.",
    "NOUS is a programming language designed for multi-agent AI systems. NOUS uses souls as first-class citizens to represent autonomous agents.",
    "Noesis is a symbolic reasoning engine embedded in the NOUS language. Noesis stores knowledge as compressed atoms instead of neural network weights.",
    "Maillard reaction occurs when amino acids and reducing sugars react at high temperatures. The Maillard reaction is responsible for browning and flavor.",
    "Greek cuisine relies heavily on olive oil, fresh vegetables, and herbs. Moussaka is a layered dish of eggplant, ground meat, and bechamel sauce.",
]


def run_benchmark() -> None:
    print("╔═══════════════════════════════════════════════╗")
    print("║  Νόηση Benchmark — Performance & Quality      ║")
    print("╚═══════════════════════════════════════════════╝\n")

    engine = NoesisEngine()

    # === 1. LEARNING THROUGHPUT ===
    print("═══ 1. Learning Throughput ═══\n")
    t0 = time.perf_counter()
    total_atoms = 0
    total_chars = 0
    for text in CORPUS:
        added = engine.learn(text, source="benchmark")
        total_atoms += added
        total_chars += len(text)
    learn_time = time.perf_counter() - t0
    print(f"  Corpus: {len(CORPUS)} documents, {total_chars:,} characters")
    print(f"  Atoms created: {total_atoms}")
    print(f"  Time: {learn_time*1000:.2f}ms")
    print(f"  Throughput: {total_chars / learn_time:,.0f} chars/sec")
    print(f"  Compression: {total_chars} chars → {total_atoms} atoms ({total_chars/max(1,total_atoms):.0f} chars/atom)\n")

    # === 2. QUERY ACCURACY ===
    print("═══ 2. Query Accuracy ═══\n")
    correct = 0
    total = len(QA_PAIRS)
    query_times: list[float] = []
    for query, expected_words in QA_PAIRS:
        t1 = time.perf_counter()
        result = engine.think(query, mode="compose", top_k=5, use_oracle=False)
        qt = (time.perf_counter() - t1) * 1000
        query_times.append(qt)
        response_lower = result.response.lower()
        found = sum(1 for w in expected_words if w in response_lower)
        hit = found >= 1
        if hit:
            correct += 1
        status = "✓" if hit else "✗"
        print(f"  {status} Q: {query[:40]:<42} score={result.top_score:.3f}  {qt:.2f}ms")
    accuracy = correct / total * 100
    avg_time = sum(query_times) / len(query_times)
    print(f"\n  Accuracy: {correct}/{total} ({accuracy:.0f}%)")
    print(f"  Avg query time: {avg_time:.2f}ms")
    print(f"  P99 query time: {sorted(query_times)[-1]:.2f}ms\n")

    # === 3. SCALING TEST ===
    print("═══ 3. Scaling Test ═══\n")
    engine2 = NoesisEngine()
    scaling_text = "The quick brown fox jumps over the lazy dog near the river bank. " * 10
    sizes = [10, 50, 100, 500, 1000]
    for n in sizes:
        e = NoesisEngine()
        t2 = time.perf_counter()
        for i in range(n):
            variant = scaling_text.replace("fox", f"fox_{i}").replace("dog", f"dog_{i}")
            e.learn(variant, source=f"scale_{i}")
        learn_t = (time.perf_counter() - t2) * 1000
        t3 = time.perf_counter()
        for _ in range(10):
            e.think("quick brown fox jumps", use_oracle=False)
        query_t = (time.perf_counter() - t3) * 1000 / 10
        print(f"  n={n:5d} | lattice={e.lattice.size:5d} atoms | learn={learn_t:8.1f}ms | query={query_t:.2f}ms")
    print()

    # === 4. EVOLUTION TEST ===
    print("═══ 4. Evolution Test ═══\n")
    engine3 = NoesisEngine()
    for text in CORPUS * 3:
        engine3.learn(text, source="evo_test")
    before = engine3.lattice.size
    t4 = time.perf_counter()
    result = engine3.evolve(min_confidence=0.1, min_usage=0)
    evo_time = (time.perf_counter() - t4) * 1000
    print(f"  Before: {result.initial_size} atoms")
    print(f"  Pruned: {result.pruned} | Merged: {result.merged}")
    print(f"  After:  {result.final_size} atoms")
    print(f"  Time: {evo_time:.2f}ms\n")

    # === 5. MEMORY USAGE ===
    print("═══ 5. Memory Usage ═══\n")
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "linux":
        mem_mb = mem / 1024
    else:
        mem_mb = mem / 1024 / 1024
    print(f"  Peak RSS: {mem_mb:.1f} MB")
    print(f"  Atoms in memory: {engine.lattice.size}")
    print(f"  Unique patterns: {len(engine.lattice.inverted)}")
    print(f"  Unique relations: {len(engine.lattice.relation_index)}\n")

    # === 6. PERSISTENCE TEST ===
    print("═══ 6. Persistence Test ═══\n")
    save_path = Path("/opt/aetherlang_agents/nous/bench_lattice.json")
    t5 = time.perf_counter()
    engine.save(save_path)
    save_time = (time.perf_counter() - t5) * 1000
    file_size = save_path.stat().st_size
    engine_reload = NoesisEngine()
    t6 = time.perf_counter()
    loaded = engine_reload.load(save_path)
    load_time = (time.perf_counter() - t6) * 1000
    print(f"  Save: {save_time:.2f}ms | {file_size:,} bytes")
    print(f"  Load: {load_time:.2f}ms | {loaded} atoms")
    print(f"  Size on disk: {file_size/1024:.1f} KB\n")

    # === SUMMARY ===
    print("╔═══════════════════════════════════════════════╗")
    print(f"║  Accuracy:    {accuracy:5.1f}%                          ║")
    print(f"║  Avg Query:   {avg_time:5.2f}ms                         ║")
    print(f"║  Atoms:       {engine.lattice.size:5d}                           ║")
    print(f"║  Memory:      {mem_mb:5.1f} MB                         ║")
    print(f"║  Disk:        {file_size/1024:5.1f} KB                         ║")
    print(f"║  GPU needed:  0                               ║")
    print(f"║  Parameters:  0                               ║")
    print("╚═══════════════════════════════════════════════╝")
    save_path.unlink(missing_ok=True)


if __name__ == "__main__":
    run_benchmark()
