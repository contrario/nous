"""
NOUS Living AST v2.0 — Ψυχόδενδρο (Psychodendro)
===================================================
Pydantic V2 nodes for the runtime-mutable AST.
Every node is typed, validated, serializable.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class Tier(str, Enum):
    TIER0A = "Tier0A"
    TIER0B = "Tier0B"
    TIER1 = "Tier1"
    TIER2 = "Tier2"
    TIER3 = "Tier3"
    GROQ = "Groq"
    TOGETHER = "Together"
    FIREWORKS = "Fireworks"
    CEREBRAS = "Cerebras"


class HealStrategy(str, Enum):
    RETRY = "retry"
    LOWER = "lower"
    RAISE = "raise"
    HIBERNATE = "hibernate"
    FALLBACK = "fallback"
    DELEGATE = "delegate"
    ALERT = "alert"
    SLEEP = "sleep"


class NousNode(BaseModel):
    model_config = {"extra": "forbid"}


# ═══════════════════════════════════════════
# LAW
# ═══════════════════════════════════════════

class LawCost(NousNode):
    kind: str = "cost"
    amount: float
    currency: str = "USD"
    per: str = "cycle"


class LawCurrency(NousNode):
    kind: str = "currency"
    amount: float
    currency: str = "USD"


class LawDuration(NousNode):
    kind: str = "duration"
    value: int
    unit: str


class LawConstitutional(NousNode):
    kind: str = "constitutional"
    count: int


class LawBool(NousNode):
    kind: str = "bool"
    value: bool


class LawInt(NousNode):
    kind: str = "int"
    value: int


LawExpr = Union[LawCost, LawCurrency, LawDuration, LawConstitutional, LawBool, LawInt]


class LawNode(NousNode):
    name: str
    expr: LawExpr


# ═══════════════════════════════════════════
# WORLD
# ═══════════════════════════════════════════

class TelemetryNode(NousNode):
    enabled: bool = True
    exporter: str = "console"
    endpoint: Optional[str] = None
    sample_rate: float = 1.0
    trace_senses: bool = True
    trace_llm: bool = True
    buffer_size: int = 1000


class WorldNode(NousNode):
    name: str
    laws: list[LawNode] = Field(default_factory=list)
    heartbeat: Optional[str] = None
    timezone: Optional[str] = None
    telemetry: Optional[TelemetryNode] = None
    config: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════
# MESSAGE
# ═══════════════════════════════════════════

class MessageFieldNode(NousNode):
    name: str
    type_expr: str
    default: Optional[Any] = None


class MessageNode(NousNode):
    name: str
    fields: list[MessageFieldNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# TYPES
# ═══════════════════════════════════════════

class TypeExpr(NousNode):
    base: str
    is_list: bool = False
    is_optional: bool = False
    key_type: Optional[str] = None
    value_type: Optional[str] = None


# ═══════════════════════════════════════════
# MEMORY
# ═══════════════════════════════════════════

class FieldDeclNode(NousNode):
    name: str
    type_expr: str
    default: Any = None


class MemoryNode(NousNode):
    fields: list[FieldDeclNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# EXPRESSIONS
# ═══════════════════════════════════════════

class ExprNode(NousNode):
    kind: str
    value: Any = None
    left: Optional[ExprNode] = None
    right: Optional[ExprNode] = None
    op: Optional[str] = None
    args: list[Any] = Field(default_factory=list)
    children: list[ExprNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# STATEMENTS
# ═══════════════════════════════════════════

class LetNode(NousNode):
    name: str
    value: Any


class RememberNode(NousNode):
    name: str
    op: str = "="
    value: Any


class SpeakNode(NousNode):
    message_type: str
    args: dict[str, Any] = Field(default_factory=dict)
    target_world: Optional[str] = None


class ListenNode(NousNode):
    target_soul: str
    message_type: str
    bind_name: str


class GuardNode(NousNode):
    condition: Any


class SenseCallNode(NousNode):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    bind_name: Optional[str] = None


class SleepNode(NousNode):
    cycles: int


class IfNode(NousNode):
    condition: Any
    then_body: list[Any] = Field(default_factory=list)
    else_body: list[Any] = Field(default_factory=list)


class ForNode(NousNode):
    var_name: str
    iterable: Any
    body: list[Any] = Field(default_factory=list)


StatementNode = Union[
    LetNode, RememberNode, SpeakNode, ListenNode,
    GuardNode, SenseCallNode, SleepNode, IfNode, ForNode
]


# ═══════════════════════════════════════════
# INSTINCT
# ═══════════════════════════════════════════

class InstinctNode(NousNode):
    statements: list[Any] = Field(default_factory=list)


# ═══════════════════════════════════════════
# DNA
# ═══════════════════════════════════════════

class GeneNode(NousNode):
    name: str
    value: Any
    range: list[Any] = Field(default_factory=list)


class DnaNode(NousNode):
    genes: list[GeneNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# HEAL
# ═══════════════════════════════════════════

class HealActionNode(NousNode):
    strategy: HealStrategy
    params: dict[str, Any] = Field(default_factory=dict)


class HealRuleNode(NousNode):
    error_type: str
    actions: list[HealActionNode] = Field(default_factory=list)


class HealNode(NousNode):
    rules: list[HealRuleNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# MIND
# ═══════════════════════════════════════════

class MindNode(NousNode):
    model: str
    tier: Tier





# ═══════════════════════════════════════════
# DREAM SYSTEM — Speculative Pre-computation
# ═══════════════════════════════════════════

class DreamMindNode(NousNode):
    model: str
    tier: Tier


class DreamSystemNode(NousNode):
    enabled: bool = True
    trigger_idle_sec: int = 30
    dream_mind: Optional[DreamMindNode] = None
    max_cache: int = 20
    speculation_depth: int = 3


# ═══════════════════════════════════════════
# IMMUNE SYSTEM — Adaptive Recovery
# ═══════════════════════════════════════════

class ImmuneSystemNode(NousNode):
    adaptive_recovery: bool = True
    share_with_clones: bool = True
    antibody_lifespan: str = "3600s"


# ═══════════════════════════════════════════
# MITOSIS — Self-Replication
# ═══════════════════════════════════════════

class MitosisNode(NousNode):
    trigger: Any = None
    max_clones: int = 3
    cooldown: str = "60s"
    clone_tier: Optional[str] = None
    verify: bool = True
    retire_trigger: Any = None
    retire_cooldown: str = "120s"
    min_clones: int = 0


# ═══════════════════════════════════════════
# SOUL
# ═══════════════════════════════════════════

class SoulNode(NousNode):
    name: str
    mind: Optional[MindNode] = None
    senses: list[str] = Field(default_factory=list)
    memory: Optional[MemoryNode] = None
    instinct: Optional[InstinctNode] = None
    dna: Optional[DnaNode] = None
    heal: Optional[HealNode] = None
    mitosis: Optional[MitosisNode] = None
    immune_system: Optional[ImmuneSystemNode] = None
    dream_system: Optional[DreamSystemNode] = None


# ═══════════════════════════════════════════
# NERVOUS SYSTEM
# ═══════════════════════════════════════════

class RouteNode(NousNode):
    source: str
    target: str


class MatchArmNode(NousNode):
    condition: Any
    target: Optional[str] = None
    is_silence: bool = False


class MatchRouteNode(NousNode):
    source: str
    arms: list[MatchArmNode] = Field(default_factory=list)


class FanInNode(NousNode):
    sources: list[str]
    target: str


class FanOutNode(NousNode):
    source: str
    targets: list[str]


class FeedbackNode(NousNode):
    source_soul: str
    source_field: str
    target_soul: str
    target_field: str


NerveStatement = Union[RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode]


class NervousSystemNode(NousNode):
    routes: list[NerveStatement] = Field(default_factory=list)


# ═══════════════════════════════════════════
# EVOLUTION
# ═══════════════════════════════════════════

class MutateStrategyNode(NousNode):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class MutateBlockNode(NousNode):
    target: str
    strategy: Optional[MutateStrategyNode] = None
    survive_condition: Any = None
    rollback_condition: Any = None


class EvolutionNode(NousNode):
    schedule: Optional[str] = None
    fitness: Any = None
    mutations: list[MutateBlockNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# PERCEPTION
# ═══════════════════════════════════════════

class PerceptionTriggerNode(NousNode):
    kind: str
    name: str
    args: list[Any] = Field(default_factory=list)


class PerceptionActionNode(NousNode):
    kind: str
    target: Optional[str] = None


class PerceptionRuleNode(NousNode):
    trigger: PerceptionTriggerNode
    action: PerceptionActionNode


class PerceptionNode(NousNode):
    rules: list[PerceptionRuleNode] = Field(default_factory=list)


# ═══════════════════════════════════════════
# NOESIS — Symbolic Intelligence
# ═══════════════════════════════════════════

class NoesisConfigNode(NousNode):
    lattice_path: Optional[str] = None
    oracle_threshold: float = 0.3
    auto_learn: bool = True
    auto_evolve: bool = False
    gap_tracking: bool = True


class ResonateNode(NousNode):
    query: Any = None
    bind_name: Optional[str] = None
    guard_field: Optional[str] = None
    guard_threshold: Optional[float] = None


# ═══════════════════════════════════════════
# IMPORT
# ═══════════════════════════════════════════

class ImportNode(NousNode):
    path: Optional[str] = None
    package: Optional[str] = None


# ═══════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════

class TestAssertNode(NousNode):
    condition: Any


class TestSetupNode(NousNode):
    statements: list[Any] = Field(default_factory=list)


class TestNode(NousNode):
    name: str
    asserts: list[TestAssertNode] = Field(default_factory=list)
    setups: list[TestSetupNode] = Field(default_factory=list)




# ═══════════════════════════════════════════
# TOPOLOGY — Distributed Deployment
# ═══════════════════════════════════════════

class ServerNode(NousNode):
    name: str
    host: str
    port: int = 9100
    souls: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class TopologyNode(NousNode):
    servers: list[ServerNode] = Field(default_factory=list)

# ═══════════════════════════════════════════
# PROGRAM (ROOT)
# ═══════════════════════════════════════════

class NousProgram(NousNode):
    noesis: Optional[NoesisConfigNode] = None
    world: Optional[WorldNode] = None
    messages: list[MessageNode] = Field(default_factory=list)
    souls: list[SoulNode] = Field(default_factory=list)
    nervous_system: Optional[NervousSystemNode] = None
    evolution: Optional[EvolutionNode] = None
    perception: Optional[PerceptionNode] = None
    topology: Optional[TopologyNode] = None
    imports: list[ImportNode] = Field(default_factory=list)
    tests: list[TestNode] = Field(default_factory=list)
