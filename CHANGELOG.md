# Changelog

## [1.3.0] — 2026-04-11

### Added
- **Deploy block** — Server deployment configuration (replicas, region, GPU, memory)
- **Topology block** — Multi-server soul distribution with per-server config
- **VS Code extension** — Syntax highlighting, LSP diagnostics, autocomplete, hover docs
- **Error diagnostics** — Line:column positioning, source context, "did you mean?" suggestions
- **3 example programs** — infra_monitor.nous, research_pipeline.nous, customer_service.nous
- **REPL** — Interactive shell with 15 commands (:info, :dna, :souls, :validate, :evolve)
- **Live evolution** — Langfuse fitness + paper trading + git + Telegram notifications
- **Evolution daemon** — Scheduled daily at 03:00 AM

### Changed
- CLI updated to v1.3.0 with 12 commands
- CodeGen emits deploy/topology as Python config dicts
- Parser handles deploy_decl and topology_decl transforms
- Validator errors now show ✗/⚠ icons

### Fixed
- Earley parser keyword merge for sense/speak/guard
- String literal quoting in generated code
- `.where()` → `.filter()` codegen for DataProxy
- Duration artifacts from speak tokenization

## [1.1.0] — 2026-04-11

### Added
- **Runtime** — Tool dispatch (19 tools), LLM caller (5 tiers), cost tracking, channels, perception
- **CodeGen v2** — Full runtime integration with sense/speak/listen/guard/where
- **9 Gate Alpha tools** — scan, RSI, Kelly, backtest, paper trade, balance, positions, Telegram, search
- **Aevolver** — DNA mutation engine on Living AST with shadow copy + validate + commit/rollback
- **CLI v1.1.0** — 9 commands including evolve and bridge

## [1.0.0] — 2026-04-11

### Added
- **EBNF Grammar** — ~200 rules, bilingual English + Greek keywords
- **Living AST** — 40+ Pydantic V2 nodes
- **Parser** — Lark Transformer (CST → AST)
- **Validator** — 8 error categories, cycle detection
- **CodeGen v1** — AST → Python 3.11+ asyncio
- **NSP** — Noosphere Shorthand Protocol, 70% token savings
- **Migrator** — YAML/TOML → .nous, 106 agents converted
- **Gate Alpha** — First .nous program compiled and validated
