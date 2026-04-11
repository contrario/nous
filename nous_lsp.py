"""
NOUS Language Server — Νοῦς LSP
================================
Provides diagnostics, autocomplete, and hover for .nous files.
Requires: pygls, lark, pydantic
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

from lark import Lark, Token, UnexpectedCharacters, UnexpectedToken
from lark.exceptions import UnexpectedInput
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument
from lsprotocol import types as lsp

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MessageNode,
    DeployNode, TopologyNode,
)
from parser import NousTransformer
from validator import validate_program

log = logging.getLogger("nous-lsp")

GRAMMAR_PATH = Path(__file__).resolve().parent.parent / "nous.lark"
if not GRAMMAR_PATH.exists():
    GRAMMAR_PATH = Path(__file__).resolve().parent / "nous.lark"

NOUS_KEYWORDS: list[str] = [
    "world", "κόσμος", "soul", "ψυχή", "mind", "νους",
    "memory", "μνήμη", "instinct", "ένστικτο", "sense", "αίσθηση",
    "speak", "λέω", "listen", "ακούω", "remember", "θυμάμαι",
    "guard", "φύλακας", "heal", "θεραπεία", "dna", "DNA",
    "law", "νόμος", "message", "μήνυμα", "senses",
    "nervous_system", "νευρικό", "evolution", "εξέλιξη",
    "perception", "αντίληψη", "deploy", "topology", "nsp",
    "let", "for", "in", "if", "else", "on", "self",
    "sleep", "cycle", "per", "constitutional",
    "wake", "wake_all", "broadcast", "alert", "silence", "σιωπή",
    "retry", "lower", "raise", "hibernate", "fallback", "delegate", "then",
    "mutate", "strategy", "survive_if", "rollback_if",
    "schedule", "fitness", "heartbeat", "timezone",
    "true", "false",
]

BLOCK_SNIPPETS: dict[str, str] = {
    "world": 'world ${1:Name} {\n\tlaw ${2:CostCeiling} = \\$${3:0.10} per cycle\n\theartbeat = ${4:5m}\n}',
    "soul": 'soul ${1:Name} {\n\tmind: ${2:deepseek-r1} @ ${3:Tier1}\n\tsenses: [${4:tool}]\n\n\tmemory {\n\t\t${5:count}: int = 0\n\t}\n\n\tinstinct {\n\t\t$0\n\t}\n\n\theal {\n\t\ton timeout => retry(2, exponential)\n\t}\n}',
    "message": 'message ${1:Name} {\n\t${2:field}: ${3:string}\n}',
    "nervous_system": 'nervous_system {\n\t${1:A} -> ${2:B}\n}',
    "evolution": 'evolution {\n\tschedule: ${1:3}:${2:00} ${3:AM}\n\tfitness: ${4:langfuse(quality_score)}\n\tmutate ${5:Soul}.dna {\n\t\tstrategy: genetic(population: 3, generations: 2)\n\t\tsurvive_if: fitness > parent.fitness\n\t\trollback_if: any_law_violated\n\t}\n}',
    "perception": 'perception {\n\ton ${1:cron}("${2:*/5 * * * *}") => ${3:wake_all}\n}',
    "deploy": 'deploy ${1:production} {\n\treplicas: ${2:1}\n\tregion: "${3:eu-central-1}"\n}',
    "topology": 'topology {\n\t${1:primary}: "${2:0.0.0.0}" {\n\t\tsouls: ${3:Soul}\n\t}\n}',
}

HEAL_ACTIONS: list[str] = [
    "retry", "lower", "raise", "hibernate",
    "fallback", "delegate", "alert", "sleep",
]

HEAL_ERRORS: list[str] = [
    "timeout", "api_error", "hallucination",
    "rate_limit", "parse_error", "budget_exceeded",
]


class NousLanguageServer(LanguageServer):

    def __init__(self) -> None:
        super().__init__("nous-lsp", "v0.1.0")
        self._lark_parser: Optional[Lark] = None
        self._program_cache: dict[str, NousProgram] = {}

    def get_parser(self) -> Lark:
        if self._lark_parser is None:
            grammar = GRAMMAR_PATH.read_text(encoding="utf-8")
            self._lark_parser = Lark(grammar, parser="earley", start="start")
        return self._lark_parser

    def parse_document(self, uri: str, source: str) -> tuple[Optional[NousProgram], list[lsp.Diagnostic]]:
        diagnostics: list[lsp.Diagnostic] = []
        try:
            parser = self.get_parser()
            tree = parser.parse(source)
            transformer = NousTransformer()
            program = transformer.transform(tree)
            self._program_cache[uri] = program

            errors = validate_program(program)
            for err in errors:
                line = getattr(err, "line", 0) or 0
                diagnostics.append(lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=max(0, line - 1), character=0),
                        end=lsp.Position(line=max(0, line - 1), character=1000),
                    ),
                    message=str(err),
                    severity=lsp.DiagnosticSeverity.Warning
                    if getattr(err, "severity", "error") == "warning"
                    else lsp.DiagnosticSeverity.Error,
                    source="nous",
                ))
            return program, diagnostics
        except UnexpectedCharacters as e:
            line = max(0, (e.line or 1) - 1)
            col = max(0, (e.column or 1) - 1)
            allowed = ", ".join(sorted(e.allowed or set())[:5])
            msg = f"Unexpected character at column {col + 1}"
            if allowed:
                msg += f". Expected one of: {allowed}"
            diagnostics.append(lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=line, character=col),
                    end=lsp.Position(line=line, character=col + 1),
                ),
                message=msg,
                severity=lsp.DiagnosticSeverity.Error,
                source="nous",
            ))
            return None, diagnostics
        except UnexpectedToken as e:
            line = max(0, (e.line or 1) - 1)
            col = max(0, (e.column or 1) - 1)
            expected = ", ".join(sorted(str(x) for x in (e.expected or set()))[:5])
            msg = f"Unexpected token '{e.token}'"
            if expected:
                msg += f". Expected: {expected}"
            diagnostics.append(lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=line, character=col),
                    end=lsp.Position(line=line, character=col + len(str(e.token))),
                ),
                message=msg,
                severity=lsp.DiagnosticSeverity.Error,
                source="nous",
            ))
            return None, diagnostics
        except Exception as e:
            diagnostics.append(lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=0, character=0),
                    end=lsp.Position(line=0, character=1000),
                ),
                message=f"Parse error: {e}",
                severity=lsp.DiagnosticSeverity.Error,
                source="nous",
            ))
            return None, diagnostics

    def get_soul_names(self, uri: str) -> list[str]:
        prog = self._program_cache.get(uri)
        if not prog:
            return []
        return [s.name for s in prog.souls]

    def get_message_names(self, uri: str) -> list[str]:
        prog = self._program_cache.get(uri)
        if not prog:
            return []
        return [m.name for m in prog.messages]

    def get_sense_names(self, uri: str) -> list[str]:
        prog = self._program_cache.get(uri)
        if not prog:
            return []
        senses: set[str] = set()
        for soul in prog.souls:
            senses.update(soul.senses)
        return sorted(senses)


server = NousLanguageServer()


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    _, diagnostics = server.parse_document(doc.uri, doc.source)
    server.publish_diagnostics(doc.uri, diagnostics)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    _, diagnostics = server.parse_document(doc.uri, doc.source)
    server.publish_diagnostics(doc.uri, diagnostics)


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    _, diagnostics = server.parse_document(doc.uri, doc.source)
    server.publish_diagnostics(doc.uri, diagnostics)


@server.feature(lsp.TEXT_DOCUMENT_COMPLETION, lsp.CompletionOptions(trigger_characters=[".", ":", "@", " "]))
def completions(params: lsp.CompletionParams) -> lsp.CompletionList:
    doc = server.workspace.get_text_document(params.text_document.uri)
    uri = doc.uri
    line_text = ""
    lines = doc.source.splitlines()
    if 0 <= params.position.line < len(lines):
        line_text = lines[params.position.line][:params.position.character]

    items: list[lsp.CompletionItem] = []

    stripped = line_text.lstrip()
    if stripped.startswith("on "):
        for err in HEAL_ERRORS:
            items.append(lsp.CompletionItem(
                label=err,
                kind=lsp.CompletionItemKind.EnumMember,
                detail="heal error type",
            ))
        return lsp.CompletionList(is_incomplete=False, items=items)

    if "=>" in line_text:
        for act in HEAL_ACTIONS:
            items.append(lsp.CompletionItem(
                label=act,
                kind=lsp.CompletionItemKind.Function,
                detail="heal action",
            ))
        for soul in server.get_soul_names(uri):
            items.append(lsp.CompletionItem(
                label=f"wake {soul}",
                kind=lsp.CompletionItemKind.Event,
            ))
        items.append(lsp.CompletionItem(label="wake_all", kind=lsp.CompletionItemKind.Event))
        return lsp.CompletionList(is_incomplete=False, items=items)

    if "::" in line_text:
        for msg in server.get_message_names(uri):
            items.append(lsp.CompletionItem(
                label=msg,
                kind=lsp.CompletionItemKind.Struct,
                detail="message type",
            ))
        return lsp.CompletionList(is_incomplete=False, items=items)

    if "sense " in stripped or "αίσθηση " in stripped:
        for s in server.get_sense_names(uri):
            items.append(lsp.CompletionItem(
                label=s,
                kind=lsp.CompletionItemKind.Function,
                detail="tool/sense",
            ))
        return lsp.CompletionList(is_incomplete=False, items=items)

    if "@" in line_text:
        for tier in ["Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3"]:
            items.append(lsp.CompletionItem(
                label=tier,
                kind=lsp.CompletionItemKind.Constant,
                detail="LLM tier",
            ))
        return lsp.CompletionList(is_incomplete=False, items=items)

    if "->" in line_text:
        for soul in server.get_soul_names(uri):
            items.append(lsp.CompletionItem(
                label=soul,
                kind=lsp.CompletionItemKind.Class,
                detail="soul",
            ))
        return lsp.CompletionList(is_incomplete=False, items=items)

    if not stripped or stripped == line_text.strip():
        for kw, snippet in BLOCK_SNIPPETS.items():
            items.append(lsp.CompletionItem(
                label=kw,
                kind=lsp.CompletionItemKind.Snippet,
                detail=f"NOUS {kw} block",
                insert_text=snippet,
                insert_text_format=lsp.InsertTextFormat.Snippet,
            ))

    for kw in NOUS_KEYWORDS:
        items.append(lsp.CompletionItem(
            label=kw,
            kind=lsp.CompletionItemKind.Keyword,
            detail="keyword",
        ))

    for soul in server.get_soul_names(uri):
        items.append(lsp.CompletionItem(
            label=soul,
            kind=lsp.CompletionItemKind.Class,
            detail="soul",
        ))

    for msg in server.get_message_names(uri):
        items.append(lsp.CompletionItem(
            label=msg,
            kind=lsp.CompletionItemKind.Struct,
            detail="message type",
        ))

    return lsp.CompletionList(is_incomplete=False, items=items)


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(params: lsp.HoverParams) -> Optional[lsp.Hover]:
    doc = server.workspace.get_text_document(params.text_document.uri)
    lines = doc.source.splitlines()
    if params.position.line >= len(lines):
        return None

    line = lines[params.position.line]
    col = params.position.character

    word_match = re.search(r'[a-zA-Z_\u0370-\u03FF][a-zA-Z0-9_\u0370-\u03FF]*', line[max(0, col - 20):col + 20])
    if not word_match:
        return None
    word = word_match.group()

    hover_docs: dict[str, str] = {
        "world": "**world** — Top-level execution environment. Contains laws, heartbeat, config.",
        "κόσμος": "**κόσμος** — Top-level execution environment (Greek). Contains laws, heartbeat, config.",
        "soul": "**soul** — Agent definition. Contains mind, senses, memory, instinct, dna, heal.",
        "ψυχή": "**ψυχή** — Agent definition (Greek). Contains mind, senses, memory, instinct, dna, heal.",
        "mind": "**mind** — LLM backend assignment. Format: `mind: model-name @ TierN`",
        "sense": "**sense** — Tool invocation. Format: `sense tool_name(args)`",
        "speak": "**speak** — Emit a typed message to a channel. Format: `speak MessageType(fields)`",
        "listen": "**listen** — Receive a typed message. Format: `let x = listen Soul::MessageType`",
        "guard": "**guard** — Assert condition. If false, skip remaining instinct. Format: `guard expr`",
        "remember": "**remember** — Mutate soul memory. Format: `remember field = value`",
        "law": "**law** — Constitutional constraint enforced at compile-time. Cost, duration, or boolean.",
        "dna": "**dna** — Evolvable parameters with ranges. Format: `name: value ~ [min, max]`",
        "heal": "**heal** — Error recovery rules. Format: `on error_type => action`",
        "nervous_system": "**nervous_system** — DAG topology. Format: `Soul1 -> Soul2`",
        "evolution": "**evolution** — Self-mutation schedule and fitness. Mutates DNA via genetic algorithms.",
        "perception": "**perception** — External event triggers (cron, telegram, system_error).",
        "deploy": "**deploy** — Server deployment configuration (replicas, region, GPU, memory).",
        "topology": "**topology** — Multi-server soul distribution.",
    }

    if word in hover_docs:
        return lsp.Hover(contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=hover_docs[word],
        ))

    prog = server._program_cache.get(doc.uri)
    if prog:
        for soul in prog.souls:
            if soul.name == word:
                senses = ", ".join(soul.senses) or "none"
                mind = f"{soul.mind.model} @ {soul.mind.tier}" if soul.mind else "none"
                genes = len(soul.dna.genes) if soul.dna else 0
                return lsp.Hover(contents=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=f"**soul {word}**\n- mind: `{mind}`\n- senses: `{senses}`\n- DNA genes: {genes}",
                ))
        for msg in prog.messages:
            if msg.name == word:
                fields = ", ".join(f"{f.name}: {f.type_expr}" for f in msg.fields)
                return lsp.Hover(contents=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=f"**message {word}** {{ {fields} }}",
                ))

    return None


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    server.start_io()


if __name__ == "__main__":
    main()
