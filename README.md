# NOUS (Νοῦς) — The Living Language

**The world's first self-evolving programming language for agentic AI systems.**

```
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \
 | |\  | |_| | |_| |___) |
 |_| \_|\___/ \___/|____/   v1.1.0
```

**Author:** Hlias Staurou (Hlia) | **Project:** Noosphere | **GitHub:** contrario

---

## What is NOUS?

NOUS is a programming language where **code is alive**. Unlike every existing language where programs are static text, NOUS programs:

- **Observe** their own execution
- **Evaluate** their performance via fitness metrics
- **Mutate** their own DNA parameters
- **Evolve** autonomously within constitutional safety boundaries
- **Self-heal** on failure without human intervention

NOUS transpiles to **Python 3.11+ asyncio** and integrates with the Noosphere Multi-Agent Platform (100+ agents, 143+ tools).

---

## Quick Start

```bash
# Install (one time)
pip install lark pydantic --break-system-packages
cp install.sh /usr/local/bin/nous && chmod +x /usr/local/bin/nous

# Use
nous compile gate_alpha.nous          # → gate_alpha.py
nous run gate_alpha.nous              # compile + execute
nous validate gate_alpha.nous         # check laws
nous info gate_alpha.nous             # program summary
nous evolve gate_alpha.nous --cycles 5  # DNA mutation
nous bridge gate_alpha.nous           # Noosphere integration
nous ast gate_alpha.nous --json       # Living AST
nous nsp "[NSP|CT.88|M.safe]"         # parse NSP tokens
nous version                          # show version
```

---

## Language Syntax

### World

Every `.nous` file defines one world — a self-contained execution environment.

```nous
world GateAlpha {
    law CostCeiling = $0.10 per cycle    # inviolable
    law MaxLatency = 30s
    law NoLiveTrading = true
    heartbeat = 5m
}
```

### Soul

The fundamental unit — agent + state + behavior + evolution + healing in one construct.

```nous
soul Scout {
    mind: deepseek-r1 @ Tier1
    senses: [scan_market, fetch_rsi]

    memory {
        signals: [Signal] = []
        confidence: float = 0.0
    }

    instinct {
        let data = sense scan_market()
        remember signals = data.where(score > 0.7)
        speak Signal(pair: data.best, score: data.score)
    }

    dna {
        temperature: 0.3 ~ [0.1, 0.9]
        threshold: 0.7 ~ [0.5, 0.95]
    }

    heal {
        on timeout => retry(3, exponential)
        on hallucination => lower(temperature, 0.1) then retry
        on budget_exceeded => hibernate until next_cycle
    }
}
```

### Messages

Typed inter-soul communication:

```nous
message Signal {
    pair: string
    score: float
    rsi: float?
    source: SoulRef
}
```

### Nervous System

DAG orchestration as native syntax:

```nous
nervous_system {
    Scout -> Quant -> Hunter       # linear pipeline
    Scout -> Monitor               # parallel branch
    [Analyst, Researcher] -> Synth # fan-in
    Alert -> [Monitor, Dashboard]  # fan-out
}
```

### Evolution

Self-mutation as a language primitive:

```nous
evolution {
    schedule: 3:00 AM
    fitness: langfuse(quality_score)

    mutate Scout.dna {
        strategy: genetic(population: 5, generations: 3)
        survive_if: fitness > parent.fitness
        rollback_if: any_law_violated
    }
}
```

### Perception

External event triggers:

```nous
perception {
    on telegram("/scan") => wake Scout
    on cron("*/5 * * * *") => wake_all
    on system_error => alert Telegram
}
```

---

## Tier System

| Tier | Provider | Cost | Models |
|------|----------|------|--------|
| Tier0A | Anthropic Direct | $0.01-0.30 | Claude Haiku, Sonnet |
| Tier0B | OpenAI | $0.01-0.15 | GPT-4o |
| Tier1 | OpenRouter | $0.001-0.01 | DeepSeek, MiMo |
| Tier2 | Free | $0.00 | Gemini Flash Lite |
| Tier3 | Local | $0.00 | Ollama, BitNet |

---

## Type System

**Primitives:** `int`, `float`, `string`, `bool`, `timestamp`, `duration`, `currency`, `tier`, `mode`, `style`

**Composites:** `[T]` (list), `{K: V}` (map), `T?` (optional), `SoulRef`, `ToolRef`

---

## NSP (Noosphere Shorthand Protocol)

Compress LLM instructions. **40-70% token savings.**

```
[NSP|CT.88|F.78|R.scout|M.safe]
→ Confidence Threshold: 0.88 | Focus coefficient: 0.78 | Router: scout | Mode: safe
```

```bash
nous nsp "[NSP|CT.88|M.safe|S.concise]"
nous nsp "CT=0.88,M=safe" --compress
```

---

## Bilingual Keywords

Every keyword works in English and Greek:

```nous
ψυχή Scout {
    μνήμη {
        signals: [Signal] = []
    }
    ένστικτο {
        let data = αίσθηση scan_market()
        θυμάμαι signals = data.filter(score > 0.7)
        λέω Signal(data.top)
    }
}
```

---

## Architecture

```
.nous file → Lark Parser → Living AST (Ψυχόδενδρο) → Validator → Python CodeGen → asyncio runtime
                                  ↑
                            Aevolver (DNA mutations operate directly on this tree)
```

The **Living AST** is not discarded after compilation — it persists in memory as the program's runtime representation. The Aevolver mutates DNA nodes directly on this graph.

---

## File Structure

```
/opt/aetherlang_agents/nous/
├── nous.lark          # EBNF grammar (~200 rules)
├── ast_nodes.py       # 40+ Pydantic V2 AST nodes
├── parser.py          # Lark → Living AST transformer
├── validator.py       # Law checker (8 error categories)
├── codegen.py         # AST → Python 3.11+ asyncio
├── cli.py             # CLI: compile/run/validate/evolve/nsp/info/bridge
├── nsp.py             # Noosphere Shorthand Protocol
├── aevolver.py        # DNA mutation engine
├── bridge.py          # Noosphere integration analyzer
├── migrate.py         # YAML/TOML → .nous converter
├── gate_alpha.nous    # Example: Gate Alpha trading cluster
└── README.md          # This file
```

---

## Migration from YAML/TOML

Convert existing Noosphere agent configs to `.nous`:

```bash
python3 migrate.py /opt/aetherlang_agents/agents/
python3 migrate.py /opt/aetherlang_agents/agents/greek_tax_advisor.yaml
```

---

## Safety Model

**Compile-time:** Type mismatches, undefined references, cycle detection, missing heal blocks.

**Runtime:** Cost tracking per LLM call, constitution hash verification, forbidden phrase detection, atomic rollback on law violations.

**Evolution:** Shadow AST → validate → test → fitness check → commit or rollback. Never unsupervised.

---

## What Makes NOUS Unique

| Innovation | Why It's Unprecedented |
|------------|----------------------|
| `soul` keyword | Agents as first-class grammar primitives |
| Living AST | Runtime-mutable AST that IS the program |
| `dna` block | Genetic evolution built into syntax |
| `law` keyword | Safety as physics, not middleware |
| `heal` block | Declarative self-repair |
| `nervous_system` | DAG as native syntax (A -> B -> C) |
| Bilingual | English + Greek keywords |
| `speak/listen` | Type-safe inter-agent channels |

---

*NOUS v1.1.0 — Born from Noosphere. Built for the future.*
*Hlias Staurou | April 2026 | Athens, Greece*
