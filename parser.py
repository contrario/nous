"""
NOUS Parser v2.0 — LALR Lark → Living AST (Ψυχόδενδρο)
========================================================
LALR parser with global cache (~4ms cached parse).
Transforms the Lark CST into Pydantic V2 AST nodes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, Token, Tree

from ast_nodes import (
    ConsciousnessNode, MetabolismNode, SymbiosisNode, TelemetryNode, NoesisConfigNode, ImportNode, TestNode, TestAssertNode, TestSetupNode,
    NousProgram, WorldNode, LawNode, LawCost, LawCurrency, LawDuration,
    PolicyNode,
    LawConstitutional, LawBool, LawInt, SoulNode, MindNode,
    MemoryNode, FieldDeclNode, InstinctNode, DnaNode, GeneNode,
    HealNode, HealRuleNode, HealActionNode, HealStrategy,
    MessageNode, MessageFieldNode, NervousSystemNode, RouteNode,
    MatchRouteNode, MatchArmNode, FanInNode, FanOutNode, FeedbackNode,
    EvolutionNode, MutateBlockNode, MutateStrategyNode,
    PerceptionNode, PerceptionRuleNode, PerceptionTriggerNode,
    PerceptionActionNode, LetNode, RememberNode, SpeakNode,
    ListenNode, GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
    Tier, TopologyNode, ServerNode, MitosisNode, ImmuneSystemNode,
    DreamSystemNode, DreamMindNode, CustomSenseNode, EmotionsNode, ReplayConfigNode,
)

GRAMMAR_PATH = Path(__file__).parent / "nous.lark"

_PARSER_CACHE: dict[str, Lark] = {}


def _load_grammar() -> str:
    if GRAMMAR_PATH.exists():
        return GRAMMAR_PATH.read_text(encoding="utf-8")
    try:
        from grammar_data import get_grammar
        return get_grammar()
    except ImportError:
        raise FileNotFoundError(f"Grammar not found: {GRAMMAR_PATH} (and grammar_data.py missing)")


def _get_parser() -> Lark:
    key = str(GRAMMAR_PATH)
    if key not in _PARSER_CACHE:
        grammar = _load_grammar()
        _PARSER_CACHE[key] = Lark(grammar, parser="lalr", start="start")
    return _PARSER_CACHE[key]


class NousTransformer(Transformer):

    def _strip(self, items: list) -> list:
        return [i for i in items if not isinstance(i, Token)]

    # ── Primitives ──

    def INT(self, tok: Token) -> int:
        return int(tok)

    def FLOAT(self, tok: Token) -> float:
        return float(tok)

    def STRING(self, tok: Token) -> str:
        return str(tok)[1:-1]

    def BOOL(self, tok: Token) -> bool:
        return str(tok) == "true"

    def NAME(self, tok: Token) -> str:
        return str(tok)

    def TIER(self, tok: Token) -> str:
        return str(tok)

    def COMP_OP(self, tok: Token) -> str:
        return str(tok)

    def DURATION_VAL(self, tok: Token) -> str:
        return str(tok)

    def ADD_OP(self, tok: Token) -> str:
        return str(tok)

    def MUL_OP(self, tok: Token) -> str:
        return str(tok)

    # ── Types ──

    def named_type(self, items: list) -> str:
        return str(items[0])

    def list_type(self, items: list) -> str:
        return f"[{items[0]}]"

    def optional_type(self, items: list) -> str:
        return f"{items[0]}?"

    def map_type(self, items: list) -> str:
        return f"{{{items[0]}: {items[1]}}}"

    # ── Literals ──

    def int_lit(self, items: list) -> Any:
        return items[0]

    def float_lit(self, items: list) -> Any:
        return items[0]

    def string_lit(self, items: list) -> Any:
        return f'"{items[0]}"'  

    def bool_lit(self, items: list) -> Any:
        return items[0]

    def currency_usd(self, items: list) -> dict:
        return {"currency": "USD", "amount": float(items[0])}

    def currency_eur(self, items: list) -> dict:
        return {"currency": "EUR", "amount": float(items[0])}

    def currency_lit(self, items: list) -> Any:
        return items[0]

    def duration_lit(self, items: list) -> str:
        return str(items[0])

    def time_hm(self, items: list) -> str:
        return f"{items[0]}:{items[1]:02d} {items[2]}"

    def now_lit(self, _items: list) -> str:
        return "now()"

    def self_ref(self, _items: list) -> str:
        return "self"

    def name_ref(self, items: list) -> str:
        return items[0]

    def list_lit(self, items: list) -> list:
        return items[0] if items else []

    def map_lit(self, items: list) -> dict:
        return items[0] if items else {}

    def expr_list(self, items: list) -> list:
        return list(items)

    # ── Expressions ──

    def world_ref(self, items: list) -> dict:
        return {"kind": "world_ref", "path": items[0]}

    def dotted_name(self, items: list) -> str:
        return ".".join(str(i) for i in items)

    def soul_field_ref(self, items: list) -> dict:
        return {"kind": "soul_field", "soul": items[0], "field": items[1]}

    def attr_access(self, items: list) -> dict:
        return {"kind": "attr", "obj": items[0], "attr": items[1]}

    def method_call(self, items: list) -> dict:
        obj, method = items[0], items[1]
        args = items[2] if len(items) > 2 else {}
        return {"kind": "method_call", "obj": obj, "method": method, "args": args}

    def func_call(self, items: list) -> dict:
        return {"kind": "func_call", "func": items[0], "args": items[1] if len(items) > 1 else {}}

    def not_expr(self, items: list) -> dict:
        return {"kind": "not", "operand": items[0]}

    def or_expr(self, items: list) -> Any:
        if len(items) == 1:
            return items[0]
        return {"kind": "binop", "op": "||", "left": items[0], "right": items[1]}

    def and_expr(self, items: list) -> Any:
        if len(items) == 1:
            return items[0]
        return {"kind": "binop", "op": "&&", "left": items[0], "right": items[1]}

    def compare_expr(self, items: list) -> Any:
        if len(items) == 1:
            return items[0]
        return {"kind": "binop", "op": items[1], "left": items[0], "right": items[2]}

    def add_expr(self, items: list) -> Any:
        if len(items) == 1:
            return items[0]
        result = items[0]
        for i in range(1, len(items), 2):
            op = items[i] if i < len(items) else "+"
            right = items[i + 1] if i + 1 < len(items) else result
            result = {"kind": "binop", "op": op, "left": result, "right": right}
        return result

    def mul_expr(self, items: list) -> Any:
        if len(items) == 1:
            return items[0]
        result = items[0]
        for i in range(1, len(items), 2):
            op = items[i] if i < len(items) else "*"
            right = items[i + 1] if i + 1 < len(items) else result
            result = {"kind": "binop", "op": op, "left": result, "right": right}
        return result

    def inline_if(self, items: list) -> dict:
        return {"kind": "inline_if", "condition": items[0], "then": items[1], "else": items[2]}

    def arg_list(self, items: list) -> dict:
        result: dict[str, Any] = {}
        for item in items:
            if isinstance(item, dict) and "arg_name" in item:
                result[item["arg_name"]] = item["arg_value"]
            elif isinstance(item, dict) and "positional" in item:
                result[f"_pos_{len(result)}"] = item["positional"]
            else:
                result[f"_pos_{len(result)}"] = item
        return result

    def named_arg(self, items: list) -> dict:
        return {"arg_name": items[0], "arg_value": items[1]}

    def positional_arg(self, items: list) -> dict:
        return {"positional": items[0]}

    def kv_list(self, items: list) -> dict:
        result: dict[str, Any] = {}
        for item in items:
            if isinstance(item, dict) and "_kv" in item:
                result[item["_kv"][0]] = item["_kv"][1]
        return result

    def kv_pair(self, items: list) -> dict:
        return {"_kv": (items[0], items[1])}

    # ── Import ──

    def import_file(self, items: list) -> ImportNode:
        s = self._strip(items)
        return ImportNode(path=s[0])

    def import_package(self, items: list) -> ImportNode:
        s = self._strip(items)
        return ImportNode(package=s[0])

    # ── Test ──

    def test_block(self, items: list) -> TestNode:
        s = self._strip(items)
        name = s[0]
        stmts = s[1:]
        asserts = [i for i in stmts if isinstance(i, TestAssertNode)]
        setups = [i for i in stmts if isinstance(i, TestSetupNode)]
        return TestNode(name=name, asserts=asserts, setups=setups)

    def test_assert(self, items: list) -> TestAssertNode:
        return TestAssertNode(condition=items[0])

    def test_setup(self, items: list) -> TestSetupNode:
        return TestSetupNode(statements=list(items))

    def test_stmt(self, items: list) -> Any:
        return items[0]

    # ── Noesis ──

    def noesis_decl(self, items: list) -> NoesisConfigNode:
        s = self._strip(items)
        config = NoesisConfigNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(config, k):
                        setattr(config, k, v)
        return config

    def noesis_lattice(self, items: list) -> dict:
        return {"lattice_path": str(items[0])}

    def noesis_threshold(self, items: list) -> dict:
        return {"oracle_threshold": float(items[0])}

    def noesis_auto_learn(self, items: list) -> dict:
        return {"auto_learn": items[0] if isinstance(items[0], bool) else str(items[0]).lower() in ("true", "1", "yes")}

    def noesis_auto_evolve(self, items: list) -> dict:
        return {"auto_evolve": items[0] if isinstance(items[0], bool) else str(items[0]).lower() in ("true", "1", "yes")}

    def noesis_gap_tracking(self, items: list) -> dict:
        return {"gap_tracking": items[0] if isinstance(items[0], bool) else str(items[0]).lower() in ("true", "1", "yes")}

    def noesis_body(self, items: list) -> Any:
        return items[0]

    # ── Resonate ──

    def resonate_bind(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value={"kind": "resonate", "query": s[1]})

    def resonate_bind_guarded(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value={
            "kind": "resonate", "query": s[1],
            "guard_field": s[2], "guard_threshold": float(s[3]),
        })

    def resonate_bare(self, items: list) -> dict:
        s = self._strip(items)
        return {"kind": "resonate", "query": s[0]}
    def resonate_bind_dynamic(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value={"kind": "resonate", "query": s[1], "is_dynamic": True})
    def resonate_bind_dynamic_guarded(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value={
            "kind": "resonate", "query": s[1], "is_dynamic": True,
            "guard_field": s[2], "guard_threshold": float(s[3]),
        })
    def resonate_bare_dynamic(self, items: list) -> dict:
        s = self._strip(items)
        return {"kind": "resonate", "query": s[0], "is_dynamic": True}
    def resonate_stmt(self, items: list) -> Any:
        return items[0]

    # ── Law ──

    def law_cost(self, items: list) -> LawCost:
        s = self._strip(items)
        c = s[0]
        return LawCost(amount=c["amount"], currency=c.get("currency", "USD"))

    def law_currency(self, items: list) -> LawCurrency:
        s = self._strip(items)
        c = s[0]
        return LawCurrency(amount=c["amount"], currency=c.get("currency", "USD"))

    def law_constitutional(self, items: list) -> LawConstitutional:
        s = self._strip(items)
        return LawConstitutional(count=s[0])

    def law_duration(self, items: list) -> LawDuration:
        s = self._strip(items)
        d = s[0]
        import re
        m = re.match(r"(\d+)(ms|s|m|h|d)", d)
        if m:
            return LawDuration(value=int(m.group(1)), unit=m.group(2))
        return LawDuration(value=0, unit="s")

    def law_bool(self, items: list) -> LawBool:
        s = self._strip(items)
        return LawBool(value=s[0])

    def law_int(self, items: list) -> LawInt:
        s = self._strip(items)
        return LawInt(value=s[0])

    def law_decl(self, items: list) -> LawNode:
        s = self._strip(items)
        return LawNode(name=s[0], expr=s[1])

    def law_expr(self, items: list) -> Any:
        return items[0]

    # ── Consciousness ──
    def consciousness_goals(self, items: list) -> dict:
        s = self._strip(items)
        names = s[0] if s and isinstance(s[0], list) else s
        return {"goals": [str(n) for n in names]}

    def consciousness_reflect_every(self, items: list) -> dict:
        return {"reflect_every": int(items[0])}

    def consciousness_self_model(self, items: list) -> dict:
        return {"self_model": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def consciousness_goal_threshold(self, items: list) -> dict:
        return {"goal_threshold": float(items[0])}

    def consciousness_introspection_depth(self, items: list) -> dict:
        return {"introspection_depth": int(items[0])}

    def consciousness_field(self, items: list):
        return items[0]

    def consciousness_block(self, items: list) -> 'ConsciousnessNode':
        s = self._strip(items)
        node = ConsciousnessNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return node

    # ── Metabolism ──
    def metabolism_max_energy(self, items: list) -> dict:
        return {"max_energy": int(items[0])}

    def metabolism_energy_per_cycle(self, items: list) -> dict:
        return {"energy_per_cycle": float(items[0])}

    def metabolism_recovery_rate(self, items: list) -> dict:
        return {"recovery_rate": float(items[0])}

    def metabolism_fatigue_tier(self, items: list) -> dict:
        return {"fatigue_tier": str(items[0])}

    def metabolism_hibernate_threshold(self, items: list) -> dict:
        return {"hibernate_threshold": int(items[0])}

    def metabolism_recovery_idle(self, items: list) -> dict:
        return {"recovery_idle_sec": int(items[0])}

    def metabolism_field(self, items: list):
        return items[0]

    def metabolism_block(self, items: list) -> 'MetabolismNode':
        s = self._strip(items)
        node = MetabolismNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return node

    # ── Symbiosis ──
    def symbiosis_bond(self, items: list) -> dict:
        s = self._strip(items)
        names = s[0] if s and isinstance(s[0], list) else s
        return {"bond_with": [str(n) for n in names]}

    def symbiosis_shared_memory(self, items: list) -> dict:
        s = self._strip(items)
        names = s[0] if s and isinstance(s[0], list) else s
        return {"shared_memory": [str(n) for n in names]}

    def symbiosis_sync_interval(self, items: list) -> dict:
        return {"sync_interval": str(items[0])}

    def symbiosis_evolve_together(self, items: list) -> dict:
        return {"evolve_together": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def symbiosis_field(self, items: list):
        return items[0]

    def symbiosis_block(self, items: list) -> SymbiosisNode:
        s = self._strip(items)
        node = SymbiosisNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return node

    # ── Telemetry ──
    def telemetry_enabled(self, items: list) -> dict:
        return {"enabled": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def telemetry_exporter(self, items: list) -> dict:
        return {"exporter": str(items[0])}

    def telemetry_endpoint(self, items: list) -> dict:
        return {"endpoint": str(items[0])}

    def telemetry_sample_rate(self, items: list) -> dict:
        return {"sample_rate": float(items[0])}

    def telemetry_trace_senses(self, items: list) -> dict:
        return {"trace_senses": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def telemetry_trace_llm(self, items: list) -> dict:
        return {"trace_llm": items[0] if isinstance(items[0], bool) else str(items[0]).lower() == "true"}

    def telemetry_buffer_size(self, items: list) -> dict:
        return {"buffer_size": int(items[0])}

    def telemetry_field(self, items: list):
        return items[0]

    def telemetry_block(self, items: list) -> dict:
        s = self._strip(items)
        node = TelemetryNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return {"telemetry": node}

    # ── World ──

    def heartbeat_decl(self, items: list) -> dict:
        return {"heartbeat": items[0]}

    def timezone_decl(self, items: list) -> dict:
        return {"timezone": items[0]}

    def config_assign(self, items: list) -> dict:
        return {"config": (items[0], items[1])}

    def world_body(self, items: list) -> Any:
        return items[0]

    def world_decl(self, items: list) -> WorldNode:
        s = self._strip(items)
        name = s[0]
        node = WorldNode(name=name)
        for item in s[1:]:
            if isinstance(item, LawNode):
                node.laws.append(item)
            elif isinstance(item, PolicyNode):
                node.policies.append(item)
            elif isinstance(item, ReplayConfigNode):
                node.replay = item
            elif isinstance(item, dict):
                if "heartbeat" in item:
                    node.heartbeat = item["heartbeat"]
                elif "timezone" in item:
                    node.timezone = item["timezone"]
                elif "telemetry" in item:
                    node.telemetry = item["telemetry"]
                elif "config" in item:
                    k, v = item["config"]
                    node.config[k] = v
        return node

    # ── Mind ──

    def model_name(self, items: list) -> str:
        return "-".join(str(i) for i in items)

    def model_part(self, items: list) -> str:
        return str(items[0])

    def model_int_name(self, items: list) -> str:
        return f"{items[0]}{items[1]}"

    def mind_decl(self, items: list) -> MindNode:
        return MindNode(model=items[0], tier=Tier(items[1]))

    # ── Senses ──

    def name_list(self, items: list) -> list[str]:
        return [str(i) for i in items]

    def senses_decl(self, items: list) -> list[str]:
        return items[0]

    # ── Memory ──

    def field_decl(self, items: list) -> FieldDeclNode:
        return FieldDeclNode(
            name=items[0],
            type_expr=items[1],
            default=items[2] if len(items) > 2 else None,
        )

    def memory_block(self, items: list) -> MemoryNode:
        s = self._strip(items)
        fields = [i for i in s if isinstance(i, FieldDeclNode)]
        return MemoryNode(fields=fields)

    # ── Statements ──

    def let_stmt(self, items: list) -> LetNode:
        return LetNode(name=items[0], value=items[1])

    def remember_assign(self, items: list) -> RememberNode:
        s = self._strip(items)
        return RememberNode(name=s[0], op="=", value=s[1])

    def remember_accum(self, items: list) -> RememberNode:
        s = self._strip(items)
        return RememberNode(name=s[0], op="+=", value=s[1])

    def speak_local(self, items: list) -> SpeakNode:
        s = self._strip(items)
        name = s[0]
        args = s[1] if len(s) > 1 else {}
        return SpeakNode(message_type=name, args=args)

    def speak_cross(self, items: list) -> SpeakNode:
        s = self._strip(items)
        world = s[0]
        msg_type = s[1]
        args = s[2] if len(s) > 2 else {}
        return SpeakNode(target_world=world, message_type=msg_type, args=args)

    def speak_stmt(self, items: list) -> Any:
        return items[0]

    def listen_local(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value={"kind": "listen", "soul": s[1], "type": s[2]})

    def listen_cross(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value={"kind": "listen", "world": s[1], "soul": s[2], "type": s[3]})

    def guard_stmt(self, items: list) -> GuardNode:
        s = self._strip(items)
        return GuardNode(condition=s[0])

    def sense_bare(self, items: list) -> SenseCallNode:
        s = self._strip(items)
        tool = s[0]
        args = s[1] if len(s) > 1 else {}
        return SenseCallNode(tool_name=tool, args=args if isinstance(args, dict) else {})

    def sense_bind(self, items: list) -> LetNode:
        s = self._strip(items)
        bind_name = s[0]
        tool = s[1]
        args = s[2] if len(s) > 2 else {}
        return LetNode(name=bind_name, value={"kind": "sense_call", "tool": tool, "args": args if isinstance(args, dict) else {}})

    def sleep_stmt(self, items: list) -> SleepNode:
        s = self._strip(items)
        dur = str(s[0])
        import re
        m = re.match(r"(\d+)", dur)
        return SleepNode(cycles=int(m.group(1)) if m else 1)

    def if_stmt(self, items: list) -> IfNode:
        cond = items[0]
        then_body: list[Any] = []
        else_body: list[Any] = []
        collecting_else = False
        for item in items[1:]:
            if isinstance(item, Token) and str(item) == "else":
                collecting_else = True
                continue
            if isinstance(item, Token):
                continue
            if collecting_else:
                else_body.append(item)
            else:
                then_body.append(item)
        return IfNode(condition=cond, then_body=then_body, else_body=else_body)

    def for_stmt(self, items: list) -> ForNode:
        s = self._strip(items)
        return ForNode(var_name=s[0], iterable=s[1], body=list(s[2:]))

    def statement(self, items: list) -> Any:
        return items[0]

    # ── Instinct ──

    def instinct_block(self, items: list) -> InstinctNode:
        s = self._strip(items)
        return InstinctNode(statements=s)

    # ── DNA ──

    def gene_decl(self, items: list) -> GeneNode:
        name = items[0]
        value = items[1]
        range_vals = list(items[2:])
        return GeneNode(name=name, value=value, range=range_vals)

    def dna_block(self, items: list) -> DnaNode:
        s = self._strip(items)
        genes = [i for i in s if isinstance(i, GeneNode)]
        return DnaNode(genes=genes)

    # ── Heal ──

    def heal_retry(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.RETRY, params={"max": items[0], "backoff": items[1]})

    def heal_retry_simple(self, _items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.RETRY, params={"max": 1})

    def heal_lower(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.LOWER, params={"param": items[0], "delta": items[1]})

    def heal_raise(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.RAISE, params={"param": items[0], "delta": items[1]})

    def heal_hibernate(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.HIBERNATE, params={"until": items[0]})

    def heal_fallback(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.FALLBACK, params={"target": items[0]})

    def heal_delegate(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.DELEGATE, params={"soul": items[0]})

    def heal_alert(self, items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.ALERT, params={"channel": items[0]})

    def heal_sleep(self, items: list) -> HealActionNode:
        dur = str(items[0])
        import re
        m = re.match(r"(\d+)", dur)
        return HealActionNode(strategy=HealStrategy.SLEEP, params={"cycles": int(m.group(1)) if m else 1})

    def heal_action(self, items: list) -> Any:
        return items[0]

    def heal_rule(self, items: list) -> HealRuleNode:
        error_type = items[0]
        actions = [i for i in items[1:] if isinstance(i, HealActionNode)]
        return HealRuleNode(error_type=error_type, actions=actions)

    def heal_block(self, items: list) -> HealNode:
        s = self._strip(items)
        rules = [i for i in s if isinstance(i, HealRuleNode)]
        return HealNode(rules=rules)




    # ── Dream System ──

    def dream_enabled(self, items: list) -> dict:
        val = items[0]
        return {"enabled": val if isinstance(val, bool) else str(val).lower() == "true"}

    def dream_idle_sec(self, items: list) -> dict:
        return {"trigger_idle_sec": int(items[0])}

    def dream_mind(self, items: list) -> dict:
        return {"dream_mind": DreamMindNode(model=items[0], tier=Tier(items[1]))}

    def dream_max_cache(self, items: list) -> dict:
        return {"max_cache": int(items[0])}

    def dream_depth(self, items: list) -> dict:
        return {"speculation_depth": int(items[0])}

    def dream_field(self, items: list) -> Any:
        return items[0]

    def dream_system_block(self, items: list) -> "DreamSystemNode":
        s = self._strip(items)
        node = DreamSystemNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return node

    # ── Immune System ──

    def immune_adaptive(self, items: list) -> dict:
        val = items[0]
        return {"adaptive_recovery": val if isinstance(val, bool) else str(val).lower() == "true"}

    def immune_share(self, items: list) -> dict:
        val = items[0]
        return {"share_with_clones": val if isinstance(val, bool) else str(val).lower() == "true"}

    def immune_lifespan(self, items: list) -> dict:
        return {"antibody_lifespan": str(items[0])}

    def immune_field(self, items: list) -> Any:
        return items[0]

    def immune_system_block(self, items: list) -> "ImmuneSystemNode":
        s = self._strip(items)
        node = ImmuneSystemNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return node

    # ── Mitosis ──

    def mitosis_trigger(self, items: list) -> dict:
        return {"trigger": items[0]}

    def mitosis_max_clones(self, items: list) -> dict:
        return {"max_clones": int(items[0])}

    def mitosis_cooldown(self, items: list) -> dict:
        return {"cooldown": str(items[0])}

    def mitosis_clone_tier(self, items: list) -> dict:
        return {"clone_tier": str(items[0])}

    def mitosis_verify(self, items: list) -> dict:
        val = items[0]
        return {"verify": val if isinstance(val, bool) else str(val).lower() == "true"}

    def mitosis_retire_trigger(self, items: list) -> dict:
        return {"retire_trigger": items[0]}

    def mitosis_retire_cooldown(self, items: list) -> dict:
        return {"retire_cooldown": str(items[0])}

    def mitosis_min_clones(self, items: list) -> dict:
        return {"min_clones": int(items[0])}

    def mitosis_field(self, items: list) -> Any:
        return items[0]

    def mitosis_block(self, items: list) -> MitosisNode:
        s = self._strip(items)
        node = MitosisNode()
        for item in s:
            if isinstance(item, dict):
                for k, v in item.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
        return node

    # ── Soul ──

    def soul_body(self, items: list) -> Any:
        return items[0]

    def soul_decl(self, items: list) -> SoulNode:
        s = self._strip(items)
        name = s[0]
        node = SoulNode(name=name)
        for item in s[1:]:
            if isinstance(item, MindNode):
                node.mind = item
            elif isinstance(item, list) and item and isinstance(item[0], str):
                node.senses = item
            elif isinstance(item, MemoryNode):
                node.memory = item
            elif isinstance(item, InstinctNode):
                node.instinct = item
            elif isinstance(item, DnaNode):
                node.dna = item
            elif isinstance(item, HealNode):
                node.heal = item
            elif isinstance(item, MitosisNode):
                node.mitosis = item
            elif isinstance(item, ImmuneSystemNode):
                node.immune_system = item
            elif isinstance(item, DreamSystemNode):
                node.dream_system = item
            elif isinstance(item, SymbiosisNode):
                node.symbiosis = item
            elif isinstance(item, MetabolismNode):
                node.metabolism = item
            elif isinstance(item, ConsciousnessNode):
                node.consciousness = item
            elif isinstance(item, EmotionsNode):
                node.emotions = item
        return node

    # ── Message ──

    def message_field(self, items: list) -> MessageFieldNode:
        name = items[0]
        type_expr = items[1]
        default = items[2] if len(items) > 2 else None
        return MessageFieldNode(name=name, type_expr=type_expr, default=default)

    def message_decl(self, items: list) -> MessageNode:
        s = self._strip(items)
        name = s[0]
        fields = [i for i in s[1:] if isinstance(i, MessageFieldNode)]
        return MessageNode(name=name, fields=fields)

    # ── Nervous System ──

    def route_linear(self, items: list) -> RouteNode:
        return RouteNode(source=items[0], target=items[1])

    def route_chain3(self, items: list) -> list[RouteNode]:
        return [RouteNode(source=items[0], target=items[1]), RouteNode(source=items[1], target=items[2])]

    def match_arm_soul(self, items: list) -> MatchArmNode:
        return MatchArmNode(condition=items[0], target=items[1])

    def match_arm_silence(self, _items: list) -> MatchArmNode:
        return MatchArmNode(condition="_", is_silence=True)

    def match_route(self, items: list) -> MatchRouteNode:
        source = items[0]
        arms = [i for i in items[1:] if isinstance(i, MatchArmNode)]
        return MatchRouteNode(source=source, arms=arms)

    def fanin_stmt(self, items: list) -> FanInNode:
        return FanInNode(sources=items[0], target=items[1])

    def fanout_stmt(self, items: list) -> FanOutNode:
        return FanOutNode(source=items[0], targets=items[1])

    def feedback_stmt(self, items: list) -> FeedbackNode:
        return FeedbackNode(source_soul=items[0], source_field=items[1], target_soul=items[2], target_field=items[3])

    def nerve_stmt(self, items: list) -> Any:
        return items[0]

    def nervous_system_decl(self, items: list) -> NervousSystemNode:
        s = self._strip(items)
        routes: list[Any] = []
        for item in s:
            if isinstance(item, list):
                routes.extend(item)
            elif item is not None:
                routes.append(item)
        return NervousSystemNode(routes=routes)

    # ── Evolution ──

    def mutate_strategy(self, items: list) -> MutateStrategyNode:
        return MutateStrategyNode(name=items[0], params=items[1] if len(items) > 1 and isinstance(items[1], dict) else {})

    def mutate_survive(self, items: list) -> dict:
        return {"survive": items[0]}

    def mutate_rollback(self, items: list) -> dict:
        return {"rollback": items[0]}

    def mutate_body(self, items: list) -> Any:
        return items[0]

    def mutate_block(self, items: list) -> MutateBlockNode:
        target = items[0]
        node = MutateBlockNode(target=target)
        for item in items[1:]:
            if isinstance(item, MutateStrategyNode):
                node.strategy = item
            elif isinstance(item, dict):
                if "survive" in item:
                    node.survive_condition = item["survive"]
                elif "rollback" in item:
                    node.rollback_condition = item["rollback"]
        return node

    def evolution_body(self, items: list) -> Any:
        return items[0]

    def evolution_decl(self, items: list) -> EvolutionNode:
        s = self._strip(items)
        node = EvolutionNode()
        for item in s:
            if isinstance(item, str) and ":" in str(item):
                node.schedule = item
            elif isinstance(item, MutateBlockNode):
                node.mutations.append(item)
            elif isinstance(item, dict) and not isinstance(item, MutateBlockNode):
                node.fitness = item
            elif not isinstance(item, Token):
                if node.fitness is None:
                    node.fitness = item
        return node

    # ── Perception ──

    def trigger_named(self, items: list) -> PerceptionTriggerNode:
        return PerceptionTriggerNode(kind="named", name=items[0], args=[items[1]])

    def trigger_named_expr(self, items: list) -> PerceptionTriggerNode:
        return PerceptionTriggerNode(kind="named", name=items[0], args=[items[1], items[2]])

    def trigger_simple(self, items: list) -> PerceptionTriggerNode:
        return PerceptionTriggerNode(kind="simple", name=items[0])

    def action_wake(self, items: list) -> PerceptionActionNode:
        return PerceptionActionNode(kind="wake", target=items[0])

    def action_wake_all(self, _items: list) -> PerceptionActionNode:
        return PerceptionActionNode(kind="wake_all")

    def action_broadcast(self, items: list) -> PerceptionActionNode:
        return PerceptionActionNode(kind="broadcast", target=items[0])

    def action_alert(self, items: list) -> PerceptionActionNode:
        return PerceptionActionNode(kind="alert", target=items[0])

    def perception_trigger(self, items: list) -> Any:
        return items[0]

    def perception_action(self, items: list) -> Any:
        return items[0]

    def perception_rule(self, items: list) -> PerceptionRuleNode:
        return PerceptionRuleNode(trigger=items[0], action=items[1])

    def perception_decl(self, items: list) -> PerceptionNode:
        s = self._strip(items)
        rules = [i for i in s if isinstance(i, PerceptionRuleNode)]
        return PerceptionNode(rules=rules)

    # ── Deploy / Topology (passthrough) ──

    def deploy_body(self, items: list) -> dict:
        return {"deploy_field": (items[0], items[1])}

    def deploy_decl(self, items: list) -> dict:
        return {"kind": "deploy", "name": items[0], "fields": items[1:]}

    def topo_body(self, items: list) -> dict:
        return {items[0]: items[1]}

    def topo_server(self, items: list) -> "ServerNode":
        s = self._strip(items)
        name = s[0]
        host_str = s[1]
        host = host_str
        port = 9100
        if ":" in host_str:
            parts = host_str.rsplit(":", 1)
            try:
                port = int(parts[1])
                host = parts[0]
            except ValueError:
                pass
        souls: list[str] = []
        config: dict = {}
        for item in s[2:]:
            if isinstance(item, dict):
                if "souls" in item:
                    val = item["souls"]
                    if isinstance(val, list):
                        souls = [str(v) for v in val]
                else:
                    config.update(item)
        return ServerNode(name=name, host=host, port=port, souls=souls, config=config)

    def topology_decl(self, items: list) -> "TopologyNode":
        s = self._strip(items)
        servers = [i for i in s if isinstance(i, ServerNode)]
        return TopologyNode(servers=servers)

    def nsp_field(self, items: list) -> dict:
        return {"name": items[0], "type": items[1]}

    def nsp_decl(self, items: list) -> dict:
        return {"kind": "nsp", "fields": items}

    # ── Top-Level ──


    def sense_description(self, items: list) -> dict:
        return {"description": items[0]}

    def sense_http_get(self, items: list) -> dict:
        return {"http_get": items[0]}

    def sense_http_post(self, items: list) -> dict:
        return {"http_post": items[0]}

    def sense_shell(self, items: list) -> dict:
        return {"shell": items[0]}

    def sense_method(self, items: list) -> dict:
        return {"method": items[0]}

    def sense_timeout(self, items: list) -> dict:
        return {"timeout": int(items[0])}

    def sense_headers(self, items: list) -> dict:
        raw = items[0] if items else {}
        clean: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, str) and len(v) >= 2 and v.startswith('"') and v.endswith('"'):
                clean[k] = v[1:-1]
            else:
                clean[k] = v
        return {"headers": clean}

    def sense_body_template(self, items: list) -> dict:
        return {"body_template": items[0]}

    def sense_returns(self, items: list) -> dict:
        return {"returns": str(items[0])}

    def sense_cache_ttl(self, items: list) -> dict:
        return {"cache_ttl": int(items[0])}

    def sense_decl(self, items: list) -> CustomSenseNode:
        stripped = self._strip(items)
        name = str(stripped[0])
        fields: dict[str, Any] = {}
        for part in stripped[1:]:
            if isinstance(part, dict):
                fields.update(part)
        return CustomSenseNode(name=name, **fields)


    def emotions_enabled(self, items: list) -> dict:
        return {"enabled": bool(items[0])}

    def emotions_valence(self, items: list) -> dict:
        return {"valence": float(items[0])}

    def emotions_arousal(self, items: list) -> dict:
        return {"arousal": float(items[0])}

    def emotions_confidence(self, items: list) -> dict:
        return {"confidence": float(items[0])}

    def emotions_fatigue(self, items: list) -> dict:
        return {"fatigue": float(items[0])}

    def emotions_decay_rate(self, items: list) -> dict:
        return {"decay_rate": float(items[0])}

    def emotions_fatigue_per_cycle(self, items: list) -> dict:
        return {"fatigue_per_cycle": float(items[0])}

    def emotions_block(self, items: list) -> EmotionsNode:
        stripped = self._strip(items)
        fields: dict[str, Any] = {}
        for part in stripped:
            if isinstance(part, dict):
                fields.update(part)
        return EmotionsNode(**fields)


    def replay_enabled(self, items: list) -> dict:
        return {"enabled": bool(items[0])}

    def replay_mode(self, items: list) -> dict:
        return {"mode": str(items[0])}

    def replay_store_type(self, items: list) -> dict:
        return {"store_type": str(items[0])}

    def replay_path(self, items: list) -> dict:
        return {"path": str(items[0])}

    def replay_fsync(self, items: list) -> dict:
        return {"fsync": str(items[0])}

    def replay_seed_base(self, items: list) -> dict:
        return {"seed_base": int(items[0])}

    def replay_capture(self, items: list) -> dict:
        names = items[0] if items and isinstance(items[0], list) else []
        return {"capture": [str(n) for n in names]}

    def replay_block(self, items: list) -> ReplayConfigNode:
        stripped = self._strip(items)
        fields: dict[str, Any] = {}
        for part in stripped:
            if isinstance(part, dict):
                fields.update(part)
        return ReplayConfigNode(**fields)

    def top_level(self, items: list) -> Any:
        return items[0]

    def start(self, items: list) -> NousProgram:
        program = NousProgram()
        for item in items:
            if isinstance(item, WorldNode):
                program.world = item
            elif isinstance(item, MessageNode):
                program.messages.append(item)
            elif isinstance(item, SoulNode):
                program.souls.append(item)
            elif isinstance(item, NervousSystemNode):
                program.nervous_system = item
            elif isinstance(item, EvolutionNode):
                program.evolution = item
            elif isinstance(item, NoesisConfigNode):
                program.noesis = item
            elif isinstance(item, PerceptionNode):
                program.perception = item
            elif isinstance(item, ImportNode):
                program.imports.append(item)
            elif isinstance(item, TestNode):
                program.tests.append(item)
            elif isinstance(item, CustomSenseNode):
                program.custom_senses.append(item)
            elif isinstance(item, TopologyNode):
                program.topology = item
        return program



    # __policy_parser_v1__
    def policy_decl(self, items: list) -> PolicyNode:
        s = self._strip(items)
        name = str(s[0])
        clauses = s[1:]
        kwargs: dict = {"name": name}
        for c in clauses:
            if not isinstance(c, dict):
                continue
            if "_policy_kind" in c:
                kwargs["kind"] = c["_policy_kind"]
            elif "_policy_signal" in c:
                kwargs["signal"] = c["_policy_signal"]
            elif "_policy_window" in c:
                kwargs["window"] = c["_policy_window"]
            elif "_policy_weight" in c:
                kwargs["weight"] = c["_policy_weight"]
            elif "_policy_action" in c:
                kwargs["action"] = c["_policy_action"]
            elif "_policy_description" in c:
                kwargs["description"] = c["_policy_description"]
            elif "_policy_inject_as" in c:
                kwargs["inject_as"] = c["_policy_inject_as"]
            elif "_policy_message" in c:
                kwargs["message"] = c["_policy_message"]
        return PolicyNode(**kwargs)

    def policy_body(self, items: list) -> Any:
        return items[0] if items else None

    def policy_kind_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_kind": str(s[0])}

    def policy_signal_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_signal": s[0]}

    def policy_window_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_window": int(s[0])}

    def policy_weight_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_weight": float(s[0])}

    def policy_description_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_description": str(s[0])}

    def policy_action_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_action": s[0]}

    def policy_number_int(self, items: list) -> float:
        s = self._strip(items)
        return float(s[0])

    def policy_number_float(self, items: list) -> float:
        s = self._strip(items)
        return float(s[0])

    def policy_action_log_only(self, items: list) -> str:
        return "log_only"

    def policy_action_intervene(self, items: list) -> str:
        return "intervene"

    def policy_action_block(self, items: list) -> str:
        return "block"

    def policy_action_inject(self, items: list) -> str:
        return "inject_message"

    def policy_action_abort(self, items: list) -> str:
        return "abort_cycle"

    # __inject_message_grammar_v1__
    def policy_inject_as_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_inject_as": s[0]}

    def policy_message_clause(self, items: list) -> dict:
        s = self._strip(items)
        return {"_policy_message": str(s[0])}

    def policy_inject_system(self, items: list) -> str:
        return "system"

    def policy_inject_user(self, items: list) -> str:
        return "user"


def parse_nous(source: str) -> NousProgram:
    parser = _get_parser()
    tree = parser.parse(source)
    transformer = NousTransformer()
    return transformer.transform(tree)


def parse_nous_file(path: str | Path) -> NousProgram:
    source = Path(path).read_text(encoding="utf-8")
    return parse_nous(source)
