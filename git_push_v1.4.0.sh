#!/bin/bash
set -e

cd /opt/aetherlang_agents/nous

# Copy updated files
echo "=== Staging files ==="

# Core language files (already on server, just need git add)
git add nous.lark parser.py codegen.py validator.py cli.py ast_nodes.py
git add multiworld.py

# New/updated support files
# README already in place
# CHANGELOG already in place
git add README.md CHANGELOG.md

# Example files
git add gate_alpha.nous
git add infra_monitor.nous 2>/dev/null || true

# Tools (if tracked in this repo)
git add -f ../tools/fetch_rsi.py 2>/dev/null || true
git add -f ../tools/gate_alpha_scan.py 2>/dev/null || true

# Other tracked files
git add aevolver.py nsp.py bridge.py migrate.py install.sh 2>/dev/null || true

echo "=== Committing ==="
git commit -m "v1.4.0: LALR parser (90x speedup), multi-world, constitutional guards, ccxt RSI

- LALR parser migration: 3.3ms/parse (was 324ms Earley)
- Multi-world concurrent execution via asyncio.TaskGroup
- Constitutional guards: C001/C003/C004 compile-time + runtime
- ccxt RSI-14 with Wilder smoothing, 5-exchange fallback
- Runtime integration: _sense_* methods, WORLD_CONFIG, model_rebuild
- CodeGen fixes: self→self.name, .where()→.filter(), channel wiring
- CLI v1.4.0: multi-file support (nous run a.nous b.nous)
- Updated README + CHANGELOG"

echo "=== Tagging ==="
git tag -a v1.4.0 -m "NOUS v1.4.0 — LALR, Multi-World, Constitutional Guards"

echo "=== Pushing ==="
git push origin main
git push origin v1.4.0

echo "=== Done ==="
git log --oneline -3
