"""S485 SD2: release.py normalizes the sdist after the build (FG-S481-L).

Two runner builds of one commit at one SOURCE_DATE_EPOCH gave two
sdists whose members were equal and whose archive metadata (gzip time,
member mtimes, owners) differed. normalize_sdist re-packs the sdist so
its bytes depend only on its members, the epoch and the deflate
library; sdist_content_digest is the identity that crosses hosts.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import struct
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_RELEASE = REPO / "scripts" / "release.py"
EPOCH = 1794833750


def _load():
    spec = importlib.util.spec_from_file_location("_s485_release", _RELEASE)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _member(name, data=b"", mode=0o644, mtime=1000, uid=1001, uname="runner",
            kind=tarfile.REGTYPE, link=""):
    t = tarfile.TarInfo(name)
    t.type = kind
    t.mode, t.mtime, t.uid, t.gid, t.uname, t.gname = mode, mtime, uid, uid, uname, uname
    t.linkname = link
    t.size = len(data) if kind == tarfile.REGTYPE else 0
    return t, (io.BytesIO(data) if kind == tarfile.REGTYPE else None)


def _sdist(path, members, gz_mtime=12345):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:", format=tarfile.PAX_FORMAT) as tf:
        for t, f in members:
            tf.addfile(t, f)
    with open(path, "wb") as fh:
        with gzip.GzipFile(filename="x.tar", mode="wb", fileobj=fh, mtime=gz_mtime) as g:
            g.write(raw.getvalue())
    return path


def _basic(order=1, mtime=1000, uid=1001, uname="runner"):
    ms = [_member("p-1/", kind=tarfile.DIRTYPE, mode=0o775, mtime=mtime, uid=uid, uname=uname),
          _member("p-1/a.py", b"print(1)\n", mtime=mtime, uid=uid, uname=uname),
          _member("p-1/PKG-INFO", b"Name: p\n", mtime=mtime + 7, uid=uid, uname=uname),
          _member("p-1/bin/run.sh", b"#!/bin/sh\n", mode=0o775, mtime=mtime, uid=uid, uname=uname)]
    return ms if order == 1 else list(reversed(ms))


def _read(path):
    raw = Path(path).read_bytes()
    tf = tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)), mode="r:")
    return raw, tf.getmembers()


def test_U01_two_builds_normalize_to_equal_bytes(tmp_path):
    R = _load()
    a = _sdist(tmp_path / "a.tar.gz", _basic(1, 1000, 1001, "runner"), 11)
    b = _sdist(tmp_path / "b.tar.gz", _basic(2, 2000, 0, "root"), 22)
    assert a.read_bytes() != b.read_bytes()
    R.normalize_sdist(a, EPOCH)
    R.normalize_sdist(b, EPOCH)
    assert a.read_bytes() == b.read_bytes()


def test_U02_normalized_fields(tmp_path):
    R = _load()
    a = _sdist(tmp_path / "a.tar.gz", _basic(2), 11)
    R.normalize_sdist(a, EPOCH)
    raw, ms = _read(a)
    assert [m.name for m in ms] == sorted(m.name for m in ms)
    assert {m.mtime for m in ms} == {EPOCH}
    assert {(m.uid, m.gid, m.uname, m.gname) for m in ms} == {(0, 0, "", "")}
    assert {m.mode for m in ms} <= {0o644, 0o755}
    assert raw[3] & 8 == 0
    assert struct.unpack("<I", raw[4:8])[0] == EPOCH


@pytest.mark.parametrize("bad", ["link"])
def test_U03_link_member_refused_file_unchanged(tmp_path, bad):
    R = _load()
    ms = _basic() + [_member("p-1/l", kind=tarfile.SYMTYPE, link="/etc/passwd")]
    a = _sdist(tmp_path / "a.tar.gz", ms)
    before = a.read_bytes()
    with pytest.raises(R.ReleaseError):
        R.normalize_sdist(a, EPOCH)
    assert a.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.tar.gz"]


def test_U04_duplicate_name_refused_file_unchanged(tmp_path):
    R = _load()
    ms = _basic() + [_member("p-1/a.py", b"other\n")]
    a = _sdist(tmp_path / "a.tar.gz", ms)
    before = a.read_bytes()
    with pytest.raises(R.ReleaseError):
        R.normalize_sdist(a, EPOCH)
    assert a.read_bytes() == before


@pytest.mark.parametrize("name", ["/abs/x.py", "p-1/../../x.py"])
def test_U05_absolute_or_dotdot_refused_file_unchanged(tmp_path, name):
    R = _load()
    a = _sdist(tmp_path / "a.tar.gz", _basic() + [_member(name, b"x\n")])
    before = a.read_bytes()
    with pytest.raises(R.ReleaseError):
        R.normalize_sdist(a, EPOCH)
    assert a.read_bytes() == before


def test_U06_phase_build_normalizes_the_sdist_only(tmp_path, monkeypatch, capsys):
    R = _load()
    dist = tmp_path / "dist"
    monkeypatch.setattr(R, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(R, "DIST_DIR", dist)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    whl_bytes = b"PK\x05\x06" + b"\0" * 18

    def fake_run(cmd, cwd=None, check=True):
        dist.mkdir()
        (dist / "nous_lang-0.0.1-py3-none-any.whl").write_bytes(whl_bytes)
        _sdist(dist / "nous_lang-0.0.1.tar.gz", _basic(2), 99)
    monkeypatch.setattr(R, "run", fake_run)
    whl, sdist = R.phase_build()
    out = capsys.readouterr().out
    assert whl.read_bytes() == whl_bytes
    raw, ms = _read(sdist)
    assert struct.unpack("<I", raw[4:8])[0] == EPOCH
    assert {m.mtime for m in ms} == {EPOCH}
    assert "SDIST_CONTENT_DIGEST " + R.sdist_content_digest(sdist) in out


def test_U07_build_epoch_from_environment(monkeypatch):
    R = _load()
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1794833750")
    assert R.build_epoch() == (1794833750, "SOURCE_DATE_EPOCH")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "17948x")
    e, src = R.build_epoch()
    assert src != "SOURCE_DATE_EPOCH"


def test_U08_execute_bit_maps_to_755(tmp_path):
    R = _load()
    a = _sdist(tmp_path / "a.tar.gz", _basic())
    R.normalize_sdist(a, EPOCH)
    _, ms = _read(a)
    modes = {m.name: m.mode for m in ms}
    assert modes["p-1/bin/run.sh"] == 0o755
    assert modes["p-1/a.py"] == 0o644
    assert modes.get("p-1/", modes.get("p-1")) == 0o755


def test_U09_content_digest_unchanged(tmp_path):
    R = _load()
    a = _sdist(tmp_path / "a.tar.gz", _basic(2), 11)
    d0 = R.sdist_content_digest(a)
    d1 = R.normalize_sdist(a, EPOCH)
    assert d0 == d1 == R.sdist_content_digest(a)
    assert len(d0) == 64 and int(d0, 16) >= 0


def test_U10_call_follows_the_build_in_phase_build():
    src = _RELEASE.read_text(encoding="utf-8")
    body = src[src.index("def phase_build"):src.index("def phase_wheel_gate")]
    assert "__s485_sdist_normalize_v1__" in src
    i = body.index('run(["python3", "-m", "build"]')
    j = body.index("normalize_sdist(")
    assert i < j
    assert hashlib.sha256(src.encode()).hexdigest()
