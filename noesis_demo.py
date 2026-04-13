"""
Νόηση (Noesis) — Live Demo
============================
Demonstrates the symbolic reasoning engine:
1. Learning from text (compression)
2. Thinking (resonance + weaving)
3. Evolution (pruning + merging)
4. Oracle integration (hybrid mode)

No GPU. No billions of parameters. Pure algorithmic intelligence.
"""
from __future__ import annotations

import time
from pathlib import Path
from noesis_engine import NoesisEngine, NoesisSoul


KNOWLEDGE_CORPUS: list[str] = [
    # Astronomy
    "The Sun is a G-type main-sequence star at the center of the Solar System. "
    "It contains 99.86% of the total mass of the Solar System. "
    "The Sun's core temperature reaches approximately 15 million degrees Celsius. "
    "Nuclear fusion in the Sun converts hydrogen into helium, releasing enormous energy. "
    "Light from the Sun takes about 8 minutes and 20 seconds to reach Earth.",

    "The Moon is Earth's only natural satellite. "
    "It orbits Earth at an average distance of 384,400 kilometers. "
    "The Moon's gravitational influence produces ocean tides on Earth. "
    "The same side of the Moon always faces Earth due to tidal locking. "
    "The Moon has no atmosphere and no liquid water on its surface.",

    "Mars is the fourth planet from the Sun in our Solar System. "
    "Mars is often called the Red Planet because of iron oxide on its surface. "
    "Olympus Mons on Mars is the largest volcano in the Solar System. "
    "Mars has two small moons named Phobos and Deimos. "
    "The average temperature on Mars is about minus 60 degrees Celsius.",

    # Greek philosophy
    "Socrates was an ancient Greek philosopher from Athens, born around 470 BC. "
    "Socrates developed the Socratic method of questioning to stimulate critical thinking. "
    "Socrates believed that wisdom begins with recognizing one's own ignorance. "
    "Socrates was sentenced to death by drinking hemlock in 399 BC. "
    "Socrates left no written works; his ideas survive through his students.",

    "Plato was a student of Socrates and founded the Academy in Athens. "
    "Plato proposed the Theory of Forms, suggesting abstract perfect entities exist beyond the physical world. "
    "The Republic is one of Plato's most influential works on justice and governance. "
    "Plato believed philosophers should rule as kings for an ideal state. "
    "Plato's dialogues remain foundational texts in Western philosophy.",

    "Aristotle studied at Plato's Academy for twenty years before founding his own school, the Lyceum. "
    "Aristotle created formal logic and the syllogism as a method of deductive reasoning. "
    "Aristotle classified living organisms and is considered the father of biology. "
    "Aristotle tutored Alexander the Great during his youth. "
    "Aristotle's works cover physics, metaphysics, ethics, politics, and poetics.",

    # Computer science
    "Alan Turing proposed the concept of a universal computing machine in 1936. "
    "The Turing machine is a mathematical model that defines the limits of computation. "
    "Turing played a crucial role in breaking the Enigma code during World War II. "
    "The Turing test evaluates whether a machine can exhibit intelligent behavior equivalent to a human. "
    "Turing is widely considered the father of theoretical computer science and artificial intelligence.",

    "Claude Shannon founded information theory with his 1948 paper. "
    "Shannon proved that information can be quantified in binary digits called bits. "
    "Shannon's noisy channel coding theorem defines the maximum rate of error-free communication. "
    "Shannon demonstrated that Boolean algebra could be applied to electrical circuits. "
    "Shannon's work laid the mathematical foundations for digital computing and telecommunications.",

    # NOUS-specific knowledge
    "NOUS is a programming language designed for multi-agent AI systems. "
    "NOUS uses souls as first-class citizens to represent autonomous agents. "
    "The nervous system in NOUS defines the directed acyclic graph connecting souls. "
    "NOUS compiles to Python 3.11+ asyncio code for concurrent execution. "
    "Laws in NOUS are constitutional constraints enforced at compile time.",

    "Noesis is a symbolic reasoning engine embedded in the NOUS language. "
    "Noesis stores knowledge as compressed atoms instead of neural network weights. "
    "Noesis uses pattern resonance instead of matrix multiplication for retrieval. "
    "Noesis can learn without backpropagation through algorithmic compression. "
    "Noesis evolves its knowledge lattice through pruning, merging, and mutation.",

    # Cooking (for Hlia)
    "Maillard reaction occurs when amino acids and reducing sugars react at high temperatures. "
    "The Maillard reaction is responsible for the browning and flavor of seared meat. "
    "Caramelization is the oxidation of sugar at temperatures above 170 degrees Celsius. "
    "Emulsification combines two immiscible liquids like oil and water into a stable mixture. "
    "Fermentation is a metabolic process where organisms convert carbohydrates to alcohol or acids.",

    "Greek cuisine relies heavily on olive oil, fresh vegetables, and herbs. "
    "Moussaka is a layered dish of eggplant, ground meat, and bechamel sauce. "
    "Souvlaki consists of small pieces of meat grilled on a skewer. "
    "Tzatziki is a yogurt-based sauce with cucumber, garlic, and olive oil. "
    "Spanakopita is a savory pie made with spinach and feta cheese in phyllo dough.",
]


def run_demo() -> None:
    print("╔══════════════════════════════════════════════╗")
    print("║  Νόηση (Noesis) — Symbolic Reasoning Engine  ║")
    print("║  No GPU • No Billions of Parameters • Pure Νοῦς ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    engine = NoesisEngine()

    print("═══ Phase 1: Learning (Compression) ═══")
    print()
    t0 = time.perf_counter()
    total_atoms = 0
    for i, text in enumerate(KNOWLEDGE_CORPUS):
        added = engine.learn(text, source=f"corpus_{i}")
        total_atoms += added
        topic = text.split(".")[0][:60]
        print(f"  [{i+1:2d}] +{added:3d} atoms | {topic}...")
    elapsed = time.perf_counter() - t0
    print()
    print(f"  Total: {total_atoms} atoms in {elapsed*1000:.1f}ms")
    print(f"  Lattice size: {engine.lattice.size} unique atoms")
    print()

    print("═══ Phase 2: Evolution (Compression) ═══")
    print()
    evo = engine.evolve(min_confidence=0.1, min_usage=0)
    print(evo)
    print()

    print("═══ Phase 3: Thinking (Resonance + Weaving) ═══")
    print()

    queries = [
        ("What is the Sun?", "compose"),
        ("Tell me about Socrates", "compose"),
        ("What did Turing contribute to computing?", "compose"),
        ("What is NOUS?", "compose"),
        ("How does the Maillard reaction work?", "compose"),
        ("What is Noesis?", "compose"),
        ("Who founded information theory?", "compose"),
        ("Mars temperature moons", "compose"),
        ("Plato Academy Forms", "compose"),
        ("Greek cuisine olive oil", "compose"),
        ("relationship between Socrates Plato Aristotle", "reason"),
        ("connection between compression and intelligence", "reason"),
    ]

    for query, mode in queries:
        result = engine.think(query, mode=mode, top_k=5, use_oracle=False)
        print(f"  Q: {query}")
        print(f"  A: {result.response[:200]}")
        print(f"     [{result.atoms_matched} atoms, score={result.top_score:.3f}, {result.elapsed_ms:.1f}ms]")
        print()

    print("═══ Phase 4: Reinforcement Learning ═══")
    print()
    engine.reinforce("What is the Sun?", was_helpful=True)
    engine.reinforce("What is Noesis?", was_helpful=True)
    engine.reinforce("random gibberish query", was_helpful=False)
    print("  Reinforced 2 positive, 1 negative")
    print()

    print("═══ Phase 5: Statistics ═══")
    print()
    stats = engine.stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()

    print("═══ Phase 6: Persistence ═══")
    print()
    save_path = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")
    engine.save(save_path)
    print(f"  Saved lattice to {save_path}")
    engine2 = NoesisEngine()
    loaded = engine2.load(save_path)
    print(f"  Loaded {loaded} atoms into new engine")
    result2 = engine2.think("What is NOUS?", use_oracle=False)
    print(f"  Verification query: {result2.response[:150]}")
    print()

    print("═══ Phase 7: Atom Inspection ═══")
    print()
    search_results = engine.search_atoms("Sun solar", top_k=3)
    for sr in search_results:
        atom = sr["atom"]
        print(f"  Atom {atom['id'][:12]}...")
        print(f"    patterns: {atom['patterns'][:5]}")
        print(f"    template: {atom['template'][:80]}...")
        print(f"    confidence: {atom['confidence']:.2f}")
        print(f"    level: {atom['level']}")
        print()

    print("═══ Phase 8: NOUS Soul Integration ═══")
    print()
    soul = NoesisSoul(name="Thinker", engine=engine)
    learn_result = soul.sense_learn(
        "Quantum computing uses qubits that can exist in superposition. "
        "Unlike classical bits, qubits leverage entanglement for exponential speedup."
    )
    print(f"  sense_learn: {learn_result}")
    think_result = soul.sense_think("quantum computing qubits")
    print(f"  sense_think: {think_result['response'][:150]}")
    print(f"  sense_stats: atoms={soul.sense_stats()['atoms']}")
    print()

    print("╔══════════════════════════════════════════════╗")
    print("║  Demo complete. Noesis is alive.              ║")
    print("║  {atoms} atoms | {queries} queries | 0 GPUs      ║".format(
        atoms=engine.lattice.size,
        queries=len(engine._query_log),
    ))
    print("╚══════════════════════════════════════════════╝")


if __name__ == "__main__":
    run_demo()
