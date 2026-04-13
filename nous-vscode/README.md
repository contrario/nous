# NOUS — VS Code Extension

Syntax highlighting, real-time validation, snippets, and LSP support for **NOUS (Νοῦς)** — a self-evolving programming language for agentic AI systems.

## Features

### Syntax Highlighting
- All NOUS keywords (English + Greek bilingual)
- World, Soul, Message, Topology blocks
- Law declarations (cost, currency, constitutional, bool, duration)
- Cross-world syntax (`@World::Message`)
- Mind/Tier declarations
- Operators, literals, comments, strings

### Real-Time Validation (LSP)
- Parse errors with line/column
- Validator errors (S001-S005, T001-T002, N001-N003, Y001-Y006, etc.)
- Constitutional guard warnings
- Runs on open, save, and change

### Code Completion
- All keywords + Greek alternatives
- Soul names, message types from current file
- Type names, tier levels
- Snippet templates for blocks

### Hover Information
- Keyword documentation
- Soul details (mind, senses, memory, DNA)
- Message field definitions
- World/law information

### Go-to-Definition
- Jump to soul declarations
- Jump to message declarations

### Commands
- `NOUS: Compile` — compile current .nous file
- `NOUS: Run` — compile and execute
- `NOUS: Deploy Topology` — deploy to remote servers

### Snippets
- `world` — world declaration
- `soul` — full soul with mind, senses, memory, instinct, heal
- `message` — message type
- `nervous_system` — routing DAG
- `topology` — distributed deployment
- `speak`, `speak @` — channel/cross-world messaging
- `listen`, `let sense`, `guard`, `remember`
- `if`, `ifelse`, `for`
- `heal`, `evolution`
- `law cost`, `law currency`, `law bool`

## Requirements

### LSP Server
The LSP requires Python 3.11+ with:
```bash
pip install pygls lark pydantic
```

### Settings
- `nous.pythonPath`: Path to Python interpreter (default: `python3`)
- `nous.parserPath`: Path to NOUS parser directory (default: `/opt/aetherlang_agents/nous`)

## Installation

### From Source
```bash
cd nous-vscode
npm install
npx vsce package
code --install-extension nous-lang-1.8.0.vsix
```

### Manual (syntax highlighting only)
Copy the extension folder to:
- Linux: `~/.vscode/extensions/nous-lang`
- macOS: `~/.vscode/extensions/nous-lang`
- Windows: `%USERPROFILE%\.vscode\extensions\nous-lang`
