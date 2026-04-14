"""
NOUS CodeGen JS — Μετάφραση (Metafrasi)
==========================================
Transforms the Living AST into JavaScript ES2022.
Souls run as async functions. Channels use BroadcastChannel.
HEARTBEAT = setInterval. LISTENER = message-driven.
"""
from __future__ import annotations

from typing import Any, Optional

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MindNode, MemoryNode,
    InstinctNode, DnaNode, HealNode, HealRuleNode, HealActionNode,
    HealStrategy, MessageNode, NervousSystemNode, RouteNode,
    MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
    LetNode, RememberNode, SpeakNode, GuardNode, SenseCallNode,
    SleepNode, IfNode, ForNode, GeneNode,
    LawCost, LawDuration, LawBool, LawInt, LawConstitutional,
    TopologyNode, ServerNode,
)


class NousCodeGenJS:

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.indent_level = 0
        self.lines: list[str] = []
        self._routes: list[tuple[str, str]] = []
        self._incoming: dict[str, list[str]] = {}
        self._outgoing: dict[str, list[str]] = {}
        self._entrypoints: set[str] = set()
        self._listeners: set[str] = set()
        self._cost_ceiling: float = 0.10
        self._heartbeat_ms: int = 300000
        self._analyze_topology()

    def _analyze_topology(self) -> None:
        ns = self.program.nervous_system
        if ns:
            for route in ns.routes:
                if isinstance(route, RouteNode):
                    self._routes.append((route.source, route.target))
                elif isinstance(route, FanInNode):
                    for src in route.sources:
                        self._routes.append((src, route.target))
                elif isinstance(route, FanOutNode):
                    for tgt in route.targets:
                        self._routes.append((route.source, tgt))
        for src, tgt in self._routes:
            self._outgoing.setdefault(src, []).append(tgt)
            self._incoming.setdefault(tgt, []).append(src)
        soul_names = {s.name for s in self.program.souls}
        self._listeners = soul_names & set(self._incoming.keys())
        self._entrypoints = soul_names - self._listeners
        if self.program.world:
            hb = self.program.world.heartbeat
            if hb:
                self._heartbeat_ms = self._duration_to_ms(hb)
            for law in self.program.world.laws:
                if isinstance(law.expr, LawCost) and law.expr.per == "cycle":
                    self._cost_ceiling = law.expr.amount

    def generate(self) -> str:
        self._emit_header()
        self._emit_runtime()
        self._emit_blank()
        self._emit_messages()
        self._emit_blank()
        self._emit_souls()
        self._emit_blank()
        self._emit_wiring()
        self._emit_blank()
        self._emit_boot()
        return "\n".join(self.lines)

    def _emit(self, text: str = "") -> None:
        if not text:
            self.lines.append("")
        else:
            self.lines.append("  " * self.indent_level + text)

    def _emit_blank(self) -> None:
        self.lines.append("")

    def _indent(self) -> None:
        self.indent_level += 1

    def _dedent(self) -> None:
        self.indent_level = max(0, self.indent_level - 1)

    def _emit_header(self) -> None:
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit("// ═══════════════════════════════════════════")
        self._emit(f"// NOUS Generated — {world_name}")
        self._emit("// Target: JavaScript ES2022 | Runtime: Browser/Deno/Node")
        self._emit("// Auto-generated from .nous source. Do not edit.")
        self._emit("// ═══════════════════════════════════════════")
        self._emit("")

    def _emit_runtime(self) -> None:
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit("// ═══ Runtime Core ═══")
        self._emit("")
        self._emit(f'const WORLD_NAME = "{world_name}";')
        self._emit(f"const HEARTBEAT_MS = {self._heartbeat_ms};")
        self._emit(f"const COST_CEILING = {self._cost_ceiling};")
        ep_list = sorted(self._entrypoints)
        ls_list = sorted(self._listeners)
        self._emit(f"const ENTRYPOINT_SOULS = {self._js_list(ep_list)};")
        self._emit(f"const LISTENER_SOULS = {self._js_list(ls_list)};")
        self._emit("")
        self._emit("class NousChannel {")
        self._indent()
        self._emit("constructor(name, maxSize = 100) {")
        self._indent()
        self._emit("this.name = name;")
        self._emit("this._queue = [];")
        self._emit("this._waiters = [];")
        self._emit("this._maxSize = maxSize;")
        self._emit("this.totalSent = 0;")
        self._emit("this.totalReceived = 0;")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async send(message) {")
        self._indent()
        self._emit("if (this._waiters.length > 0) {")
        self._indent()
        self._emit("const resolve = this._waiters.shift();")
        self._emit("resolve(message);")
        self._dedent()
        self._emit("} else if (this._queue.length < this._maxSize) {")
        self._indent()
        self._emit("this._queue.push(message);")
        self._dedent()
        self._emit("} else {")
        self._indent()
        self._emit('console.warn(`Channel [${this.name}]: backpressure — queue full`);')
        self._dedent()
        self._emit("}")
        self._emit("this.totalSent++;")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async receive(timeoutMs = null) {")
        self._indent()
        self._emit("if (this._queue.length > 0) {")
        self._indent()
        self._emit("this.totalReceived++;")
        self._emit("return this._queue.shift();")
        self._dedent()
        self._emit("}")
        self._emit("return new Promise((resolve, reject) => {")
        self._indent()
        self._emit("this._waiters.push((msg) => { this.totalReceived++; resolve(msg); });")
        self._emit("if (timeoutMs !== null) {")
        self._indent()
        self._emit("setTimeout(() => {")
        self._indent()
        self._emit("const idx = this._waiters.indexOf(resolve);")
        self._emit("if (idx >= 0) this._waiters.splice(idx, 1);")
        self._emit("resolve(null);")
        self._dedent()
        self._emit("}, timeoutMs);")
        self._dedent()
        self._emit("}")
        self._dedent()
        self._emit("});")
        self._dedent()
        self._emit("}")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("class NousRuntime {")
        self._indent()
        self._emit("constructor() {")
        self._indent()
        self._emit("this.channels = {};")
        self._emit("this.souls = {};")
        self._emit("this.running = false;")
        self._emit("this.cycleCount = 0;")
        self._emit("this.totalCost = 0;")
        self._emit("this._intervals = [];")
        self._emit("this._log = [];")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("getChannel(name) {")
        self._indent()
        self._emit("if (!this.channels[name]) {")
        self._indent()
        self._emit("this.channels[name] = new NousChannel(name);")
        self._dedent()
        self._emit("}")
        self._emit("return this.channels[name];")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async send(channelName, message) {")
        self._indent()
        self._emit("const ch = this.getChannel(channelName);")
        self._emit("await ch.send(message);")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async receive(channelName, timeoutMs = null) {")
        self._indent()
        self._emit("const ch = this.getChannel(channelName);")
        self._emit("return await ch.receive(timeoutMs);")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("log(soul, msg) {")
        self._indent()
        self._emit("const ts = new Date().toISOString().substr(11, 8);")
        self._emit("const entry = `${ts} | ${soul} | ${msg}`;")
        self._emit("this._log.push(entry);")
        self._emit("console.log(entry);")
        self._emit("if (typeof document !== 'undefined' && document.getElementById('nous-log')) {")
        self._indent()
        self._emit("const el = document.getElementById('nous-log');")
        self._emit("el.textContent += entry + '\\n';")
        self._emit("el.scrollTop = el.scrollHeight;")
        self._dedent()
        self._emit("}")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async sense(toolName, args = {}) {")
        self._indent()
        self._emit("if (toolName === 'http_get' && args.url) {")
        self._indent()
        self._emit("try {")
        self._indent()
        self._emit("const resp = await fetch(args.url);")
        self._emit("return await resp.json();")
        self._dedent()
        self._emit("} catch(e) { return { error: e.message }; }")
        self._dedent()
        self._emit("} else if (toolName === 'http_post' && args.url) {")
        self._indent()
        self._emit("try {")
        self._indent()
        self._emit("const resp = await fetch(args.url, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(args.body || {}) });")
        self._emit("return await resp.json();")
        self._dedent()
        self._emit("} catch(e) { return { error: e.message }; }")
        self._dedent()
        self._emit("}")
        self._emit("return null;")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("stop() {")
        self._indent()
        self._emit("this.running = false;")
        self._emit("this._intervals.forEach(id => clearInterval(id));")
        self._emit("this._intervals = [];")
        self._emit("this.log('RUNTIME', 'Shutdown complete');")
        self._dedent()
        self._emit("}")
        self._dedent()
        self._emit("}")

    def _emit_messages(self) -> None:
        if not self.program.messages:
            return
        self._emit("// ═══ Message Types ═══")
        self._emit("")
        for msg in self.program.messages:
            fields = ", ".join(f.name for f in msg.fields)
            defaults: list[str] = []
            for f in msg.fields:
                if f.default is not None:
                    defaults.append(f"this.{f.name} = {f.name} ?? {self._val_to_js(f.default)};")
                else:
                    defaults.append(f"this.{f.name} = {f.name};")
            params = ", ".join(
                f"{f.name} = {self._val_to_js(f.default)}" if f.default is not None
                else f.name
                for f in msg.fields
            )
            self._emit(f"class {msg.name} {{")
            self._indent()
            self._emit(f"constructor({{ {params} }} = {{}}) {{")
            self._indent()
            for d in defaults:
                self._emit(d)
            self._dedent()
            self._emit("}")
            self._dedent()
            self._emit("}")
            self._emit("")

    def _emit_souls(self) -> None:
        self._emit("// ═══ Soul Definitions ═══")
        for soul in self.program.souls:
            self._emit_soul(soul)

    def _emit_soul(self, soul: SoulNode) -> None:
        is_listener = soul.name in self._listeners
        wake = "LISTENER" if is_listener else "HEARTBEAT"
        self._emit("")
        self._emit(f"class Soul_{soul.name} {{")
        self._indent()
        self._emit(f"constructor(runtime) {{")
        self._indent()
        self._emit(f'this.name = "{soul.name}";')
        self._emit("this._rt = runtime;")
        if soul.mind:
            self._emit(f'this.model = "{soul.mind.model}";')
            self._emit(f'this.tier = "{soul.mind.tier.value}";')
        else:
            self._emit('this.model = "unknown";')
            self._emit('this.tier = "Tier1";')
        self._emit(f"this.senses = {self._js_list(soul.senses)};")
        self._emit("this.cycleCount = 0;")
        if soul.memory:
            for f in soul.memory.fields:
                self._emit(f"this.{f.name} = {self._val_to_js(f.default)};")
        if soul.dna:
            for gene in soul.dna.genes:
                self._emit(f"this.dna_{gene.name} = {self._val_to_js(gene.value)};")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async instinct() {")
        self._indent()
        if soul.instinct and soul.instinct.statements:
            for stmt in soul.instinct.statements:
                self._emit_statement(stmt, soul.name)
        self._emit("this.cycleCount++;")
        self._emit(f'this._rt.log(this.name, `cycle ${{this.cycleCount}} complete`);')
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("async heal(error) {")
        self._indent()
        self._emit("const errorType = error.constructor.name.toLowerCase();")
        self._emit("const errorMsg = error.message ? error.message.toLowerCase() : '';")
        if soul.heal and soul.heal.rules:
            for i, rule in enumerate(soul.heal.rules):
                kw = "if" if i == 0 else "} else if"
                self._emit(f'{kw} (errorType === "{rule.error_type}" || errorMsg.includes("{rule.error_type}")) {{')
                self._indent()
                for action in rule.actions:
                    self._emit_heal_action_js(action)
                self._emit("return true;")
                self._dedent()
            self._emit("}")
        self._emit(f'this._rt.log(this.name, `unhandled error: ${{error.message}}`);')
        self._emit("return false;")
        self._dedent()
        self._emit("}")
        self._dedent()
        self._emit("}")

    def _emit_statement(self, stmt: Any, soul_name: str) -> None:
        if isinstance(stmt, LetNode):
            value = stmt.value
            if isinstance(value, dict):
                kind = value.get("kind", "")
                if kind == "listen":
                    src_soul = value.get("soul", "")
                    msg_type = value.get("type", "")
                    channel = f"{src_soul}_{msg_type}"
                    self._emit(f'const {stmt.name} = await this._rt.receive("{channel}");')
                    return
                elif kind == "sense_call":
                    tool = value.get("tool", "unknown")
                    args = value.get("args", {})
                    args_str = self._args_to_js(args)
                    self._emit(f'const {stmt.name} = await this._rt.sense("{tool}", {args_str});')
                    return
            self._emit(f"const {stmt.name} = {self._expr_to_js(value)};")

        elif isinstance(stmt, RememberNode):
            val = self._expr_to_js(stmt.value)
            if stmt.op == "+=":
                self._emit(f"this.{stmt.name} += {val};")
            else:
                self._emit(f"this.{stmt.name} = {val};")

        elif isinstance(stmt, SpeakNode):
            if stmt.target_world:
                channel = f"cross_{stmt.target_world}_{stmt.message_type}"
            else:
                channel = f"{soul_name}_{stmt.message_type}"
            args_str = self._kv_to_js(stmt.args)
            self._emit(f'await this._rt.send("{channel}", new {stmt.message_type}({{ {args_str} }}));')

        elif isinstance(stmt, GuardNode):
            cond = self._expr_to_js(stmt.condition)
            self._emit(f"if (!({cond})) return;")

        elif isinstance(stmt, SenseCallNode):
            args_str = self._args_to_js(stmt.args)
            if stmt.bind_name:
                self._emit(f'const {stmt.bind_name} = await this._rt.sense("{stmt.tool_name}", {args_str});')
            else:
                self._emit(f'await this._rt.sense("{stmt.tool_name}", {args_str});')

        elif isinstance(stmt, SleepNode):
            self._emit(f"await new Promise(r => setTimeout(r, HEARTBEAT_MS * {stmt.cycles}));")

        elif isinstance(stmt, IfNode):
            cond = self._expr_to_js(stmt.condition)
            self._emit(f"if ({cond}) {{")
            self._indent()
            for s in stmt.then_body:
                self._emit_statement(s, soul_name)
            self._dedent()
            if stmt.else_body:
                self._emit("} else {")
                self._indent()
                for s in stmt.else_body:
                    self._emit_statement(s, soul_name)
                self._dedent()
            self._emit("}")

        elif isinstance(stmt, ForNode):
            iterable = self._expr_to_js(stmt.iterable)
            self._emit(f"for (const {stmt.var_name} of {iterable}) {{")
            self._indent()
            for s in stmt.body:
                self._emit_statement(s, soul_name)
            self._dedent()
            self._emit("}")

    def _emit_heal_action_js(self, action: HealActionNode) -> None:
        if action.strategy == HealStrategy.RETRY:
            max_r = action.params.get("max", 1)
            backoff = action.params.get("backoff", "fixed")
            self._emit(f"for (let _r = 0; _r < {max_r}; _r++) {{")
            self._indent()
            if backoff == "exponential":
                self._emit("await new Promise(r => setTimeout(r, Math.pow(2, _r) * 1000));")
            else:
                self._emit("await new Promise(r => setTimeout(r, 1000));")
            self._emit("try { await this.instinct(); break; } catch(e) { continue; }")
            self._dedent()
            self._emit("}")
        elif action.strategy == HealStrategy.HIBERNATE:
            self._emit("await new Promise(r => setTimeout(r, HEARTBEAT_MS));")
        elif action.strategy == HealStrategy.SLEEP:
            cycles = action.params.get("cycles", 1)
            self._emit(f"await new Promise(r => setTimeout(r, HEARTBEAT_MS * {cycles}));")

    def _emit_wiring(self) -> None:
        self._emit("// ═══ Runtime Wiring ═══")
        self._emit("")
        self._emit("function buildRuntime() {")
        self._indent()
        self._emit("const rt = new NousRuntime();")
        self._emit("rt.running = true;")
        self._emit("")
        for soul in self.program.souls:
            self._emit(f"const {soul.name.lower()} = new Soul_{soul.name}(rt);")
            self._emit(f'rt.souls["{soul.name}"] = {soul.name.lower()};')
        self._emit("")
        for soul in self.program.souls:
            sname = soul.name
            is_listener = sname in self._listeners
            if is_listener:
                sources = self._incoming.get(sname, [])
                if sources:
                    first_src = sources[0]
                    first_src_soul = self._find_soul(first_src)
                    msg_type = self._find_speak_type(first_src_soul) if first_src_soul else None
                    if msg_type:
                        channel = f"{first_src}_{msg_type}"
                        self._emit(f"// {sname}: LISTENER on {channel}")
                        self._emit(f"(async () => {{")
                        self._indent()
                        self._emit("while (rt.running) {")
                        self._indent()
                        self._emit("try {")
                        self._indent()
                        self._emit(f'await rt.receive("{channel}", HEARTBEAT_MS);')
                        self._emit(f"await {sname.lower()}.instinct();")
                        self._dedent()
                        self._emit(f"}} catch(e) {{ await {sname.lower()}.heal(e); }}")
                        self._dedent()
                        self._emit("}")
                        self._dedent()
                        self._emit("})();")
            else:
                self._emit(f"// {sname}: HEARTBEAT every {self._heartbeat_ms}ms")
                self._emit(f"(async () => {{")
                self._indent()
                self._emit("try {")
                self._indent()
                self._emit(f"await {sname.lower()}.instinct();")
                self._dedent()
                self._emit(f"}} catch(e) {{ await {sname.lower()}.heal(e); }}")
                self._dedent()
                self._emit("})();")
                self._emit(f"const _iv_{sname.lower()} = setInterval(async () => {{")
                self._indent()
                self._emit("if (!rt.running) return;")
                self._emit("try {")
                self._indent()
                self._emit(f"await {sname.lower()}.instinct();")
                self._dedent()
                self._emit(f"}} catch(e) {{ await {sname.lower()}.heal(e); }}")
                self._dedent()
                self._emit("}, HEARTBEAT_MS);")
                self._emit(f"rt._intervals.push(_iv_{sname.lower()});")
            self._emit("")
        self._emit("return rt;")
        self._dedent()
        self._emit("}")

    def _emit_boot(self) -> None:
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit("// ═══ Boot ═══")
        self._emit("")
        self._emit(f'console.log("═══ NOUS Runtime JS — {world_name} ═══");')
        self._emit('console.log(`  Heartbeat: ${HEARTBEAT_MS}ms`);')
        self._emit('console.log(`  Cost ceiling: $${COST_CEILING}`);')
        self._emit('console.log(`  Entrypoints: ${ENTRYPOINT_SOULS.join(", ")}`);')
        self._emit('console.log(`  Listeners: ${LISTENER_SOULS.join(", ")}`);')
        self._emit("")
        self._emit("const runtime = buildRuntime();")
        self._emit("")
        self._emit("if (typeof window !== 'undefined') {")
        self._indent()
        self._emit("window.nousRuntime = runtime;")
        self._emit("window.nousStop = () => runtime.stop();")
        self._dedent()
        self._emit("}")
        self._emit("")
        self._emit("if (typeof module !== 'undefined') {")
        self._indent()
        self._emit("module.exports = { runtime, buildRuntime, NousRuntime, NousChannel };")
        self._dedent()
        self._emit("}")

    def _find_soul(self, name: str) -> SoulNode | None:
        for s in self.program.souls:
            if s.name == name:
                return s
        return None

    def _find_speak_type(self, soul: SoulNode) -> str | None:
        if not soul.instinct:
            return None
        for stmt in soul.instinct.statements:
            if isinstance(stmt, SpeakNode):
                return stmt.message_type
            if isinstance(stmt, IfNode):
                for s in stmt.then_body:
                    if isinstance(s, SpeakNode):
                        return s.message_type
                for s in stmt.else_body:
                    if isinstance(s, SpeakNode):
                        return s.message_type
            if isinstance(stmt, ForNode):
                for s in stmt.body:
                    if isinstance(s, SpeakNode):
                        return s.message_type
        return None

    def _expr_to_js(self, expr: Any) -> str:
        if expr is None:
            return "null"
        if isinstance(expr, bool):
            return "true" if expr else "false"
        if isinstance(expr, (int, float)):
            return str(expr)
        if isinstance(expr, str):
            if expr == "self":
                return "this"
            if expr == "now()":
                return "Date.now() / 1000"
            if expr.startswith('"') or expr.startswith("'"):
                return expr
            if expr.replace("_", "").replace(".", "").isalnum() and expr[0:1].isalpha():
                return expr
            escaped = expr.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(expr, list):
            items = ", ".join(self._expr_to_js(i) for i in expr)
            return f"[{items}]"
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                left = self._expr_to_js(expr["left"])
                right = self._expr_to_js(expr["right"])
                op = expr["op"]
                if op == "&&":
                    op = "&&"
                elif op == "||":
                    op = "||"
                return f"({left} {op} {right})"
            elif kind == "not":
                return f"!({self._expr_to_js(expr['operand'])})"
            elif kind == "neg":
                return f"-({self._expr_to_js(expr['operand'])})"
            elif kind == "attr":
                obj = self._expr_to_js(expr["obj"])
                return f"{obj}.{expr['attr']}"
            elif kind == "method_call":
                obj = self._expr_to_js(expr["obj"])
                args = self._args_to_js(expr.get("args", {}))
                return f"{obj}.{expr['method']}({args})"
            elif kind == "func_call":
                func = self._expr_to_js(expr["func"])
                args = self._args_to_js(expr.get("args", {}))
                return f"{func}({args})"
            elif kind == "soul_field":
                return f'rt.souls["{expr["soul"]}"].{expr["field"]}'
            elif kind == "inline_if":
                cond = self._expr_to_js(expr["condition"])
                then = self._expr_to_js(expr["then"])
                else_ = self._expr_to_js(expr["else"])
                return f"({cond} ? {then} : {else_})"
            elif kind == "listen":
                channel = f"{expr['soul']}_{expr['type']}"
                return f'await this._rt.receive("{channel}")'
            elif kind == "sense_call":
                tool = expr.get("tool", "")
                args = self._args_to_js(expr.get("args", {}))
                return f'await this._rt.sense("{tool}", {args})'
            return str(expr)
        return str(expr)

    def _val_to_js(self, val: Any) -> str:
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, str):
            if val == "now()":
                return "Date.now() / 1000"
            if val.startswith('"'):
                return val
            return f'"{val}"'
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, list):
            items = ", ".join(self._val_to_js(i) for i in val)
            return f"[{items}]"
        if isinstance(val, dict):
            return self._expr_to_js(val)
        return str(val)

    def _args_to_js(self, args: Any) -> str:
        if not args:
            return "{}"
        if isinstance(args, dict):
            parts = []
            for k, v in args.items():
                if k.startswith("_pos_"):
                    parts.append(self._expr_to_js(v))
                else:
                    parts.append(f"{k}: {self._expr_to_js(v)}")
            if any(k.startswith("_pos_") for k in args):
                return ", ".join(parts)
            return "{ " + ", ".join(parts) + " }"
        return str(args)

    def _kv_to_js(self, kv: Any) -> str:
        if not kv:
            return ""
        if isinstance(kv, dict):
            parts = []
            for k, v in kv.items():
                parts.append(f"{k}: {self._expr_to_js(v)}")
            return ", ".join(parts)
        return str(kv)

    def _js_list(self, items: list[str]) -> str:
        return "[" + ", ".join(f'"{i}"' for i in items) + "]"

    def _duration_to_ms(self, duration: str) -> int:
        import re
        m = re.match(r"(\d+)(ms|s|m|h|d)", duration)
        if not m:
            return 300000
        val = int(m.group(1))
        unit = m.group(2)
        if unit == "ms":
            return val
        elif unit == "s":
            return val * 1000
        elif unit == "m":
            return val * 60000
        elif unit == "h":
            return val * 3600000
        elif unit == "d":
            return val * 86400000
        return val * 1000


def generate_javascript(program: NousProgram) -> str:
    gen = NousCodeGenJS(program)
    return gen.generate()
