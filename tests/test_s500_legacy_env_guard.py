"""S500 E1: the API refuses to start where 10.0.0 took a key from the .env
above the modules and 11.0.0 takes none.

10.0.0's nous_api loaded that file by python-dotenv's load_dotenv when
NOUS_ENV_FILE was unset; 11.0.0 does not, so keys kept only there would
leave the API with none. The lifespan refuses exactly that case, reading
the file with load_dotenv's own arguments, and refuses a file that exists
and cannot be read (10.0.0 did not start there). Files and keys live only
in tmp_path; the legacy path is monkeypatched except in T15."""
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import nous_api
import nous_api_server as srv

KEY = "Zq7Wk9Xp3Lm2Rv8"
ROOT = Path(__file__).resolve().parent.parent


def _setup(tmp_path, monkeypatch, text, env_file=None, keys=()):
    p = tmp_path / ".env"
    if text is not None:
        p.write_text(text)
    monkeypatch.setattr(srv, "_legacy_env_path", lambda: p)
    if env_file is None:
        monkeypatch.delenv("NOUS_ENV_FILE", raising=False)
    else:
        monkeypatch.setenv("NOUS_ENV_FILE", env_file)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.setattr(srv, "API_KEYS", set(keys))
    monkeypatch.setattr(srv, "API_KEYS_FROM_ENV", False)
    return p


def _no_key_text(s):
    return not any(KEY[i:i + 4] in s for i in range(len(KEY) - 3))


def test_t1_keys_only_in_legacy_env_refuse(tmp_path, monkeypatch):
    p = _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    with pytest.raises(RuntimeError) as e:
        srv._legacy_env_guard()
    assert str(p) in str(e.value)


def test_t2_env_file_set_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY,
           env_file=str(tmp_path / "x.env"))
    srv._legacy_env_guard()


def test_t3_keys_configured_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY,
           keys=["Other9Key4Ab"])
    srv._legacy_env_guard()


def test_t4_other_names_only_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           "OPENROUTER_API_KEY=abc\nNOUS_TRACE_DIR=/tmp/x\n")
    srv._legacy_env_guard()


def test_t5_empty_value_starts(tmp_path, monkeypatch):
    for text in ("NOUS_API_KEYS=\n", 'NOUS_API_KEYS=""\n'):
        _setup(tmp_path, monkeypatch, text)
        srv._legacy_env_guard()


def test_t6_no_file_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, None)
    srv._legacy_env_guard()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file")
def test_t7_unreadable_file_refuses(tmp_path, monkeypatch):
    p = _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    p.chmod(0)
    try:
        with pytest.raises(RuntimeError) as e:
            srv._legacy_env_guard()
    finally:
        p.chmod(0o600)
    assert "cannot be read (PermissionError)" in str(e.value)
    assert str(p) in str(e.value)


def test_t8_no_key_text_in_message_or_log(tmp_path, monkeypatch, caplog):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="nous_api")
    with pytest.raises(RuntimeError) as e:
        srv._legacy_env_guard()
    assert _no_key_text(str(e.value))
    assert caplog.records
    assert all(_no_key_text(r.getMessage()) for r in caplog.records)


def test_t9_export_and_spaces_refuse(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "export NOUS_API_KEYS = '%s'\n" % KEY)
    with pytest.raises(RuntimeError):
        srv._legacy_env_guard()


def test_t10_comment_line_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "# NOUS_API_KEYS=%s\n" % KEY)
    srv._legacy_env_guard()


def test_t11_lifespan_refuses_then_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    entered = []
    with pytest.raises(RuntimeError):
        with TestClient(srv.app):
            entered.append(1)
    assert entered == []
    monkeypatch.setenv("NOUS_ENV_FILE", str(tmp_path / "x.env"))
    with TestClient(srv.app) as c:
        assert c.get("/v1/health").status_code == 200


def test_t12_empty_value_then_next_line_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=\nOTHER=1\n")
    srv._legacy_env_guard()


def test_t13_commas_only_start(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS= , ,\n")
    srv._legacy_env_guard()


def test_t14_no_dotenv_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    monkeypatch.setitem(sys.modules, "dotenv", None)
    monkeypatch.setitem(sys.modules, "dotenv.main", None)
    srv._legacy_env_guard()


def test_t15_path_is_the_one_10_0_0_loaded():
    want = Path(nous_api.__file__).parent.parent / ".env"
    assert srv._legacy_env_path() == want


def test_t16_empty_env_file_variable_refuses(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY, env_file="")
    with pytest.raises(RuntimeError):
        srv._legacy_env_guard()


def test_t17_reference_resolved_from_environment_refuses(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "A_S500=\nNOUS_API_KEYS=${A_S500}\n")
    monkeypatch.setenv("A_S500", KEY)
    with pytest.raises(RuntimeError):
        srv._legacy_env_guard()


def test_t18_reference_empty_in_environment_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "A_S500=%s\nNOUS_API_KEYS=${A_S500}\n" % KEY)
    monkeypatch.setenv("A_S500", "")
    srv._legacy_env_guard()


def test_t19_dotenv_disabled_as_installed(tmp_path, monkeypatch):
    import dotenv.main
    honoured = callable(getattr(dotenv.main, "_load_dotenv_disabled", None))
    for value, starts in (("1", True), ("true", True), ("YES", True),
                          ("0", False), ("no", False), ("", False)):
        _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", value)
        if starts and honoured:
            srv._legacy_env_guard()
        else:
            with pytest.raises(RuntimeError):
                srv._legacy_env_guard()


def test_t20_keys_variable_in_process_starts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    monkeypatch.setattr(srv, "API_KEYS_FROM_ENV", True)
    srv._legacy_env_guard()


def test_t21_flag_read_before_the_scrub():
    code = "import nous_api; print(nous_api.API_KEYS_FROM_ENV)"
    got = []
    for extra in ({"NOUS_API_KEYS": ""}, {}):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
        env.update(extra)
        r = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(ROOT),
                           env=env, capture_output=True, text=True, timeout=120)
        got.append(r.stdout.strip().splitlines()[-1:])
    assert got == [["True"], ["False"]]


def test_t22_read_error_refuses(tmp_path, monkeypatch):
    import dotenv.main

    def boom(self):
        raise PermissionError(13, "Permission denied")
    p = _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    monkeypatch.setattr(dotenv.main.DotEnv, "dict", boom)
    with pytest.raises(RuntimeError) as e:
        srv._legacy_env_guard()
    assert "cannot be read (PermissionError)" in str(e.value)
    assert str(p) in str(e.value)


def _locals_text(e):
    return "".join(traceback.TracebackException(
        type(e.value), e.value, e.value.__traceback__,
        capture_locals=True).format())


def test_t23_undecodable_file_refuses_without_its_bytes(tmp_path, monkeypatch,
                                                         caplog):
    p = tmp_path / ".env"
    _setup(tmp_path, monkeypatch, None)
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="nous_api")
    p.write_bytes(b"NOUS_API_KEYS=" + KEY.encode() + b"\xe9\xff\n")
    with pytest.raises(RuntimeError) as e:
        srv._legacy_env_guard()
    m = str(e.value)
    assert "cannot be read (UnicodeDecodeError)" in m
    assert e.value.__context__ is None and e.value.__cause__ is None
    t = "".join(traceback.format_exception(e.value))
    for s in (m, t):
        assert "0x" not in s and "can't decode" not in s and "\\xe9" not in s
    for s in (m, t, _locals_text(e)):
        assert _no_key_text(s)
    assert caplog.records
    assert all(_no_key_text(r.getMessage()) for r in caplog.records)


def test_t24_no_key_in_any_frame(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    with pytest.raises(RuntimeError) as e:
        srv._legacy_env_guard()
    assert e.value.__context__ is None
    assert _no_key_text(_locals_text(e))


DIFF_CASES = [
    ("NOUS_API_KEYS=%s\n" % KEY, {}),
    ("export NOUS_API_KEYS = '%s'\n" % KEY, {}),
    ("A_S500=\nNOUS_API_KEYS=${A_S500}\n", {"A_S500": KEY}),
    ("A_S500=%s\nNOUS_API_KEYS=${A_S500}\n" % KEY, {"A_S500": ""}),
    ("NOUS_API_KEYS=%s\n" % KEY, {"PYTHON_DOTENV_DISABLED": "1"}),
    ("NOUS_API_KEYS=%s\n" % KEY, {"PYTHON_DOTENV_DISABLED": "YES"}),
    ("NOUS_API_KEYS=%s\n" % KEY, {"PYTHON_DOTENV_DISABLED": "0"}),
    ("# NOUS_API_KEYS=%s\n" % KEY, {}),
    ("NOUS_API_KEYS= , ,\n", {}),
    ("NOUS_API_KEYS=\n", {}),
    ("NOUS_API_KEYS\n", {}),
    ("NOUS_API_KEYS=%s\r\nB=1\r\n" % KEY, {}),
]
DIFF_CODE = (
    "import os, sys\n"
    "from dotenv import load_dotenv\n"
    "load_dotenv(sys.argv[1])\n"
    "v = os.environ.get('NOUS_API_KEYS', '')\n"
    "print(any(k.strip() for k in v.split(',')))\n")


def test_t25_agrees_with_load_dotenv(tmp_path, monkeypatch):
    got, want = [], []
    for i, (text, env) in enumerate(DIFF_CASES):
        d = tmp_path / str(i)
        d.mkdir()
        p = d / ".env"
        p.write_bytes(text.encode())
        e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
        e.update(env)
        r = subprocess.run([sys.executable, "-B", "-c", DIFF_CODE, str(p)],
                           cwd=str(d), env=e, capture_output=True, text=True,
                           timeout=60)
        want.append(r.stdout.strip() == "True")
        monkeypatch.setattr(srv, "_legacy_env_path", lambda p=p: p)
        monkeypatch.delenv("NOUS_ENV_FILE", raising=False)
        monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
        monkeypatch.delenv("A_S500", raising=False)
        monkeypatch.setattr(srv, "API_KEYS", set())
        monkeypatch.setattr(srv, "API_KEYS_FROM_ENV", False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        try:
            srv._legacy_env_guard()
            got.append(False)
        except RuntimeError:
            got.append(True)
    assert got == want, list(zip(got, want))
    assert True in want and False in want


def test_t26_served_app_is_the_guarded_app():
    assert nous_api.app is srv.app


def test_t27_reader_missing_refuses(tmp_path, monkeypatch):
    import dotenv.main
    _setup(tmp_path, monkeypatch, "NOUS_API_KEYS=%s\n" % KEY)
    monkeypatch.delattr(dotenv.main, "DotEnv")
    with pytest.raises(RuntimeError) as e:
        srv._legacy_env_guard()
    assert "cannot be read (AttributeError)" in str(e.value)


def test_t28_reader_missing_no_file_starts(tmp_path, monkeypatch):
    import dotenv.main
    _setup(tmp_path, monkeypatch, None)
    monkeypatch.delattr(dotenv.main, "DotEnv")
    srv._legacy_env_guard()
