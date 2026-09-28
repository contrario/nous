"""
S386 anchor journal: docs/ANCHOR_JOURNAL_DESIGN.md sections 13 and 14.

Drives mint_release_vsa.anchor() through its seams with a replay of the
published 6.0.1 bundle. Seams that fail call the real Rekor and TSA clients
over an httpx.MockTransport, so each exception and its cause are the ones
the live clients raise. No network, no Rekor write.

# __s387_test_anchor_journal_v1__
"""
from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest

import cli_verify_release
import mint_release_vsa as M
import rekor_anchor_v2
import tsa_client
from rekor_verify_v2 import RekorAnchorV2

_REPO = Path(__file__).resolve().parent.parent
_RVSA = _REPO / "website" / ".well-known" / "nous" / "release-vsa"
_VER = "6.0.1"
_OTHER_VER = "6.0.0"
_REF = _RVSA / _VER
_OTHER = _RVSA / _OTHER_VER
_VSA_NAME = "nous_lang-" + _VER + ".build-vsa.intoto.json"
_BUNDLE_NAME = "nous_lang-" + _VER + ".rekor-v2-bundle.json"
_MINTED = (
    _VSA_NAME,
    "build-vsa.intoto.json",
    "verify_build_vsa_offline.py",
    "release-verifier-key.json",
)
_AFTER_MINT = sorted(n for m in _MINTED for n in (m, m + ".sha256"))
_AFTER_ANCHOR = sorted(
    _AFTER_MINT
    + [_BUNDLE_NAME, _BUNDLE_NAME + ".sha256", "index.json", "index.json.sha256"]
)
_REPLAY_LOG_ID = "s387-replay-log-id"
_REAL_ANCHOR = rekor_anchor_v2.anchor_manifest_to_rekor_v2
_REAL_TSA = tsa_client.anchor_timestamp

pytestmark = pytest.mark.skipif(
    not (_REF.is_dir() and _OTHER.is_dir()),
    reason="6.0.1 / 6.0.0 release-VSA reference dirs not present (clean-venv/sdist)",
)


def _published_bundle(ref: Path, ver: str) -> dict[str, Any]:
    name = "nous_lang-" + ver + ".rekor-v2-bundle.json"
    return json.loads((ref / name).read_text(encoding="utf-8"))


def _published_gen_time() -> str:
    index = json.loads((_REF / "index.json").read_text(encoding="utf-8"))
    for art in index["artifacts"]:
        if art.get("kind") == "rekor_v2_transparency_log":
            return str(art["rfc3161GenTime"])
    raise AssertionError("published 6.0.1 index has no rekor artifact")


def _replay(ref: Path, ver: str) -> RekorAnchorV2:
    tle = _published_bundle(ref, ver)["transparency_log_entry"]
    ip = tle["inclusion_proof"]
    return RekorAnchorV2(
        log_id=_REPLAY_LOG_ID,
        log_index=int(tle["log_index"]),
        body_b64=str(tle["canonicalized_body"]),
        checkpoint_envelope=str(ip["checkpoint"]),
        inclusion_proof_hashes=[str(h) for h in ip["hashes"]],
    )


def _vsa_sha(ref: Path, ver: str) -> str:
    name = "nous_lang-" + ver + ".build-vsa.intoto.json"
    return M.vsa_payload_sha256(json.loads((ref / name).read_text(encoding="utf-8")))


def _raising_client(exc_type: type[httpx.TransportError]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("synthetic " + exc_type.__name__, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _status_client(status: int) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="synthetic status " + str(status))

    return httpx.Client(transport=httpx.MockTransport(handler))


_POST_ERRORS: dict[str, type[httpx.TransportError]] = {
    "connect_error": httpx.ConnectError,
    "connect_timeout": httpx.ConnectTimeout,
    "read_timeout": httpx.ReadTimeout,
}


class _Seams:
    def __init__(self, *, post: list[str], tsa: list[str], verify: list[str]) -> None:
        self.post_plan = list(post)
        self.tsa_plan = list(tsa)
        self.verify_plan = list(verify)
        self.posts = 0
        self.tsa_calls = 0
        self.verify_calls = 0
        self.token = base64.b64decode(_published_bundle(_REF, _VER)["rfc3161_timestamp"])
        self.gen_time = _published_gen_time()

    def anchor_fn(self, canonical: bytes, **kw: Any) -> RekorAnchorV2:
        self.posts += 1
        step = self.post_plan.pop(0) if self.post_plan else "ok"
        if step == "ok":
            return _replay(_REF, _VER)
        if step == "http409":
            with _status_client(409) as client:
                return _REAL_ANCHOR(canonical, client=client, base_url="https://rekor.invalid")
        with _raising_client(_POST_ERRORS[step]) as client:
            return _REAL_ANCHOR(canonical, client=client, base_url="https://rekor.invalid")

    def timestamp_fn(self, *, timestamped_data: bytes, **kw: Any) -> bytes:
        self.tsa_calls += 1
        step = self.tsa_plan.pop(0) if self.tsa_plan else "ok"
        if step == "ok":
            return self.token
        with _status_client(500) as client:
            return _REAL_TSA(
                timestamped_data=timestamped_data,
                client=client,
                base_url="https://tsa.invalid",
            )

    def verify_fn(self, bundle_dir: str, pins_dir: str) -> dict[str, Any]:
        self.verify_calls += 1
        status = self.verify_plan.pop(0) if self.verify_plan else "PASS"
        return {
            "convergence": status,
            "evidence": {"rfc3161_gen_time": self.gen_time},
            "legs": {"root2_inclusion": {"status": status}},
        }

    def calls(self) -> tuple[int, int, int]:
        return (self.posts, self.tsa_calls, self.verify_calls)


def _mint_dir(tmp_path: Path) -> tuple[Path, Path]:
    d = tmp_path / "out"
    d.mkdir()
    for name in _AFTER_MINT:
        shutil.copy2(_REF / name, d / name)
    pins = tmp_path / "pins"
    pins.mkdir()
    (pins / "trusted_root.json").write_text("{}", encoding="utf-8")
    (pins / "tsa_chain.pem").write_text("x", encoding="utf-8")
    return d, pins


def _journal_path(d: Path) -> Path:
    r = d.resolve()
    return r.parent / (r.name + ".anchor-journal.json")


def _names(d: Path) -> list[str]:
    return sorted(p.name for p in d.iterdir())


def _run(d: Path, pins: Path, s: _Seams) -> Any:
    try:
        return M.anchor(
            _VER,
            d,
            pins_dir=pins,
            anchor_fn=s.anchor_fn,
            timestamp_fn=s.timestamp_fn,
            verify_fn=s.verify_fn,
        )
    except Exception as exc:
        return exc


def _logged_record(*, version: str, payload_sha: str, entry: RekorAnchorV2) -> dict[str, Any]:
    return {
        "canonicalizedBody": entry.body_b64,
        "checkpointEnvelope": entry.checkpoint_envelope,
        "inclusionProofHashes": list(entry.inclusion_proof_hashes),
        "logId": entry.log_id,
        "logIndex": entry.log_index,
        "rekorBaseUrl": None,
        "schemaVersion": 1,
        "state": "LOGGED",
        "version": version,
        "vsaPayloadSha256": payload_sha,
    }


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")


def _same_bundle(d: Path) -> bool:
    return (d / _BUNDLE_NAME).read_bytes() == (_REF / _BUNDLE_NAME).read_bytes()


def test_tsa_failure_after_post_then_rerun_posts_once(tmp_path: Path) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=["http500"], verify=[])
    first = _run(d, pins, s)
    second = _run(d, pins, s)
    assert s.posts == 1, "a rerun after a TSA failure POSTed again: " + str(s.posts) + " POSTs"
    assert isinstance(first, M.MintError), "TSA failure escaped as " + repr(first)
    assert str(first).startswith("TSA timestamp failed"), str(first)
    assert second == 0, repr(second)
    assert s.tsa_calls == 2, str(s.tsa_calls)
    assert _same_bundle(d), "resumed bundle differs from the published 6.0.1 bundle"
    assert _names(d) == _AFTER_ANCHOR, _names(d)


@pytest.mark.parametrize("failure", ["read_timeout", "http409"])
def test_unknown_post_outcome_then_rerun_refuses_without_post(tmp_path: Path, failure: str) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=[failure], tsa=[], verify=[])
    first = _run(d, pins, s)
    second = _run(d, pins, s)
    assert s.posts == 1, "a rerun after an unknown Rekor outcome POSTed again: " + str(s.posts)
    assert (s.tsa_calls, s.verify_calls) == (0, 0), str(s.calls())
    assert isinstance(first, M.MintError), "unknown POST outcome escaped as " + repr(first)
    assert isinstance(second, M.MintError), repr(second)
    assert str(first).startswith("rekor outcome unknown"), str(first)
    assert str(second).startswith("rekor outcome unknown"), str(second)
    journal = json.loads(_journal_path(d).read_bytes())
    assert journal["state"] == "ATTEMPTED", journal["state"]
    assert _names(d) == _AFTER_MINT, _names(d)


@pytest.mark.parametrize("cause", ["connect_error", "connect_timeout"])
def test_post_that_never_left_the_host_removes_journal_and_rerun_submits_once(
    tmp_path: Path, cause: str
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=[cause], tsa=[], verify=[])
    first = _run(d, pins, s)
    assert isinstance(first, M.MintError), "a POST that never left the host escaped as " + repr(first)
    head = "rekor submit failed before any request left the host"
    assert str(first).startswith(head), str(first)
    assert not _journal_path(d).exists(), "journal left behind after " + cause
    assert _names(d) == _AFTER_MINT, _names(d)
    second = _run(d, pins, s)
    assert second == 0, repr(second)
    assert s.calls() == (2, 1, 1), str(s.calls())
    assert _names(d) == _AFTER_ANCHOR, _names(d)


def test_verify_failure_after_bundle_then_rerun_finishes_without_network(tmp_path: Path) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=["ok"], verify=["FAIL"])
    first = _run(d, pins, s)
    assert isinstance(first, M.MintError), repr(first)
    assert (d / _BUNDLE_NAME).is_file(), "bundle not written before the verify"
    assert not (d / "index.json").exists(), "index written after a failed verify"
    second = _run(d, pins, s)
    assert second == 0, "no way to finish after a verify failure: " + repr(second)
    assert s.calls() == (1, 1, 2), str(s.calls())
    assert _same_bundle(d), "bundle changed by the resume"
    assert _names(d) == _AFTER_ANCHOR, _names(d)


@pytest.mark.parametrize("sidecar", ["missing", "different", "unwritable"])
def test_logged_resume_with_bundle_checks_its_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sidecar: str
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=["ok"], verify=["FAIL"])
    first = _run(d, pins, s)
    assert isinstance(first, M.MintError), repr(first)
    side = d / (_BUNDLE_NAME + ".sha256")
    if sidecar == "unwritable":
        side.unlink()
        real_atomic = M._atomic_write

        def failing_atomic(path: Path, data: bytes) -> None:
            if path.name == side.name:
                raise OSError("synthetic write failure on " + path.name)
            real_atomic(path, data)

        monkeypatch.setattr(M, "_atomic_write", failing_atomic)
        second = _run(d, pins, s)
        assert isinstance(second, M.MintError), repr(second)
        assert str(second).startswith("cannot write the rekor bundle sidecar"), str(second)
        assert s.calls() == (1, 1, 1), str(s.calls())
        return
    if sidecar == "missing":
        side.unlink()
    else:
        other = (_OTHER / ("nous_lang-" + _OTHER_VER + ".rekor-v2-bundle.json")).read_bytes()
        side.write_bytes((M._sha256_hex(other) + "  " + _BUNDLE_NAME + "\n").encode("ascii"))
    second = _run(d, pins, s)
    if sidecar == "missing":
        assert second == 0, repr(second)
        good = M._sha256_hex((d / _BUNDLE_NAME).read_bytes()) + "  " + _BUNDLE_NAME + "\n"
        assert side.read_bytes() == good.encode("ascii"), side.read_bytes()
        assert _names(d) == _AFTER_ANCHOR, _names(d)
    else:
        assert isinstance(second, M.MintError), repr(second)
        head = "rekor bundle sidecar does not match the bundle"
        assert str(second).startswith(head), str(second)
        assert not (d / "index.json").exists(), "index written over a mismatched sidecar"
    assert s.calls()[:2] == (1, 1), str(s.calls())


@pytest.mark.parametrize("bundle", ["foreign", "unreadable"])
def test_logged_resume_refuses_a_bundle_that_does_not_match_the_journal(tmp_path: Path, bundle: str) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=["ok"], verify=["FAIL"])
    first = _run(d, pins, s)
    assert isinstance(first, M.MintError), repr(first)
    if bundle == "foreign":
        data = (_OTHER / ("nous_lang-" + _OTHER_VER + ".rekor-v2-bundle.json")).read_bytes()
        head = "rekor bundle does not match the anchor journal"
    else:
        data = (d / _BUNDLE_NAME).read_bytes()[:-2]
        head = "rekor bundle unreadable"
    (d / _BUNDLE_NAME).write_bytes(data)
    (d / (_BUNDLE_NAME + ".sha256")).write_bytes(
        (M._sha256_hex(data) + "  " + _BUNDLE_NAME + "\n").encode("ascii")
    )
    second = _run(d, pins, s)
    assert isinstance(second, M.MintError), repr(second)
    assert str(second).startswith(head), str(second)
    assert s.calls() == (1, 1, 1), str(s.calls())
    assert not (d / "index.json").exists(), "index written over a foreign bundle"


def test_network_failure_through_main_is_anchor_refused_rc2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=["http500"], verify=[])
    monkeypatch.setattr(rekor_anchor_v2, "anchor_manifest_to_rekor_v2", s.anchor_fn)
    monkeypatch.setattr(tsa_client, "anchor_timestamp", s.timestamp_fn)
    monkeypatch.setattr(cli_verify_release, "verify_convergence", s.verify_fn)
    argv = ["anchor", _VER, "--dir", str(d), "--pins-dir", str(pins)]
    rc: Any
    try:
        rc = M.main(argv)
    except Exception as exc:
        rc = exc
    err = capsys.readouterr().err
    assert rc == 2, "main() let a network failure escape: " + repr(rc)
    assert err.startswith("ANCHOR REFUSED: TSA timestamp failed"), err[:200]
    journal = json.loads(_journal_path(d).read_bytes())
    assert journal["state"] == "LOGGED", journal["state"]
    assert journal["rekorBaseUrl"] == rekor_anchor_v2.REKOR_V2_DEFAULT_BASE_URL, journal["rekorBaseUrl"]
    assert M.main(argv) == 0
    assert s.calls() == (1, 2, 1), str(s.calls())
    assert _names(d) == _AFTER_ANCHOR, _names(d)


def test_success_leaves_logged_journal_beside_dir_and_exact_names(tmp_path: Path) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=["ok"], verify=["PASS"])
    rc = M.anchor(
        _VER, d, pins_dir=pins, anchor_fn=s.anchor_fn, timestamp_fn=s.timestamp_fn, verify_fn=s.verify_fn
    )
    assert rc == 0
    jp = _journal_path(d)
    assert jp.is_file(), "no anchor journal beside " + str(d)
    raw = jp.read_bytes()
    expected = _logged_record(version=_VER, payload_sha=_vsa_sha(_REF, _VER), entry=_replay(_REF, _VER))
    assert json.loads(raw) == expected
    assert raw == _canonical(expected), "journal bytes are not canonical JSON"
    assert _same_bundle(d), "bundle differs from the published 6.0.1 bundle"
    assert _names(d) == _AFTER_ANCHOR, _names(d)
    assert _names(tmp_path) == sorted(["out", "out.anchor-journal.json", "pins"]), _names(tmp_path)
    again = _run(d, pins, s)
    assert isinstance(again, M.MintError), repr(again)
    assert str(again).startswith("rekor bundle already exists"), str(again)
    assert s.calls() == (1, 1, 1), str(s.calls())


def test_logged_journal_for_a_foreign_entry_refused_without_network(tmp_path: Path) -> None:
    assert _vsa_sha(_OTHER, _OTHER_VER) != _vsa_sha(_REF, _VER), "control: 6.0.0 and 6.0.1 share a payload"
    d, pins = _mint_dir(tmp_path)
    record = _logged_record(
        version=_VER, payload_sha=_vsa_sha(_REF, _VER), entry=_replay(_OTHER, _OTHER_VER)
    )
    _journal_path(d).write_bytes(_canonical(record))
    s = _Seams(post=[], tsa=[], verify=[])
    out = _run(d, pins, s)
    assert s.calls() == (0, 0, 0), "a seam ran with a journal that binds another VSA: " + str(s.calls())
    assert isinstance(out, M.MintError), repr(out)
    assert str(out).startswith("journaled rekor entry does not bind this VSA"), str(out)
    assert _names(d) == _AFTER_MINT, _names(d)


@pytest.mark.parametrize("case", ["unparseable", "unknown_state", "other_version", "other_payload"])
def test_foreign_or_unreadable_journal_refused_without_network(tmp_path: Path, case: str) -> None:
    d, pins = _mint_dir(tmp_path)
    entry = _replay(_REF, _VER)
    good = _logged_record(version=_VER, payload_sha=_vsa_sha(_REF, _VER), entry=entry)
    if case == "unparseable":
        data = _canonical(good)[:-1]
    elif case == "unknown_state":
        data = _canonical(dict(good, state="LOGGED_" + _vsa_sha(_REF, _VER)[:8]))
    elif case == "other_version":
        data = _canonical(dict(good, version=_OTHER_VER))
    else:
        data = _canonical(dict(good, vsaPayloadSha256=_vsa_sha(_OTHER, _OTHER_VER)))
    _journal_path(d).write_bytes(data)
    s = _Seams(post=[], tsa=[], verify=[])
    out = _run(d, pins, s)
    assert s.calls() == (0, 0, 0), "a seam ran with a " + case + " journal: " + str(s.calls())
    assert isinstance(out, M.MintError), repr(out)
    assert str(out).startswith("anchor journal "), str(out)
    assert _journal_path(d).read_bytes() == data, "the tool changed a journal it refused"
    assert _names(d) == _AFTER_MINT, _names(d)


@pytest.mark.parametrize("when", ["nothing_written", "written_then_failed", "left_behind"])
def test_journal_write_failure_before_post_makes_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=[], tsa=[], verify=[])
    real_write = M._write_journal
    real_remove = M._remove_journal
    fired = []

    def failing_write(path: Path, record: dict[str, Any]) -> None:
        if not fired:
            fired.append(record["state"])
            if when != "nothing_written":
                real_write(path, record)
            raise OSError("synthetic journal write failure")
        real_write(path, record)

    def failing_remove(path: Path) -> None:
        raise OSError("synthetic journal remove failure")

    monkeypatch.setattr(M, "_write_journal", failing_write)
    if when == "left_behind":
        monkeypatch.setattr(M, "_remove_journal", failing_remove)
    first = _run(d, pins, s)
    assert s.posts == 0, "POSTed after the journal write failed"
    assert fired == ["ATTEMPTED"], fired
    assert isinstance(first, M.MintError), repr(first)
    assert str(first).startswith("cannot write the anchor journal"), str(first)
    monkeypatch.setattr(M, "_remove_journal", real_remove)
    second = _run(d, pins, s)
    if when == "left_behind":
        assert "is left ATTEMPTED" in str(first), str(first)
        assert json.loads(_journal_path(d).read_bytes())["state"] == "ATTEMPTED"
        assert isinstance(second, M.MintError), repr(second)
        assert str(second).startswith("rekor outcome unknown from an earlier run"), str(second)
        assert s.posts == 0, str(s.posts)
    else:
        assert str(first).endswith("a rerun starts fresh"), str(first)
        assert second == 0, repr(second)
        assert s.calls() == (1, 1, 1), str(s.calls())


def test_journal_write_failure_after_post_refuses_the_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=[], verify=[])
    real_write = M._write_journal

    def failing_logged(path: Path, record: dict[str, Any]) -> None:
        if record["state"] == "LOGGED":
            raise OSError("synthetic journal write failure")
        real_write(path, record)

    monkeypatch.setattr(M, "_write_journal", failing_logged)
    first = _run(d, pins, s)
    monkeypatch.setattr(M, "_write_journal", real_write)
    second = _run(d, pins, s)
    assert s.posts == 1, "POSTed again after the LOGGED write failed: " + str(s.posts)
    assert isinstance(first, M.MintError), repr(first)
    assert str(first).startswith("cannot record the Rekor entry in the anchor journal"), str(first)
    assert json.loads(_journal_path(d).read_bytes())["state"] == "ATTEMPTED"
    assert isinstance(second, M.MintError), repr(second)
    assert str(second).startswith("rekor outcome unknown from an earlier run"), str(second)


def test_connect_failure_with_unremovable_journal_refuses_the_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["connect_error"], tsa=[], verify=[])

    def failing_remove(path: Path) -> None:
        raise OSError("synthetic journal remove failure")

    monkeypatch.setattr(M, "_remove_journal", failing_remove)
    first = _run(d, pins, s)
    second = _run(d, pins, s)
    assert s.posts == 1, str(s.posts)
    assert isinstance(first, M.MintError), repr(first)
    assert str(first).startswith("rekor submit failed before any request left the host"), str(first)
    assert "could not be removed" in str(first), str(first)
    assert isinstance(second, M.MintError), repr(second)
    assert str(second).startswith("rekor outcome unknown from an earlier run"), str(second)


@pytest.mark.parametrize("stage", ["bundle", "index", "verify_stage"])
def test_write_failure_after_post_resumes_without_a_second_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    d, pins = _mint_dir(tmp_path)
    s = _Seams(post=["ok"], tsa=[], verify=[])
    target = {"bundle": _BUNDLE_NAME, "index": "index.json"}.get(stage, "")
    real_with_sidecar = M._write_with_sidecar
    real_tmpdir = M.tempfile.TemporaryDirectory
    fired = []

    def failing_with_sidecar(path: Path, data: bytes) -> None:
        if path.name == target and not fired:
            fired.append(path.name)
            raise OSError("synthetic write failure on " + path.name)
        real_with_sidecar(path, data)

    def failing_tmpdir(*a: Any, **k: Any) -> Any:
        if not fired:
            fired.append("tmpdir")
            raise OSError("synthetic staging failure")
        return real_tmpdir(*a, **k)

    if stage == "verify_stage":
        monkeypatch.setattr(M.tempfile, "TemporaryDirectory", failing_tmpdir)
    else:
        monkeypatch.setattr(M, "_write_with_sidecar", failing_with_sidecar)
    first = _run(d, pins, s)
    heads = {
        "bundle": "cannot write the rekor bundle",
        "index": "cannot write index.json",
        "verify_stage": "cannot stage the post-anchor self-verify",
    }
    assert isinstance(first, M.MintError), repr(first)
    assert str(first).startswith(heads[stage]), str(first)
    assert len(fired) == 1, fired
    second = _run(d, pins, s)
    assert second == 0, repr(second)
    expected_calls = {"bundle": (1, 2, 1), "index": (1, 1, 2), "verify_stage": (1, 1, 1)}
    assert s.calls() == expected_calls[stage], str(s.calls())
    assert _same_bundle(d), "bundle differs from the published 6.0.1 bundle"
    assert _names(d) == _AFTER_ANCHOR, _names(d)


_BAD_RECORDS: dict[str, Any] = {
    "a_list": lambda good: [good],
    "extra_key": lambda good: dict(good, extra=1),
    "schema_2": lambda good: dict(good, schemaVersion=2),
    "schema_bool": lambda good: dict(good, schemaVersion=True),
    "short_sha": lambda good: dict(good, vsaPayloadSha256=good["vsaPayloadSha256"][:63]),
    "url_int": lambda good: dict(good, rekorBaseUrl=1),
    "log_index_negative": lambda good: dict(good, logIndex=-1),
    "log_id_int": lambda good: dict(good, logId=1),
    "empty_body": lambda good: dict(good, canonicalizedBody=""),
    "hashes_not_list": lambda good: dict(good, inclusionProofHashes="x"),
    "attempted_with_entry": lambda good: dict(good, state="ATTEMPTED"),
}


@pytest.mark.parametrize("bad", sorted(_BAD_RECORDS))
def test_malformed_journal_refused_without_network(tmp_path: Path, bad: str) -> None:
    d, pins = _mint_dir(tmp_path)
    good = _logged_record(version=_VER, payload_sha=_vsa_sha(_REF, _VER), entry=_replay(_REF, _VER))
    assert M._journal_problem(good) == "", "control: the good record is refused"
    data = _canonical(_BAD_RECORDS[bad](good))
    _journal_path(d).write_bytes(data)
    s = _Seams(post=[], tsa=[], verify=[])
    out = _run(d, pins, s)
    assert s.calls() == (0, 0, 0), "a seam ran with a " + bad + " journal: " + str(s.calls())
    assert isinstance(out, M.MintError), repr(out)
    assert str(out).startswith("anchor journal unreadable"), str(out)


def test_journal_path_is_a_sibling_and_refuses_the_root(tmp_path: Path) -> None:
    d = tmp_path / "out"
    assert M.anchor_journal_path(d) == tmp_path.resolve() / "out.anchor-journal.json"
    with pytest.raises(M.MintError):
        M.anchor_journal_path(Path("/"))
