# ΝΟΗΣΗ + NOUS — SESSION HANDOFF (Phases 2-6)
## 13 Απριλίου 2026 | Απόγευμα-Βράδυ | Hlia + Claude
## Από Quality Engine μέχρι NOUS Language Integration

---

## 1. ΤΙ ΕΙΧΑΜΕ ΠΡΙΝ ΞΕΚΙΝΗΣΟΥΜΕ

### Noesis Engine v1.0
- 370 atoms στο lattice, 300KB JSON
- Resonator: raw token overlap (F1 scoring), όλες οι λέξεις ίσο βάρος
- Weaver: compose mode, βάζει atoms σε σειρά score χωρίς φιλτράρισμα
- Oracle: DeepSeek → Mistral → SiliconFlow → Claude (4 tiers)
- Telegram bot: 14 commands, 7 free APIs
- 2 servers: A (neurodoc 188.245.245.132), B (neuroaether 46.224.188.209)
- Cron: daily feeds 04:00, auto-restart 5min, lattice sync A↔B at 04:30

### NOUS Language v1.9.0
- 332 γραμμές grammar (nous.lark)
- 40+ AST nodes (Pydantic V2)
- Full pipeline: parse → validate → codegen → py_compile
- 18 CLI commands
- Noesis integration μόνο μέσω `sense noesis_think()` wrappers

---

## 2. PHASE 2 — QUALITY ENGINE

### Τι κάναμε
Αντικαταστήσαμε το raw token overlap scoring με BM25, προσθέσαμε query understanding, deduplication, answer ranking, και relevance gate.

### Αρχεία
- `noesis_quality_patch.py` — monkey-patch, αντικαθιστά `Resonator.resonate()` και `Weaver._compose()` χωρίς να αλλάξει το `noesis_engine.py`

### Πώς δουλεύει

**BM25 Scoring:**
- Κάθε query token παίρνει IDF score: `log((N - df + 0.5) / (df + 0.5) + 1)`
- Σπάνιοι όροι (π.χ. "tx-105") παίρνουν πολύ υψηλό IDF
- Συχνοί όροι (π.χ. "action", "system") παίρνουν χαμηλό IDF
- Parameters: k1=1.5, b=0.75

**Query Classification (EN + GR):**
- "What is X?" / "Τι είναι X?" → boost `is_a` relation +0.4
- "Who created X?" / "Ποιος δημιούργησε X?" → boost `created_by` +0.3
- "When/Where/How/Why" + Greek equivalents
- Subject extraction: αφαιρεί question words, articles

**Deduplication:**
- Jaccard similarity μεταξύ atom patterns και templates
- Threshold ≥0.6 → κρατάει μόνο τον καλύτερο
- Αποφεύγει πανομοιότυπες απαντήσεις

**Relevance Gate (προστέθηκε μετά από testing):**
- Βρίσκει τους ΣΠΑΝΙΟΤΕΡΟΥΣ query tokens (lowest df)
- Αν υπάρχουν rare tokens (df ≤ max(2, total_atoms/100))
- Atoms που δεν περιέχουν ΚΑΝΕΝΑΝ rare token → score ×0.05
- Αποτέλεσμα: TX-105 atom 6.49 vs Einstein 0.13 (ήταν 2.60)

**Relevance Floor στον Weaver:**
- Atoms με score < 20% του top score → αφαιρούνται από response text
- Αποτρέπει irrelevant atoms να εμφανίζονται στο Telegram

### Bugs & Fixes

**Bug 1: `_inv_index` → `inverted`**
- Ο quality patch χρησιμοποιούσε `lattice._inv_index` αλλά το actual field ονομάζεται `lattice.inverted`
- BM25 doc_freq ήταν κενό → IDF=0 για όλους τους όρους
- Fix: `lattice.inverted`

**Bug 2: Weaver method name**
- Πρώτη version: patch σε `Weaver.compose()` (δεν υπάρχει)
- Actual method: `Weaver._compose()`
- Fix: monkey-patch `_compose` αντί `compose`

**Bug 3: Resonate signature mismatch**
- Πρώτη version: `resonate(query, top_k)` 
- Actual signature: `resonate(query, lattice, top_k, min_score)`
- Fix: match exact signature

**Bug 4: Relevance threshold too loose (10%)**
- Αρχικό: `median_df = total_atoms // 10 = 37`
- "action" (df≈5) classified as rare → Einstein passed gate
- Fix: `max(2, total_atoms // 100) = 3`

**Bug 5: "action" still passed gate (1% threshold)**
- "action" df≈3, still ≤ threshold
- Fix: use only the RAREST tokens (min_df among query tokens)
- `min_df = 1` (tx-105), only tokens with df ≤ 1 count as rare

**Bug 6: TX-105 tokenization**
- `_tokenize()` strips hyphens: "TX-105" → "tx" + "105"
- Subject extraction keeps compound: "tx-105" stays whole
- Both forms added to `all_query_tokens`

### Benchmark Results

| Query | Before | After |
|-------|--------|-------|
| TX-105 query | Einstein 2.60 #1 | TX-105 6.49 #1, Einstein 0.13 |
| Maillard reaction | 5 atoms, correct | 5 atoms, 4.81 score, 2ms |

### Tests: 23/23 ✓

---

## 3. PHASE 3 — REASONING ENGINE

### Τι κάναμε
Πρόσθεσε 4 νέους τύπους atoms: logic, math, temporal + contradiction detection.

### Αρχεία
- `noesis_reasoning.py` — core module
- `noesis_reasoning_patch.py` — monkey-patch

### Πώς δουλεύει

**Logic Atoms:**
- Ανιχνεύει IF/THEN, WHEN/comma, implies patterns
- Greek: ΑΝ/ΤΟΤΕ, ΟΤΑΝ
- Stores: `_type: "logic"`, `_condition`, `_conclusion`
- Evaluation: `evaluate_logic(atom, {"temperature": 180})` → True/False/None
- AND/OR compound conditions
- **Bug fix:** AND/OR check πρέπει να γίνεται ΠΡΙΝ το simple comparison regex, αλλιώς "temperature > 140 and time > 30" parsed λάθος

**Math Atoms:**
- Ανιχνεύει formulas: `kelly = (win_prob * odds - 1) / (odds - 1)`
- Safe eval με whitelist: abs, min, max, sqrt, log, sin, cos, tan, pi, e
- Variable substitution: `evaluate_math(atom, {"win_prob": 0.6, "odds": 2.0})` → 0.2

**Temporal Atoms:**
- Explicit: `(valid: 2026-04-13, expires: 2026-04-14)`
- Auto-detect by keyword + preset TTL:
  - crypto/bitcoin/price: 24h
  - weather/temperature: 6h
  - earthquake: 1h
  - news: 48h
  - stock/exchange_rate: 24h
- `is_expired()`: checks `_expires` against current time
- `filter_expired()`: removes expired atoms from resonation results

**Contradiction Detection:**
- Checks `is_a` conflicts: "Pluto is a planet" vs "Pluto is a dwarf planet"
- Relation conflicts: same subject, same key, different values
- Resolution: demote loser (lower confidence or older birth)
- If confidence drops to 0 → remove from lattice

**Negation Detection:**
- Patterns: "is not", "cannot", "does not", "δεν είναι/μπορεί"
- Stores: `_negates: "pluto|is|a planet since 2006"`

**Integration:**
- `Compressor.compress()` patched → auto-detects atom type on learning
- `Resonator.resonate()` patched → chains Phase 2 resonate → filters expired
- `NoesisEngine` gets new methods: `.find_contradictions()`, `.evaluate()`, `.expire_sweep()`

### Bug Fix: `_rebuild_indices` → `lattice.remove()`
- `expire_sweep` αρχικά: `del lattice.atoms[id]` + `lattice._rebuild_indices()`
- `_rebuild_indices()` δεν υπάρχει στο Lattice
- Fix: `lattice.remove(aid)` — proper cleanup of trie, inverted, concepts, relations

### Tests: 28/28 ✓

---

## 4. PHASE 4 — SCALING ENGINE

### Τι κάναμε
WAL (Write-Ahead Log), lattice merge μεταξύ servers, backup rotation.

### Αρχεία
- `noesis_scaling.py` — core: WAL, LatticeMerger, BackupManager
- `noesis_scaling_patch.py` — monkey-patch
- `noesis_merge.py` — standalone merge script για cron

### Πώς δουλεύει

**WAL (Write-Ahead Log):**
- Append-only JSONL file: `noesis_wal.jsonl`
- Operations: `add`, `remove`, `update`
- Auto-compaction μετά 100 entries
- Replay on load: εφαρμόζει pending operations
- Format: `{"op": "add", "atom": {...}, "ts": 1234567890.0}`

**Lattice Merge:**
- `LatticeMerger.merge(path_a, path_b, output_path)`:
  - Union: atoms που υπάρχουν μόνο σε A ή B → κρατάει
  - Conflict: ίδιο atom ID σε A και B → winner by fitness
  - Fitness: `confidence × 0.4 + success_rate × 0.4 + 0.2`
  - Tie: newer birth wins
- `merge_into_lattice(lattice, other_path)`: live merge χωρίς restart
- Stats: `a_only`, `b_only`, `both_a_wins`, `both_b_wins`, `total`

**Backup Rotation:**
- `BackupManager(backup_dir, max_backups=7)`
- Timestamp filenames: `noesis_lattice_20260413_140621_823.json`
- Millisecond precision αποφεύγει same-second collisions
- Auto-rotate: κρατάει τα τελευταία 7
- Restore: `mgr.restore(backup_path, target_path)`
- List: returns name, path, size_kb, atoms, modified

**Cron Integration (Server A):**
```
# Existing:
30 4 * * * scp lattice.json B:lattice_A.json     # sync A→B
35 4 * * * scp B:lattice.json lattice_B.json      # sync B→A

# New (Phase 4):
40 4 * * * python3 noesis_merge.py >> /var/log/noesis_merge.log 2>&1
```

### Bug Fix: Backup name collision
- `time.strftime("%Y%m%d_%H%M%S")` → same-second backups overwrite
- Fix: `+ f"_{int(time.time() * 1000) % 1000:03d}"` (milliseconds)

### Tests: 17/17 ✓

---

## 5. PHASE 5 — AUTO-FEEDING

### Τι κάναμε
Curiosity engine (εντοπισμός κενών γνώσης), oracle weaning (σταδιακή αποκοπή), topic discovery (ανάλυση lattice).

### Αρχεία
- `noesis_autofeeding.py` — core: CuriosityEngine, OracleWeaner, TopicDiscovery
- `noesis_autofeeding_patch.py` — monkey-patch

### Πώς δουλεύει

**Curiosity Engine:**
- Κάθε `think()` call καταγράφεται
- Score < 0.5 → gap (κενό γνώσης)
- Max 100 gaps, eviction: resolved first, then oldest
- `get_unresolved(limit=10)`: sorted by score (worst first)
- Cooldown: 24h μεταξύ retry attempts
- Auto-resolve: αν re-query score ≥ 0.5
- Persistence: `noesis_gaps.json`
- `save()` / `load()` for restart survival

**Oracle Weaner:**
- Σταδιακή αύξηση oracle threshold:
  - 100 atoms → 0.30
  - 500 → 0.35
  - 1000 → 0.40
  - 2500 → 0.45
  - 5000 → 0.50
  - 10000 → 0.55
  - 25000 → 0.60
- Autonomy bonus: αν autonomy ≥ 80%, +bonus (capped at 0.70)
- Auto-applies μετά κάθε `think()` call
- Status: shows current threshold, next level, atoms needed

**Topic Discovery:**
- Analyzes lattice tags → topics
- Strength: `atom_count × avg_confidence`
- Strong topics: strength ≥ 5.0
- Weak topics: strength < 2.0
- `suggest_feeds()`: suggests wiki/arxiv feeds for weak topics
- Source analysis: ποιες πηγές τροφοδοτούν πόσα atoms

**Current Lattice Analysis (370 atoms):**
- 50 topics discovered
- Strong: nous(12.0), trading(9.6), noesis(9.6), nasa(8.8), soul(8.0), black holes(8.0)
- Sources: noesis_knowledge.txt(120), nasa_ads(35), arxiv(33), nasa(22), github(11)
- Weaning: threshold 0.30, next level at 500 atoms → 0.35

### Integration
- `NoesisEngine.think()` patched → records gaps + updates weaning
- New methods: `.init_autofeeding()`, `.curiosity_stats()`, `.knowledge_gaps()`, `.weaning_status()`, `.discover_topics()`, `.suggest_feeds()`, `.save_gaps()`

### Tests: 24/24 ✓

---

## 6. PHASE 6 — NOUS LANGUAGE INTEGRATION

### Τι κάναμε
Πρόσθεσε native NOUS syntax για Noesis: `noesis {}` block + `resonate` keyword.

### Αρχεία τροποποιημένα
- `nous.lark` — grammar: noesis_decl, resonate_stmt, NOESIS/RESONATE keywords
- `ast_nodes.py` — NoesisConfigNode, ResonateNode, NousProgram.noesis field
- `parser.py` — transformer methods, Token filtering, NousProgram builder
- `codegen.py` — _emit_noesis_init(), resonate dispatch
- `validator.py` — NS001 warning, _check_noesis()

### Grammar Additions

```lark
# Top-level declaration
noesis_decl: NOESIS "{" noesis_body* "}"
noesis_body: "lattice" ":" STRING            -> noesis_lattice
           | "oracle_threshold" ":" FLOAT    -> noesis_threshold
           | "auto_learn" ":" BOOL           -> noesis_auto_learn
           | "auto_evolve" ":" BOOL          -> noesis_auto_evolve
           | "gap_tracking" ":" BOOL         -> noesis_gap_tracking

# Statement (inside instinct)
resonate_stmt: "let" NAME "=" RESONATE STRING                          -> resonate_bind
             | "let" NAME "=" RESONATE STRING "with" NAME ">" FLOAT    -> resonate_bind_guarded
             | RESONATE STRING                                         -> resonate_bare

# Keywords (bilingual)
NOESIS: "noesis" | "νόηση"
RESONATE: "resonate" | "αντήχηση"
```

### AST Nodes

```python
class NoesisConfigNode(NousNode):
    lattice_path: Optional[str] = None
    oracle_threshold: float = 0.3
    auto_learn: bool = True
    auto_evolve: bool = False
    gap_tracking: bool = True

class ResonateNode(NousNode):
    query: Any = None
    bind_name: Optional[str] = None
    guard_field: Optional[str] = None
    guard_threshold: Optional[float] = None
```

### CodeGen Output

```python
# noesis {} block generates:
from noesis_engine import NoesisEngine
from pathlib import Path as _NoesisPath
_noesis_engine = NoesisEngine()
_noesis_lattice_path = _NoesisPath("noesis_lattice.json")
if _noesis_lattice_path.exists():
    _noesis_engine.load(_noesis_lattice_path)
_noesis_engine.oracle.confidence_threshold = 0.3
_noesis_auto_learn = True

# resonate "query" generates:
result = _noesis_engine.think("What is NOUS?")
```

### Bugs & Fixes

**Bug 1: NOESIS.2 → NOESIS**
- Patch αρχικά χρησιμοποιούσε `NOESIS.2:` (priority syntax)
- Actual grammar δεν χρησιμοποιεί priorities
- Fix: `NOESIS:` χωρίς priority

**Bug 2: top_level alternatives**
- Patch ψάχνε `import_decl`, `test_decl` στο top_level
- Δεν υπάρχουν στο actual grammar
- Fix: insert μετά `topology_decl`

**Bug 3: Comments // vs #**
- Test file χρησιμοποιούσε `//` comments
- NOUS grammar χρησιμοποιεί `#` comments
- Fix: `# comment` αντί `// comment`

**Bug 4: Tier format**
- Test: `@tier1` (lowercase)
- Grammar TIER regex: `/Tier[0-3][A-B]?/` (capital T)
- Fix: `@Tier1`

**Bug 5: NUMBER → FLOAT**
- Grammar δεν έχει `NUMBER` terminal
- Fix: `FLOAT` για threshold, `INT` δεν χρειάστηκε

**Bug 6: LET terminal undefined**
- Grammar χρησιμοποιεί inline `"let"`, όχι `LET` terminal
- Fix: `"let"` αντί `LET`

**Bug 7: RESONATE Token in items**
- `resonate_bind` items: `[Token(NAME), Token(RESONATE), Token(STRING)]`
- Transformer items[1] = RESONATE keyword, not query
- Fix: filter out RESONATE tokens before accessing items

**Bug 8: NoesisConfigNode not in NousProgram**
- Parser `start()` δεν handled `NoesisConfigNode`
- NousProgram class δεν είχε `noesis` field
- Fix: add field + `elif isinstance(item, NoesisConfigNode)` in start()

**Bug 9: Parser import syntax**
- `from ast_nodes import (\n    NoesisConfigNode,` — wrong insertion point
- Fix: insert inside parentheses

**Bug 10: CodeGen indentation (deploy script)**
- Bash heredoc escaped newlines `\\n` produced wrong indentation
- Fix: applied codegen changes manually with str_replace instead

**Bug 11: parse_source → parse_nous**
- Function ονομάζεται `parse_nous`, όχι `parse_source`

### Test Results
- Parse: ✓ (noesis=True, souls=[Thinker, Learner])
- CodeGen: ✓ (185 lines)
- py_compile: ✓
- `nous ast noesis_integration_test.nous` → shows noesis config ✓
- `L85: result = _noesis_engine.think("What is NOUS?")` ✓

### NOUS Syntax Examples

```nous
# English
noesis {
    lattice: "noesis_lattice.json"
    oracle_threshold: 0.3
    auto_learn: true
}

soul Thinker {
    instinct {
        let result = resonate "What is NOUS?"
        guard result.top_score > 0.3
        speak Knowledge(response: result.response)
    }
}

# Greek
νόηση {
    lattice: "noesis_lattice.json"
    oracle_threshold: 0.3
    auto_learn: true
}

soul Σκεπτόμενος {
    instinct {
        let αποτέλεσμα = αντήχηση "Τι είναι η NOUS;"
    }
}
```

---

## 7. ΑΡΧΕΙΑ ΑΝΑ SERVER

### Νέα αρχεία (13 files)
```
noesis_quality_patch.py        # Phase 2: BM25 + intent + dedup + relevance gate
noesis_quality_test.py         # Phase 2: 23 tests
noesis_reasoning.py            # Phase 3: Logic/math/temporal/contradiction core
noesis_reasoning_patch.py      # Phase 3: monkey-patch
noesis_reasoning_test.py       # Phase 3: 28 tests
noesis_scaling.py              # Phase 4: WAL + merge + backups core
noesis_scaling_patch.py        # Phase 4: monkey-patch
noesis_scaling_test.py         # Phase 4: 17 tests
noesis_merge.py                # Phase 4: standalone merge for cron
noesis_autofeeding.py          # Phase 5: curiosity + weaning + topics
noesis_autofeeding_patch.py    # Phase 5: monkey-patch
noesis_autofeeding_test.py     # Phase 5: 24 tests
noesis_integration_test.nous   # Phase 6: test file
```

### Τροποποιημένα αρχεία (6 files)
```
noesis_engine.py               # Bottom: 4 import lines added
nous.lark                      # Phase 6: noesis_decl + resonate_stmt + keywords
ast_nodes.py                   # Phase 6: NoesisConfigNode + NousProgram.noesis
parser.py                      # Phase 6: transformer methods + start() handler
codegen.py                     # Phase 6: _emit_noesis_init + resonate dispatch
validator.py                   # Phase 6: _check_noesis + NS001 warning
```

### noesis_engine.py imports (bottom of file)
```python
import noesis_quality_patch      # Phase 2
import noesis_reasoning_patch    # Phase 3
import noesis_scaling_patch      # Phase 4
import noesis_autofeeding_patch  # Phase 5
```

### Cron (Server A)
```
40 4 * * * cd /opt/aetherlang_agents/nous && python3 noesis_merge.py >> /var/log/noesis_merge.log 2>&1
```

---

## 8. TESTS — ΣΥΝΟΛΟ

| Phase | Tests | Status |
|-------|-------|--------|
| 2 — Quality | 23/23 | ✓ Server A+B |
| 3 — Reasoning | 28/28 | ✓ Server A+B |
| 4 — Scaling | 17/17 | ✓ Server A+B |
| 5 — Auto-feeding | 24/24 | ✓ Server A+B |
| 6 — NOUS Integration | Parse+CodeGen+py_compile | ✓ Server A |
| **Total** | **92 unit tests + pipeline** | **✓** |

---

## 9. SERVER STATUS

### Server A (neurodoc)
```
Phases 2-6: deployed ✓
Bot: running (auto-restart cron)
Lattice: 371 atoms
Quality patch: v2.0
Reasoning patch: v3.0
Scaling patch: v4.0
Autofeeding patch: v5.0
NOUS grammar: noesis + resonate ✓
```

### Server B (neuroaether)
```
Phases 2-5: deployed ✓
Phase 6: needs scp of 5 core files
Bot: running (auto-restart cron)
```

---

## 10. ΤΙ ΑΚΟΛΟΥΘΕΙ

### Phase 7: Νέες Πηγές Γνώσης
- Gemini ως free oracle tier (GEMINI_API_KEY υπάρχει στον Server B)
- Serper Google Search (SERPER_API_KEY υπάρχει στον Server B)
- FDA API (FDA_API_KEY υπάρχει)
- OpenWeather (OPENWEATHER_API_KEY υπάρχει)
- HuggingFace Inference (free model inference)

### Phase 8: Production Hardening
- Error recovery: αν crash, reload lattice, continue
- Rate limiting: max oracle calls/hour
- Structured JSON logging
- Metrics dashboard: Telegram weekly report (atoms, queries, autonomy, cost)
- Backup rotation: ήδη μέρος Phase 4, extend σε automated

### Potential Phase 9: Advanced NOUS
- `resonate` with dynamic expressions (not just string literals)
- `atom` as first-class type in NOUS type system
- Noesis soul template in standard library
- `noesis evolve` command in CLI

---

## 11. ΑΡΧΙΤΕΚΤΟΝΙΚΕΣ ΑΠΟΦΑΣΕΙΣ

**Γιατί monkey-patch αντί direct edit:**
Ο Hlia ανεβάζει αρχεία μέσω chat. Monkey-patch = 1 νέο αρχείο + 1 γραμμή import. Κανένα ρίσκο σε υπάρχοντα κώδικα. Rollback = αφαίρεσε τη γραμμή import.

**Γιατί BM25 αντί embeddings:**
0 dependencies, 0.1ms per query, works with existing inverted index. Embeddings θα χρειαστούν model download + GPU.

**Γιατί relevance gate με min_df:**
Simpler than semantic similarity. Λειτουργεί εξαιρετικά για entity queries (TX-105, specific names). False positive rate μειώθηκε δραστικά.

**Γιατί temporal atoms με preset TTL:**
Crypto prices αλλάζουν κάθε λεπτό, weather κάθε ώρες. Auto-detect by keyword αντί manual tagging = zero friction.

**Γιατί cron merge αντί real-time:**
Τα 2 servers τρέχουν ανεξάρτητα. Real-time sync = complexity + failure modes. Daily merge = simple, reliable, good enough.

**Γιατί noesis ως top-level block:**
Σκεφτήκαμε world-level ή soul-level. Top-level = μία φορά per program, shared μεταξύ souls, cleaner semantics.

**Γιατί resonate with STRING αντί expr:**
Earley parser greedy matching σε `expr` δημιουργεί ambiguity. STRING = unambiguous, covers 90% of use cases. Dynamic expressions σε Phase 9.

---

*Νόηση v2.0 — Intelligence with Quality, Reasoning, Scaling, Auto-feeding, and NOUS Integration*
*92 tests | 6 phases | 2 servers | 371 atoms | 185 lines generated*
*Hlias Staurou + Claude | 13 Απριλίου 2026 | Athens, Greece*
