"""
NOUS LSP Server — Γλωσσικός Σύμβουλος (Glossikos Symvoulos)
==============================================================
Language Server Protocol implementation for NOUS.
Provides diagnostics, code actions (auto-fix), and hover info.
Communicates via JSON-RPC 2.0 over stdin/stdout.
"""
from __future__ import annotations

import json
import sys
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("nous.lsp")


@dataclass
class Position:
    line: int
    character: int

    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass
class Range:
    start: Position
    end: Position

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass
class Diagnostic:
    range: Range
    severity: int
    code: str
    source: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "range": self.range.to_dict(),
            "severity": self.severity,
            "code": self.code,
            "source": self.source,
            "message": self.message,
        }


@dataclass
class TextEdit:
    range: Range
    newText: str

    def to_dict(self) -> dict[str, Any]:
        return {"range": self.range.to_dict(), "newText": self.newText}


@dataclass
class CodeAction:
    title: str
    kind: str
    diagnostics: list[Diagnostic]
    edit: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": title_str if (title_str := self.title) else "",
            "kind": self.kind,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "edit": self.edit,
        }


SEVERITY_ERROR = 1
SEVERITY_WARNING = 2
SEVERITY_INFO = 3
SEVERITY_HINT = 4


def _loc_to_line(source: str, location: str) -> int:
    lines = source.splitlines()
    if not location:
        return 0
    m = re.match(r"soul (\w+)", location)
    if m:
        soul_name = m.group(1)
        for i, line in enumerate(lines):
            if re.match(rf"\s*soul\s+{re.escape(soul_name)}\b", line):
                return i
    if "nervous_system" in location:
        for i, line in enumerate(lines):
            if "nervous_system" in line:
                return i
    if "evolution" in location:
        for i, line in enumerate(lines):
            if "evolution" in line:
                return i
    if "perception" in location:
        for i, line in enumerate(lines):
            if "perception" in line:
                return i
    return 0


def _find_block_end(source: str, start_line: int) -> int:
    lines = source.splitlines()
    depth = 0
    for i in range(start_line, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth <= 0 and i > start_line:
            return i
    return len(lines) - 1


def _find_soul_block_line(source: str, soul_name: str, block_name: str) -> int:
    lines = source.splitlines()
    in_soul = False
    depth = 0
    for i, line in enumerate(lines):
        if re.match(rf"\s*soul\s+{re.escape(soul_name)}\b", line):
            in_soul = True
            depth = 0
        if in_soul:
            depth += line.count("{") - line.count("}")
            if re.match(rf"\s*{re.escape(block_name)}\b", line.strip()):
                return i
            if depth <= 0 and i > 0:
                in_soul = False
    return -1


def _find_soul_closing_brace(source: str, soul_name: str) -> int:
    lines = source.splitlines()
    in_soul = False
    depth = 0
    soul_start = -1
    for i, line in enumerate(lines):
        if re.match(rf"\s*soul\s+{re.escape(soul_name)}\b", line):
            in_soul = True
            soul_start = i
            depth = 0
        if in_soul:
            depth += line.count("{") - line.count("}")
            if depth <= 0 and i > soul_start:
                return i
    return len(lines) - 1


def _find_last_top_level_position(source: str) -> int:
    lines = source.splitlines()
    return len(lines)


def _find_memory_closing_brace(source: str, soul_name: str) -> int:
    lines = source.splitlines()
    in_soul = False
    in_memory = False
    depth = 0
    mem_depth = 0
    soul_start = -1
    for i, line in enumerate(lines):
        if re.match(rf"\s*soul\s+{re.escape(soul_name)}\b", line):
            in_soul = True
            soul_start = i
            depth = 0
        if in_soul:
            depth += line.count("{") - line.count("}")
            stripped = line.strip()
            if stripped.startswith("memory") and "{" in stripped:
                in_memory = True
                mem_depth = 0
            if in_memory:
                mem_depth += line.count("{") - line.count("}")
                if mem_depth <= 0:
                    return i
            if depth <= 0 and i > soul_start:
                break
    return -1


class NousDiagnostics:
    def __init__(self) -> None:
        pass

    def compute(self, uri: str, source: str) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        try:
            from parser import parse_nous
            program = parse_nous(source)
        except Exception as e:
            err_str = str(e)
            line_num = 0
            m = re.search(r"line (\d+)", err_str)
            if m:
                line_num = max(0, int(m.group(1)) - 1)
            diagnostics.append(Diagnostic(
                range=Range(Position(line_num, 0), Position(line_num, 200)),
                severity=SEVERITY_ERROR,
                code="PARSE",
                source="nous",
                message=err_str[:300],
            ))
            return diagnostics

        from validator import validate_program
        vresult = validate_program(program)
        for err in vresult.errors:
            line = _loc_to_line(source, err.location)
            sev = SEVERITY_ERROR
            diagnostics.append(Diagnostic(
                range=Range(Position(line, 0), Position(line, 200)),
                severity=sev,
                code=err.code,
                source="nous.validator",
                message=err.message,
            ))
        for warn in vresult.warnings:
            line = _loc_to_line(source, warn.location)
            diagnostics.append(Diagnostic(
                range=Range(Position(line, 0), Position(line, 200)),
                severity=SEVERITY_WARNING,
                code=warn.code,
                source="nous.validator",
                message=warn.message,
            ))

        if vresult.ok:
            from typechecker import typecheck_program
            tresult = typecheck_program(program)
            for err in tresult.errors:
                line = _loc_to_line(source, err.location)
                diagnostics.append(Diagnostic(
                    range=Range(Position(line, 0), Position(line, 200)),
                    severity=SEVERITY_ERROR,
                    code=err.code,
                    source="nous.typechecker",
                    message=err.message,
                ))
            for warn in tresult.warnings:
                line = _loc_to_line(source, warn.location)
                diagnostics.append(Diagnostic(
                    range=Range(Position(line, 0), Position(line, 200)),
                    severity=SEVERITY_WARNING,
                    code=warn.code,
                    source="nous.typechecker",
                    message=warn.message,
                ))

        # __lint_diagnostics_v1__
        try:
            from governance_lint import GovernanceLinter
            linter = GovernanceLinter()
            report = linter.lint_source(source)
            sev_map = {"error": SEVERITY_ERROR, "warning": SEVERITY_WARNING, "info": 3}
            for issue in report.issues:
                if issue.rule == "L100":
                    continue
                line = 0
                if issue.policy:
                    pat = re.compile(r"^\s*policy\s+" + re.escape(issue.policy) + r"\b", re.MULTILINE)
                    m = pat.search(source)
                    if m:
                        line = source[:m.start()].count("\n")
                diagnostics.append(Diagnostic(
                    range=Range(Position(line, 0), Position(line, 200)),
                    severity=sev_map.get(issue.severity, SEVERITY_WARNING),
                    code=issue.rule,
                    source="nous.lint",
                    message=issue.message,
                ))
        except Exception as exc:
            log.warning(f"Lint stage failed: {exc!r}")

        return diagnostics


class NousCodeActions:
    FIX_MAP: dict[str, str] = {
        "W001": "fix_no_world",
        "S002": "fix_no_mind",
        "S003": "fix_no_heal",
        "S005": "fix_no_senses",
        "N002": "fix_undefined_soul_ref",
        "T001": "fix_undefined_message_speak",
        "T002": "fix_undefined_message_listen",
        "TC001": "fix_undefined_memory_field",
        "TC004": "fix_missing_speak_fields",
        "TC005": "fix_unknown_speak_field",
        "S004": "fix_no_instinct",
        "N001": "fix_no_nervous_system",
    }

    def __init__(self) -> None:
        pass

    def compute(self, uri: str, source: str, diagnostics: list[Diagnostic]) -> list[CodeAction]:
        actions: list[CodeAction] = []
        for diag in diagnostics:
            method_name = self.FIX_MAP.get(diag.code)
            if method_name and hasattr(self, method_name):
                method = getattr(self, method_name)
                result = method(uri, source, diag)
                if result:
                    if isinstance(result, list):
                        actions.extend(result)
                    else:
                        actions.append(result)
        return actions

    def _make_action(self, title: str, uri: str, diag: Diagnostic, edits: list[TextEdit]) -> CodeAction:
        return CodeAction(
            title=title,
            kind="quickfix",
            diagnostics=[diag],
            edit={
                "changes": {
                    uri: [e.to_dict() for e in edits],
                },
            },
        )

    def fix_no_world(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        insert_line = 0
        snippet = 'world MyWorld {\n    law cost_ceiling = $0.10 per cycle\n    heartbeat = 5m\n}\n\n'
        edit = TextEdit(
            range=Range(Position(insert_line, 0), Position(insert_line, 0)),
            newText=snippet,
        )
        return self._make_action("Add world declaration", uri, diag, [edit])

    def fix_no_mind(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"Soul (\w+)", diag.message)
        if not m:
            return None
        soul_name = m.group(1)
        soul_line = _loc_to_line(source, f"soul {soul_name}")
        lines = source.splitlines()
        insert_line = soul_line + 1
        for i in range(soul_line, min(soul_line + 3, len(lines))):
            if "{" in lines[i]:
                insert_line = i + 1
                break
        snippet = "    mind: claude-sonnet @ Tier0A\n"
        edit = TextEdit(
            range=Range(Position(insert_line, 0), Position(insert_line, 0)),
            newText=snippet,
        )
        return self._make_action(f"Add mind to {soul_name}", uri, diag, [edit])

    def fix_no_heal(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"Soul (\w+)", diag.message)
        if not m:
            return None
        soul_name = m.group(1)
        close_line = _find_soul_closing_brace(source, soul_name)
        snippet = '    heal {\n        on timeout => retry(3, exponential)\n        on api_error => retry(2, exponential)\n    }\n'
        edit = TextEdit(
            range=Range(Position(close_line, 0), Position(close_line, 0)),
            newText=snippet,
        )
        return self._make_action(f"Add heal block to {soul_name}", uri, diag, [edit])

    def fix_no_senses(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"Soul (\w+)", diag.message)
        if not m:
            return None
        soul_name = m.group(1)
        mind_line = _find_soul_block_line(source, soul_name, "mind")
        if mind_line >= 0:
            insert_line = mind_line + 1
        else:
            soul_line = _loc_to_line(source, f"soul {soul_name}")
            insert_line = soul_line + 1
            lines = source.splitlines()
            for i in range(soul_line, min(soul_line + 3, len(lines))):
                if "{" in lines[i]:
                    insert_line = i + 1
                    break
        snippet = "    senses: [http_get, http_post]\n"
        edit = TextEdit(
            range=Range(Position(insert_line, 0), Position(insert_line, 0)),
            newText=snippet,
        )
        return self._make_action(f"Add senses to {soul_name}", uri, diag, [edit])

    def fix_no_instinct(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"Soul (\w+)", diag.message)
        if not m:
            return None
        soul_name = m.group(1)
        close_line = _find_soul_closing_brace(source, soul_name)
        snippet = '    instinct {\n        # TODO: add logic\n    }\n'
        edit = TextEdit(
            range=Range(Position(close_line, 0), Position(close_line, 0)),
            newText=snippet,
        )
        return self._make_action(f"Add instinct block to {soul_name}", uri, diag, [edit])

    def fix_undefined_soul_ref(self, uri: str, source: str, diag: Diagnostic) -> list[CodeAction]:
        m = re.search(r"undefined soul: (\w+)", diag.message)
        if not m:
            return []
        soul_name = m.group(1)
        actions: list[CodeAction] = []
        from error_recovery import _levenshtein
        try:
            from parser import parse_nous
            program = parse_nous(source)
            existing = [s.name for s in program.souls]
        except Exception:
            existing = []
        best_match: Optional[str] = None
        best_dist = 3
        for name in existing:
            d = _levenshtein(soul_name.lower(), name.lower())
            if d < best_dist:
                best_dist = d
                best_match = name
        if best_match:
            lines = source.splitlines()
            for i, line in enumerate(lines):
                if soul_name in line and "->" in line:
                    new_line = line.replace(soul_name, best_match)
                    edit = TextEdit(
                        range=Range(Position(i, 0), Position(i, len(line))),
                        newText=new_line,
                    )
                    actions.append(self._make_action(
                        f"Did you mean '{best_match}'?", uri, diag, [edit]
                    ))
                    break
        insert_line = _find_last_top_level_position(source)
        snippet = f'\nsoul {soul_name} {{\n    mind: claude-sonnet @ Tier0A\n    instinct {{\n        # TODO: implement\n    }}\n    heal {{\n        on timeout => retry(3, exponential)\n    }}\n}}\n'
        edit = TextEdit(
            range=Range(Position(insert_line, 0), Position(insert_line, 0)),
            newText=snippet,
        )
        actions.append(self._make_action(
            f"Create soul '{soul_name}'", uri, diag, [edit]
        ))
        return actions

    def fix_undefined_message_speak(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"undefined message type: (\w+)", diag.message)
        if not m:
            return None
        msg_name = m.group(1)
        lines = source.splitlines()
        insert_before_first_soul = 0
        for i, line in enumerate(lines):
            if re.match(r"\s*soul\s+\w+", line):
                insert_before_first_soul = i
                break
        else:
            insert_before_first_soul = len(lines)
        snippet = f'\nmessage {msg_name} {{\n    data: string\n    timestamp: float = 0.0\n}}\n\n'
        edit = TextEdit(
            range=Range(Position(insert_before_first_soul, 0), Position(insert_before_first_soul, 0)),
            newText=snippet,
        )
        return self._make_action(f"Create message '{msg_name}'", uri, diag, [edit])

    def fix_undefined_message_listen(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"undefined message type: (\w+)", diag.message)
        if not m:
            return None
        msg_name = m.group(1)
        return self.fix_undefined_message_speak(uri, source, Diagnostic(
            range=diag.range,
            severity=diag.severity,
            code=diag.code,
            source=diag.source,
            message=f"speak uses undefined message type: {msg_name}",
        ))

    def fix_undefined_memory_field(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"undefined memory field: (\w+)", diag.message)
        if not m:
            return None
        field_name = m.group(1)
        soul_match = re.search(r"soul (\w+)", diag.message) or re.search(r"@ soul (\w+)", str(diag.range))
        soul_name = ""
        lines = source.splitlines()
        diag_line = diag.range.start.line
        depth = 0
        for i in range(diag_line, -1, -1):
            sm = re.match(r"\s*soul\s+(\w+)", lines[i])
            if sm:
                soul_name = sm.group(1)
                break
        if not soul_name:
            return None
        mem_line = _find_soul_block_line(source, soul_name, "memory")
        if mem_line >= 0:
            mem_close = _find_memory_closing_brace(source, soul_name)
            if mem_close >= 0:
                snippet = f"        {field_name}: int = 0\n"
                edit = TextEdit(
                    range=Range(Position(mem_close, 0), Position(mem_close, 0)),
                    newText=snippet,
                )
                return self._make_action(f"Add '{field_name}' to {soul_name} memory", uri, diag, [edit])
        else:
            soul_line = _loc_to_line(source, f"soul {soul_name}")
            insert_line = soul_line + 1
            for i in range(soul_line, min(soul_line + 3, len(lines))):
                if "{" in lines[i]:
                    insert_line = i + 1
                    break
            snippet = f"    memory {{\n        {field_name}: int = 0\n    }}\n"
            edit = TextEdit(
                range=Range(Position(insert_line, 0), Position(insert_line, 0)),
                newText=snippet,
            )
            return self._make_action(f"Add memory block with '{field_name}' to {soul_name}", uri, diag, [edit])

    def fix_missing_speak_fields(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        m = re.search(r"speak (\w+) missing required fields: (.+)", diag.message)
        if not m:
            return None
        msg_name = m.group(1)
        missing_fields = [f.strip() for f in m.group(2).split(",")]
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if f"speak {msg_name}(" in line.strip():
                paren_idx = line.index("(")
                close_idx = line.rindex(")")
                existing_args = line[paren_idx+1:close_idx].strip()
                new_args_parts = []
                for fld in missing_fields:
                    new_args_parts.append(f'{fld}: ""')
                if existing_args:
                    new_args = existing_args + ", " + ", ".join(new_args_parts)
                else:
                    new_args = ", ".join(new_args_parts)
                new_line = line[:paren_idx+1] + new_args + line[close_idx:]
                edit = TextEdit(
                    range=Range(Position(i, 0), Position(i, len(line))),
                    newText=new_line,
                )
                return self._make_action(
                    f"Add missing fields to speak {msg_name}", uri, diag, [edit]
                )
        return None

    def fix_unknown_speak_field(self, uri: str, source: str, diag: Diagnostic) -> Optional[CodeAction]:
        m = re.search(r"speak (\w+) provides unknown field: (\w+)", diag.message)
        if not m:
            return None
        msg_name = m.group(1)
        bad_field = m.group(2)
        try:
            from parser import parse_nous
            program = parse_nous(source)
            msg_node = next((msg for msg in program.messages if msg.name == msg_name), None)
            if not msg_node:
                return None
            known_fields = [f.name for f in msg_node.fields]
        except Exception:
            return None
        from error_recovery import _levenshtein
        best: Optional[str] = None
        best_d = 3
        for f in known_fields:
            d = _levenshtein(bad_field.lower(), f.lower())
            if d < best_d:
                best_d = d
                best = f
        if not best:
            return None
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if f"speak {msg_name}(" in line and bad_field in line:
                new_line = line.replace(bad_field, best, 1)
                edit = TextEdit(
                    range=Range(Position(i, 0), Position(i, len(line))),
                    newText=new_line,
                )
                return self._make_action(
                    f"Replace '{bad_field}' with '{best}'", uri, diag, [edit]
                )
        return None

    def fix_no_nervous_system(self, uri: str, source: str, diag: Diagnostic) -> CodeAction:
        try:
            from parser import parse_nous
            program = parse_nous(source)
            soul_names = [s.name for s in program.souls]
        except Exception:
            soul_names = ["Soul1", "Soul2"]
        if len(soul_names) < 2:
            return None
        routes = " -> ".join(soul_names)
        insert_line = _find_last_top_level_position(source)
        snippet = f"\nnervous_system {{\n    {routes}\n}}\n"
        edit = TextEdit(
            range=Range(Position(insert_line, 0), Position(insert_line, 0)),
            newText=snippet,
        )
        return self._make_action("Add nervous_system with chain route", uri, diag, [edit])


class NousLSPServer:
    def __init__(self) -> None:
        self._diagnostics_engine = NousDiagnostics()
        self._actions_engine = NousCodeActions()
        self._documents: dict[str, str] = {}
        self._running = True

    def run(self) -> None:
        log.info("NOUS LSP Server starting...")
        while self._running:
            try:
                msg = self._read_message()
                if msg is None:
                    break
                self._handle_message(msg)
            except Exception as e:
                log.error(f"LSP error: {e}")

    def _read_message(self) -> Optional[dict[str, Any]]:
        headers: dict[str, str] = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            line_str = line.decode("utf-8").strip()
            if not line_str:
                break
            if ":" in line_str:
                key, val = line_str.split(":", 1)
                headers[key.strip()] = val.strip()
        content_length = int(headers.get("Content-Length", "0"))
        if content_length == 0:
            return None
        body = sys.stdin.buffer.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _send_message(self, msg: dict[str, Any]) -> None:
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        sys.stdout.buffer.write(header.encode("utf-8"))
        sys.stdout.buffer.write(body.encode("utf-8"))
        sys.stdout.buffer.flush()

    def _respond(self, req_id: Any, result: Any) -> None:
        self._send_message({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _notify(self, method: str, params: Any) -> None:
        self._send_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _handle_message(self, msg: dict[str, Any]) -> None:
        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            self._respond(req_id, {
                "capabilities": {
                    "textDocumentSync": 1,
                    "codeActionProvider": True,
                    "hoverProvider": True,
                    "diagnosticProvider": {
                        "interFileDependencies": False,
                        "workspaceDiagnostics": False,
                    },
                },
                "serverInfo": {
                    "name": "nous-lsp",
                    "version": "1.0.0",
                },
            })

        elif method == "initialized":
            pass

        elif method == "shutdown":
            self._respond(req_id, None)

        elif method == "exit":
            self._running = False

        elif method == "textDocument/didOpen":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            text = td.get("text", "")
            self._documents[uri] = text
            self._publish_diagnostics(uri, text)

        elif method == "textDocument/didChange":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            changes = params.get("contentChanges", [])
            if changes:
                self._documents[uri] = changes[-1].get("text", "")
            self._publish_diagnostics(uri, self._documents.get(uri, ""))

        elif method == "textDocument/didClose":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            self._documents.pop(uri, None)
            self._notify("textDocument/publishDiagnostics", {
                "uri": uri, "diagnostics": [],
            })

        elif method == "textDocument/codeAction":
            self._handle_code_action(req_id, params)

        elif method == "textDocument/hover":
            self._handle_hover(req_id, params)

        elif req_id is not None:
            self._respond(req_id, None)

    def _publish_diagnostics(self, uri: str, source: str) -> None:
        diags = self._diagnostics_engine.compute(uri, source)
        self._notify("textDocument/publishDiagnostics", {
            "uri": uri,
            "diagnostics": [d.to_dict() for d in diags],
        })

    def _handle_code_action(self, req_id: Any, params: dict[str, Any]) -> None:
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        source = self._documents.get(uri, "")
        context = params.get("context", {})
        raw_diags = context.get("diagnostics", [])
        diags: list[Diagnostic] = []
        for rd in raw_diags:
            r = rd.get("range", {})
            s = r.get("start", {})
            e = r.get("end", {})
            diags.append(Diagnostic(
                range=Range(
                    Position(s.get("line", 0), s.get("character", 0)),
                    Position(e.get("line", 0), e.get("character", 0)),
                ),
                severity=rd.get("severity", 1),
                code=rd.get("code", ""),
                source=rd.get("source", ""),
                message=rd.get("message", ""),
            ))
        actions = self._actions_engine.compute(uri, source, diags)
        self._respond(req_id, [a.to_dict() for a in actions])

    def _handle_hover(self, req_id: Any, params: dict[str, Any]) -> None:
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        line = pos.get("line", 0)
        char = pos.get("character", 0)
        source = self._documents.get(uri, "")
        lines = source.splitlines()
        if line >= len(lines):
            self._respond(req_id, None)
            return
        current_line = lines[line]
        word = self._word_at(current_line, char)
        hover_text = self._get_hover_info(word, source)
        if hover_text:
            self._respond(req_id, {
                "contents": {"kind": "markdown", "value": hover_text},
            })
        else:
            self._respond(req_id, None)

    def _word_at(self, line: str, col: int) -> str:
        if col >= len(line):
            return ""
        start = col
        while start > 0 and (line[start-1].isalnum() or line[start-1] == "_"):
            start -= 1
        end = col
        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1
        return line[start:end]

    def _get_hover_info(self, word: str, source: str) -> Optional[str]:
        keyword_docs: dict[str, str] = {
            "soul": "**soul** — An autonomous agent with mind, memory, instinct, and heal blocks.",
            "world": "**world** — The environment declaration. Contains laws, heartbeat, and config.",
            "mind": "**mind** — LLM assignment: `mind: model-name @ TierXY`",
            "instinct": "**instinct** — The execution logic block. Runs on heartbeat or message.",
            "memory": "**memory** — Persistent state fields for a soul.",
            "heal": "**heal** — Error recovery rules: `on error_type => strategy`",
            "dna": "**dna** — Evolvable parameters: `gene_name: value ~ [min, max]`",
            "speak": "**speak** — Send a message: `speak MessageType(field: value)`",
            "listen": "**listen** — Receive a message: `let x = listen Soul::MessageType`",
            "guard": "**guard** — Early return if condition is false: `guard condition`",
            "remember": "**remember** — Update memory: `remember field = value`",
            "sense": "**sense** — Call an external tool: `sense tool_name(args)`",
            "nervous_system": "**nervous_system** — Message routing between souls.",
            "topology": "**topology** — Distributed deployment: assign souls to network nodes.",
            "evolution": "**evolution** — Self-modification rules for DNA parameters.",
            "perception": "**perception** — Event-driven triggers and responses.",
            "noesis": "**noesis** — Symbolic intelligence engine configuration.",
            "resonate": "**resonate** — Query the Noesis knowledge lattice.",
        }
        if word in keyword_docs:
            return keyword_docs[word]
        try:
            from parser import parse_nous
            program = parse_nous(source)
            for s in program.souls:
                if s.name == word:
                    mind = f"{s.mind.model} @ {s.mind.tier.value}" if s.mind else "none"
                    senses = ", ".join(s.senses) if s.senses else "none"
                    mem_count = len(s.memory.fields) if s.memory else 0
                    return f"**soul {s.name}**\n- Mind: {mind}\n- Senses: {senses}\n- Memory fields: {mem_count}"
            for m in program.messages:
                if m.name == word:
                    fields = ", ".join(f"{f.name}: {f.type_expr}" for f in m.fields)
                    return f"**message {m.name}**\n- Fields: {fields}"
        except Exception:
            pass
        return None


def run_lsp() -> None:
    logging.basicConfig(
        filename="/tmp/nous_lsp.log",
        level=logging.DEBUG,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )
    server = NousLSPServer()
    server.run()


def check_file(path: str) -> tuple[list[dict], list[dict]]:
    source = Path(path).read_text(encoding="utf-8")
    uri = f"file://{path}"
    engine_d = NousDiagnostics()
    engine_a = NousCodeActions()
    diags = engine_d.compute(uri, source)
    actions = engine_a.compute(uri, source, diags)
    return [d.to_dict() for d in diags], [a.to_dict() for a in actions]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        if target:
            diags, actions = check_file(target)
            print(f"Diagnostics ({len(diags)}):")
            for d in diags:
                print(f"  [{d['code']}] {d['message']}")
            print(f"\nCode Actions ({len(actions)}):")
            for a in actions:
                print(f"  → {a['title']}")
        else:
            print("Usage: nous lsp check <file.nous>")
    else:
        run_lsp()
