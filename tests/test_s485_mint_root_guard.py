"""S485: the mint's root guard (FG-S481-M, N, P, Q; D483).

Invariant: when mint_release_vsa runs as root it executes no byte another
principal can write. The guard acts for euid 0 only; these tests inject
euid, the accepted owners and lstat, so none runs as root and none writes
or reads a key. The test user stands in for root through the owners tuple;
"foreign" paths are made foreign by the injected lstat.
"""
from __future__ import annotations

import ast
import importlib
import importlib.machinery
import os
import stat
import sys
import types
from pathlib import Path

import pytest

import mint_release_vsa as M

_REPO = Path(M.__file__).resolve().parent
OWN = (0, os.geteuid())
OTHER = 54321
GOOD = types.SimpleNamespace(isolated=1, safe_path=True, dont_write_bytecode=1)


class _St:
    def __init__(self, st, uid=None, mode_or=0):
        self.st_uid = st.st_uid if uid is None else uid
        self.st_gid = st.st_gid
        self.st_mode = st.st_mode | mode_or


def _lstat(foreign=()):
    foreign = {os.path.abspath(str(p)) for p in foreign}

    def f(p):
        st = os.lstat(p)
        if os.path.abspath(str(p)) in foreign:
            return _St(st, uid=OTHER)
        return _St(st)

    return f


def _script(tmp_path, name="mint_copy.py"):
    d = tmp_path / "copy"
    d.mkdir(exist_ok=True)
    os.chmod(d, 0o755)
    s = d / name
    s.write_text("# stand-in\n", encoding="ascii")
    os.chmod(s, 0o644)
    return s


def _boot(tmp_path, **kw):
    if "script" not in kw:
        kw["script"] = str(_script(tmp_path))
    args = dict(euid=0, flags=GOOD, meta_path=[], path_hooks=[], path=[],
                modules={}, owners=OWN, lstat=_lstat(), site_dirs=[])
    args.update(kw)
    return M._s485_root_boot(**args)


def test_T01_boot_noop_for_non_root(tmp_path):
    mp = [importlib.machinery.PathFinder]
    assert _boot(tmp_path, euid=1000, meta_path=mp) is None
    assert mp == [importlib.machinery.PathFinder]


def test_T02_boot_refuses_root_without_isolated(tmp_path):
    flags = types.SimpleNamespace(isolated=0, safe_path=False, dont_write_bytecode=1)
    with pytest.raises(M.RootGuardError, match="-I -B"):
        _boot(tmp_path, flags=flags)


def test_T03_boot_refuses_root_without_dont_write_bytecode(tmp_path):
    flags = types.SimpleNamespace(isolated=1, safe_path=True, dont_write_bytecode=0)
    with pytest.raises(M.RootGuardError, match="-I -B"):
        _boot(tmp_path, flags=flags)


def test_T04_boot_removes_editable_finder_hook_placeholder(tmp_path):
    fake = type("_EditableFinder", (), {"__module__": "__editable___x_1_0_finder",
                                         "find_spec": classmethod(lambda c, *a, **k: None)})

    def hook(p):
        raise ImportError(p)

    hook.__module__ = "__editable___x_1_0_finder"
    mp = [importlib.machinery.PathFinder, fake]
    hooks = [hook]
    path = ["__editable__.x-1.0.finder.__path_hook__"]
    removed = _boot(tmp_path, meta_path=mp, path_hooks=hooks, path=path)
    assert len(removed) == 3
    assert fake not in mp and hook not in hooks
    assert not any(isinstance(p, str) and p.startswith("__editable__") for p in path)


def test_T05_boot_refuses_script_not_root_owned(tmp_path):
    s = _script(tmp_path)
    with pytest.raises(M.RootGuardError, match="not root-owned"):
        _boot(tmp_path, script=str(s), lstat=_lstat(foreign=[s]))


def test_T06_boot_refuses_script_dir_group_writable(tmp_path):
    s = _script(tmp_path)
    os.chmod(s.parent, 0o775)
    with pytest.raises(M.RootGuardError, match="writable by group or other"):
        _boot(tmp_path, script=str(s))


def test_T07_boot_refuses_link_in_lexical_chain_owned_by_other(tmp_path):
    s = _script(tmp_path)
    ld = tmp_path / "linkdir"
    ld.mkdir()
    os.chmod(ld, 0o755)
    (ld / "s.py").symlink_to(s)
    with pytest.raises(M.RootGuardError, match="not root-owned"):
        _boot(tmp_path, script=str(ld / "s.py"), lstat=_lstat(foreign=[ld]))


def test_T08_boot_refuses_sticky_world_writable_path_entry(tmp_path):
    e = tmp_path / "sticky8"
    e.mkdir()
    os.chmod(e, 0o1777)
    with pytest.raises(M.RootGuardError, match="writable by group or other"):
        _boot(tmp_path, path=[str(e)])


def test_T09_boot_refuses_missing_entry_under_writable_ancestor(tmp_path):
    w = tmp_path / "w9"
    w.mkdir()
    os.chmod(w, 0o777)
    with pytest.raises(M.RootGuardError, match="writable by group or other"):
        _boot(tmp_path, path=[str(w / "missing" / "deeper")])


def test_T10_boot_refuses_pth_not_root_owned(tmp_path):
    sd = tmp_path / "site10"
    sd.mkdir()
    os.chmod(sd, 0o755)
    pth = sd / "x.pth"
    pth.write_text("\n", encoding="ascii")
    os.chmod(pth, 0o644)
    with pytest.raises(M.RootGuardError, match="not root-owned"):
        _boot(tmp_path, site_dirs=[str(sd)], lstat=_lstat(foreign=[pth]))


def test_T11_boot_refuses_loaded_module_not_root_owned(tmp_path):
    f = tmp_path / "m11.py"
    f.write_text("\n", encoding="ascii")
    os.chmod(f, 0o644)
    mod = types.ModuleType("m11")
    mod.__file__ = str(f)
    with pytest.raises(M.RootGuardError, match="not root-owned"):
        _boot(tmp_path, modules={"m11": mod}, lstat=_lstat(foreign=[f]))


def _real(monkeypatch):
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(sys, "path_hooks", list(sys.path_hooks))
    monkeypatch.setattr(sys, "path", list(sys.path))


def _boot_real(monkeypatch, tmp_path, entry, foreign=()):
    _real(monkeypatch)
    sys.path.insert(0, str(entry))
    _boot(tmp_path, meta_path=sys.meta_path, path_hooks=sys.path_hooks, path=[str(entry)],
          lstat=_lstat(foreign=foreign))
    sys.path_importer_cache.clear()


def _pkgdir(tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    os.chmod(d, 0o755)
    return d


def test_T12_boot_installs_guard_first(monkeypatch, tmp_path):
    _boot_real(monkeypatch, tmp_path, _pkgdir(tmp_path, "e12"))
    assert isinstance(sys.meta_path[0], M._S485Guard)


def test_T13_guard_refuses_foreign_origin_and_module_does_not_run(monkeypatch, tmp_path):
    d = _pkgdir(tmp_path, "e13")
    sentinel = tmp_path / "ran13"
    m = d / "evil485t13.py"
    m.write_text("open(%r, 'w').close()\n" % str(sentinel), encoding="ascii")
    os.chmod(m, 0o644)
    _boot_real(monkeypatch, tmp_path, d, foreign=[m])
    with pytest.raises(ImportError, match="root guard"):
        importlib.import_module("evil485t13")
    assert not sentinel.exists()
    sys.modules.pop("evil485t13", None)


def test_T14_guard_refuses_writable_cache_dir(monkeypatch, tmp_path):
    d = _pkgdir(tmp_path, "e14")
    m = d / "mod485t14.py"
    m.write_text("X = 1\n", encoding="ascii")
    os.chmod(m, 0o644)
    c = d / "__pycache__"
    c.mkdir()
    os.chmod(c, 0o777)
    _boot_real(monkeypatch, tmp_path, d)
    with pytest.raises(ImportError, match="writable by group or other"):
        importlib.import_module("mod485t14")
    sys.modules.pop("mod485t14", None)


def test_T15_guard_refuses_foreign_namespace_location(monkeypatch, tmp_path):
    d = _pkgdir(tmp_path, "e15")
    ns = d / "ns485t15"
    ns.mkdir()
    os.chmod(ns, 0o755)
    _boot_real(monkeypatch, tmp_path, d, foreign=[ns])
    with pytest.raises(ImportError, match="not root-owned"):
        importlib.import_module("ns485t15")
    sys.modules.pop("ns485t15", None)


def test_T16_guard_allows_root_files_under_sticky_ancestor(monkeypatch, tmp_path):
    st = tmp_path / "st16"
    st.mkdir()
    os.chmod(st, 0o1777)
    d = st / "sub"
    d.mkdir()
    os.chmod(d, 0o755)
    m = d / "ok485t16.py"
    m.write_text("RAN = 16\n", encoding="ascii")
    os.chmod(m, 0o644)
    _boot_real(monkeypatch, tmp_path, d)
    mod = importlib.import_module("ok485t16")
    assert mod.RAN == 16
    sys.modules.pop("ok485t16", None)


def test_T17_check_refuses_when_guard_not_first(monkeypatch, tmp_path):
    _boot_real(monkeypatch, tmp_path, _pkgdir(tmp_path, "e17"))
    M._s485_root_check(euid=0, modules={}, meta_path=sys.meta_path, owners=OWN,
                       lstat=_lstat())
    g = sys.meta_path.pop(0)
    sys.meta_path.append(g)
    with pytest.raises(M.RootGuardError, match="not first"):
        M._s485_root_check(euid=0, modules={}, meta_path=sys.meta_path, owners=OWN,
                           lstat=_lstat())


def test_T18_boot_call_precedes_build_vsa_import():
    tree = ast.parse((_REPO / "mint_release_vsa.py").read_text(encoding="utf-8"))
    body = tree.body
    boot = [i for i, n in enumerate(body)
            if "_s485_root_boot()" in ast.unparse(n) and not isinstance(n, ast.FunctionDef)]
    imp = [i for i, n in enumerate(body)
           if isinstance(n, ast.Try) and any(isinstance(x, ast.Import)
                                             and any(a.name == "build_vsa" for a in x.names)
                                             for x in n.body)]
    assert boot and imp and boot[0] < imp[0]


def test_T19_mint_checks_before_reading_the_seed(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(M, "_s485_root_prepare", lambda command: calls.append("prepare:" + command))

    def seed(p):
        calls.append("seed")
        raise M.MintError("stop")

    monkeypatch.setattr(M, "_load_operator_seed", seed)
    with pytest.raises(M.MintError, match="stop"):
        M.mint("9.9.9", tmp_path / "out", key_path=tmp_path / "k", work_dir=tmp_path / "w")
    assert calls == ["prepare:mint", "seed"]


def test_T20_anchor_checks_before_network(monkeypatch, tmp_path):
    calls = []

    def prep(command):
        calls.append("prepare:" + command)
        raise M.MintError("stop20")

    monkeypatch.setattr(M, "_s485_root_prepare", prep)

    def net(*a, **k):
        calls.append("network")

    with pytest.raises(M.MintError, match="stop20"):
        M.anchor("9.9.9", tmp_path, pins_dir=tmp_path, anchor_fn=net, timestamp_fn=net,
                 verify_fn=net)
    assert calls == ["prepare:anchor"]


def test_T21_root1_child_argv_bare_env_without_python_vars(monkeypatch, tmp_path):
    (tmp_path / M.VERIFIER_VSA_FILENAME).write_text("{}", encoding="ascii")
    seen = {}

    def run(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env")
        return types.SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setenv("PYTHONPATH", "/nowhere")
    monkeypatch.setattr("subprocess.run", run)
    M._root1_self_verify(tmp_path, "x")
    assert len(seen["argv"]) == 2
    env = seen["env"]
    assert env is not None
    assert not [k for k in env if k.startswith("PYTHON")]
    assert set(env) <= {"PATH", "LANG"}


def test_T22_release_steps_name_a_root_owned_copy_and_I_B():
    src = (_REPO / "scripts" / "release.py").read_text(encoding="utf-8")
    assert "python3 -I -B <copy>/mint_release_vsa.py mint X.Y.Z" in src
    assert "python3 -I -B <copy>/mint_release_vsa.py anchor X.Y.Z" in src
    assert "root-owned copy staged from the tag" in src
    assert '"  4) mint:   python3 mint_release_vsa.py mint X.Y.Z --out /tmp/vsaX"' not in src


_ARGV = {
    "mint": lambda t: ["mint", "9.9.9", "--out", str(t / "out")],
    "anchor": lambda t: ["anchor", "9.9.9", "--dir", str(t), "--pins-dir", str(t)],
}
_LABEL = {"mint": "MINT REFUSED: ", "anchor": "ANCHOR REFUSED: "}


def _swallowed(monkeypatch, tmp_path, name):
    d = _pkgdir(tmp_path, "r_" + name)
    m = d / (name + ".py")
    m.write_text("X = 1\n", encoding="ascii")
    os.chmod(m, 0o644)
    _real(monkeypatch)
    sys.path.insert(0, str(d))
    sys.path_importer_cache.clear()
    g = M._S485Guard(list(sys.meta_path), owners=OWN, lstat=_lstat(foreign=[m]))
    try:
        g.find_spec(name)
    except ImportError:
        pass
    sys.meta_path.append(g)
    return g


@pytest.mark.parametrize("cmd", ["mint", "anchor"])
def test_T23_main_turns_a_guard_refusal_into_refused_exit_2(monkeypatch, tmp_path, capsys,
                                                            cmd):
    def boom(*a, **k):
        raise M._S485GuardImportError("root guard: x485t23: not root-owned", name="x485t23")

    monkeypatch.setattr(M, cmd, boom)
    assert M.main(_ARGV[cmd](tmp_path)) == 2
    err = capsys.readouterr().err
    assert err.startswith(_LABEL[cmd] + "root guard: x485t23: not root-owned")


def test_T25_main_lets_a_plain_import_error_through(monkeypatch, tmp_path):
    _real(monkeypatch)

    def boom(*a, **k):
        raise ImportError("plain485t25")

    monkeypatch.setattr(M, "mint", boom)
    with pytest.raises(ImportError, match="plain485t25") as ei:
        M.main(_ARGV["mint"](tmp_path))
    assert not isinstance(ei.value, M._S485GuardImportError)


def test_T26_a_swallowed_refusal_fails_the_next_check(monkeypatch, tmp_path):
    d = _pkgdir(tmp_path, "e26")
    m = d / "evil485t26.py"
    m.write_text("X = 1\n", encoding="ascii")
    os.chmod(m, 0o644)
    _boot_real(monkeypatch, tmp_path, d, foreign=[m])
    try:
        importlib.import_module("evil485t26")
    except ImportError:
        pass
    assert "evil485t26" not in sys.modules
    with pytest.raises(M.RootGuardError, match="imports refused: evil485t26: "):
        M._s485_root_check(euid=0, modules={}, meta_path=sys.meta_path, owners=OWN,
                           lstat=_lstat())


@pytest.mark.parametrize("cmd", ["mint", "anchor"])
def test_T27_main_refuses_when_a_refusal_was_swallowed(monkeypatch, tmp_path, capsys, cmd):
    name = "evil485t27" + cmd
    _swallowed(monkeypatch, tmp_path, name)
    monkeypatch.setattr(M, cmd, lambda *a, **k: 0)
    assert M.main(_ARGV[cmd](tmp_path)) == 2
    err = capsys.readouterr().err
    assert err.startswith(_LABEL[cmd] + "root guard: imports refused: " + name + ": ")


def test_T28_main_refuses_when_a_refusal_ends_in_another_error(monkeypatch, tmp_path, capsys):
    _swallowed(monkeypatch, tmp_path, "evil485t28")

    def boom(*a, **k):
        raise RuntimeError("wrapped485t28")

    monkeypatch.setattr(M, "mint", boom)
    assert M.main(_ARGV["mint"](tmp_path)) == 2
    err = capsys.readouterr().err
    assert err.startswith("MINT REFUSED: root guard: imports refused: evil485t28: ")
    assert "RuntimeError: wrapped485t28" in err


def test_T29_boot_tests_do_not_walk_the_host_sys_path(monkeypatch, tmp_path):
    w = tmp_path / "x777"
    w.mkdir()
    os.chmod(w, 0o777)
    _real(monkeypatch)
    sys.path.append(str(w / "python3xx.zip"))
    _boot_real(monkeypatch, tmp_path, _pkgdir(tmp_path, "e29"))
    assert isinstance(sys.meta_path[0], M._S485Guard)


_DRIVER = """import os, re, sys
mint, stub = sys.argv[1], sys.argv[2]
foreign = {os.path.join(stub, n + ".py") for n in sys.argv[3:]}
src = open(mint, encoding="utf-8").read()
m = re.search(r"^try:.*\\n    import build_vsa\\n", src, re.M)
if m is None:
    sys.exit(97)
ns = {"__name__": "mint_head", "__file__": mint}
exec(compile(src[:m.start()], mint, "exec"), ns)
sys.path.insert(0, stub)


class _St:
    def __init__(self, st, uid):
        self.st_uid, self.st_gid, self.st_mode = uid, st.st_gid, st.st_mode


def lstat(p):
    st = os.lstat(p)
    return _St(st, 54321 if os.path.abspath(p) in foreign else st.st_uid)


sys.meta_path.insert(0, ns["_S485Guard"](list(sys.meta_path), owners=(0, os.geteuid()),
                                         lstat=lstat))
block = src[m.start():src.index("\\nDEFAULT_OPERATOR_KEY")]
exec(compile(block, mint, "exec"), ns)
print("NOT_REFUSED")
"""


def _module_level(tmp_path, build_vsa_src, extra=None, foreign=()):
    stub = tmp_path / "stub"
    stub.mkdir()
    os.chmod(stub, 0o755)
    (stub / "build_vsa.py").write_text(build_vsa_src, encoding="ascii")
    for n, s in (extra or {}).items():
        (stub / (n + ".py")).write_text(s, encoding="ascii")
    drv = tmp_path / "drv.py"
    drv.write_text(_DRIVER, encoding="ascii")
    import subprocess
    return subprocess.run([sys.executable, str(drv), str(_REPO / "mint_release_vsa.py"),
                           str(stub)] + list(foreign), capture_output=True, text=True,
                          cwd=str(tmp_path))


def test_T30_module_level_refusal_is_refused_exit_2(tmp_path):
    ran = tmp_path / "ran30"
    r = _module_level(tmp_path, "open(%r, 'w').close()\n" % str(ran), foreign=["build_vsa"])
    assert r.returncode == 2, (r.returncode, r.stderr[-400:])
    assert r.stderr.startswith("MINT REFUSED: root guard: imports refused: build_vsa: "
                               "not root-owned: ")
    assert "Traceback" not in r.stderr and not ran.exists()


def test_T31_module_level_refusal_caught_then_another_error_exit_2(tmp_path):
    ran = tmp_path / "ran31"
    r = _module_level(tmp_path,
                      "try:\n    import evil485t31\nexcept ImportError:\n    pass\n"
                      "raise RuntimeError('wrapped485t31')\n",
                      extra={"evil485t31": "open(%r, 'w').close()\n" % str(ran)},
                      foreign=["evil485t31"])
    assert r.returncode == 2, (r.returncode, r.stderr[-400:])
    assert r.stderr.startswith("MINT REFUSED: root guard: imports refused: evil485t31: ")
    assert not ran.exists()


def test_T32_module_level_error_without_refusal_propagates(tmp_path):
    r = _module_level(tmp_path, "raise RuntimeError('plain485t32')\n")
    assert r.returncode == 1
    assert "RuntimeError: plain485t32" in r.stderr and "MINT REFUSED" not in r.stderr


def test_T33_own_dir_makes_and_accepts_a_fresh_dir(tmp_path):
    d = tmp_path / "out33"
    M._s485_own_dir(d, "t33", create=True, euid=0, owners=OWN, lstat=_lstat())
    assert d.is_dir()


def test_T34_own_dir_refuses_a_dir_of_another_owner(tmp_path):
    d = tmp_path / "out34"
    d.mkdir()
    os.chmod(d, 0o755)
    with pytest.raises(M.MintError, match=r"^root guard \(t34\): not root-owned: "):
        M._s485_own_dir(d, "t34", create=True, euid=0, owners=OWN, lstat=_lstat(foreign=[d]))


def test_T35_own_dir_refuses_a_sticky_world_writable_parent(tmp_path):
    st = tmp_path / "st35"
    st.mkdir()
    os.chmod(st, 0o1777)
    d = st / "out35"
    with pytest.raises(M.MintError, match=r"writable by group or other: .*st35 \(1777\)"):
        M._s485_own_dir(d, "t35", create=True, euid=0, owners=OWN, lstat=_lstat())
    assert not d.exists()


def test_T36_own_dir_does_nothing_for_another_euid(tmp_path):
    d = tmp_path / "x36" / "out36"
    M._s485_own_dir(d, "t36", create=True, euid=1000, owners=OWN,
                    lstat=_lstat(foreign=[tmp_path]))
    assert not d.exists() and not (tmp_path / "x36").exists()


def test_T37_mint_checks_both_dirs_before_its_first_mkdir():
    src = (_REPO / "mint_release_vsa.py").read_text(encoding="utf-8")
    body = src[src.index("def mint("):src.index("def _root1_self_verify")]
    order = [body.index('_s485_checkpoint("mint: before the first write")'),
             body.index('_s485_own_dir(out_dir, "mint: the out dir", create=True)'),
             body.index('_s485_own_dir(work_dir, "mint: the work dir", create=True)'),
             body.index("work_dir.mkdir(parents=True, exist_ok=True)")]
    assert order == sorted(order)


def test_T38_anchor_checks_its_dir_after_prepare_before_network(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(M, "_s485_root_prepare", lambda command: calls.append("prepare:" + command))

    def own(d, what, *, create, **kw):
        calls.append("own:%s:%s" % (what, create))
        raise M.MintError("stop38")

    monkeypatch.setattr(M, "_s485_own_dir", own)

    def net(*a, **k):
        calls.append("network")

    with pytest.raises(M.MintError, match="stop38"):
        M.anchor("9.9.9", tmp_path / "d38", pins_dir=tmp_path, anchor_fn=net, timestamp_fn=net,
                 verify_fn=net)
    assert calls == ["prepare:anchor", "own:anchor: the dir:False"]


@pytest.mark.parametrize("cmd", ["mint", "anchor"])
def test_T39_a_mint_error_after_a_kept_refusal_names_it(monkeypatch, tmp_path, capsys, cmd):
    name = "evil485t39" + cmd
    _swallowed(monkeypatch, tmp_path, name)

    def boom(*a, **k):
        raise M.MintError("other cause 39")

    monkeypatch.setattr(M, cmd, boom)
    assert M.main(_ARGV[cmd](tmp_path)) == 2
    err = capsys.readouterr().err
    assert err.startswith(_LABEL[cmd] + "other cause 39; root guard: imports refused: "
                          + name + ": ")
    kept = M._s485_refused()

    def boom2(*a, **k):
        raise M.MintError("root guard (x): imports refused: " + "; ".join(kept))

    monkeypatch.setattr(M, cmd, boom2)
    assert M.main(_ARGV[cmd](tmp_path)) == 2
    err2 = capsys.readouterr().err
    assert "; root guard: imports refused:" not in err2
    assert err2.count(kept[0]) == 1


@pytest.mark.parametrize("cmd", ["mint", "anchor"])
def test_T40_system_exit_after_a_kept_refusal_exits_2(monkeypatch, tmp_path, capsys, cmd):
    name = "evil485t40" + cmd
    _swallowed(monkeypatch, tmp_path, name)

    def boom(*a, **k):
        raise SystemExit(0)

    monkeypatch.setattr(M, cmd, boom)
    assert M.main(_ARGV[cmd](tmp_path)) == 2
    err = capsys.readouterr().err
    assert err.startswith(_LABEL[cmd] + "root guard: imports refused: " + name + ": ")
    assert "(then SystemExit: 0)" in err


def test_T41_keyboard_interrupt_after_a_kept_refusal_propagates(monkeypatch, tmp_path):
    _swallowed(monkeypatch, tmp_path, "evil485t41")

    def boom(*a, **k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(M, "mint", boom)
    with pytest.raises(KeyboardInterrupt):
        M.main(_ARGV["mint"](tmp_path))


def test_T42_release_steps_name_a_root_only_bundle_dir():
    src = (_REPO / "scripts" / "release.py").read_text(encoding="utf-8")
    assert "mint X.Y.Z --out /root/nous-vsa/X.Y.Z" in src
    assert "anchor X.Y.Z --dir /root/nous-vsa/X.Y.Z" in src
    assert "/tmp/vsaX" not in src
