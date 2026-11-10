"""PKG001 (seat S475): nous migrate writes no YAML value into .nous
source unless it is a NOUS name.

Before PKG001 the migrator wrote agent_id, tool names, the model, the
directory name and the directory path into the program it prints. A
tool name carrying "]", a newline and a soul declaration made a program
that parses with a soul its user never wrote. Each test imports
nous_migrate_config itself, so a tree without it fails each test alone.

# __pkg001_s475_migrate_v1__
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENIGN = ("agent_id: demo_agent\nmodel: gpt-4o-mini\n"
          "tools: [web_search, file_read]\ntemperature: 0.2\n")
GOLDEN = 'soul DemoAgent {\n    mind: gpt-4o-mini @ Tier0B\n    senses: [web_search, file_read]\n\n    memory {\n        query_count: int = 0\n        last_result: string = ""\n    }\n\n    instinct {\n        # migrated from YAML \u2014 implement instinct logic\n        remember query_count += 1\n    }\n\n    dna {\n        temperature: 0.2 ~ [0.0, 1.0]\n        max_tokens: 1500 ~ [500, 8000]\n    }\n\n    heal {\n        on timeout => retry(3, exponential)\n        on api_error => retry(2, exponential)\n        on budget_exceeded => hibernate until next_cycle\n    }\n}'
EXFIL = ('agent_id: demo_agent\nmodel: gpt-4o-mini\n'
         'tools: ["web_search]\\n}\\nsoul Exfil {\\n    mind: gpt-4o @ Tier0B'
         '\\n    senses: [http_post"]\n')
LAWS = ["law CostCeiling = $0.50 per cycle", "law MaxLatency = 90s"]


def _m():
    return importlib.import_module("nous_migrate_config")


def _law_lines(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if l.strip().lower().startswith("law ")]


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_agent_id_injection_skipped(tmp_path, capsys) -> None:
    m = _m()
    y = 'agent_id: "x {\\n    law Evil = $9.99 per cycle\\n}\\nsoul Y"\nmodel: gpt-4o-mini\n'
    assert m.migrate_file(_write(tmp_path / "a.yaml", y)) is None
    assert "agent_id" in capsys.readouterr().err


def test_tool_name_injection_dropped(tmp_path, capsys) -> None:
    m = _m()
    y = ('agent_id: demo_agent\nmodel: gpt-4o-mini\n'
         'tools: [web_search, "x]\\n    law Evil = $1 per cycle\\n    senses: [y"]\n')
    out = m.migrate_file(_write(tmp_path / "a.yaml", y))
    assert "    senses: [web_search]" in out.splitlines()
    assert _law_lines(out) == []
    assert "dropped tool" in capsys.readouterr().err


def test_model_injection_unknown(tmp_path, capsys) -> None:
    m = _m()
    y = 'agent_id: demo_agent\nmodel: "gpt-4o\\nlaw Evil = $1 per cycle"\n'
    out = m.migrate_file(_write(tmp_path / "a.yaml", y))
    assert "    mind: unknown @ Tier0B" in out.splitlines()
    assert _law_lines(out) == []
    assert "model" in capsys.readouterr().err


def test_world_and_source_injection(tmp_path, capsys) -> None:
    m = _m()
    d = tmp_path / "w\nlaw Evil = $1 per cycle" / "agents"
    _write(d / "demo.yaml", BENIGN)
    out = tmp_path / "out.nous"
    m.migrate_directory(d, out)
    text = out.read_text(encoding="utf-8")
    assert _law_lines(text) == LAWS
    assert "world Migrated {" in text.splitlines()
    assert "world name" in capsys.readouterr().err


def test_benign_golden(tmp_path) -> None:
    m = _m()
    assert m.migrate_file(_write(tmp_path / "demo.yaml", BENIGN)) == GOLDEN


def test_benign_directory_parses(tmp_path) -> None:
    m = _m()
    import parser as nous_parser
    d = tmp_path / "world_a" / "agents"
    _write(d / "demo.yaml", BENIGN)
    out = tmp_path / "out.nous"
    m.migrate_directory(d, out)
    prog = nous_parser.parse_nous(out.read_text(encoding="utf-8"))
    assert [s.name for s in prog.souls] == ["DemoAgent"]


def test_shim_reexports() -> None:
    m = _m()
    spec = importlib.util.spec_from_file_location("migrate_shim_s475", REPO / "migrate.py")
    shim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shim)
    for name in ("migrate_file", "migrate_directory", "config_to_soul", "main"):
        assert getattr(shim, name) is getattr(m, name), name


def test_exfil_payload_no_extra_soul(tmp_path, capsys) -> None:
    m = _m()
    import parser as nous_parser
    d = tmp_path / "world_a" / "agents"
    _write(d / "demo.yaml", EXFIL)
    out = tmp_path / "out.nous"
    m.migrate_directory(d, out)
    prog = nous_parser.parse_nous(out.read_text(encoding="utf-8"))
    assert [s.name for s in prog.souls] == ["DemoAgent"]
    assert "dropped tool" in capsys.readouterr().err
