"""
NOUS Migration v2 — Μετανάστευση Πηγαίου Κώδικα (Source Migration)
====================================================================
Converts Python agent source code to .nous definitions.
Pattern detection: asyncio loops → souls, API calls → senses,
state dicts → memory, LLM clients → mind, queues → routes.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


MODEL_PATTERNS: dict[str, tuple[str, str]] = {
    "claude": ("claude-sonnet", "Tier0A"),
    "anthropic": ("claude-sonnet", "Tier0A"),
    "gpt-4": ("gpt-4o", "Tier0B"),
    "gpt-3": ("gpt-3.5-turbo", "Tier0B"),
    "openai": ("gpt-4o", "Tier0B"),
    "deepseek": ("deepseek-r1", "Tier1"),
    "gemini": ("gemini-flash", "Tier2"),
    "ollama": ("llama3", "Tier3"),
    "llama": ("llama3", "Tier3"),
    "mistral": ("mistral", "Tier1"),
}

SENSE_PATTERNS: dict[str, str] = {
    "httpx.AsyncClient": "http_request",
    "httpx.get": "http_get",
    "httpx.post": "http_post",
    "aiohttp.ClientSession": "http_request",
    "requests.get": "http_get",
    "requests.post": "http_post",
    "subprocess.run": "shell_exec",
    "os.popen": "shell_exec",
    "smtplib": "send_email",
    "telegram": "send_telegram",
    "slack_sdk": "send_slack",
    "redis": "redis_query",
    "psycopg": "db_query",
    "sqlite3": "db_query",
    "sqlalchemy": "db_query",
    "boto3": "aws_call",
    "google.cloud": "gcp_call",
    "websocket": "ws_connect",
    "bs4": "scrape_html",
    "selenium": "browser_action",
    "pandas": "data_process",
    "json.loads": "parse_json",
    "json.dumps": "serialize_json",
}


@dataclass
class DetectedSoul:
    name: str
    source_type: str
    model: str = ""
    tier: str = "Tier1"
    senses: list[str] = field(default_factory=list)
    memory_fields: list[tuple[str, str, str]] = field(default_factory=list)
    has_loop: bool = False
    has_queue_get: bool = False
    has_queue_put: bool = False
    queue_targets: list[str] = field(default_factory=list)
    queue_sources: list[str] = field(default_factory=list)
    heal_patterns: list[str] = field(default_factory=list)
    raw_statements: int = 0
    confidence: float = 0.0


@dataclass
class DetectedRoute:
    source: str
    target: str
    via: str = "queue"


@dataclass
class MigrationResult:
    source_file: Path
    souls: list[DetectedSoul] = field(default_factory=list)
    routes: list[DetectedRoute] = field(default_factory=list)
    world_name: str = ""
    imports_found: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    nous_source: str = ""

    @property
    def ok(self) -> bool:
        return len(self.souls) > 0


class PythonAnalyzer(ast.NodeVisitor):

    def __init__(self, source_path: Path) -> None:
        self.source_path = source_path
        self.souls: list[DetectedSoul] = []
        self.routes: list[DetectedRoute] = []
        self.env_vars: list[str] = []
        self.imports: list[str] = []
        self._current_soul: Optional[DetectedSoul] = None
        self._class_map: dict[str, DetectedSoul] = {}
        self._inside_class: bool = False
        self._queue_wiring: list[tuple[str, str, str]] = []

    def analyze(self, tree: ast.AST) -> None:
        self._scan_imports(tree)
        self._scan_env_vars(tree)
        self.visit(tree)
        self._scan_main_wiring(tree)
        self._infer_routes()
        self._calculate_confidence()

    def _scan_imports(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.imports.append(node.module)

    def _scan_env_vars(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                src = ast.dump(node)
                if "os.environ" in src or "os.getenv" in src or "getenv" in src:
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            self.env_vars.append(arg.value)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        soul = DetectedSoul(
            name=node.name,
            source_type="class",
        )
        self._current_soul = soul
        self._class_map[node.name] = soul
        self._inside_class = True

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                self._detect_memory_from_init(item, soul)
                for sub in ast.walk(item):
                    self._detect_model(sub, soul)

            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(item):
                    self._detect_model(sub, soul)
                    self._detect_senses_node(sub, soul)
                    self._detect_loops(sub, soul)
                    self._detect_queues(sub, soul)
                    self._detect_heal(sub, soul)

        soul.raw_statements = len(list(ast.walk(node)))
        self.souls.append(soul)
        self._current_soul = None
        self._inside_class = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._inside_class:
            return
        if node.name.startswith("_"):
            return
        if node.name == "main":
            return

        soul = DetectedSoul(
            name=node.name,
            source_type="async_func",
        )
        self._current_soul = soul

        for item in ast.walk(node):
            self._detect_model(item, soul)
            self._detect_senses_node(item, soul)
            self._detect_loops(item, soul)
            self._detect_queues(item, soul)
            self._detect_heal(item, soul)

        soul.raw_statements = len(list(ast.walk(node)))

        if soul.has_loop or soul.senses or soul.model:
            self.souls.append(soul)

        self._current_soul = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._inside_class:
            return
        if node.name.startswith("_"):
            return
        if node.name == "main":
            return

        soul = DetectedSoul(
            name=node.name,
            source_type="func",
        )
        self._current_soul = soul

        for item in ast.walk(node):
            self._detect_model(item, soul)
            self._detect_senses_node(item, soul)
            self._detect_loops(item, soul)
            self._detect_queues(item, soul)
            self._detect_heal(item, soul)

        soul.raw_statements = len(list(ast.walk(node)))

        if soul.model or (soul.senses and soul.has_loop):
            self.souls.append(soul)

        self._current_soul = None

    def _detect_model(self, node: ast.AST, soul: DetectedSoul) -> None:
        if soul.model:
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.lower()
            for pattern, (model, tier) in MODEL_PATTERNS.items():
                if pattern in val:
                    soul.model = model
                    soul.tier = tier
                    return
        if isinstance(node, ast.Attribute):
            val = node.attr.lower()
            for pattern, (model, tier) in MODEL_PATTERNS.items():
                if pattern in val:
                    soul.model = model
                    soul.tier = tier
                    return

    def _detect_senses_node(self, node: ast.AST, soul: DetectedSoul) -> None:
        if not isinstance(node, ast.Call):
            return
        call_chain = self._extract_call_chain(node)
        if not call_chain:
            return

        for pattern, sense_name in SENSE_PATTERNS.items():
            if sense_name in soul.senses:
                continue
            parts = pattern.lower().split(".")
            chain_lower = [c.lower() for c in call_chain]
            chain_str = ".".join(chain_lower)
            if any(p in chain_str for p in parts):
                soul.senses.append(sense_name)
            elif any(p in chain_lower for p in parts):
                soul.senses.append(sense_name)

    def _extract_call_chain(self, node: ast.Call) -> list[str]:
        parts: list[str] = []
        current = node.func
        while True:
            if isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            elif isinstance(current, ast.Name):
                parts.append(current.id)
                break
            elif isinstance(current, ast.Call):
                sub = self._extract_call_chain(current)
                parts.extend(sub)
                break
            else:
                break
        parts.reverse()
        return parts

    def _detect_memory_from_init(self, node: ast.FunctionDef, soul: DetectedSoul) -> None:
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        if target.value.id == "self":
                            fname = target.attr
                            if fname.startswith("_"):
                                continue
                            if any(skip in fname.lower() for skip in ("queue", "client", "session", "anthropic", "lock", "semaphore", "event")):
                                continue
                            ftype = _infer_type(stmt.value)
                            fdefault = _infer_default(stmt.value)
                            soul.memory_fields.append((fname, ftype, fdefault))

    def _detect_loops(self, node: ast.AST, soul: DetectedSoul) -> None:
        if isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                soul.has_loop = True
        elif isinstance(node, (ast.AsyncFor,)):
            soul.has_loop = True

    def _detect_queues(self, node: ast.AST, soul: DetectedSoul) -> None:
        if not isinstance(node, ast.Call):
            return
        chain = self._extract_call_chain(node)
        chain_str = ".".join(chain).lower()
        if "put" in chain or "put_nowait" in chain:
            soul.has_queue_put = True
            for part in chain:
                if "queue" in part.lower() or "output" in part.lower():
                    soul.queue_targets.append(part)
        if "get" in chain and ("queue" in chain_str or "input" in chain_str or "channel" in chain_str):
            soul.has_queue_get = True
            for part in chain:
                if "queue" in part.lower() or "input" in part.lower():
                    soul.queue_sources.append(part)

    def _detect_heal(self, node: ast.AST, soul: DetectedSoul) -> None:
        if isinstance(node, ast.ExceptHandler):
            if node.type:
                exc_name = ""
                if isinstance(node.type, ast.Name):
                    exc_name = node.type.id
                elif isinstance(node.type, ast.Attribute):
                    exc_name = node.type.attr
                if exc_name:
                    soul.heal_patterns.append(exc_name.lower())

    def _scan_main_wiring(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "main":
                    self._parse_main_body(node)

    def _parse_main_body(self, node: ast.AST) -> None:
        var_to_class: dict[str, str] = {}
        queue_vars: set[str] = set()
        assignments: dict[str, str] = {}

        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    tname = ""
                    if isinstance(target, ast.Name):
                        tname = target.id
                    if not tname:
                        continue
                    if isinstance(stmt.value, ast.Call):
                        if isinstance(stmt.value.func, ast.Name):
                            cname = stmt.value.func.id
                            if cname in self._class_map:
                                var_to_class[tname] = cname
                            elif "queue" in cname.lower() or cname == "Queue":
                                queue_vars.add(tname)
                        elif isinstance(stmt.value.func, ast.Attribute):
                            attr_chain = []
                            cur = stmt.value.func
                            while isinstance(cur, ast.Attribute):
                                attr_chain.append(cur.attr)
                                cur = cur.value
                            if isinstance(cur, ast.Name):
                                attr_chain.append(cur.id)
                            attr_chain.reverse()
                            full = ".".join(attr_chain)
                            if "queue" in full.lower():
                                queue_vars.add(tname)

            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        var = target.value.id
                        attr = target.attr
                        if isinstance(stmt.value, ast.Name) and stmt.value.id in queue_vars:
                            queue_name = stmt.value.id
                            class_name = var_to_class.get(var, var)
                            if "output" in attr.lower():
                                self._queue_wiring.append((class_name, queue_name, "output"))
                            elif "input" in attr.lower():
                                self._queue_wiring.append((class_name, queue_name, "input"))

    def _infer_routes(self) -> None:
        outputs: dict[str, str] = {}
        inputs: dict[str, str] = {}

        for class_name, queue_name, direction in self._queue_wiring:
            if direction == "output":
                outputs[queue_name] = class_name
            elif direction == "input":
                inputs[queue_name] = class_name

        for queue_name in outputs:
            if queue_name in inputs:
                src = outputs[queue_name]
                tgt = inputs[queue_name]
                self.routes.append(DetectedRoute(src, tgt, via=queue_name))

        if not self.routes:
            producers = [s for s in self.souls if s.has_queue_put]
            consumers = [s for s in self.souls if s.has_queue_get]
            if len(producers) == 1 and len(consumers) == 1 and producers[0].name != consumers[0].name:
                self.routes.append(DetectedRoute(producers[0].name, consumers[0].name))

    def _calculate_confidence(self) -> None:
        for soul in self.souls:
            score = 0.0
            if soul.model:
                score += 0.3
            if soul.senses:
                score += 0.2
            if soul.has_loop:
                score += 0.15
            if soul.memory_fields:
                score += 0.15
            if soul.heal_patterns:
                score += 0.1
            if soul.has_queue_put or soul.has_queue_get:
                score += 0.1
            soul.confidence = min(score, 1.0)


def _infer_type(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int):
            return "int"
        elif isinstance(node.value, float):
            return "float"
        elif isinstance(node.value, str):
            return "string"
        elif isinstance(node.value, bool):
            return "bool"
    elif isinstance(node, ast.List):
        return "[string]"
    elif isinstance(node, ast.Dict):
        return "map"
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id == "dict":
                return "map"
            elif node.func.id == "list":
                return "[string]"
            elif node.func.id == "set":
                return "[string]"
    return "string"


def _infer_default(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return f'"{node.value}"'
        return str(node.value)
    elif isinstance(node, ast.List):
        return "[]"
    elif isinstance(node, ast.Dict):
        return "%{}"
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in ("dict", "list", "set"):
                return "[]" if node.func.id != "dict" else "%{}"
    return '""'


def _to_pascal(name: str) -> str:
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)


def generate_nous(result: MigrationResult) -> str:
    lines: list[str] = []
    world_name = result.world_name or _to_pascal(result.source_file.stem)

    lines.append(f"# {world_name}.nous — Auto-migrated from {result.source_file.name}")
    lines.append(f"# Detected: {len(result.souls)} souls, {len(result.routes)} routes")
    lines.append(f"# Review all generated code before use")
    lines.append("")

    lines.append(f"world {world_name} {{")
    lines.append("    law CostCeiling = $0.50 per cycle")
    lines.append("    law MaxLatency = 60s")
    lines.append("    heartbeat = 5m")
    lines.append("}")
    lines.append("")

    msg_pairs: list[tuple[str, str]] = []
    for route in result.routes:
        msg_name = f"{route.source}Signal"
        lines.append(f"message {msg_name} {{")
        lines.append("    data: string")
        lines.append("    timestamp: float")
        lines.append("}")
        lines.append("")
        msg_pairs.append((route.source, msg_name))

    for soul in result.souls:
        soul_name = _to_pascal(soul.name)
        lines.append(f"soul {soul_name} {{")

        model = soul.model or "gemini-flash"
        tier = soul.tier or "Tier2"
        lines.append(f"    mind: {model} @ {tier}")

        if soul.senses:
            senses_str = ", ".join(soul.senses[:10])
            lines.append(f"    senses: [{senses_str}]")

        if soul.memory_fields:
            lines.append("")
            lines.append("    memory {")
            for fname, ftype, fdefault in soul.memory_fields:
                if fname.startswith("_"):
                    continue
                lines.append(f"        {fname}: {ftype} = {fdefault}")
            lines.append("    }")

        lines.append("")
        lines.append("    instinct {")

        is_listener = any(r.target == soul.name or r.target == soul_name for r in result.routes)
        is_speaker = any(r.source == soul.name or r.source == soul_name for r in result.routes)

        if is_listener:
            for route in result.routes:
                if route.target == soul.name or route.target == soul_name:
                    src_pascal = _to_pascal(route.source)
                    msg_name = f"{route.source}Signal"
                    lines.append(f"        let signal = listen {src_pascal}::{msg_name}")
            lines.append("        # TODO: implement processing logic")
        else:
            for sense in soul.senses[:3]:
                lines.append(f"        let result = sense {sense}()")
            if not soul.senses:
                lines.append("        # TODO: implement instinct logic")

        if is_speaker:
            for route in result.routes:
                if route.source == soul.name or route.source == soul_name:
                    msg_name = f"{route.source}Signal"
                    lines.append(f'        speak {msg_name}(data: "result", timestamp: 0)')

        lines.append("    }")

        lines.append("")
        lines.append("    dna {")
        lines.append("        temperature: 0.3 ~ [0.1, 0.9]")
        lines.append("    }")

        if soul.heal_patterns:
            lines.append("")
            lines.append("    heal {")
            heal_set = set(soul.heal_patterns)
            if "timeout" in heal_set or "timeouterror" in heal_set:
                lines.append("        on timeout => retry(3, exponential)")
            if "connectionerror" in heal_set or "httperror" in heal_set:
                lines.append("        on api_error => retry(2, exponential)")
            if not heal_set & {"timeout", "timeouterror", "connectionerror", "httperror"}:
                lines.append("        on timeout => retry(2, exponential)")
            lines.append("    }")

        lines.append("}")
        lines.append("")

    if result.routes:
        lines.append("nervous_system {")
        for route in result.routes:
            src = _to_pascal(route.source)
            tgt = _to_pascal(route.target)
            lines.append(f"    {src} -> {tgt}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def migrate_python(source: Path, output: Optional[Path] = None) -> MigrationResult:
    code = source.read_text(encoding="utf-8")
    tree = ast.parse(code, filename=str(source))

    analyzer = PythonAnalyzer(source)
    analyzer.analyze(tree)

    result = MigrationResult(
        source_file=source,
        souls=analyzer.souls,
        routes=analyzer.routes,
        world_name=_to_pascal(source.stem),
        imports_found=analyzer.imports,
        env_vars=analyzer.env_vars,
    )

    if not result.souls:
        result.warnings.append("No soul candidates detected in source")

    low_confidence = [s for s in result.souls if s.confidence < 0.3]
    for s in low_confidence:
        result.warnings.append(f"Low confidence ({s.confidence:.0%}) for soul '{s.name}' — review carefully")

    result.nous_source = generate_nous(result)

    if output:
        output.write_text(result.nous_source, encoding="utf-8")

    return result


def print_migration_report(result: MigrationResult) -> None:
    print(f"\n{'='*50}")
    print(f"NOUS Migration v2 — {result.source_file.name}")
    print(f"{'='*50}")
    print(f"Source:     {result.source_file}")
    print(f"Souls:      {len(result.souls)}")
    print(f"Routes:     {len(result.routes)}")
    print(f"Imports:    {len(result.imports_found)}")
    print(f"Env vars:   {len(result.env_vars)}")

    if result.souls:
        print(f"\nDetected Souls:")
        for s in result.souls:
            wake = "LISTENER" if s.has_queue_get else "HEARTBEAT"
            model_info = f"{s.model} @ {s.tier}" if s.model else "undetected"
            print(f"  {_to_pascal(s.name):20s} | {s.source_type:10s} | {model_info:25s} | {wake:10s} | confidence: {s.confidence:.0%}")
            if s.senses:
                print(f"    senses: {', '.join(s.senses)}")
            if s.memory_fields:
                print(f"    memory: {len(s.memory_fields)} fields")

    if result.routes:
        print(f"\nDetected Routes:")
        for r in result.routes:
            print(f"  {_to_pascal(r.source)} -> {_to_pascal(r.target)}")

    if result.warnings:
        print(f"\nWarnings:")
        for w in result.warnings:
            print(f"  ⚠ {w}")

    print(f"\nGenerated: {len(result.nous_source.splitlines())} lines of .nous")
