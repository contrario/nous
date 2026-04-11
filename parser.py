"""
NOUS Parser v2.0 — LALR Edition (Ψυχόδενδρο)
===============================================
Clean LALR parser. No post-processing workarounds.
All keyword ambiguity resolved at grammar level.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, Token

from ast_nodes import (
    NousProgram, WorldNode, LawNode, LawCost, LawDuration,
    LawConstitutional, LawBool, LawInt, SoulNode, MindNode,
    MemoryNode, FieldDeclNode, InstinctNode, DnaNode, GeneNode,
    HealNode, HealRuleNode, HealActionNode, HealStrategy,
    MessageNode, MessageFieldNode, NervousSystemNode, RouteNode,
    MatchRouteNode, MatchArmNode, FanInNode, FanOutNode, FeedbackNode,
    EvolutionNode, MutateBlockNode, MutateStrategyNode,
    PerceptionNode, PerceptionRuleNode, PerceptionTriggerNode,
    PerceptionActionNode, LetNode, RememberNode, SpeakNode,
    ListenNode, GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
    Tier,
)

GRAMMAR_PATH = Path(__file__).parent / "nous.lark"

_PARSER_CACHE: Lark | None = None


def _get_parser() -> Lark:
    global _PARSER_CACHE
    if _PARSER_CACHE is None:
        grammar = GRAMMAR_PATH.read_text(encoding="utf-8")
        _PARSER_CACHE = Lark(grammar, parser="lalr", start="start")
    return _PARSER_CACHE


def _strip(items: list) -> list:
    return [i for i in items if i is not None and not isinstance(i, Token)]


class NousTransformer(Transformer):

    def WORLD(self, _t: Token) -> None: return None
    def SOUL(self, _t: Token) -> None: return None
    def MEMORY(self, _t: Token) -> None: return None
    def INSTINCT(self, _t: Token) -> None: return None
    def SENSE(self, _t: Token) -> None: return None
    def REMEMBER(self, _t: Token) -> None: return None
    def SPEAK(self, _t: Token) -> None: return None
    def LISTEN(self, _t: Token) -> None: return None
    def DNA(self, _t: Token) -> None: return None
    def HEAL(self, _t: Token) -> None: return None
    def LAW(self, _t: Token) -> None: return None
    def GUARD(self, _t: Token) -> None: return None
    def SLEEP(self, _t: Token) -> None: return None
    def NERVOUS_SYSTEM(self, _t: Token) -> None: return None
    def EVOLUTION(self, _t: Token) -> None: return None
    def PERCEPTION(self, _t: Token) -> None: return None
    def MESSAGE(self, _t: Token) -> None: return None
    def SILENCE(self, _t: Token) -> None: return None
    def WAKE_ALL(self, _t: Token) -> None: return None
    def CONSTITUTIONAL(self, _t: Token) -> None: return None
    def PER(self, _t: Token) -> None: return None
    def CYCLE(self, _t: Token) -> None: return None

    def INT(self, tok: Token) -> int: return int(tok)
    def FLOAT(self, tok: Token) -> float: return float(tok)
    def STRING(self, tok: Token) -> str: return str(tok)[1:-1]
    def BOOL(self, tok: Token) -> bool: return tok == "true"
    def NAME(self, tok: Token) -> str: return str(tok)
    def TIER(self, tok: Token) -> str: return str(tok)
    def COMP_OP(self, tok: Token) -> str: return str(tok)
    def DURATION_UNIT(self, tok: Token) -> str: return str(tok)
    def ADD_OP(self, tok: Token) -> str: return str(tok)
    def MUL_OP(self, tok: Token) -> str: return str(tok)

    def named_type(self, items: list) -> str: return str(items[0])
    def list_type(self, items: list) -> str: return f"[{items[0]}]"
    def optional_type(self, items: list) -> str: return f"{items[0]}?"
    def map_type(self, items: list) -> str: return f"{{{items[0]}: {items[1]}}}"

    def int_lit(self, items: list) -> Any: return items[0]
    def float_lit(self, items: list) -> Any: return items[0]
    def bool_lit(self, items: list) -> Any: return items[0]
    def now_lit(self, _items: list) -> str: return "now()"
    def self_ref(self, _items: list) -> str: return "self"

    def string_lit(self, items: list) -> dict:
        return {"kind": "string_lit", "value": items[0]}

    def currency_usd(self, items: list) -> dict:
        v = _strip(items)
        return {"currency": "USD", "amount": float(v[0])}

    def currency_eur(self, items: list) -> dict:
        v = _strip(items)
        return {"currency": "EUR", "amount": float(v[0])}

    def currency_lit(self, items: list) -> Any: return items[0]

    def duration_lit(self, items: list) -> str:
        v = _strip(items)
        return f"{v[0]}{v[1]}"

    def time_hm(self, items: list) -> str:
        v = _strip(items)
        return f"{v[0]}:{v[1]:02d} {v[2]}"

    def name_ref(self, items: list) -> str: return items[0]
    def list_lit(self, items: list) -> list: return items[0] if items else []
    def map_lit(self, items: list) -> dict: return items[0] if items else {}
    def expr_list(self, items: list) -> list: return list(items)

    def world_ref(self, items: list) -> dict:
        return {"kind": "world_ref", "path": items[0]}

    def dotted_name(self, items: list) -> str:
        return ".".join(str(i) for i in items)

    def soul_field_ref(self, items: list) -> dict:
        return {"kind": "soul_field", "soul": items[0], "field": items[1]}

    def attr_access(self, items: list) -> dict:
        return {"kind": "attr", "obj": items[0], "attr": items[1]}

    def method_call(self, items: list) -> dict:
        return {"kind": "method_call", "obj": items[0], "method": items[1], "args": items[2] if len(items) > 2 else {}}

    def func_call(self, items: list) -> dict:
        return {"kind": "func_call", "func": items[0], "args": items[1] if len(items) > 1 else {}}

    def not_expr(self, items: list) -> dict:
        return {"kind": "not", "operand": items[0]}

    def neg_expr(self, items: list) -> dict:
        return {"kind": "neg", "operand": items[0]}

    def or_expr(self, items: list) -> Any:
        if len(items) == 1: return items[0]
        result = items[0]
        for i in range(1, len(items)):
            result = {"kind": "binop", "op": "||", "left": result, "right": items[i]}
        return result

    def and_expr(self, items: list) -> Any:
        if len(items) == 1: return items[0]
        result = items[0]
        for i in range(1, len(items)):
            result = {"kind": "binop", "op": "&&", "left": result, "right": items[i]}
        return result

    def compare_expr(self, items: list) -> Any:
        if len(items) == 1: return items[0]
        return {"kind": "binop", "op": items[1], "left": items[0], "right": items[2]}

    def add_expr(self, items: list) -> Any:
        if len(items) == 1: return items[0]
        result = items[0]
        for i in range(1, len(items), 2):
            result = {"kind": "binop", "op": items[i], "left": result, "right": items[i + 1]}
        return result

    def mul_expr(self, items: list) -> Any:
        if len(items) == 1: return items[0]
        result = items[0]
        for i in range(1, len(items), 2):
            result = {"kind": "binop", "op": items[i], "left": result, "right": items[i + 1]}
        return result

    def inline_if(self, items: list) -> dict:
        return {"kind": "inline_if", "condition": items[0], "then": items[1], "else": items[2]}

    def named_arg(self, items: list) -> dict:
        return {"arg_name": items[0], "arg_value": items[1]}

    def positional_arg(self, items: list) -> Any:
        return items[0]

    def arg_list(self, items: list) -> dict:
        result: dict[str, Any] = {}
        for item in items:
            if isinstance(item, dict) and "arg_name" in item:
                result[item["arg_name"]] = item["arg_value"]
            else:
                result[f"_pos_{len(result)}"] = item
        return result

    def kv_list(self, items: list) -> dict:
        result: dict[str, Any] = {}
        for item in items:
            if isinstance(item, dict) and "_kv" in item:
                result[item["_kv"][0]] = item["_kv"][1]
        return result

    def kv_pair(self, items: list) -> dict:
        return {"_kv": (items[0], items[1])}

    def law_cost(self, items: list) -> LawCost:
        v = _strip(items)
        c = v[0]
        return LawCost(amount=c["amount"], currency=c.get("currency", "USD"))

    def law_constitutional(self, items: list) -> LawConstitutional:
        v = _strip(items)
        return LawConstitutional(count=v[0])

    def law_duration(self, items: list) -> LawDuration:
        v = _strip(items)
        d = v[0]
        val = int(d[:-1]) if d[-1].isalpha() else int(d[:-2])
        unit = d[-1] if d[-1].isalpha() else d[-2:]
        return LawDuration(value=val, unit=unit)

    def law_bool(self, items: list) -> LawBool:
        v = _strip(items)
        return LawBool(value=v[0])

    def law_int(self, items: list) -> LawInt:
        v = _strip(items)
        return LawInt(value=v[0])

    def law_decl(self, items: list) -> LawNode:
        v = _strip(items)
        return LawNode(name=v[0], expr=v[1])

    def law_expr(self, items: list) -> Any: return items[0]

    def heartbeat_decl(self, items: list) -> dict:
        v = _strip(items)
        return {"heartbeat": v[0]}

    def timezone_decl(self, items: list) -> dict:
        v = _strip(items)
        return {"timezone": v[0]}

    def config_assign(self, items: list) -> dict:
        return {"config": (items[0], items[1])}

    def world_body(self, items: list) -> Any: return items[0]

    def world_decl(self, items: list) -> WorldNode:
        v = _strip(items)
        node = WorldNode(name=v[0])
        for item in v[1:]:
            if isinstance(item, LawNode):
                node.laws.append(item)
            elif isinstance(item, dict):
                if "heartbeat" in item: node.heartbeat = item["heartbeat"]
                elif "timezone" in item: node.timezone = item["timezone"]
                elif "config" in item:
                    k, val = item["config"]
                    node.config[k] = val
        return node

    def model_name(self, items: list) -> str:
        return "-".join(str(i) for i in items)

    def mind_decl(self, items: list) -> MindNode:
        v = _strip(items)
        return MindNode(model=v[0], tier=Tier(v[1]))

    def name_list(self, items: list) -> list[str]:
        return [str(i) for i in items]

    def senses_decl(self, items: list) -> list[str]:
        return items[0]

    def field_decl(self, items: list) -> FieldDeclNode:
        return FieldDeclNode(name=items[0], type_expr=items[1], default=items[2])

    def memory_block(self, items: list) -> MemoryNode:
        v = _strip(items)
        return MemoryNode(fields=[i for i in v if isinstance(i, FieldDeclNode)])

    def let_stmt(self, items: list) -> LetNode:
        return LetNode(name=items[0], value=items[1])

    def let_sense_stmt(self, items: list) -> LetNode:
        v = _strip(items)
        return LetNode(name=v[0], value={"kind": "sense_call", "tool": v[1], "args": v[2] if len(v) > 2 else {}})

    def let_listen_stmt(self, items: list) -> LetNode:
        v = _strip(items)
        return LetNode(name=v[0], value={"kind": "listen", "soul": v[1], "type": v[2]})

    def remember_set(self, items: list) -> RememberNode:
        v = _strip(items)
        return RememberNode(name=v[0], op="=", value=v[1])

    def remember_add(self, items: list) -> RememberNode:
        v = _strip(items)
        return RememberNode(name=v[0], op="+=", value=v[1])

    def speak_stmt(self, items: list) -> SpeakNode:
        v = _strip(items)
        return SpeakNode(message_type=v[0], args=v[1] if len(v) > 1 else {})

    def guard_stmt(self, items: list) -> GuardNode:
        v = _strip(items)
        return GuardNode(condition=v[0])

    def sense_call(self, items: list) -> SenseCallNode:
        v = _strip(items)
        args = v[1] if len(v) > 1 else {}
        return SenseCallNode(tool_name=v[0], args=args if isinstance(args, dict) else {})

    def sleep_stmt(self, items: list) -> SleepNode:
        v = _strip(items)
        return SleepNode(cycles=v[0])

    def then_block(self, items: list) -> list:
        return _strip(items)

    def else_block(self, items: list) -> list:
        return _strip(items)

    def if_no_else(self, items: list) -> IfNode:
        v = _strip(items)
        return IfNode(condition=v[0], then_body=v[1] if len(v) > 1 else [], else_body=[])

    def if_else(self, items: list) -> IfNode:
        v = _strip(items)
        return IfNode(condition=v[0], then_body=v[1] if len(v) > 1 else [], else_body=v[2] if len(v) > 2 else [])

    def for_stmt(self, items: list) -> ForNode:
        v = _strip(items)
        return ForNode(var_name=v[0], iterable=v[1], body=list(v[2:]))

    def statement(self, items: list) -> Any: return items[0]
    def expr_stmt(self, items: list) -> Any: return items[0]

    def instinct_block(self, items: list) -> InstinctNode:
        v = _strip(items)
        return InstinctNode(statements=v)

    def gene_decl(self, items: list) -> GeneNode:
        return GeneNode(name=items[0], value=items[1], range=list(items[2:]))

    def dna_block(self, items: list) -> DnaNode:
        v = _strip(items)
        return DnaNode(genes=[i for i in v if isinstance(i, GeneNode)])

    def heal_retry(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.RETRY, params={"max": v[0], "backoff": v[1]})

    def heal_retry_simple(self, _items: list) -> HealActionNode:
        return HealActionNode(strategy=HealStrategy.RETRY, params={"max": 1})

    def heal_lower(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.LOWER, params={"param": v[0], "delta": v[1]})

    def heal_raise(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.RAISE, params={"param": v[0], "delta": v[1]})

    def heal_hibernate(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.HIBERNATE, params={"until": v[0]})

    def heal_fallback(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.FALLBACK, params={"target": v[0]})

    def heal_delegate(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.DELEGATE, params={"soul": v[0]})

    def heal_alert(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.ALERT, params={"channel": v[0]})

    def heal_sleep(self, items: list) -> HealActionNode:
        v = _strip(items)
        return HealActionNode(strategy=HealStrategy.SLEEP, params={"cycles": v[0]})

    def heal_action(self, items: list) -> Any: return items[0]

    def heal_rule(self, items: list) -> HealRuleNode:
        v = _strip(items)
        return HealRuleNode(error_type=v[0], actions=[i for i in v[1:] if isinstance(i, HealActionNode)])

    def heal_block(self, items: list) -> HealNode:
        v = _strip(items)
        return HealNode(rules=[i for i in v if isinstance(i, HealRuleNode)])

    def soul_body(self, items: list) -> Any: return items[0]

    def soul_decl(self, items: list) -> SoulNode:
        v = _strip(items)
        node = SoulNode(name=v[0])
        for item in v[1:]:
            if isinstance(item, MindNode): node.mind = item
            elif isinstance(item, list) and item and isinstance(item[0], str): node.senses = item
            elif isinstance(item, MemoryNode): node.memory = item
            elif isinstance(item, InstinctNode): node.instinct = item
            elif isinstance(item, DnaNode): node.dna = item
            elif isinstance(item, HealNode): node.heal = item
        return node

    def message_field(self, items: list) -> MessageFieldNode:
        return MessageFieldNode(name=items[0], type_expr=items[1], default=items[2] if len(items) > 2 else None)

    def message_decl(self, items: list) -> MessageNode:
        v = _strip(items)
        return MessageNode(name=v[0], fields=[i for i in v[1:] if isinstance(i, MessageFieldNode)])

    def route_chain(self, items: list) -> list[RouteNode]:
        names = [str(i) for i in items]
        return [RouteNode(source=names[i], target=names[i + 1]) for i in range(len(names) - 1)]

    def match_arm_soul(self, items: list) -> MatchArmNode:
        return MatchArmNode(condition=items[0], target=items[1])

    def match_arm_silence(self, _items: list) -> MatchArmNode:
        return MatchArmNode(condition="_", is_silence=True)

    def match_route(self, items: list) -> MatchRouteNode:
        return MatchRouteNode(source=items[0], arms=[i for i in items[1:] if isinstance(i, MatchArmNode)])

    def fanin_stmt(self, items: list) -> FanInNode:
        return FanInNode(sources=items[0], target=items[1])

    def fanout_stmt(self, items: list) -> FanOutNode:
        return FanOutNode(source=items[0], targets=items[1])

    def feedback_stmt(self, items: list) -> FeedbackNode:
        return FeedbackNode(source_soul=items[0], source_field=items[1], target_soul=items[2], target_field=items[3])

    def nerve_stmt(self, items: list) -> Any: return items[0]

    def nervous_system_decl(self, items: list) -> NervousSystemNode:
        v = _strip(items)
        routes: list = []
        for item in v:
            if isinstance(item, list): routes.extend(item)
            else: routes.append(item)
        return NervousSystemNode(routes=routes)

    def mutate_strategy(self, items: list) -> MutateStrategyNode:
        return MutateStrategyNode(name=items[0], params=items[1] if len(items) > 1 and isinstance(items[1], dict) else {})

    def mutate_survive(self, items: list) -> dict: return {"survive": items[0]}
    def mutate_rollback(self, items: list) -> dict: return {"rollback": items[0]}
    def mutate_body(self, items: list) -> Any: return items[0]

    def mutate_block(self, items: list) -> MutateBlockNode:
        target = items[0]
        node = MutateBlockNode(target=target)
        for item in items[1:]:
            if isinstance(item, MutateStrategyNode): node.strategy = item
            elif isinstance(item, dict):
                if "survive" in item: node.survive_condition = item["survive"]
                elif "rollback" in item: node.rollback_condition = item["rollback"]
        return node

    def evolution_body(self, items: list) -> Any: return items[0]

    def evolution_decl(self, items: list) -> EvolutionNode:
        v = _strip(items)
        node = EvolutionNode()
        for item in v:
            if isinstance(item, str) and ":" in item: node.schedule = item
            elif isinstance(item, MutateBlockNode): node.mutations.append(item)
            elif isinstance(item, dict): node.fitness = item
            elif not isinstance(item, (MutateBlockNode, str)) and node.fitness is None: node.fitness = item
        return node

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

    def perception_trigger(self, items: list) -> Any: return items[0]
    def perception_action(self, items: list) -> Any: return items[0]

    def perception_rule(self, items: list) -> PerceptionRuleNode:
        return PerceptionRuleNode(trigger=items[0], action=items[1])

    def perception_decl(self, items: list) -> PerceptionNode:
        v = _strip(items)
        return PerceptionNode(rules=[i for i in v if isinstance(i, PerceptionRuleNode)])

    def deploy_decl(self, items: list) -> dict:
        v = _strip(items)
        config: dict[str, Any] = {}
        for item in v[1:]:
            if isinstance(item, dict) and "_kv" in item: config[item["_kv"][0]] = item["_kv"][1]
        return {"kind": "deploy", "name": v[0], "config": config}

    def deploy_body(self, items: list) -> dict: return {"_kv": (items[0], items[1])}

    def topology_decl(self, items: list) -> dict:
        return {"kind": "topology", "servers": [i for i in items if isinstance(i, dict) and i.get("kind") == "topo_server"]}

    def topo_server(self, items: list) -> dict:
        config: dict[str, Any] = {}
        for item in items[2:]:
            if isinstance(item, dict) and "_kv" in item: config[item["_kv"][0]] = item["_kv"][1]
        return {"kind": "topo_server", "name": items[0], "address": items[1], "config": config}

    def topo_body(self, items: list) -> dict: return {"_kv": (items[0], items[1])}
    def top_level(self, items: list) -> Any: return items[0]

    def start(self, items: list) -> NousProgram:
        program = NousProgram()
        for item in items:
            if isinstance(item, WorldNode): program.world = item
            elif isinstance(item, MessageNode): program.messages.append(item)
            elif isinstance(item, SoulNode): program.souls.append(item)
            elif isinstance(item, NervousSystemNode): program.nervous_system = item
            elif isinstance(item, EvolutionNode): program.evolution = item
            elif isinstance(item, PerceptionNode): program.perception = item
        return program


def parse_nous(source: str) -> NousProgram:
    parser = _get_parser()
    tree = parser.parse(source)
    return NousTransformer().transform(tree)


def parse_nous_file(path: str | Path) -> NousProgram:
    source = Path(path).read_text(encoding="utf-8")
    return parse_nous(source)
