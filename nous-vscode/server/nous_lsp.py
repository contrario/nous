"""
NOUS Language Server — Νοῦς LSP
=================================
Real-time validation, hover, completion, go-to-definition.
Requires: pygls, lark, pydantic
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

from lark import Lark, Token
from lark.exceptions import UnexpectedCharacters, UnexpectedToken

from pygls.server import LanguageServer
from pygls.lsp import types

NOUS_VERSION = "1.8.0"
log = logging.getLogger("nous.lsp")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from ast_nodes import (
        NousProgram, WorldNode, SoulNode, MessageNode,
        TopologyNode, TopologyServerNode,
    )
    from parser import parse_nous, NousTransformer, GRAMMAR_PATH
    from validator import validate_program
    HAS_NOUS = True
except ImportError:
    HAS_NOUS = False

KEYWORDS_EN = [
    "world", "soul", "message", "memory", "instinct", "dna", "heal",
    "senses", "mind", "law", "guard", "speak", "listen", "sense",
    "remember", "sleep", "let", "if", "else", "for", "in", "on",
    "nervous_system", "evolution", "perception", "topology", "deploy",
    "heartbeat", "timezone", "true", "false", "self", "now",
    "match", "silence", "wake_all", "wake", "broadcast", "alert",
    "retry", "lower", "raise", "hibernate", "fallback", "delegate",
    "mutate", "schedule", "fitness", "strategy", "survive_if", "rollback_if",
    "per", "cycle", "constitutional", "nsp",
]

KEYWORDS_GR = [
    "κόσμος", "ψυχή", "μήνυμα", "μνήμη", "ένστικτο", "θεραπεία",
    "νόμος", "φύλακας", "λέω", "ακούω", "αίσθηση", "θυμάμαι",
    "ύπνος", "νευρικό", "εξέλιξη", "αντίληψη", "σιωπή",
]

BUILTIN_TYPES = [
    "string", "float", "int", "bool", "timestamp", "duration",
    "currency", "SoulRef", "ToolRef",
]

TIERS = ["Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3"]

SNIPPET_TEMPLATES = {
    "world": 'world ${1:WorldName} {\n\tlaw ${2:LawName} = ${3:value}\n\theartbeat = ${4:5m}\n}',
    "soul": 'soul ${1:SoulName} {\n\tmind: ${2:model} @ ${3:Tier1}\n\tsenses: [${4:tool}]\n\n\tmemory {\n\t\t${5:field}: ${6:string} = ${7:""}\n\t}\n\n\tinstinct {\n\t\t${0}\n\t}\n\n\theal {\n\t\ton timeout => retry\n\t}\n}',
    "message": 'message ${1:MsgName} {\n\t${2:field}: ${3:string}\n}',
    "nervous_system": 'nervous_system {\n\t${1:Source} -> ${2:Target}\n}',
    "topology": 'topology {\n\t${1:server}: "${2:host}" {\n\t\tsouls: [${3:Soul}]\n\t\tport: ${4:9100}\n\t}\n}',
}

KEYWORD_DOCS: dict[str, str] = {
    "world": "Declares a world — the top-level container for laws, config, and souls.",
    "soul": "Declares a soul — an autonomous agent with mind, senses, memory, instinct, dna, and heal.",
    "message": "Declares a message type — typed data passed between souls via channels.",
    "memory": "Soul memory block — persistent state fields across cycles.",
    "instinct": "Soul instinct block — the behavioral logic executed each cycle.",
    "dna": "Soul DNA block — evolvable parameters with ranges for mutation.",
    "heal": "Soul heal block — error recovery strategies (retry, fallback, hibernate, etc.).",
    "senses": "Soul senses — list of tools the soul can invoke.",
    "mind": "Soul mind — LLM model and tier assignment (e.g. `mind: gpt-4o @ Tier2`).",
    "law": "World law — constraints enforced at compile-time and runtime.",
    "guard": "Guard statement — exits instinct if condition is false.",
    "speak": "Speak statement — sends a message to a channel. Use `@World::` for cross-world.",
    "listen": "Listen expression — receives a message from a soul's channel.",
    "sense": "Sense call — invokes a tool from the soul's senses list.",
    "remember": "Remember statement — updates soul memory fields.",
    "nervous_system": "Nervous system — defines the routing DAG between souls.",
    "evolution": "Evolution block — DNA mutation schedule, fitness function, strategies.",
    "perception": "Perception block — event-driven triggers (webhooks, cron, signals).",
    "topology": "Topology block — distributed deployment across multiple servers via SSH.",
    "let": "Variable binding — `let name = expression`.",
    "if": "Conditional — `if condition { body } else { body }`.",
    "for": "Loop — `for item in collection { body }`.",
    "self": "Reference to the current soul's name.",
    "constitutional": "Constitutional law level — priority enforcement (1-4).",
}


class NousLanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("nous-lsp", NOUS_VERSION)
        self._programs: dict[str, NousProgram] = {}
        self._source_cache: dict[str, str] = {}

    def get_program(self, uri: str) -> NousProgram | None:
        return self._programs.get(uri)

    def parse_and_validate(self, uri: str, source: str) -> list[types.Diagnostic]:
        self._source_cache[uri] = source
        diagnostics: list[types.Diagnostic] = []

        if not HAS_NOUS:
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=0, character=0),
                    end=types.Position(line=0, character=1),
                ),
                message="NOUS parser not found. Set nous.parserPath in settings.",
                severity=types.DiagnosticSeverity.Warning,
            ))
            return diagnostics

        try:
            program = parse_nous(source)
            self._programs[uri] = program
        except UnexpectedCharacters as e:
            line = max(0, (e.line or 1) - 1)
            col = max(0, (e.column or 1) - 1)
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=line, character=col),
                    end=types.Position(line=line, character=col + 1),
                ),
                message=f"Parse error: {e}",
                severity=types.DiagnosticSeverity.Error,
                source="nous-parser",
            ))
            return diagnostics
        except UnexpectedToken as e:
            line = max(0, (e.line or 1) - 1)
            col = max(0, (e.column or 1) - 1)
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=line, character=col),
                    end=types.Position(line=line, character=col + 1),
                ),
                message=f"Unexpected token: {e.token}. Expected: {', '.join(e.expected)}",
                severity=types.DiagnosticSeverity.Error,
                source="nous-parser",
            ))
            return diagnostics
        except Exception as e:
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=0, character=0),
                    end=types.Position(line=0, character=1),
                ),
                message=f"Parse error: {e}",
                severity=types.DiagnosticSeverity.Error,
                source="nous-parser",
            ))
            return diagnostics

        result = validate_program(program)
        for err in result.errors:
            line = self._find_location_line(source, err.location)
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=line, character=0),
                    end=types.Position(line=line, character=100),
                ),
                message=f"[{err.code}] {err.message}",
                severity=types.DiagnosticSeverity.Error,
                source="nous-validator",
            ))
        for warn in result.warnings:
            line = self._find_location_line(source, warn.location)
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=line, character=0),
                    end=types.Position(line=line, character=100),
                ),
                message=f"[{warn.code}] {warn.message}",
                severity=types.DiagnosticSeverity.Warning,
                source="nous-validator",
            ))
        return diagnostics

    def _find_location_line(self, source: str, location: str) -> int:
        if not location:
            return 0
        parts = location.split()
        if len(parts) >= 2:
            name = parts[1]
            for i, line in enumerate(source.splitlines()):
                if name in line:
                    return i
        return 0

    def get_completions(self, uri: str, position: types.Position) -> list[types.CompletionItem]:
        items: list[types.CompletionItem] = []
        source = self._source_cache.get(uri, "")
        lines = source.splitlines()
        if position.line >= len(lines):
            return items

        line = lines[position.line]
        prefix = line[:position.character].strip()

        for kw in KEYWORDS_EN:
            if kw.startswith(prefix) or not prefix:
                snippet = SNIPPET_TEMPLATES.get(kw)
                items.append(types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Keyword,
                    detail=KEYWORD_DOCS.get(kw, "NOUS keyword"),
                    insert_text=snippet if snippet else kw,
                    insert_text_format=types.InsertTextFormat.Snippet if snippet else types.InsertTextFormat.PlainText,
                ))

        for kw in KEYWORDS_GR:
            items.append(types.CompletionItem(
                label=kw,
                kind=types.CompletionItemKind.Keyword,
                detail="NOUS keyword (Greek)",
            ))

        for t in BUILTIN_TYPES:
            items.append(types.CompletionItem(
                label=t,
                kind=types.CompletionItemKind.TypeParameter,
                detail="NOUS type",
            ))

        for tier in TIERS:
            items.append(types.CompletionItem(
                label=tier,
                kind=types.CompletionItemKind.EnumMember,
                detail="LLM tier level",
            ))

        program = self._programs.get(uri)
        if program:
            for soul in program.souls:
                items.append(types.CompletionItem(
                    label=soul.name,
                    kind=types.CompletionItemKind.Class,
                    detail=f"Soul: {soul.mind.model if soul.mind else 'no mind'} @ {soul.mind.tier.value if soul.mind else '?'}",
                ))
            for msg in program.messages:
                fields = ", ".join(f"{f.name}: {f.type_expr}" for f in msg.fields)
                items.append(types.CompletionItem(
                    label=msg.name,
                    kind=types.CompletionItemKind.Struct,
                    detail=f"Message({fields})",
                ))

        return items

    def get_hover(self, uri: str, position: types.Position) -> str | None:
        source = self._source_cache.get(uri, "")
        lines = source.splitlines()
        if position.line >= len(lines):
            return None

        line = lines[position.line]
        word = self._word_at(line, position.character)
        if not word:
            return None

        if word in KEYWORD_DOCS:
            return f"**{word}** — {KEYWORD_DOCS[word]}"

        if word in BUILTIN_TYPES:
            return f"**{word}** — NOUS built-in type"

        if word in TIERS:
            tier_desc = {
                "Tier0A": "Cheapest — simple classification, routing",
                "Tier0B": "Budget — basic analysis",
                "Tier1": "Standard — general reasoning",
                "Tier2": "Advanced — complex analysis",
                "Tier3": "Premium — deep reasoning, creative",
            }
            return f"**{word}** — {tier_desc.get(word, 'LLM tier')}"

        program = self._programs.get(uri)
        if program:
            for soul in program.souls:
                if soul.name == word:
                    mind = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "no mind"
                    senses = ", ".join(soul.senses) if soul.senses else "none"
                    mem = len(soul.memory.fields) if soul.memory else 0
                    genes = len(soul.dna.genes) if soul.dna else 0
                    return f"**Soul: {soul.name}**\n\n- Mind: `{mind}`\n- Senses: `[{senses}]`\n- Memory: {mem} fields\n- DNA: {genes} genes"

            for msg in program.messages:
                if msg.name == word:
                    fields = "\n".join(f"- `{f.name}`: {f.type_expr}" for f in msg.fields)
                    return f"**Message: {msg.name}**\n\n{fields}"

            if program.world and program.world.name == word:
                laws = len(program.world.laws)
                hb = program.world.heartbeat or "default"
                return f"**World: {word}**\n\n- Laws: {laws}\n- Heartbeat: `{hb}`"

        return None

    def get_definitions(self, uri: str, position: types.Position) -> list[types.Location]:
        source = self._source_cache.get(uri, "")
        lines = source.splitlines()
        if position.line >= len(lines):
            return []

        word = self._word_at(lines[position.line], position.character)
        if not word:
            return []

        results: list[types.Location] = []
        for i, line in enumerate(lines):
            if re.match(rf'\b(soul|ψυχή)\s+{re.escape(word)}\b', line.strip()):
                results.append(types.Location(
                    uri=uri,
                    range=types.Range(
                        start=types.Position(line=i, character=0),
                        end=types.Position(line=i, character=len(line)),
                    ),
                ))
            elif re.match(rf'\b(message|μήνυμα)\s+{re.escape(word)}\b', line.strip()):
                results.append(types.Location(
                    uri=uri,
                    range=types.Range(
                        start=types.Position(line=i, character=0),
                        end=types.Position(line=i, character=len(line)),
                    ),
                ))
        return results

    def _word_at(self, line: str, col: int) -> str:
        if col > len(line):
            col = len(line)
        left = col
        while left > 0 and (line[left - 1].isalnum() or line[left - 1] in "_\u0370\u03FF"):
            left -= 1
        right = col
        while right < len(line) and (line[right].isalnum() or line[right] in "_\u0370\u03FF"):
            right += 1
        return line[left:right]


server = NousLanguageServer()


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: types.DidOpenTextDocumentParams) -> None:
    uri = params.text_document.uri
    source = params.text_document.text
    diagnostics = server.parse_and_validate(uri, source)
    server.publish_diagnostics(uri, diagnostics)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: types.DidSaveTextDocumentParams) -> None:
    uri = params.text_document.uri
    source = server._source_cache.get(uri)
    if source is None:
        return
    diagnostics = server.parse_and_validate(uri, source)
    server.publish_diagnostics(uri, diagnostics)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: types.DidChangeTextDocumentParams) -> None:
    uri = params.text_document.uri
    for change in params.content_changes:
        if hasattr(change, "text"):
            source = change.text
            diagnostics = server.parse_and_validate(uri, source)
            server.publish_diagnostics(uri, diagnostics)


@server.feature(types.TEXT_DOCUMENT_COMPLETION, types.CompletionOptions(trigger_characters=[".", ":", "@"]))
def completion(params: types.CompletionParams) -> types.CompletionList:
    items = server.get_completions(params.text_document.uri, params.position)
    return types.CompletionList(is_incomplete=False, items=items)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(params: types.HoverParams) -> types.Hover | None:
    text = server.get_hover(params.text_document.uri, params.position)
    if text is None:
        return None
    return types.Hover(
        contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=text),
    )


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(params: types.DefinitionParams) -> list[types.Location]:
    return server.get_definitions(params.text_document.uri, params.position)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    server.start_io()


if __name__ == "__main__":
    main()
