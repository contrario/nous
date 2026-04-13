"""
NOUS LSP Server — Νόηση (Noesis)
==================================
Language Server Protocol for NOUS .nous files.
JSON-RPC over stdio. No external LSP libraries.
Provides: diagnostics, completion, hover, go-to-definition.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("nous.lsp")

NOUS_KEYWORDS = [
    "world", "soul", "message", "nervous_system", "evolution", "perception",
    "mind", "senses", "memory", "instinct", "dna", "heal",
    "law", "heartbeat", "timezone",
    "let", "remember", "speak", "listen", "sense", "guard",
    "if", "else", "for", "in", "on", "match", "sleep",
    "import", "test", "deploy", "topology", "nsp",
    "true", "false", "self", "now", "cycle", "per",
    "retry", "lower", "raise", "hibernate", "fallback", "delegate", "alert",
    "wake", "wake_all", "broadcast", "silence",
    "constitutional", "mutate", "strategy", "survive_if", "rollback_if",
    "fitness", "schedule",
]

NOUS_TYPES = ["string", "float", "int", "bool", "timestamp", "duration", "currency", "SoulRef", "ToolRef"]

TIER_VALUES = ["Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3"]


class NousDocument:
    """Tracks an open .nous file and its analysis results."""

    def __init__(self, uri: str, text: str) -> None:
        self.uri = uri
        self.text = text
        self.lines = text.split("\n")
        self.program: Any = None
        self.parse_error: Optional[str] = None
        self.soul_names: list[str] = []
        self.message_names: list[str] = []
        self.message_fields: dict[str, list[dict[str, str]]] = {}
        self.memory_fields: dict[str, list[dict[str, str]]] = {}
        self.sense_names: dict[str, list[str]] = {}
        self.soul_lines: dict[str, int] = {}
        self.message_lines: dict[str, int] = {}
        self._analyze()

    def _analyze(self) -> None:
        try:
            sys_path_backup = list(sys.path)
            script_dir = str(Path(__file__).parent)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            from parser import parse_nous
            self.program = parse_nous(self.text)
            self.parse_error = None
            sys.path[:] = sys_path_backup
        except Exception as e:
            self.parse_error = str(e)
            self._analyze_fallback()
            return

        for soul in self.program.souls:
            self.soul_names.append(soul.name)
            if soul.senses:
                self.sense_names[soul.name] = soul.senses
            if soul.memory:
                self.memory_fields[soul.name] = [
                    {"name": f.name, "type": f.type_expr} for f in soul.memory.fields
                ]

        for msg in self.program.messages:
            self.message_names.append(msg.name)
            self.message_fields[msg.name] = [
                {"name": f.name, "type": f.type_expr} for f in msg.fields
            ]

        for i, line in enumerate(self.lines):
            stripped = line.strip()
            m = re.match(r"soul\s+(\w+)", stripped)
            if m:
                self.soul_lines[m.group(1)] = i
            m = re.match(r"message\s+(\w+)", stripped)
            if m:
                self.message_lines[m.group(1)] = i

    def _analyze_fallback(self) -> None:
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            m = re.match(r"soul\s+(\w+)", stripped)
            if m:
                self.soul_names.append(m.group(1))
                self.soul_lines[m.group(1)] = i
            m = re.match(r"message\s+(\w+)", stripped)
            if m:
                self.message_names.append(m.group(1))
                self.message_lines[m.group(1)] = i

    def get_diagnostics(self) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        if self.parse_error:
            line_num = 0
            col = 0
            m = re.search(r"line (\d+)", self.parse_error)
            if m:
                line_num = max(0, int(m.group(1)) - 1)
            m2 = re.search(r"column (\d+)", self.parse_error)
            if m2:
                col = max(0, int(m2.group(1)) - 1)
            diagnostics.append({
                "range": _range(line_num, col, line_num, col + 10),
                "severity": 1,
                "source": "nous-parser",
                "message": self.parse_error,
            })
            return diagnostics

        if self.program is None:
            return diagnostics

        try:
            script_dir = str(Path(__file__).parent)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            from validator import validate_program
            vr = validate_program(self.program)
            for e in vr.errors:
                line_num = self._find_location_line(e.location)
                diagnostics.append({
                    "range": _range(line_num, 0, line_num, 100),
                    "severity": 1,
                    "source": "nous-validator",
                    "message": f"{e.code}: {e.message}",
                })
            for w in vr.warnings:
                line_num = self._find_location_line(w.location)
                diagnostics.append({
                    "range": _range(line_num, 0, line_num, 100),
                    "severity": 2,
                    "source": "nous-validator",
                    "message": f"{w.code}: {w.message}",
                })

            from typechecker import typecheck_program
            tc = typecheck_program(self.program)
            for e in tc.errors:
                line_num = self._find_location_line(e.location)
                diagnostics.append({
                    "range": _range(line_num, 0, line_num, 100),
                    "severity": 1,
                    "source": "nous-typechecker",
                    "message": f"{e.code}: {e.message}",
                })
            for w in tc.warnings:
                line_num = self._find_location_line(w.location)
                diagnostics.append({
                    "range": _range(line_num, 0, line_num, 100),
                    "severity": 2,
                    "source": "nous-typechecker",
                    "message": f"{w.code}: {w.message}",
                })
        except Exception as e:
            log.error(f"Diagnostic error: {e}")

        return diagnostics

    def _find_location_line(self, location: str) -> int:
        if not location:
            return 0
        m = re.search(r"soul (\w+)", location)
        if m:
            return self.soul_lines.get(m.group(1), 0)
        return 0

    def get_completions(self, line: int, character: int) -> list[dict[str, Any]]:
        if line >= len(self.lines):
            return []
        text_line = self.lines[line]
        prefix = text_line[:character].strip()
        items: list[dict[str, Any]] = []

        if "::" in prefix:
            parts = prefix.split("::")
            soul_name = parts[0].split()[-1] if parts[0] else ""
            if soul_name in self.message_fields:
                pass
            for msg_name in self.message_names:
                items.append(_completion(msg_name, 7, detail=f"message {msg_name}"))
            return items

        if prefix.endswith(".") or "." in prefix.split()[-1] if prefix.split() else False:
            last_word = prefix.split()[-1] if prefix.split() else ""
            if "." in last_word:
                obj_name = last_word.split(".")[0]
                for soul_name, fields in self.memory_fields.items():
                    for f in fields:
                        items.append(_completion(f["name"], 5, detail=f"{f['type']}"))
                for msg_name, fields in self.message_fields.items():
                    for f in fields:
                        items.append(_completion(f["name"], 5, detail=f"{f['type']}"))
                return items

        if re.match(r"\s*mind\s*:", prefix):
            for model in ["claude-haiku", "claude-sonnet", "deepseek-r1", "gemini-flash", "gpt-4o-mini"]:
                items.append(_completion(model, 12, detail="model"))
            return items

        if re.match(r".*@\s*$", prefix):
            for tier in TIER_VALUES:
                items.append(_completion(tier, 12, detail="tier"))
            return items

        if re.match(r"\s*(speak|listen)\s+", prefix):
            for msg in self.message_names:
                items.append(_completion(msg, 7, detail="message"))
            return items

        if re.match(r"\s*sense\s+", prefix):
            all_senses: set[str] = set()
            for senses in self.sense_names.values():
                all_senses.update(senses)
            for s in sorted(all_senses):
                items.append(_completion(s, 3, detail="tool"))
            return items

        if re.match(r"\s*(soul|->|listen)\s*", prefix):
            for soul in self.soul_names:
                items.append(_completion(soul, 7, detail="soul"))
            return items

        if ":" in prefix and not prefix.strip().startswith("#"):
            for t in NOUS_TYPES:
                items.append(_completion(t, 7, detail="type"))
            return items

        for kw in NOUS_KEYWORDS:
            if kw.startswith(prefix.split()[-1]) if prefix.split() else True:
                items.append(_completion(kw, 14, detail="keyword"))

        for soul in self.soul_names:
            items.append(_completion(soul, 7, detail="soul"))
        for msg in self.message_names:
            items.append(_completion(msg, 7, detail="message"))

        return items[:50]

    def get_hover(self, line: int, character: int) -> Optional[dict[str, Any]]:
        if line >= len(self.lines):
            return None
        text_line = self.lines[line]
        word = _word_at(text_line, character)
        if not word:
            return None

        if word in self.soul_lines:
            soul = next((s for s in (self.program.souls if self.program else []) if s.name == word), None)
            if soul:
                mind_str = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none"
                senses_str = ", ".join(soul.senses) if soul.senses else "none"
                mem_count = len(soul.memory.fields) if soul.memory else 0
                text = f"**soul {word}**\n\nmind: {mind_str}\nsenses: {senses_str}\nmemory: {mem_count} fields"
                if soul.dna:
                    genes = ", ".join(g.name for g in soul.dna.genes)
                    text += f"\ndna: {genes}"
                return {"contents": {"kind": "markdown", "value": text}}

        if word in self.message_fields:
            fields = self.message_fields[word]
            fields_str = "\n".join(f"  {f['name']}: {f['type']}" for f in fields)
            text = f"**message {word}**\n\n```\n{fields_str}\n```"
            return {"contents": {"kind": "markdown", "value": text}}

        if word in NOUS_KEYWORDS:
            return {"contents": {"kind": "markdown", "value": f"**{word}** — NOUS keyword"}}

        if word in NOUS_TYPES:
            return {"contents": {"kind": "markdown", "value": f"**{word}** — NOUS type"}}

        for soul_name, fields in self.memory_fields.items():
            for f in fields:
                if f["name"] == word:
                    return {"contents": {"kind": "markdown", "value": f"**{word}**: {f['type']}\n\nmemory field of soul {soul_name}"}}

        return None

    def get_definition(self, line: int, character: int) -> Optional[dict[str, Any]]:
        if line >= len(self.lines):
            return None
        text_line = self.lines[line]
        word = _word_at(text_line, character)
        if not word:
            return None

        if word in self.soul_lines:
            target_line = self.soul_lines[word]
            return {"uri": self.uri, "range": _range(target_line, 0, target_line, 0)}

        if word in self.message_lines:
            target_line = self.message_lines[word]
            return {"uri": self.uri, "range": _range(target_line, 0, target_line, 0)}

        return None


def _range(sl: int, sc: int, el: int, ec: int) -> dict[str, Any]:
    return {
        "start": {"line": sl, "character": sc},
        "end": {"line": el, "character": ec},
    }


def _completion(label: str, kind: int, detail: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {"label": label, "kind": kind}
    if detail:
        item["detail"] = detail
    return item


def _word_at(line: str, col: int) -> str:
    if col > len(line):
        col = len(line)
    left = col
    while left > 0 and (line[left - 1].isalnum() or line[left - 1] in "_-"):
        left -= 1
    right = col
    while right < len(line) and (line[right].isalnum() or line[right] in "_-"):
        right += 1
    return line[left:right]


class NousLSPServer:
    """JSON-RPC Language Server over stdio."""

    def __init__(self) -> None:
        self.documents: dict[str, NousDocument] = {}
        self.running = True
        self._stdin = sys.stdin.buffer
        self._stdout = sys.stdout.buffer

    def run(self) -> None:
        log.info("NOUS LSP Server starting...")
        while self.running:
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
            line = self._stdin.readline()
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
        body = self._stdin.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _send_message(self, msg: dict[str, Any]) -> None:
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._stdout.write(header.encode("utf-8"))
        self._stdout.write(body)
        self._stdout.flush()

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
                    "textDocumentSync": {"openClose": True, "change": 1, "save": True},
                    "completionProvider": {"triggerCharacters": [".", ":", "@", " "]},
                    "hoverProvider": True,
                    "definitionProvider": True,
                },
                "serverInfo": {"name": "nous-lsp", "version": "1.0.0"},
            })
        elif method == "initialized":
            pass
        elif method == "shutdown":
            self._respond(req_id, None)
        elif method == "exit":
            self.running = False
        elif method == "textDocument/didOpen":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            text = td.get("text", "")
            doc = NousDocument(uri, text)
            self.documents[uri] = doc
            self._publish_diagnostics(uri, doc)
        elif method == "textDocument/didChange":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            changes = params.get("contentChanges", [])
            if changes:
                text = changes[0].get("text", "")
                doc = NousDocument(uri, text)
                self.documents[uri] = doc
                self._publish_diagnostics(uri, doc)
        elif method == "textDocument/didSave":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            if uri in self.documents:
                self._publish_diagnostics(uri, self.documents[uri])
        elif method == "textDocument/completion":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            pos = params.get("position", {})
            doc = self.documents.get(uri)
            if doc:
                items = doc.get_completions(pos.get("line", 0), pos.get("character", 0))
                self._respond(req_id, {"isIncomplete": False, "items": items})
            else:
                self._respond(req_id, {"isIncomplete": False, "items": []})
        elif method == "textDocument/hover":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            pos = params.get("position", {})
            doc = self.documents.get(uri)
            if doc:
                hover = doc.get_hover(pos.get("line", 0), pos.get("character", 0))
                self._respond(req_id, hover)
            else:
                self._respond(req_id, None)
        elif method == "textDocument/definition":
            td = params.get("textDocument", {})
            uri = td.get("uri", "")
            pos = params.get("position", {})
            doc = self.documents.get(uri)
            if doc:
                defn = doc.get_definition(pos.get("line", 0), pos.get("character", 0))
                self._respond(req_id, defn)
            else:
                self._respond(req_id, None)
        elif req_id is not None:
            self._respond(req_id, None)

    def _publish_diagnostics(self, uri: str, doc: NousDocument) -> None:
        diagnostics = doc.get_diagnostics()
        self._notify("textDocument/publishDiagnostics", {
            "uri": uri,
            "diagnostics": diagnostics,
        })


def main() -> None:
    logging.basicConfig(
        filename=str(Path.home() / ".nous" / "lsp.log"),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    Path.home().joinpath(".nous").mkdir(exist_ok=True)
    server = NousLSPServer()
    server.run()


if __name__ == "__main__":
    main()
