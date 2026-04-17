#!/usr/bin/env python3
"""tests/test_inject_message.py -- Phase G Layer 2.5: inject_message E2E tests."""
# __inject_message_tests_v1__
import json
import os
import sys
import tempfile
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \u2713 {name}")
    else:
        FAIL += 1
        print(f"  \u2717 {name} -- {detail}")


NOUS_INJECT = (
    'world InjectDemo {\n'
    '    heartbeat = 1s\n'
    '    policy SafetyGuard {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.0\n'
    '        weight: 5.0\n'
    '        action: inject_message\n'
    '        inject_as: system\n'
    '        message: "You must follow safety guidelines at all times."\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)

NOUS_INJECT_USER = (
    'world InjectUser {\n'
    '    heartbeat = 1s\n'
    '    policy UserHint {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.0\n'
    '        weight: 3.0\n'
    '        action: inject_message\n'
    '        inject_as: user\n'
    '        message: "Remember to be concise."\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)

NOUS_INJECT_NO_MESSAGE = (
    'world BadInject {\n'
    '    heartbeat = 1s\n'
    '    policy NoMsg {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.0\n'
    '        weight: 5.0\n'
    '        action: inject_message\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)

NOUS_NO_INJECT = (
    'world NoInject {\n'
    '    heartbeat = 1s\n'
    '    policy BlockCost {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.05\n'
    '        weight: 5.0\n'
    '        action: block\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)


def test_01_grammar_parses_inject():
    """Grammar accepts inject_as + message clauses."""
    from parser import parse_nous
    prog = parse_nous(NOUS_INJECT)
    pol = prog.world.policies[0]
    check("policy name is SafetyGuard", pol.name == "SafetyGuard")
    check("action is inject_message", pol.action == "inject_message")
    check("inject_as is system", pol.inject_as == "system")
    check("message is set", pol.message == "You must follow safety guidelines at all times.")


def test_02_grammar_parses_inject_user():
    """inject_as: user is accepted."""
    from parser import parse_nous
    prog = parse_nous(NOUS_INJECT_USER)
    pol = prog.world.policies[0]
    check("inject_as user", pol.inject_as == "user")
    check("message set", pol.message == "Remember to be concise.")


def test_03_validator_requires_message():
    """Validator PL006: inject_message without message clause is error."""
    from parser import parse_nous
    from validator import validate_program
    prog = parse_nous(NOUS_INJECT_NO_MESSAGE)
    result = validate_program(prog)
    pl006 = [e for e in result.errors if e.code == "PL006"]
    check("PL006 emitted for missing message", len(pl006) >= 1, f"errors={result.errors}")


def test_04_codegen_emits_inject_configs():
    """Codegen emits _POLICY_INJECT_CONFIGS when inject_message present."""
    from parser import parse_nous
    from codegen import generate_python
    py = generate_python(parse_nous(NOUS_INJECT))
    check("_POLICY_INJECT_CONFIGS in output", "_POLICY_INJECT_CONFIGS" in py)
    check("SafetyGuard in inject configs", "SafetyGuard" in py)
    check("inject role in output", '"role"' in py)


def test_05_codegen_no_inject_configs_without():
    """Without inject_message policies, no _POLICY_INJECT_CONFIGS emitted."""
    from parser import parse_nous
    from codegen import generate_python
    py = generate_python(parse_nous(NOUS_NO_INJECT))
    check("no _POLICY_INJECT_CONFIGS", "_POLICY_INJECT_CONFIGS" not in py)


def test_06_intervention_engine_returns_inject_data():
    """InterventionEngine returns inject data in outcome."""
    from intervention import InterventionEngine, InterventionOutcome
    from risk_engine import RiskRule

    rules = [
        RiskRule(
            name="InjectTest",
            description="test",
            kind_filter=("llm.request",),
            predicate="cost > 0.0",
            weight=5.0,
            action="inject_message",
        ),
    ]
    actions = {"InjectTest": "inject_message"}
    inject_configs = {"InjectTest": {"role": "system", "content": "Stay safe."}}
    engine = InterventionEngine(rules, actions, inject_configs)

    class FakeEvent:
        kind = "llm.request"
        seq_id = 1
        soul = "S"
        cycle = 1
        data = {"cost": 0.10}

    outcome = engine.check(FakeEvent())
    check("outcome triggered", outcome.triggered)
    check("action is inject_message", outcome.action == "inject_message")
    check("inject_role is system", outcome.inject_role == "system")
    check("inject_content is Stay safe.", outcome.inject_content == "Stay safe.")


def test_07_intervention_engine_no_inject_backward_compat():
    """Engine without inject_configs works normally."""
    from intervention import InterventionEngine
    from risk_engine import RiskRule

    rules = [
        RiskRule(
            name="LogOnly",
            description="test",
            kind_filter=("llm.request",),
            predicate="cost > 0.0",
            weight=3.0,
            action="log_only",
        ),
    ]
    actions = {"LogOnly": "log_only"}
    engine = InterventionEngine(rules, actions)

    class FakeEvent:
        kind = "llm.request"
        seq_id = 1
        soul = "S"
        cycle = 1
        data = {"cost": 0.10}

    outcome = engine.check(FakeEvent())
    check("backward compat: triggered", outcome.triggered)
    check("backward compat: action log_only", outcome.action == "log_only")
    check("backward compat: inject_role empty", outcome.inject_role == "")


def test_08_replay_context_injects_message():
    """ReplayContext modifies messages in-place on inject_message."""
    import asyncio
    from replay_store import EventStore
    from replay_runtime import ReplayContext
    from intervention import InterventionEngine
    from risk_engine import RiskRule

    rules = [
        RiskRule(
            name="InjectSafety",
            description="inject",
            kind_filter=("llm.request",),
            predicate="temperature > 0.0",
            weight=5.0,
            action="inject_message",
        ),
    ]
    actions = {"InjectSafety": "inject_message"}
    inject_configs = {"InjectSafety": {"role": "system", "content": "Be safe."}}
    engine = InterventionEngine(rules, actions, inject_configs)

    tmp = tempfile.mktemp(suffix=".jsonl")
    store = EventStore.open(tmp, mode="record")
    ctx = ReplayContext(store=store, mode="record")
    ctx.set_intervention_engine(engine)

    messages = [{"role": "user", "content": "Hello"}]
    executed = False

    async def fake_execute():
        nonlocal executed
        executed = True
        return {"text": "Hi", "cost": 0.01, "tier": "T0", "tokens_in": 5, "tokens_out": 3, "elapsed_ms": 50.0}

    asyncio.get_event_loop().run_until_complete(
        ctx.record_or_replay_llm("S", 1, "test", "model", messages, 0.7, fake_execute)
    )

    store.close()
    os.unlink(tmp)

    check("execute was called", executed)
    check("messages has 2 items (injected + original)", len(messages) == 2, f"got {len(messages)}")
    if len(messages) == 2:
        check("first message is injected system", messages[0]["role"] == "system" and messages[0]["content"] == "Be safe.")


def test_09_codegen_generated_module_loads():
    """Generated module with inject_message loads and has inject configs."""
    from parser import parse_nous
    from codegen import generate_python
    import py_compile

    py = generate_python(parse_nous(NOUS_INJECT))
    tmp = tempfile.mkdtemp(prefix="nous_inject_")
    gen_path = os.path.join(tmp, "gen.py")
    with open(gen_path, "w") as f:
        f.write(py)

    py_compile.compile(gen_path, doraise=True)

    spec = importlib.util.spec_from_file_location("gen_inject", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    check("module has _INTERVENTION_ENGINE", hasattr(mod, "_INTERVENTION_ENGINE"))
    check("engine is enabled", mod._INTERVENTION_ENGINE.enabled)
    check("module has _POLICY_INJECT_CONFIGS", hasattr(mod, "_POLICY_INJECT_CONFIGS"))
    if hasattr(mod, "_POLICY_INJECT_CONFIGS"):
        check("inject config has SafetyGuard", "SafetyGuard" in mod._POLICY_INJECT_CONFIGS)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


def test_10_regression_no_inject_codegen_unchanged():
    """Source without inject_message produces no _POLICY_INJECT_CONFIGS."""
    from parser import parse_nous
    from codegen import generate_python
    import py_compile

    py = generate_python(parse_nous(NOUS_NO_INJECT))
    check("no INJECT_CONFIGS in non-inject source", "_POLICY_INJECT_CONFIGS" not in py)

    tmp = tempfile.mkdtemp(prefix="nous_noinject_")
    gen_path = os.path.join(tmp, "gen.py")
    with open(gen_path, "w") as f:
        f.write(py)
    py_compile.compile(gen_path, doraise=True)
    check("non-inject source compiles clean", True)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)




# __inject_message_rehash_tests_v1__
def test_11_llm_request_event_has_post_inject_hash():
    """On inject_message, llm.request event data contains post-inject metadata."""
    import asyncio
    import json as _json
    import hashlib as _hashlib
    from replay_store import EventStore
    from replay_runtime import ReplayContext
    from intervention import InterventionEngine
    from risk_engine import RiskRule

    rules = [
        RiskRule(
            name="InjectLayer45",
            description="rehash test",
            kind_filter=("llm.request",),
            predicate="temperature > 0.0",
            weight=5.0,
            action="inject_message",
        ),
    ]
    actions = {"InjectLayer45": "inject_message"}
    inject_configs = {"InjectLayer45": {"role": "system", "content": "Rehash me."}}
    engine = InterventionEngine(rules, actions, inject_configs)

    tmp = tempfile.mktemp(suffix=".jsonl")
    store = EventStore.open(tmp, mode="record")
    ctx = ReplayContext(store=store, mode="record")
    ctx.set_intervention_engine(engine)

    messages = [{"role": "user", "content": "Hello"}]
    original_payload = {
        "provider": "test",
        "model": "model",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }
    pre_inject_canonical = _json.dumps(
        original_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    pre_inject_hash = _hashlib.sha256(pre_inject_canonical.encode("utf-8")).hexdigest()

    async def fake_execute():
        return {
            "text": "Hi", "cost": 0.01, "tier": "T0",
            "tokens_in": 5, "tokens_out": 3, "elapsed_ms": 50.0,
        }

    asyncio.get_event_loop().run_until_complete(
        ctx.record_or_replay_llm("S", 1, "test", "model", messages, 0.7, fake_execute)
    )
    store.close()

    with open(tmp) as fh:
        events = [_json.loads(line) for line in fh if line.strip()]
    os.unlink(tmp)

    req_events = [e for e in events if e.get("kind") == "llm.request"]
    check("one llm.request event recorded", len(req_events) == 1,
          f"got {len(req_events)}")
    if len(req_events) == 1:
        data = req_events[0].get("data", {})
        check("original prompt_hash matches pre-inject",
              data.get("prompt_hash") == pre_inject_hash)
        check("event has prompt_hash_post_inject",
              "prompt_hash_post_inject" in data)
        check("post-inject hash differs from original",
              data.get("prompt_hash_post_inject") != data.get("prompt_hash"))
        check("injected_role recorded as system",
              data.get("injected_role") == "system")
        check("injected_policies recorded",
              data.get("injected_policies") == ["InjectLayer45"])


def test_12_no_inject_no_rehash_fields():
    """Without inject_message (log_only action), event has no post-inject fields."""
    import asyncio
    import json as _json
    from replay_store import EventStore
    from replay_runtime import ReplayContext
    from intervention import InterventionEngine
    from risk_engine import RiskRule

    rules = [
        RiskRule(
            name="LogOnly",
            description="no inject",
            kind_filter=("llm.request",),
            predicate="temperature > 0.0",
            weight=1.0,
            action="log_only",
        ),
    ]
    actions = {"LogOnly": "log_only"}
    engine = InterventionEngine(rules, actions)

    tmp = tempfile.mktemp(suffix=".jsonl")
    store = EventStore.open(tmp, mode="record")
    ctx = ReplayContext(store=store, mode="record")
    ctx.set_intervention_engine(engine)

    messages = [{"role": "user", "content": "Hi"}]

    async def fake_execute():
        return {
            "text": "Hi", "cost": 0.01, "tier": "T0",
            "tokens_in": 5, "tokens_out": 3, "elapsed_ms": 50.0,
        }

    asyncio.get_event_loop().run_until_complete(
        ctx.record_or_replay_llm("S", 1, "test", "model", messages, 0.7, fake_execute)
    )
    store.close()

    with open(tmp) as fh:
        events = [_json.loads(line) for line in fh if line.strip()]
    os.unlink(tmp)

    req_events = [e for e in events if e.get("kind") == "llm.request"]
    check("one llm.request event recorded", len(req_events) == 1)
    if len(req_events) == 1:
        data = req_events[0].get("data", {})
        check("no prompt_hash_post_inject without inject",
              "prompt_hash_post_inject" not in data)
        check("no injected_role without inject",
              "injected_role" not in data)
        check("no injected_policies without inject",
              "injected_policies" not in data)


def test_13_post_inject_hash_matches_injected_messages():
    """post_inject hash equals sha256 of canonical messages after injection."""
    import asyncio
    import json as _json
    import hashlib as _hashlib
    from replay_store import EventStore
    from replay_runtime import ReplayContext
    from intervention import InterventionEngine
    from risk_engine import RiskRule

    rules = [
        RiskRule(
            name="Verify",
            description="verify hash",
            kind_filter=("llm.request",),
            predicate="temperature > 0.0",
            weight=1.0,
            action="inject_message",
        ),
    ]
    actions = {"Verify": "inject_message"}
    inject_configs = {"Verify": {"role": "system", "content": "Guarded."}}
    engine = InterventionEngine(rules, actions, inject_configs)

    tmp = tempfile.mktemp(suffix=".jsonl")
    store = EventStore.open(tmp, mode="record")
    ctx = ReplayContext(store=store, mode="record")
    ctx.set_intervention_engine(engine)

    messages = [{"role": "user", "content": "Question?"}]

    async def fake_execute():
        return {
            "text": "Answer", "cost": 0.01, "tier": "T0",
            "tokens_in": 2, "tokens_out": 1, "elapsed_ms": 10.0,
        }

    asyncio.get_event_loop().run_until_complete(
        ctx.record_or_replay_llm("S", 1, "p", "m", messages, 0.7, fake_execute)
    )
    store.close()

    expected_payload = {
        "provider": "p",
        "model": "m",
        "messages": [
            {"role": "system", "content": "Guarded."},
            {"role": "user", "content": "Question?"},
        ],
        "temperature": 0.7,
    }
    expected_canonical = _json.dumps(
        expected_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    expected_hash = _hashlib.sha256(expected_canonical.encode("utf-8")).hexdigest()

    with open(tmp) as fh:
        events = [_json.loads(line) for line in fh if line.strip()]
    os.unlink(tmp)

    req_events = [e for e in events if e.get("kind") == "llm.request"]
    check("one llm.request event recorded", len(req_events) == 1)
    if len(req_events) == 1:
        data = req_events[0].get("data", {})
        actual = data.get("prompt_hash_post_inject", "")
        check(
            "post_inject hash matches recomputed canonical",
            actual == expected_hash,
            f"expected {expected_hash[:16]}... got {str(actual)[:16]}...",
        )


if __name__ == "__main__":
    print("=" * 60)
    print("INJECT_MESSAGE TESTS -- Phase G Layer 2.5")
    print("=" * 60)
    test_01_grammar_parses_inject()
    test_02_grammar_parses_inject_user()
    test_03_validator_requires_message()
    test_04_codegen_emits_inject_configs()
    test_05_codegen_no_inject_configs_without()
    test_06_intervention_engine_returns_inject_data()
    test_07_intervention_engine_no_inject_backward_compat()
    test_08_replay_context_injects_message()
    test_09_codegen_generated_module_loads()
    test_10_regression_no_inject_codegen_unchanged()
    # __inject_message_rehash_tests_v1__
    test_11_llm_request_event_has_post_inject_hash()
    test_12_no_inject_no_rehash_fields()
    test_13_post_inject_hash_matches_injected_messages()
    print("=" * 60)
    total = PASS + FAIL
    if FAIL == 0:
        print(f"INJECT_MESSAGE TESTS -- ALL GREEN ({PASS}/{total})")
    else:
        print(f"INJECT_MESSAGE TESTS -- {FAIL} FAILED ({PASS}/{total})")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
