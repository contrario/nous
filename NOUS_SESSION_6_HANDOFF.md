# NOUS SESSION 6 — HANDOFF (IN PROGRESS)

## Ημερομηνία: 13 Απριλίου 2026
## Engineer: Claude (Staff-Level Principal Language Designer)
## User: Hlias Staurou (Hlia)

---

## ΣΥΝΟΨΗ SESSION 6

Priority 1 (Distributed Topology) ολοκληρώθηκε. Grammar, Parser, Validator, CodeGen, CLI updates + νέο `topology.py` (500+ lines) για SSH deployment, TCP cross-server channels, και health monitoring.

---

## PRIORITY 1: DISTRIBUTED TOPOLOGY ✅ (v1.8.0)

### Τι κάναμε

**Grammar (nous.lark):**
1. Keyword terminals with `.2` priority: `LET`, `IF`, `ELSE`, `FOR`, `IN`, `ON`, `MATCH`
2. `DURATION_VAL: /\d+(ms|s|m|h|d)(?![a-zA-Z_])/` — combined regex preventing cross-token matching (fixes `9100ssh_user` → `9100s` bug)
3. `then_body`, `else_body`, `for_body` sub-rules for cleaner LALR compatibility
4. `TIER.2`, `BOOL.2` priority added

**AST (ast_nodes.py):**
1. `TopologyServerNode(name, host, config)` — server in topology block
2. `TopologyNode(servers: list[TopologyServerNode])` — topology block
3. `NousProgram.topology: Optional[TopologyNode]` — program root

**Parser (parser.py):**
1. `_strip()` helper — removes None + Token objects from items (keyword terminals)
2. `topo_body()`, `topo_server()`, `topology_decl()` — topology block parsing
3. `deploy_body()`, `deploy_decl()` — deploy block parsing
4. `then_body()`, `else_body()`, `for_body()` — sub-rule handlers
5. Fixed ALL handlers for keyword terminal items:
   - `let_stmt`, `listen_expr`, `sense_call`, `if_stmt`, `for_stmt`
   - `inline_if`, `heal_rule`, `perception_rule`, `match_route`
6. `DURATION_VAL` terminal handler
7. `start()` updated for TopologyNode

**Validator (validator.py):**
1. `_check_topology()` — 6 new validation checks:
   - Y001: Duplicate server names
   - Y002: Duplicate host addresses (warning)
   - Y003: Undefined soul references in topology
   - Y004: Soul assigned to multiple servers
   - Y005: Port outside 1024-65535 range (warning)
   - Y006: Unassigned souls (warning)

**topology.py (NEW — 520 lines):**
1. **ServerSpec** — Pydantic-free config from TopologyServerNode
2. **SSHRunner** — asyncio subprocess SSH/SCP:
   - `run_command(cmd, timeout)` — remote command execution
   - `upload_file(local, remote)` — SCP upload
   - `check_alive()` — connectivity test
   - StrictHostKeyChecking=no, BatchMode=yes, configurable key/port/user
3. **SSHDeployer** — Deploy compiled .py to remote servers:
   - `deploy_all()` — concurrent deployment to all servers
   - `_deploy_one(spec)` — per-server: SSH check → mkdir → upload → stop old → start new
   - `_filter_souls(names)` — strips soul classes not assigned to server
   - `stop_all()` — pkill remote processes
4. **TCPBridgeMessage** — Length-prefixed JSON framing:
   - `encode(msg)` — struct.pack 4-byte length + JSON payload
   - `decode(reader)` — async read with 10MB limit
5. **TCPBridgeServer** — TCP server for cross-server message receiving:
   - `start()` / `stop()` — asyncio.start_server lifecycle
   - `subscribe(msg_type)` — returns asyncio.Queue for message type
   - `_handle_connection()` — continuous read loop, dispatches to subscribers
6. **TCPBridgeClient** — TCP client for cross-server sending:
   - `connect(name, host, port)` — asyncio.open_connection with timeout
   - `send(name, msg)` — length-prefixed JSON write with drain
   - `close_all()` — cleanup all connections
7. **CrossServerBus** — Unified pub/sub across servers:
   - `start()` — starts local bridge server
   - `connect_peers(servers)` — connects to all remote servers
   - `publish(target, type, payload)` — send to specific server or local
   - `subscribe(type)` — receive messages of type
8. **HealthMonitor** — Periodic health checks via SSH:
   - `start()` / `stop()` — asyncio task lifecycle
   - `check_all()` — concurrent health check all servers
   - `_check_one(spec)` — pgrep + /proc/stat for PID/uptime
   - Configurable interval (default 15s)
9. **TopologyManager** — Orchestrator:
   - `deploy()` — full deployment pipeline
   - `start_bridge(name, port)` — start cross-server bus
   - `start_monitoring()` — start health monitor
   - `status()` / `stop()` / `stop_all()` — management

**CLI (cli.py v1.8.0):**
1. `nous deploy file.nous` — Parse → Validate → Compile → SSH deploy to all topology servers
2. `nous topology file.nous show` — Display topology configuration
3. `nous topology file.nous status` — Health check all servers (🟢/🔴)
4. `nous topology file.nous stop` — Kill remote processes

**Test file (topology_test.nous):**
- 2 servers: alpha (188.245.245.132) + beta (10.0.0.2)
- 4 souls distributed: Scout+Quant on alpha, Hunter+Monitor on beta
- Full nervous_system routing
- Per-server config: port, ssh_key, ssh_user, python, env_file

### Bugs Found & Fixed
1. **`topology_decl` skipping first server** — `items[1:]` assumed keyword token at items[0], but Earley Transformer strips it. Fixed: `items` → filter by type.
2. **Duration tokenization** — `9100ssh_user` tokenized as `9100s` + `sh_user`. Fixed: `DURATION_VAL: /\d+(ms|s|m|h|d)(?![a-zA-Z_])/` combined regex with negative lookahead.
3. **Keyword terminal indices** — Adding `LET.2`, `IF.2`, `ELSE.2`, `FOR.2`, `IN.2`, `ON.2`, `MATCH.2` shifted items in all handlers. Fixed: `_strip()` helper removes Token objects.
4. **`inline_if` wrong indices** — `if cond { then } else { else }` produced `if if else buy`. Fixed with `_strip()`.

### Verified
```
topology_test.nous:
  Parse:     ✓ (4 souls, 2 servers)
  Validate:  ✓ (0 errors, 0 warnings)
  Compile:   ✓ (323 lines)
  py_compile: PASS
  CLI deploy: ✓ (SSH fails as expected from dev environment)
  CLI topology show: ✓

gate_alpha.nous (backward compat):
  Parse:     ✓ (4 souls)
  Validate:  ✓ (0 errors)
  Compile:   ✓ (337 lines)
  py_compile: PASS

All 6 Python files: py_compile PASS
```

---

## UPDATED FILE LIST

| File | Status | Description |
|------|--------|-------------|
| `nous.lark` | **UPDATED** | Keyword terminals `.2`, DURATION_VAL, sub-rules |
| `ast_nodes.py` | **UPDATED** | +TopologyServerNode, +TopologyNode, NousProgram.topology |
| `parser.py` | **UPDATED** | +_strip(), +topology handlers, fixed all keyword handlers |
| `validator.py` | **UPDATED** | +_check_topology() Y001-Y006 |
| `codegen.py` | unchanged | (compatible with new AST) |
| `topology.py` | **NEW** | SSH deploy, TCP bridge, health monitor |
| `cli.py` | **UPDATED** | v1.8.0, +deploy, +topology commands |
| `topology_test.nous` | **NEW** | 2-server distributed test |

---

## COMPLETE CLI (v1.8.0)

```
nous compile file.nous          # Compile to Python
nous run file.nous              # Compile + execute
nous run a.nous b.nous          # Multi-world concurrent
nous validate file.nous         # Check laws
nous watch file.nous            # Hot reload
nous shell [file.nous]          # Interactive REPL
nous deploy file.nous           # Deploy topology via SSH
nous topology file.nous show    # Show topology config
nous topology file.nous status  # Health check servers
nous topology file.nous stop    # Stop remote processes
nous ast file.nous [--json]     # Living AST
nous info file.nous             # Program summary
nous evolve file.nous --cycles N  # DNA mutation
nous nsp "[NSP|CT.88]"          # Parse NSP
nous bridge file.nous           # Noosphere integration
nous version                    # Show version
```

---

## CRITICAL PATTERNS — UPDATED

### Parser
- `_strip()` removes None + Token objects from Transformer items
- ALL statement handlers must use `_strip()` for correct indexing
- `DURATION_VAL` is a combined terminal — no separate DURATION_UNIT
- Keyword terminals (LET, IF, ELSE, FOR, IN, ON, MATCH) have `.2` priority
- Earley parser (not LALR) — LALR has state merging issues with nested for/if bodies

### Topology
- `ServerSpec.from_ast()` converts TopologyServerNode → deployment config
- `SSHRunner` uses `asyncio.create_subprocess_exec` (zero deps)
- `TCPBridgeMessage` uses 4-byte length prefix + JSON
- `CrossServerBus` = local TCPBridgeServer + remote TCPBridgeClients
- `_filter_souls()` strips unassigned soul classes from compiled code
- Deploy dir: `/opt/nous_remote/`
- Health monitor: pgrep + /proc/stat for PID/uptime

---

## SESSION 6 — REMAINING PRIORITIES

### Priority 2: VS Code Extension Update
### Priority 3: White Paper v1.2
### Priority 4: REPL Improvements
### Priority 5: Test Runner
### Priority 6: Package Manager
### Priority 7: Documentation Generator
### Priority 8: Performance Profiler
### Priority 9: Full LSP Server

---

## ENVIRONMENT

- **Server:** Hetzner CCX23, 188.245.245.132, Debian 12, Python 3.12
- **Git:** github.com/contrario/nous (v1.7.0 → push v1.8.0)
- **Version:** v1.8.0 (Distributed Topology)
