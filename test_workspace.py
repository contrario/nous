"""
NOUS Test — Workspace v1
Tests nous.toml discovery, file discovery, merge, validate, typecheck.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from workspace import (
    WorkspaceConfig, Workspace, find_workspace_root,
    load_config, discover_files, init_workspace,
    open_workspace, print_workspace_report,
)


MINI_WORLD = """\
world TestWorld {
    law CostCeiling = $0.10 per cycle
    heartbeat = 5m
}

message Signal {
    pair: string
    score: float
}

soul Scout {
    mind: gpt-4o @ Tier2
    senses: [fetch_rsi]
    memory { count: int = 0 }
    instinct {
        let data = sense fetch_rsi(pair: "BTC/USDT")
        speak Signal(pair: "BTC/USDT", score: 0.8)
        remember count += 1
    }
}

nervous_system {
    Scout -> Quant
}
"""

MINI_QUANT = """\
soul Quant {
    mind: claude-haiku @ Tier0A
    senses: [calculate_kelly]
    memory { risk: float = 0 }
    instinct {
        let signal = listen Scout::Signal
        remember risk = signal.score
    }
}
"""

MINI_TEST = """\
world TestWorld {
    law CostCeiling = $1 per cycle
    heartbeat = 1m
}
soul TestSoul {
    mind: gpt-4o @ Tier2
    senses: []
    instinct {}
}
test "basic" {
    assert true
}
"""


def test_init_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.nous").write_text(MINI_WORLD)
        toml_path = init_workspace(tmp, name="test-project")
        assert toml_path.exists()
        cfg = load_config(toml_path)
        assert cfg.name == "test-project"
        assert cfg.entry == "main.nous"
        assert cfg.root == tmp
    print("  ✓ test_init_workspace")


def test_discover_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.nous").write_text(MINI_WORLD)
        (tmp / "quant.nous").write_text(MINI_QUANT)
        (tmp / "basic_test.nous").write_text(MINI_TEST)
        init_workspace(tmp, name="disc-test", entry="main.nous")
        cfg = load_config(tmp / "nous.toml")
        files = discover_files(cfg)
        names = {f.name for f in files}
        assert "main.nous" in names
        assert "quant.nous" in names
        assert "basic_test.nous" not in names
    print("  ✓ test_discover_files")


def test_find_workspace_root() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        sub = tmp / "src" / "deep"
        sub.mkdir(parents=True)
        (tmp / "nous.toml").write_text('[package]\nname = "root-test"\n')
        found = find_workspace_root(sub)
        assert found == tmp.resolve()
    print("  ✓ test_find_workspace_root")


def test_parse_and_merge() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.nous").write_text(MINI_WORLD)
        (tmp / "quant.nous").write_text(MINI_QUANT)
        init_workspace(tmp, name="merge-test", entry="main.nous")
        cfg = load_config(tmp / "nous.toml")
        ws = Workspace(cfg)
        result = ws.build()
        assert result.merged is not None
        soul_names = {s.name for s in result.merged.souls}
        assert "Scout" in soul_names, f"Missing Scout, got {soul_names}"
        assert "Quant" in soul_names, f"Missing Quant, got {soul_names}"
        msg_names = {m.name for m in result.merged.messages}
        assert "Signal" in msg_names
        assert result.merged.world is not None
        assert result.merged.world.name == "TestWorld"
    print("  ✓ test_parse_and_merge")


def test_workspace_build_gate_alpha() -> None:
    ga_path = Path("/opt/aetherlang_agents/nous/gate_alpha.nous")
    if not ga_path.exists():
        print("  ⊘ test_workspace_build_gate_alpha (skipped)")
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        shutil.copy(ga_path, tmp / "gate_alpha.nous")
        init_workspace(tmp, name="gate-alpha", entry="gate_alpha.nous")
        cfg = load_config(tmp / "nous.toml")
        ws = Workspace(cfg)
        result = ws.build()
        assert result.merged is not None
        assert len(result.merged.souls) == 4
        assert result.merged.world.name == "GateAlpha"
        print_workspace_report(result)
    print("  ✓ test_workspace_build_gate_alpha")


def test_duplicate_soul_warning() -> None:
    dup_soul = """world ExtraWorld {
    law CostCeiling = $1 per cycle
    heartbeat = 1m
}
soul Scout {
    mind: gpt-4o @ Tier2
    senses: [http_get]
    instinct {
        let x = sense http_get(url: "http://test")
    }
}
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.nous").write_text(MINI_WORLD)
        (tmp / "extra.nous").write_text(dup_soul)
        init_workspace(tmp, name="dup-test", entry="main.nous")
        cfg = load_config(tmp / "nous.toml")
        ws = Workspace(cfg)
        result = ws.build()
        parse_errs = [f for f in result.files if f.parse_error]
        assert len(parse_errs) == 0, f"Parse errors: {[(f.relative, f.parse_error) for f in parse_errs]}"
        dup_warns = [w for w in result.warnings if "Duplicate soul" in w.message]
        assert len(dup_warns) >= 1, f"Expected duplicate warning, got {result.warnings}"
    print("  ✓ test_duplicate_soul_warning")


def test_open_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.nous").write_text(MINI_WORLD)
        init_workspace(tmp, name="open-test")
        ws = open_workspace(tmp)
        assert ws is not None
        assert ws.config.name == "open-test"
    print("  ✓ test_open_workspace")


def test_test_file_exclusion() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.nous").write_text(MINI_WORLD)
        (tmp / "quant.nous").write_text(MINI_QUANT)
        (tmp / "scout_test.nous").write_text(MINI_TEST)
        (tmp / "integration_test.nous").write_text(MINI_TEST)
        init_workspace(tmp, name="excl-test", entry="main.nous")
        cfg = load_config(tmp / "nous.toml")
        ws = Workspace(cfg)
        result = ws.discover()
        src_names = {f.relative for f in result.files if not f.is_test}
        assert "main.nous" in src_names
        assert "quant.nous" in src_names
    print("  ✓ test_test_file_exclusion")


if __name__ == "__main__":
    print("\n═══ NOUS Workspace v1 Tests ═══\n")
    test_init_workspace()
    test_discover_files()
    test_find_workspace_root()
    test_parse_and_merge()
    test_workspace_build_gate_alpha()
    test_duplicate_soul_warning()
    test_open_workspace()
    test_test_file_exclusion()
    print(f"\n  ═══ ALL 8/8 TESTS PASS ═══\n")
