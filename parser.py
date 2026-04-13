"""
NOUS Parser — Lark → Living AST (Ψυχόδενδρο)
===============================================
Transforms the Lark CST into Pydantic V2 AST nodes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, Token, Tree

from ast_nodes import (
    NousProgram, WorldNode, LawNode, LawCost, LawDuration,
    LawConstitutional, LawBool, LawInt, LawCurrency, SoulNode, MindNode,
    MemoryNode, FieldDeclNode, InstinctNode, DnaNode, GeneNode,
    HealNode, HealRuleNode, HealActionNode, HealStrategy,
    MessageNode, MessageFieldNode, NervousSystemNode, RouteNode,
    MatchRouteNode, MatchArmNode, FanInNode, FanOutNode, FeedbackNode,
    EvolutionNode, MutateBlockNode, MutateStrategyNode,
    PerceptionNode, PerceptionRuleNode, PerceptionTriggerNode,
    PerceptionActionNode, LetNode, RememberNode, SpeakNode,
    ListenNode, GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
    Tier, TopologyNode, TopologyServerNode,
    TestNode, TestAssertNode, TestMockNode, TestRunNode,
)

GRAMMAR_PATH = Path(__file__).parent / "nous.lark"
_PARSER_CACHE: Lark | None = None


def _get_parser() -> Lark:
    global _PARSER_CACHE
    if _PARSER_CACHE is None:
        grammar = GRAMMAR_PATH.read_text()
        _PARSER_CACHE = Lark(grammar, parser="lalr", start="start")
    return _PARSER_CACHE


class NousTransformer(Transformer):

    def _strip(self, items: list) -> list:
        """Remove None and raw Token objects (keyword terminals) from items."""
        return [i for i in items if i is not None and not isinstance(i, Token)]

    # ── Primitives ──

    def INT(self, tok: Token) -> int:
        return int(tok)

    def FLOAT(self, tok: Token) -> float:
        return float(tok)

    def STRING(self, tok: Token) -> str:
        return str(tok)[1:-1]

    def BOOL(self, tok: Token) -> bool:
        return tok == "true"

    def NAME(self, tok: Token) -> str:
        return str(tok)

    def TIER(self, tok: Token) -> str:
        return str(tok)

    def COMP_OP(self, tok: Token) -> str:
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
        return items[0]

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

    def DURATION_VAL(self, tok: Token) -> str:
        return str(tok)

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

    def soul_ref(self, items: list) -> str:
        return str(items[0])

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

    def neg_expr(self, items: list) -> dict:
        return {"kind": "neg", "operand": items[0]}

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

    def ADD_OP(self, tok: Token) -> str:
        return str(tok)

    def MUL_OP(self, tok: Token) -> str:
        return str(tok)

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
        s = self._strip(items)
        return {"kind": "inline_if", "condition": s[0], "then": s[1], "else": s[2]}

    def msg_positional(self, items: list) -> dict:
        return {"kind": "message_construct", "type": items[0], "args": items[1] if len(items) > 1 else {}}

    def msg_braced(self, items: list) -> dict:
        return {"kind": "message_construct", "type": items[0], "args": items[1] if len(items) > 1 else {}}

    def message_construct(self, items: list) -> Any:
        return items[0]

    def arg_list(self, items: list) -> dict:
        result = {}
        for item in items:
            if isinstance(item, dict) and "arg_name" in item:
                result[item["arg_name"]] = item["arg_value"]
            elif isinstance(item, dict) and "positional" in item:
                result[f"_pos_{len(result)}"] = item["positional"]
            else:
                result[f"_pos_{len(result)}"] = item
        return result

    def arg(self, items: list) -> Any:
        if len(items) == 2:
            return {"arg_name": items[0], "arg_value": items[1]}
        return items[0]

    def kv_list(self, items: list) -> dict:
        result = {}
        for item in items:
            if isinstance(item, dict) and "_kv" in item:
                result[item["_kv"][0]] = item["_kv"][1]
        return result

    def kv_pair(self, items: list) -> dict:
        return {"_kv": (items[0], items[1])}

    # ── Law ──

    def law_cost(self, items: list) -> LawCost:
        c = items[0]
        return LawCost(amount=c["amount"], currency=c.get("currency", "USD"))

    def law_constitutional(self, items: list) -> LawConstitutional:
        return LawConstitutional(count=items[0])

    def law_duration(self, items: list) -> LawDuration:
        d = items[0]
        val = int(d[:-1]) if d[-1].isalpha() else int(d[:-2])
        unit = d[-1] if d[-1].isalpha() else d[-2:]
        return LawDuration(value=val, unit=unit)

    def law_bool(self, items: list) -> LawBool:
        return LawBool(value=items[0])

    def law_int(self, items: list) -> LawInt:
        return LawInt(value=items[0])

    def law_currency(self, items: list) -> LawCurrency:
        c = items[0]
        return LawCurrency(amount=c["amount"], currency=c.get("currency", "USD"))

    def law_decl(self, items: list) -> LawNode:
        return LawNode(name=items[1], expr=items[2])

    def law_expr(self, items: list) -> Any:
        return items[0]

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
        name = items[1]
        node = WorldNode(name=name)
        for item in items[2:]:
            if isinstance(item, LawNode):
                node.laws.append(item)
            elif isinstance(item, dict):
                if "heartbeat" in item:
                    node.heartbeat = item["heartbeat"]
                elif "timezone" in item:
                    node.timezone = item["timezone"]
                elif "config" in item:
                    k, v = item["config"]
                    node.config[k] = v
        return node

    # ── Mind ──

    def model_name(self, items: list) -> str:
        return "-".join(str(i) for i in items)

    def mind_decl(self, items: list) -> MindNode:
        return MindNode(model=items[0], tier=Tier(items[1]))

    # ── Senses ──

    def name_list(self, items: list) -> list[str]:
        return [str(i) for i in items]

    def senses_decl(self, items: list) -> list[str]:
        return items[0]

    # ── Memory ──

    def field_decl(self, items: list) -> FieldDeclNode:
        return FieldDeclNode(name=items[0], type_expr=items[1], default=items[2])

    def memory_block(self, items: list) -> MemoryNode:
        fields = [i for i in items[1:] if isinstance(i, FieldDeclNode)]
        return MemoryNode(fields=fields)

    # ── Statements ──

    def let_stmt(self, items: list) -> LetNode:
        s = self._strip(items)
        return LetNode(name=s[0], value=s[1])

    def remember_stmt(self, items: list) -> RememberNode:
        if len(items) == 3:
            return RememberNode(name=items[1], op="+=", value=items[2])
        return RememberNode(name=items[1], value=items[2])

    def speak_stmt(self, items: list) -> SpeakNode:
        s = self._strip(items)
        msg_name = s[0]
        args = s[1] if len(s) > 1 and isinstance(s[1], dict) else {}
        return SpeakNode(message_type=str(msg_name), args=args)

    def listen_expr(self, items: list) -> LetNode:
        s = self._strip(items)
        bind_name = s[0]
        soul = s[1]
        msg_type = s[2]
        return LetNode(name=bind_name, value={"kind": "listen", "soul": soul, "type": msg_type})

    def guard_stmt(self, items: list) -> GuardNode:
        return GuardNode(condition=items[1])

    def sense_call(self, items: list) -> Any:
        s = self._strip(items)
        if len(s) >= 3 and isinstance(s[1], dict):
            return LetNode(name=s[0], value={"kind": "sense_call", "tool": s[0], "args": s[1] if isinstance(s[1], dict) else {}})
        has_let = any(isinstance(i, Token) and str(i) == "let" for i in items)
        if has_let:
            bind_name = s[0]
            tool = s[1]
            args = s[2] if len(s) > 2 and isinstance(s[2], dict) else {}
            return LetNode(name=bind_name, value={"kind": "sense_call", "tool": tool, "args": args})
        tool = s[0]
        args = s[1] if len(s) > 1 and isinstance(s[1], dict) else {}
        return SenseCallNode(tool_name=tool, args=args)

    def sleep_stmt(self, items: list) -> SleepNode:
        return SleepNode(cycles=items[1])

    def if_stmt(self, items: list) -> IfNode:
        s = self._strip(items)
        cond = s[0]
        then_body: list[Any] = s[1] if len(s) > 1 and isinstance(s[1], list) else []
        else_body: list[Any] = s[2] if len(s) > 2 and isinstance(s[2], list) else []
        return IfNode(condition=cond, then_body=then_body, else_body=else_body)

    def for_stmt(self, items: list) -> ForNode:
        s = self._strip(items)
        var_name = s[0]
        iterable = s[1]
        body: list[Any] = s[2] if len(s) > 2 and isinstance(s[2], list) else []
        return ForNode(var_name=var_name, iterable=iterable, body=body)

    def statement(self, items: list) -> Any:
        return items[0]

    # ── Instinct ──

    def stmt_body(self, items: list) -> list[Any]:
        return [i for i in items if not isinstance(i, Token)]

    def instinct_block(self, items: list) -> InstinctNode:
        s = self._strip(items)
        stmts = s[0] if s and isinstance(s[0], list) else []
        return InstinctNode(statements=stmts)

    # ── DNA ──

    def gene_decl(self, items: list) -> GeneNode:
        name = items[0]
        value = items[1]
        range_vals = list(items[2:])
        return GeneNode(name=name, value=value, range=range_vals)

    def dna_block(self, items: list) -> DnaNode:
        genes = [i for i in items[1:] if isinstance(i, GeneNode)]
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
        return HealActionNode(strategy=HealStrategy.SLEEP, params={"cycles": items[0]})

    def heal_action(self, items: list) -> Any:
        return items[0]

    def heal_rule(self, items: list) -> HealRuleNode:
        s = self._strip(items)
        error_type = s[0]
        actions = [i for i in s[1:] if isinstance(i, HealActionNode)]
        return HealRuleNode(error_type=error_type, actions=actions)

    def heal_block(self, items: list) -> HealNode:
        rules = [i for i in items[1:] if isinstance(i, HealRuleNode)]
        return HealNode(rules=rules)

    # ── Soul ──

    def soul_body(self, items: list) -> Any:
        return items[0]

    def soul_decl(self, items: list) -> SoulNode:
        name = items[1]
        node = SoulNode(name=name)
        for item in items[2:]:
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
        return node

    # ── Message ──

    def message_field(self, items: list) -> MessageFieldNode:
        name = items[0]
        type_expr = items[1]
        default = items[2] if len(items) > 2 else None
        return MessageFieldNode(name=name, type_expr=type_expr, default=default)

    def message_decl(self, items: list) -> MessageNode:
        name = items[1]
        fields = [i for i in items[2:] if isinstance(i, MessageFieldNode)]
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
        s = self._strip(items)
        source = s[0]
        arms = [i for i in s[1:] if isinstance(i, MatchArmNode)]
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
        routes: list = []
        for item in items[1:]:
            if isinstance(item, list):
                routes.extend(item)
            elif item is not None and not isinstance(item, Token):
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
        node = EvolutionNode()
        for item in items[1:]:
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
        s = self._strip(items)
        return PerceptionRuleNode(trigger=s[0], action=s[1])

    def perception_decl(self, items: list) -> PerceptionNode:
        rules = [i for i in items[1:] if isinstance(i, PerceptionRuleNode)]
        return PerceptionNode(rules=rules)

    # ── Test ──

    def test_assert_expr(self, items: list) -> TestAssertNode:
        s = self._strip(items)
        return TestAssertNode(kind="expr", expr=s[0])

    def test_assert_field(self, items: list) -> TestAssertNode:
        s = self._strip(items)
        return TestAssertNode(kind="field", soul=s[0], field=s[1], op=s[2], expected=s[3])

    def test_assert_spoke(self, items: list) -> TestAssertNode:
        s = self._strip(items)
        return TestAssertNode(kind="spoke", message_type=s[0])

    def test_mock_tool(self, items: list) -> TestMockNode:
        s = self._strip(items)
        return TestMockNode(tool_name=s[0], returns=s[1])

    def test_run_soul(self, items: list) -> TestRunNode:
        s = self._strip(items)
        return TestRunNode(soul_name=s[0])

    def test_stmt(self, items: list) -> Any:
        return items[0]

    def test_decl(self, items: list) -> TestNode:
        s = self._strip(items)
        desc = s[0] if s else ""
        stmts = [i for i in s[1:] if isinstance(i, (TestAssertNode, TestMockNode, TestRunNode))]
        return TestNode(description=desc, stmts=stmts)

    # ── Topology ──

    def topo_body(self, items: list) -> dict:
        return {"_topo_kv": (items[0], items[1])}

    def topo_server(self, items: list) -> TopologyServerNode:
        name = items[0]
        host = items[1]
        config: dict[str, Any] = {}
        for item in items[2:]:
            if isinstance(item, dict) and "_topo_kv" in item:
                k, v = item["_topo_kv"]
                config[k] = v
        return TopologyServerNode(name=name, host=host, config=config)

    def topology_decl(self, items: list) -> TopologyNode:
        servers = [i for i in items if isinstance(i, TopologyServerNode)]
        return TopologyNode(servers=servers)

    # ── Deploy ──

    def deploy_body(self, items: list) -> dict:
        return {"_deploy_kv": (items[0], items[1])}

    def deploy_decl(self, items: list) -> dict:
        name = items[0]
        config: dict[str, Any] = {}
        for item in items[1:]:
            if isinstance(item, dict) and "_deploy_kv" in item:
                k, v = item["_deploy_kv"]
                config[k] = v
        return {"kind": "deploy", "name": name, "config": config}

    # ── Top-Level ──

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
            elif isinstance(item, PerceptionNode):
                program.perception = item
            elif isinstance(item, TopologyNode):
                program.topology = item
            elif isinstance(item, TestNode):
                program.tests.append(item)
        return program


def parse_nous(source: str) -> NousProgram:
    """Parse a .nous source string into a Living AST."""
    lark_parser = _get_parser()
    tree = lark_parser.parse(source)
    transformer = NousTransformer()
    return transformer.transform(tree)


def parse_nous_file(path: str | Path) -> NousProgram:
    """Parse a .nous file into a Living AST."""
    source = Path(path).read_text(encoding="utf-8")
    return parse_nous(source)
