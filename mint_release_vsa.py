from __future__ import annotations

# __s171_mint_release_vsa_phase1_v1__
#
# Release-VSA MINT orchestrator -- Phase 1 (MINT, fully reversible).
#
# Verifies the two federation legs (SLSA build provenance via sigstore; PEP 740
# publish attestation via pypi-attestations) for a published NOUS release,
# assembles and Ed25519-signs a release VSA with the operator seed, emits the
# self-contained offline verifier, and writes a PARTIAL bundle directory with a
# .sha256 sidecar per file. It then runs a ROOT-1-only self-verify (operator
# signature + subject identity + policy) using the just-emitted offline
# verifier, which does not require the Rekor bundle.
#
# This phase performs NO Rekor write and writes NO index.json. The irreversible
# public-log anchor and the index are Phase 2 (ANCHOR), a separate gated step.
#
# Boundary: the federation-verifying dependencies (sigstore, pypi-attestations)
# are confined to this operator-side tool. They never enter the shipped offline
# verify path (verify_build_vsa_offline.py / nous build-attest-verify stay
# cryptography + z3 + stdlib only). A release VSA EVIDENCES the operator's
# endorsement; it PROVES nothing. The evidence layer is a monitor, not a guard.
#
# Refuse over guess: every precondition miss raises MintError (message starts
# with the cause). A raise after the first write leaves what was written.

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# __s485_root_guard_v1__
# Root guard (S485; FG-S481-M, N, P, Q). When this script runs as root it
# executes no byte another principal can write: run it as python3 -I -B
# from a root-owned copy staged from the tag, never from the live tree.
# For euid 0 the boot below refuses unless -I and -B; removes every import
# hook an editable install put in this process; refuses unless the script,
# every sys.path entry (a missing one by its nearest existing ancestor),
# every .pth of a site dir and every module already loaded are owned by
# root and not writable by group or other, through their lexical and
# resolved chains (a sticky ancestor allowed, never a sticky target); puts
# the script's directory first; and installs a finder first on
# sys.meta_path that refuses a spec, before its module runs, unless its
# origin, its cache directory and its search locations pass the same test.
# A .pth runs before this code: detected and refused, not prevented. For
# any other euid nothing here acts.
import importlib.util as _s485_ilu
import stat as _s485_stat

_S485_TAG = "__editable__"
_S485_W = 0o022


class RootGuardError(Exception):
    pass


class _S485GuardImportError(ImportError):
    pass


def _s485_chain(p: str) -> list[str]:
    out = []
    d = p
    while True:
        out.append(d)
        nd = os.path.dirname(d)
        if nd == d:
            return out
        d = nd


def _s485_unsafe(path: str, *, owners: tuple[int, ...] = (0,), lstat: Any = os.lstat,
                 target_sticky: bool = False) -> str | None:
    lex = os.path.abspath(path)
    real = os.path.realpath(lex)
    for form in (lex, real):
        q = form
        while True:
            try:
                lstat(q)
                break
            except FileNotFoundError:
                nq = os.path.dirname(q)
                if nq == q:
                    return "no existing ancestor: " + form
                q = nq
            except OSError as exc:
                return "cannot stat " + q + ": " + exc.__class__.__name__
        for d in _s485_chain(q):
            try:
                st = lstat(d)
            except OSError as exc:
                return "cannot stat " + d + ": " + exc.__class__.__name__
            if st.st_uid not in owners:
                return "not root-owned: %s (uid %d)" % (d, st.st_uid)
            if _s485_stat.S_ISLNK(st.st_mode):
                continue
            if st.st_mode & _S485_W:
                sticky = bool(st.st_mode & _s485_stat.S_ISVTX)
                if not sticky or (d == q and not target_sticky):
                    return "writable by group or other: %s (%o)" % (
                        d, _s485_stat.S_IMODE(st.st_mode))
    return None


def _s485_site_dirs() -> list[str]:
    try:
        import site
        dirs = list(site.getsitepackages())
    except Exception:
        dirs = []
    return [d for d in dirs if os.path.isdir(d)]


def _s485_strip(meta_path: list, path_hooks: list, path: list) -> list[str]:
    removed = []
    for f in list(meta_path):
        mod = getattr(f, "__module__", "") or ""
        name = getattr(f, "__name__", type(f).__name__)
        if mod.startswith(_S485_TAG) or name.startswith(_S485_TAG):
            meta_path.remove(f)
            removed.append("meta_path:" + mod + "." + name)
    for h in list(path_hooks):
        mod = getattr(h, "__module__", "") or ""
        if mod.startswith(_S485_TAG):
            path_hooks.remove(h)
            removed.append("path_hook:" + mod)
    for p in list(path):
        if isinstance(p, str) and p.startswith(_S485_TAG):
            path.remove(p)
            removed.append("path:" + p)
    return removed


def _s485_editable_left(meta_path: list, path_hooks: list) -> list[str]:
    return [repr(x) for x in list(meta_path) + list(path_hooks)
            if _S485_TAG in repr(x) or "editable" in repr(x).lower()]


def _s485_module_paths(mod: Any) -> list[str]:
    out = []
    for attr in ("__file__", "__cached__"):
        v = getattr(mod, attr, None)
        if isinstance(v, str) and v:
            out.append(v)
    spec = getattr(mod, "__spec__", None)
    locs = getattr(spec, "submodule_search_locations", None) if spec is not None else None
    for loc in list(locs or []):
        if isinstance(loc, str) and loc and not loc.startswith(_S485_TAG):
            out.append(loc)
    return out


def _s485_check_modules(modules: Any, owners: tuple[int, ...], lstat: Any) -> None:
    for name, mod in list(modules.items()):
        if mod is None:
            continue
        for p in _s485_module_paths(mod):
            why = _s485_unsafe(p, owners=owners, lstat=lstat)
            if why:
                raise RootGuardError("module " + name + ": " + why)


class _S485Guard:
    """First on sys.meta_path in a root run: asks the other finders for
    the spec and refuses it, before its module runs, unless its origin,
    its cache directory and its search locations pass _s485_unsafe.
    Each refusal is kept in .refused (__s485_guard_refusals_v1__): a
    caller that catches the ImportError does not erase it."""

    def __init__(self, meta_path: list, *, owners: tuple[int, ...] = (0,),
                 lstat: Any = os.lstat) -> None:
        self._mp = meta_path
        self._owners = owners
        self._lstat = lstat
        self.refused: list[str] = []

    def check_spec(self, spec: Any) -> str | None:
        paths = []
        o = spec.origin
        if spec.has_location and isinstance(o, str):
            paths.append(o)
            if o.endswith(".py"):
                try:
                    paths.append(_s485_ilu.cache_from_source(o))
                except (NotImplementedError, ValueError):
                    pass
        for loc in list(spec.submodule_search_locations or []):
            if isinstance(loc, str) and loc and not loc.startswith(_S485_TAG):
                paths.append(loc)
        for p in paths:
            why = _s485_unsafe(p, owners=self._owners, lstat=self._lstat)
            if why:
                return why
        return None

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        for f in list(self._mp):
            if f is self:
                continue
            fs = getattr(f, "find_spec", None)
            if fs is None:
                continue
            spec = fs(fullname, path, target)
            if spec is None:
                continue
            why = self.check_spec(spec)
            if why:
                self.refused.append(fullname + ": " + why)
                raise _S485GuardImportError("root guard: " + fullname + ": " + why,
                                            name=fullname)
            return spec
        return None

    def invalidate_caches(self) -> None:
        return None


def _s485_refused(meta_path: Any = None) -> list[str]:
    """The refusals kept by every guard on meta_path, in order."""
    meta_path = sys.meta_path if meta_path is None else meta_path
    out: list[str] = []
    for f in list(meta_path):
        if isinstance(f, _S485Guard):
            out.extend(f.refused)
    return out


def _s485_after(label: str, rc: int, exc: BaseException | None = None) -> int:
    """A refusal a library caught still ends the root run: exit 2."""
    refused = _s485_refused()
    if not refused:
        return rc
    tail = "" if exc is None else " (then " + type(exc).__name__ + ": " + str(exc) + ")"
    print(label + " REFUSED: root guard: imports refused: " + "; ".join(refused) + tail,
          file=sys.stderr)
    return 2


def _s485_root_boot(*, euid: int | None = None, flags: Any = None, meta_path: Any = None,
                    path_hooks: Any = None, path: Any = None, modules: Any = None,
                    script: str | None = None, owners: tuple[int, ...] = (0,),
                    lstat: Any = os.lstat, site_dirs: Any = None) -> list[str] | None:
    if euid is None:
        euid = os.geteuid()
    if euid != 0:
        return None
    flags = sys.flags if flags is None else flags
    if not (flags.isolated and flags.safe_path and flags.dont_write_bytecode):
        raise RootGuardError("run as root needs python3 -I -B (isolated, no bytecode written)")
    meta_path = sys.meta_path if meta_path is None else meta_path
    path_hooks = sys.path_hooks if path_hooks is None else path_hooks
    path = sys.path if path is None else path
    modules = sys.modules if modules is None else modules
    script = os.path.abspath(__file__) if script is None else script
    site_dirs = _s485_site_dirs() if site_dirs is None else site_dirs
    removed = _s485_strip(meta_path, path_hooks, path)
    left = _s485_editable_left(meta_path, path_hooks)
    if left:
        raise RootGuardError("editable import hooks left: " + " ".join(left))
    why = _s485_unsafe(script, owners=owners, lstat=lstat)
    if why:
        raise RootGuardError("the script: " + why)
    home = os.path.dirname(os.path.realpath(script))
    while home in path:
        path.remove(home)
    path.insert(0, home)
    for e in list(path):
        if not isinstance(e, str):
            continue
        e2 = e or os.getcwd()
        why = _s485_unsafe(e2, owners=owners, lstat=lstat)
        if why:
            raise RootGuardError("sys.path entry " + e2 + ": " + why)
    for sd in site_dirs:
        try:
            names = sorted(os.listdir(sd))
        except OSError:
            continue
        for n in names:
            if n.endswith(".pth"):
                why = _s485_unsafe(os.path.join(sd, n), owners=owners, lstat=lstat)
                if why:
                    raise RootGuardError(".pth " + n + ": " + why)
    _s485_check_modules(modules, owners, lstat)
    meta_path.insert(0, _S485Guard(meta_path, owners=owners, lstat=lstat))
    sys.path_importer_cache.clear()
    return removed


def _s485_root_check(*, euid: int | None = None, modules: Any = None, meta_path: Any = None,
                     path_hooks: Any = None, owners: tuple[int, ...] = (0,),
                     lstat: Any = os.lstat) -> None:
    if euid is None:
        euid = os.geteuid()
    if euid != 0:
        return
    meta_path = sys.meta_path if meta_path is None else meta_path
    if not meta_path or not isinstance(meta_path[0], _S485Guard):
        raise RootGuardError("the guard is not first on sys.meta_path")
    refused = _s485_refused(meta_path)
    if refused:
        raise RootGuardError("imports refused: " + "; ".join(refused))
    left = _s485_editable_left(meta_path, sys.path_hooks if path_hooks is None else path_hooks)
    if left:
        raise RootGuardError("editable import hooks left: " + " ".join(left))
    _s485_check_modules(sys.modules if modules is None else modules, owners, lstat)


try:
    _S485_BOOT = _s485_root_boot()
except RootGuardError as _s485_exc:
    sys.stderr.write("MINT REFUSED: root guard: " + str(_s485_exc) + "\n")
    raise SystemExit(2)

try:  # __s485h_root_paths_v1__
    import build_vsa
except Exception:
    if not _s485_refused():
        raise
    sys.stderr.write("MINT REFUSED: root guard: imports refused: "
                     + "; ".join(_s485_refused()) + "\n")
    raise SystemExit(2)

DEFAULT_OPERATOR_KEY = "/root/.local/share/nous/keys/release_attest_signing.key"
COMMITTED_RELEASE_PIN_B64 = "E3FNG9zFMRjhg/iVkOu9K3gH5mmG6Uwvdy8EvwHsYVo="
GITHUB_API = "https://api.github.com"
PYPI_INTEGRITY = "https://pypi.org/integrity"
REPOSITORY = "contrario/nous"
WORKFLOW = "release.yml"
WORKFLOW_REF_PREFIX = "refs/tags/"
SLSA_BUILD_LEVEL = "SLSA_BUILD_LEVEL_2"
SLSA_PROVENANCE_PREDICATE = "https://slsa.dev/provenance/v1"
PEP740_PUBLISH_PREDICATE = "https://docs.pypi.org/attestations/publish/v1"
BUILD_TYPE = "https://actions.github.io/buildtypes/workflow/v1"

RELEASE_BOUNDARY = (
    "This release VSA EVIDENCES that the NOUS release operator verified, with "
    "standard Sigstore tooling, that these exact published wheel and sdist "
    "bytes carry a SLSA build provenance (keyless GitHub Actions, "
    "Fulcio/Rekor) and a PEP 740 PyPI publish attestation, both naming these "
    "bytes, at SLSA Build Level 2. It is an operator-key root ALONGSIDE the "
    "federation roots; it is not a second build. The offline verifier checks "
    "the operator signature and re-derives the subject digests, but does NOT "
    "re-derive the named federation attestations (toolchain tier: fetch + "
    "Sigstore). It PROVES nothing (no Z3/Farkas leg). The evidence layer is a monitor, not a "
    "guard."
)
OFFLINE_SCOPE = (
    "EVIDENCES operator endorsement + subject identity; named federation "
    "attestations are recorded by URI + digest but NOT re-derived offline "
    "(toolchain tier)"
)

BACKFILL_NOTE = (
    "This release VSA was MINTED at backfilledAt, later than the original "
    "release of the named version. Its Rekor anchor is a separate Phase-2 "
    "step performed at or after backfilledAt; the RFC3161 timestamp "
    "recorded with the Rekor bundle (rfc3161GenTime in index.json) records "
    "that anchor instant. The Rekor inclusion proof and that RFC3161 "
    "timestamp EVIDENCE that this VSA payload existed no later than the "
    "anchor timestamp; they do NOT evidence anchoring at release time and "
    "set no lower bound on when the payload came to exist. The release-time "
    "evidence is the named federation attestations (SLSA build provenance + "
    "PEP 740 publish leg), dated at the original release; this VSA "
    "summarizes them. It PROVES nothing (no Z3/Farkas leg). The evidence layer is a "
    "monitor, not a guard."
)


class MintError(ValueError):
    """Raised on any precondition or verification failure in the MINT phase.
    The message starts with the cause. A raise after the first write
    leaves the files already written; nothing removes them."""


# __s485_root_guard_v1__
_S485_EAGER = {
    "mint": ("datetime", "subprocess", "httpx",
             "cryptography.hazmat.primitives.serialization",
             "cryptography.hazmat.primitives.asymmetric.ed25519",
             "sigstore.models", "sigstore.verify", "sigstore.verify.policy",
             "pypi_attestations"),
    "anchor": ("datetime", "httpx", "rekor_anchor", "rekor_anchor_v2",
               "tsa_client", "cli_verify_release", "rekor_v2_offline"),
}


def _s485_checkpoint(stage: str) -> None:
    try:
        _s485_root_check()
    except RootGuardError as exc:
        raise MintError("root guard (" + stage + "): " + str(exc)) from exc


def _s485_root_prepare(command: str) -> None:
    """For a root run: import the command's whole closure first, through
    the guard, then check every loaded module, before the seed is read
    (mint) or the network is touched (anchor)."""
    if os.geteuid() != 0:
        return
    import importlib

    for name in _S485_EAGER[command]:
        try:
            importlib.import_module(name)
        except ImportError as exc:
            raise MintError("root guard (" + command + "): cannot import " + name
                            + ": " + str(exc)) from exc
    _s485_checkpoint(command + ": before " + ("the seed" if command == "mint" else "the network"))


def _s485_own_dir(d: Path, what: str, *, create: bool, euid: int | None = None,
                  owners: tuple[int, ...] = (0,), lstat: Any = os.lstat) -> None:
    """__s485h_root_paths_v1__ For a root run: the directory the mint
    writes into, or the anchor reads and writes beside (its journal is a
    sibling), and its parent must be root-owned and not writable by group
    or other; the parent is checked as a target, so a sticky /tmp is
    refused. Made 0o755 first when create is set. For any other euid
    nothing here acts."""
    if (os.geteuid() if euid is None else euid) != 0:
        return
    p = os.path.abspath(str(d))
    why = None
    for par in sorted({os.path.dirname(p), os.path.dirname(os.path.realpath(p))}):
        why = why or _s485_unsafe(par, owners=owners, lstat=lstat)
    if not why and create:
        try:
            os.makedirs(p, mode=0o755, exist_ok=True)
        except OSError as exc:
            why = "cannot make " + p + ": " + exc.__class__.__name__
    if not why:
        why = _s485_unsafe(p, owners=owners, lstat=lstat)
    if why:
        raise MintError("root guard (" + what + "): " + why)


def _s485_kept(exc: BaseException) -> str:
    """The kept refusals a MintError's text does not already name."""
    r = _s485_refused()
    if not r or all(x in str(exc) for x in r):
        return ""
    return "; root guard: imports refused: " + "; ".join(r)


def _s485_child_env() -> dict[str, str]:
    return {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_http() -> "Any":
    import httpx

    return httpx


def _get_json(url: str, *, accept: str | None = None) -> dict[str, Any]:
    httpx = _require_http()
    headers = {"Accept": accept} if accept else {}
    try:
        resp = httpx.get(url, headers=headers, timeout=httpx.Timeout(30.0, connect=10.0))
    except httpx.RequestError as exc:
        raise MintError("federation fetch failed for " + url + ": " + repr(exc)) from exc
    if resp.status_code != 200:
        raise MintError(
            "federation fetch returned HTTP "
            + str(resp.status_code)
            + " for "
            + url
            + ": "
            + resp.text[:256]
        )
    try:
        obj = resp.json()
    except json.JSONDecodeError as exc:
        raise MintError("federation fetch returned non-JSON for " + url + ": " + repr(exc)) from exc
    if not isinstance(obj, dict):
        raise MintError("federation fetch returned non-object JSON for " + url)
    return obj


def _load_operator_seed(key_path: Path) -> bytes:
    if not key_path.is_file():
        raise MintError("operator seed not found: " + str(key_path))
    seed = key_path.read_bytes()
    if len(seed) != 32:
        raise MintError("operator seed must be 32 raw bytes, got " + str(len(seed)))
    return seed


def _operator_pubkey_b64(seed: bytes) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _pypi_files(version: str) -> dict[str, Any]:
    url = "https://pypi.org/pypi/nous-lang/" + version + "/json"
    doc = _get_json(url)
    files = doc.get("urls")
    if not isinstance(files, list) or not files:
        raise MintError("PyPI returned no files for nous-lang " + version)
    out: dict[str, dict[str, str]] = {}
    for f in files:
        if not isinstance(f, dict):
            continue
        pt = f.get("packagetype")
        name = f.get("filename")
        digests = f.get("digests") or {}
        sha = digests.get("sha256")
        dl_url = f.get("url")
        if not isinstance(name, str) or not isinstance(sha, str) or not isinstance(dl_url, str):
            continue
        if pt == "bdist_wheel":
            out["wheel"] = {"name": name, "sha256": sha, "url": dl_url}
        elif pt == "sdist":
            out["sdist"] = {"name": name, "sha256": sha, "url": dl_url}
    if "wheel" not in out or "sdist" not in out:
        raise MintError(
            "PyPI files for "
            + version
            + " missing wheel or sdist: found "
            + str(sorted(out))
        )
    return out


def _verify_build_leg(version: str, wheel_sha256: str) -> dict[str, Any]:
    url = (
        GITHUB_API
        + "/repos/"
        + REPOSITORY
        + "/attestations/sha256:"
        + wheel_sha256
    )
    doc = _get_json(url, accept="application/vnd.github+json")
    atts = doc.get("attestations")
    if not isinstance(atts, list) or not atts:
        raise MintError("GitHub returned no build attestations for sha256:" + wheel_sha256)
    att = atts[0]
    bundle = att.get("bundle") if isinstance(att, dict) else None
    if not isinstance(bundle, dict):
        raise MintError("GitHub attestation has no bundle object")
    dsse = bundle.get("dsseEnvelope")
    if not isinstance(dsse, dict) or "payload" not in dsse:
        raise MintError("GitHub attestation bundle has no dsseEnvelope.payload")

    from sigstore.models import Bundle
    from sigstore.verify import Verifier
    from sigstore.verify import policy as vpol

    try:
        sb = Bundle.from_json(json.dumps(bundle))
    except Exception as exc:
        raise MintError("GitHub attestation bundle is not a valid Sigstore bundle: " + repr(exc)) from exc

    expected_ref = WORKFLOW_REF_PREFIX + "v" + version
    identity = vpol.AllOf(
        [
            vpol.OIDCSourceRepositoryURI("https://github.com/" + REPOSITORY),
            vpol.GitHubWorkflowRepository(REPOSITORY),
            vpol.OIDCSourceRepositoryRef(expected_ref),
        ]
    )
    verifier = Verifier.production()
    try:
        payload_type, payload_bytes = verifier.verify_dsse(sb, identity)
    except Exception as exc:
        raise MintError("SLSA build provenance failed Sigstore verification: " + repr(exc)) from exc

    payload_b64 = dsse["payload"]
    try:
        decoded = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MintError("build-leg dsseEnvelope.payload is not valid base64: " + repr(exc)) from exc
    if decoded != payload_bytes:
        raise MintError("build-leg verified payload does not equal the recorded dsseEnvelope.payload")

    try:
        statement = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError("build-leg payload is not valid JSON: " + repr(exc)) from exc
    predicate = statement.get("predicate") if isinstance(statement, dict) else None
    pred_obj = predicate if isinstance(predicate, dict) else {}
    build_def = pred_obj.get("buildDefinition") or {}
    external = build_def.get("externalParameters") or {}
    run_details = pred_obj.get("runDetails") or {}
    builder = run_details.get("builder") or {}
    source_commit = ""
    rd = build_def.get("resolvedDependencies") or []
    for dep in rd:
        if isinstance(dep, dict) and dep.get("uri", "").startswith("git+https://github.com/" + REPOSITORY):
            digest = dep.get("digest") or {}
            source_commit = str(digest.get("gitCommit", ""))
            break

    payload_sha256 = _sha256_hex(decoded)
    return {
        "uri": url,
        "payload_sha256": payload_sha256,
        "predicate_type": SLSA_PROVENANCE_PREDICATE,
        "build_identity": {
            "buildType": BUILD_TYPE,
            "builderId": "https://github.com/"
            + REPOSITORY
            + "/.github/workflows/"
            + WORKFLOW
            + "@"
            + expected_ref,
            "path": ".github/workflows/" + WORKFLOW,
            "ref": expected_ref,
            "repository": "https://github.com/" + REPOSITORY,
            "sourceCommit": source_commit,
        },
        "_builder_id_seen": str(builder.get("id", "")),
        "_external_workflow": external.get("workflow") if isinstance(external, dict) else None,
    }


def _verify_publish_leg(version: str, filename: str, dist_path: Path) -> dict[str, Any]:
    import pypi_attestations as pa

    url = (
        PYPI_INTEGRITY
        + "/nous-lang/"
        + version
        + "/"
        + filename
        + "/provenance"
    )
    doc = _get_json(url)
    bundles = doc.get("attestation_bundles")
    if not isinstance(bundles, list) or not bundles:
        raise MintError("PyPI provenance has no attestation_bundles for " + filename)
    bundle0 = bundles[0]
    atts = bundle0.get("attestations") if isinstance(bundle0, dict) else None
    if not isinstance(atts, list) or not atts:
        raise MintError("PyPI provenance bundle has no attestations for " + filename)
    att0 = atts[0]
    envelope = att0.get("envelope") if isinstance(att0, dict) else None
    if not isinstance(envelope, dict) or "statement" not in envelope:
        raise MintError("PyPI provenance attestation envelope has no statement for " + filename)

    statement_b64 = envelope["statement"]
    try:
        statement_bytes = base64.b64decode(statement_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MintError("publish-leg envelope.statement is not valid base64: " + repr(exc)) from exc

    try:
        prov = pa.Provenance.model_validate(doc)
    except Exception as exc:
        raise MintError("PyPI provenance failed schema validation: " + repr(exc)) from exc
    attestation = prov.attestation_bundles[0].attestations[0]

    dist = pa.Distribution.from_file(dist_path)
    publisher = pa.GitHubPublisher(
        repository=REPOSITORY,
        workflow=WORKFLOW,
    )
    try:
        predicate_type, _claims = attestation.verify(publisher, dist)
    except pa.VerificationError as exc:
        raise MintError("PEP 740 publish attestation failed verification for " + filename + ": " + repr(exc)) from exc

    payload_sha256 = _sha256_hex(statement_bytes)
    return {
        "uri": url,
        "payload_sha256": payload_sha256,
        "predicate_type": PEP740_PUBLISH_PREDICATE,
        "_predicate_type_seen": str(predicate_type),
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mint_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


VERIFIER_VSA_FILENAME = "build-vsa.intoto.json"  # __s236_p1_alias_const_v1__


def _write_with_sidecar(path: Path, data: bytes) -> None:
    _atomic_write(path, data)
    sidecar = path.with_name(path.name + ".sha256")
    digest_line = _sha256_hex(data) + "  " + path.name + "\n"
    _atomic_write(sidecar, digest_line.encode("ascii"))


def mint(version: str, out_dir: Path, *, key_path: Path, work_dir: Path, backfill: bool = False) -> int:
    _s485_root_prepare("mint")  # __s485_root_guard_v1__
    seed = _load_operator_seed(key_path)
    pin = _operator_pubkey_b64(seed)
    if pin != COMMITTED_RELEASE_PIN_B64:
        raise MintError(
            "operator key does not match the committed consumer pin "
            "(derived "
            + pin
            + " != "
            + COMMITTED_RELEASE_PIN_B64
            + "); minting would ship a dir the shipped verifier rejects"
        )

    files = _pypi_files(version)
    wheel = files["wheel"]
    sdist = files["sdist"]

    _s485_checkpoint("mint: before the first write")  # __s485_root_guard_v1__
    _s485_own_dir(out_dir, "mint: the out dir", create=True)  # __s485h_root_paths_v1__
    _s485_own_dir(work_dir, "mint: the work dir", create=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    httpx = _require_http()
    dist_paths: dict[str, Path] = {}
    for label, meta in (("wheel", wheel), ("sdist", sdist)):
        dl = work_dir / meta["name"]
        try:
            resp = httpx.get(meta["url"], timeout=httpx.Timeout(60.0, connect=10.0))
        except httpx.RequestError as exc:
            raise MintError("artifact download failed for " + meta["name"] + ": " + repr(exc)) from exc
        if resp.status_code != 200:
            raise MintError("artifact download returned HTTP " + str(resp.status_code) + " for " + meta["name"])
        body = resp.content
        got = _sha256_hex(body)
        if got != meta["sha256"]:
            raise MintError(
                "downloaded "
                + label
                + " sha256 mismatch: PyPI="
                + meta["sha256"][:16]
                + "... local="
                + got[:16]
                + "..."
            )
        _atomic_write(dl, body)
        dist_paths[label] = dl

    build_leg = _verify_build_leg(version, wheel["sha256"])
    publish_whl = _verify_publish_leg(version, wheel["name"], dist_paths["wheel"])
    publish_sdist = _verify_publish_leg(version, sdist["name"], dist_paths["sdist"])

    subject_federation = [
        {
            "name": wheel["name"],
            "sha256": wheel["sha256"],
            "buildLeg": {
                "uri": build_leg["uri"],
                "payloadSha256": build_leg["payload_sha256"],
                "predicateType": build_leg["predicate_type"],
            },
            "publishLeg": {
                "uri": publish_whl["uri"],
                "payloadSha256": publish_whl["payload_sha256"],
                "predicateType": publish_whl["predicate_type"],
            },
        },
        {
            "name": sdist["name"],
            "sha256": sdist["sha256"],
            "buildLeg": {
                "uri": build_leg["uri"],
                "payloadSha256": build_leg["payload_sha256"],
                "predicateType": build_leg["predicate_type"],
            },
            "publishLeg": {
                "uri": publish_sdist["uri"],
                "payloadSha256": publish_sdist["payload_sha256"],
                "predicateType": publish_sdist["predicate_type"],
            },
        },
    ]

    ext = {
        "boundary": RELEASE_BOUNDARY,
        "buildIdentity": build_leg["build_identity"],
        "offlineScope": OFFLINE_SCOPE,
        "subjectFederation": subject_federation,
    }

    input_attestations = [
        {"uri": build_leg["uri"], "sha256": build_leg["payload_sha256"]},
        {"uri": publish_whl["uri"], "sha256": publish_whl["payload_sha256"]},
        {"uri": publish_sdist["uri"], "sha256": publish_sdist["payload_sha256"]},
    ]

    import datetime as _dt

    time_verified = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if backfill:  # __s226_backfill_ext_v1__
        ext["backfill"] = {
            "backfilledAt": time_verified,
            "originalReleaseTag": "v" + version,
            "note": BACKFILL_NOTE,
        }

    statement = build_vsa.assemble_build_vsa_statement(
        subjects=[
            {"name": wheel["name"], "sha256": wheel["sha256"]},
            {"name": sdist["name"], "sha256": sdist["sha256"]},
        ],
        input_attestations=input_attestations,
        verified_levels=[SLSA_BUILD_LEVEL],
        ext=ext,
        resource_uri="pkg:pypi/nous-lang@" + version,
        time_verified=time_verified,
    )

    for subj in statement["subject"]:
        name = subj["name"]
        want = subj["digest"]["sha256"]
        local = dist_paths["wheel"] if name == wheel["name"] else dist_paths["sdist"]
        got = _sha256_hex(local.read_bytes())
        if got != want:
            raise MintError(
                "self-grade: subject digest mismatch for "
                + name
                + " (statement="
                + want[:16]
                + "... local="
                + got[:16]
                + "...)"
            )

    if statement["predicate"]["policy"]["digest"]["sha256"] != build_vsa.build_policy_fingerprint():
        raise MintError("self-grade: policy digest does not match build_policy_fingerprint()")

    envelope = build_vsa.sign_build_vsa(statement, seed)

    out_dir.mkdir(parents=True, exist_ok=True)
    vsa_name = "nous_lang-" + version + ".build-vsa.intoto.json"
    envelope_bytes = json.dumps(envelope, sort_keys=True, indent=2).encode("utf-8")
    _write_with_sidecar(out_dir / vsa_name, envelope_bytes)
    _write_with_sidecar(out_dir / VERIFIER_VSA_FILENAME, envelope_bytes)  # __s236_p1_alias_emit_v1__

    verifier_key_doc = {
        "alg": "ed25519",
        "keyid": _sha256_hex(base64.b64decode(pin)),
        "publicKeyRaw": pin,
        "schema": "nous.release_vsa.verifier_key.v1",
        "verifiedLevels": [SLSA_BUILD_LEVEL],
        "verifierId": build_vsa.NOUS_RELEASE_VERIFIER_ID,
    }
    verifier_key_bytes = json.dumps(verifier_key_doc, sort_keys=True, indent=2).encode("utf-8")
    _write_with_sidecar(out_dir / "release-verifier-key.json", verifier_key_bytes)

    emitted = build_vsa.emit_build_vsa_verifier(str(out_dir), pin)
    verifier_bytes = emitted.read_bytes()
    sidecar = emitted.with_name(emitted.name + ".sha256")
    digest_line = _sha256_hex(verifier_bytes) + "  " + emitted.name + "\n"
    _atomic_write(sidecar, digest_line.encode("ascii"))

    root1 = _root1_self_verify(out_dir, vsa_name)

    print("MINT complete (Phase 1, reversible) for nous-lang " + version)
    print("  out dir:            " + str(out_dir))
    print("  vsa:                " + vsa_name)
    print("  vsa (verifier name):" + VERIFIER_VSA_FILENAME)  # __s236_p1_alias_print_v1__
    print("  verifier:           " + emitted.name)
    print("  verifier key:       release-verifier-key.json")
    print("  operator pin:       " + pin)
    print("  build-leg payload:  " + build_leg["payload_sha256"][:16] + "...")
    print("  whl  publish:       " + publish_whl["payload_sha256"][:16] + "...")
    print("  sdist publish:      " + publish_sdist["payload_sha256"][:16] + "...")
    print("  source commit:      " + (build_leg["build_identity"]["sourceCommit"] or "(unresolved)"))
    print("  ROOT-1 self-verify: " + ("PASS" if root1 == 0 else "FAIL (rc=" + str(root1) + ")"))
    print()
    print("NO Rekor write performed. NO index.json written. ANCHOR is Phase 2,")
    print("a separate gated step. The VSA payload digest to anchor is:")
    payload_sha = _sha256_hex(base64.b64decode(envelope["payload"]))
    print("  vsaPayloadSha256:   " + payload_sha)
    if root1 != 0:
        return 1
    return 0


def _root1_self_verify(out_dir: Path, vsa_name: str) -> int:  # __s236_p1_root1_no_construct_v1__
    import subprocess

    alias = out_dir / VERIFIER_VSA_FILENAME
    if not alias.is_file():
        raise MintError(
            "the offline verifier reads " + VERIFIER_VSA_FILENAME
            + " and the mint did not write it: " + str(alias)
        )
    _s485_checkpoint("mint: before the ROOT-1 child")  # __s485_root_guard_v1__
    result = subprocess.run(
        [sys.executable, str(out_dir / "verify_build_vsa_offline.py")],
        capture_output=True,
        text=True,
        env=_s485_child_env(),  # __s485_root_guard_v1__
    )
    sys.stdout.write(result.stdout)
    # __s172_p0a_root1_stderr_suppress_v1__
    # rc 2 = no named subject present locally to re-derive (expected: this dir
    # holds only the VSA, not the wheel/sdist). ROOT-1 legs (signature,
    # identity, policy) print OK before that point; treat rc 2 as ROOT-1 PASS.
    is_root1_pass = (
        result.returncode == 2
        and "release VSA DSSE Ed25519 signature verified" in result.stdout
    )
    if result.stderr and not is_root1_pass:
        sys.stderr.write(result.stderr)
    if is_root1_pass:
        return 0
    return result.returncode


# __s172_p0b1_release_bundle_index_v1__
NOUS_BUILD_VSA_EXT_KEY = "https://nous-lang.org/build-vsa/ext/v1"
RELEASE_VSA_INDEX_SCHEMA = "nous.release_vsa.index.v1"
RELEASE_VSA_BASE_URL = "https://nous-lang.org/.well-known/nous/release-vsa/"
PYPI_PROJECT_URL = "https://pypi.org/project/nous-lang/"
REKOR_LEG_BOUNDARY = (
    "EVIDENCES public, append-only, RFC3161-timestamped inclusion of the VSA "
    "payload digest in the Rekor v2 transparency log. The bundle is "
    "self-contained: it carries the RFC6962 inclusion proof, the C2SP "
    "signed-note checkpoint, and the RFC3161 timestamp token, and is "
    "verifiable fully offline with cryptography + Python stdlib only. It "
    "PROVES nothing (no Z3/Farkas leg). The evidence layer is a monitor, not a guard."
)


def decode_build_vsa_statement(envelope: dict[str, Any]) -> dict[str, Any]:
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise MintError("build-vsa envelope has no payload")
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MintError(
            "build-vsa payload is not valid base64: " + str(exc)
        ) from exc
    try:
        statement = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError(
            "build-vsa payload is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(statement, dict):
        raise MintError("build-vsa payload is not a JSON object")
    return statement


def vsa_payload_sha256(envelope: dict[str, Any]) -> str:
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise MintError("build-vsa envelope has no payload")
    return hashlib.sha256(
        base64.b64decode(payload_b64, validate=True)
    ).hexdigest()


def canonical_bytes_to_anchor(envelope: dict[str, Any]) -> bytes:
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise MintError("build-vsa envelope has no payload")
    return base64.b64decode(payload_b64, validate=True)


def _decode_canonicalized_body(body_b64: str) -> dict[str, Any]:
    try:
        body = json.loads(
            base64.b64decode(body_b64, validate=True).decode("utf-8")
        )
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError(
            "canonicalized_body is not valid base64/JSON: " + str(exc)
        ) from exc
    if not isinstance(body, dict):
        raise MintError("canonicalized_body is not a JSON object")
    return body


def _hashedrekord_leaf(body: dict[str, Any]) -> dict[str, Any]:
    spec = body.get("spec")
    if not isinstance(spec, dict):
        raise MintError("canonicalized_body has no spec object")
    leaf = spec.get("hashedRekordV002") or spec.get("hashedRekord") or spec
    if not isinstance(leaf, dict):
        raise MintError("canonicalized_body spec leaf is not an object")
    return leaf


def _derive_entry_signature(body_b64: str) -> str:
    leaf = _hashedrekord_leaf(_decode_canonicalized_body(body_b64))
    try:
        content = leaf["signature"]["content"]
    except (KeyError, TypeError) as exc:
        raise MintError(
            "cannot derive entry_signature from canonicalized_body: " + str(exc)
        ) from exc
    if not isinstance(content, str) or not content:
        raise MintError("entry_signature content is not a non-empty string")
    return content


def _anchored_digest_hex(body_b64: str) -> str:
    leaf = _hashedrekord_leaf(_decode_canonicalized_body(body_b64))
    try:
        digest_b64 = leaf["data"]["digest"]
    except (KeyError, TypeError) as exc:
        raise MintError(
            "cannot derive anchored digest from canonicalized_body: " + str(exc)
        ) from exc
    return base64.b64decode(str(digest_b64), validate=True).hex()


def _entry_kind(body_b64: str) -> str:
    body = _decode_canonicalized_body(body_b64)
    kind = str(body.get("kind", ""))
    api = str(body.get("apiVersion", ""))
    if not kind or not api:
        raise MintError("canonicalized_body missing kind/apiVersion")
    return kind + "/" + api


def _leaf_hash_hex(body_b64: str) -> str:
    leaf = base64.b64decode(body_b64, validate=True)
    return hashlib.sha256(b"\x00" + leaf).hexdigest()


def _checkpoint_tree_size(checkpoint_envelope: str) -> int:
    import rekor_v2_offline

    cp = rekor_v2_offline.parse_checkpoint(checkpoint_envelope)
    return int(cp.tree_size)


def _checkpoint_origin(checkpoint_envelope: str) -> str:
    lines = checkpoint_envelope.splitlines()
    if not lines or not lines[0]:
        raise MintError("checkpoint envelope has no origin line")
    return lines[0]


def assemble_rekor_bundle(anchor: Any, rfc3161_token_der: bytes) -> dict[str, Any]:
    """Assemble the offline rekor-v2-bundle.json dict from a live Rekor anchor.

    anchor is duck-typed as rekor_anchor_v2.RekorAnchorV2 (reads only
    .body_b64, .checkpoint_envelope, .inclusion_proof_hashes, .log_index);
    typed Any so this pure-assembly path does not import the live httpx anchor
    client. Shape matches the rekor_v2_offline consumer.
    """
    body_b64 = str(anchor.body_b64)
    checkpoint_envelope = str(anchor.checkpoint_envelope)
    return {
        "entry_signature": _derive_entry_signature(body_b64),
        "rfc3161_timestamp": base64.b64encode(rfc3161_token_der).decode("ascii"),
        "transparency_log_entry": {
            "canonicalized_body": body_b64,
            "inclusion_proof": {
                "checkpoint": checkpoint_envelope,
                "hashes": [str(h) for h in anchor.inclusion_proof_hashes],
                "tree_size": _checkpoint_tree_size(checkpoint_envelope),
            },
            "log_index": int(anchor.log_index),
        },
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release_index(
    version: str,
    out_dir: Path,
    *,
    statement: dict[str, Any],
    bundle: dict[str, Any],
    bundle_filename: str,
    vsa_filename: str,
    verifier_filename: str,
    verifier_key_filename: str,
    operator_pin_b64: str,
    vsa_payload_sha256_hex: str,
    rfc3161_gen_time: str,
    emitted_at: str,
) -> dict[str, Any]:
    predicate = statement["predicate"]
    ext = predicate[NOUS_BUILD_VSA_EXT_KEY]
    build_identity = ext["buildIdentity"]
    subject_federation = ext["subjectFederation"]
    subjects = statement["subject"]

    base = RELEASE_VSA_BASE_URL + version + "/"

    name_to_sha: dict[str, str] = {}
    for s in subjects:
        name_to_sha[str(s["name"])] = str(s["digest"]["sha256"])
    wheel_name = None
    sdist_name = None
    for name in name_to_sha:
        if name.endswith(".whl"):
            wheel_name = name
        elif name.endswith(".tar.gz"):
            sdist_name = name
    if wheel_name is None or sdist_name is None:
        raise MintError("statement subjects missing wheel or sdist")

    artifacts: list[dict[str, Any]] = []
    artifacts.append({
        "kind": "release_vsa_dsse",
        "name": vsa_filename,
        "sha256": _sha256_file(out_dir / vsa_filename),
        "url": base + vsa_filename,
    })
    artifacts.append({
        "kind": "offline_verifier",
        "name": verifier_filename,
        "sha256": _sha256_file(out_dir / verifier_filename),
        "url": base + verifier_filename,
        "verifierKeyPinned": operator_pin_b64,
    })
    artifacts.append({
        "kind": "release_verifier_key",
        "name": verifier_key_filename,
        "sha256": _sha256_file(out_dir / verifier_key_filename),
        "url": base + verifier_key_filename,
    })
    artifacts.append({
        "kind": "wheel",
        "name": wheel_name,
        "sha256": name_to_sha[wheel_name],
        "source": "pypi",
        "url": PYPI_PROJECT_URL + version + "/",
    })
    artifacts.append({
        "kind": "sdist",
        "name": sdist_name,
        "sha256": name_to_sha[sdist_name],
        "source": "pypi",
        "url": PYPI_PROJECT_URL + version + "/",
    })

    wheel_entry = None
    for entry in subject_federation:
        if str(entry["name"]).endswith(".whl"):
            wheel_entry = entry
    if wheel_entry is None:
        raise MintError("subjectFederation has no wheel entry")
    bl = wheel_entry["buildLeg"]
    for entry in subject_federation:
        if str(entry["buildLeg"]["payloadSha256"]) != str(bl["payloadSha256"]):
            raise MintError(
                "federation build legs do not share one provenance payloadSha256"
            )
    artifacts.append({
        "kind": "federation_build_leg",
        "payloadSha256": str(bl["payloadSha256"]),
        "predicateType": str(bl["predicateType"]),
        "uri": str(bl["uri"]),
    })

    for entry in subject_federation:
        pl = entry["publishLeg"]
        artifacts.append({
            "kind": "federation_publish_leg",
            "name": str(entry["name"]),
            "payloadSha256": str(pl["payloadSha256"]),
            "predicateType": str(pl["predicateType"]),
            "uri": str(pl["uri"]),
        })

    tle = bundle["transparency_log_entry"]
    body_b64 = str(tle["canonicalized_body"])
    ip = tle["inclusion_proof"]
    checkpoint_envelope = str(ip["checkpoint"])
    anchored = _anchored_digest_hex(body_b64)
    if anchored != vsa_payload_sha256_hex:
        raise MintError(
            "binding self-check failed: anchored digest "
            + anchored[:16] + "... != vsaPayloadSha256 "
            + vsa_payload_sha256_hex[:16] + "..."
        )
    artifacts.append({
        "anchoredDigestSha256": anchored,
        "boundary": REKOR_LEG_BOUNDARY,
        "entryKind": _entry_kind(body_b64),
        "kind": "rekor_v2_transparency_log",
        "leafHash": _leaf_hash_hex(body_b64),
        "logIndex": int(tle["log_index"]),
        "name": bundle_filename,
        "rekorShard": "https://" + _checkpoint_origin(checkpoint_envelope),
        "rfc3161GenTime": rfc3161_gen_time,
        "sha256": _sha256_file(out_dir / bundle_filename),
        "treeSize": int(ip["tree_size"]),
        "url": base + bundle_filename,
    })

    index: dict[str, Any] = {
        "artifacts": artifacts,
        "boundary": str(ext["boundary"]),
        "buildIdentity": {
            "buildType": str(build_identity["buildType"]),
            "builderId": str(build_identity["builderId"]),
            "path": str(build_identity["path"]),
            "ref": str(build_identity["ref"]),
            "repository": str(build_identity["repository"]),
            "sourceCommit": str(build_identity["sourceCommit"]),
        },
        "emittedAt": emitted_at,
        "policyDigest": str(predicate["policy"]["digest"]["sha256"]),
        "policyId": str(predicate["policy"]["uri"]),
        "schema": RELEASE_VSA_INDEX_SCHEMA,
        "verifiedLevels": [str(x) for x in predicate["verifiedLevels"]],
        "verifierId": str(predicate["verifier"]["id"]),
        "verifierKeyid": hashlib.sha256(
            base64.b64decode(operator_pin_b64, validate=True)
        ).hexdigest(),
        "verifierPublicKeyRaw": operator_pin_b64,
        "version": version,
        "vsaPayloadSha256": vsa_payload_sha256_hex,
    }
    bf = ext.get("backfill")  # __s226_backfill_index_mirror_v1__
    if isinstance(bf, dict):
        index["backfill"] = bf
    return index


# __s387_anchor_journal_v1__
ANCHOR_JOURNAL_SUFFIX = ".anchor-journal.json"
ANCHOR_JOURNAL_SCHEMA_VERSION = 1
JOURNAL_ATTEMPTED = "ATTEMPTED"
JOURNAL_LOGGED = "LOGGED"
_JOURNAL_BASE_KEYS = frozenset(
    {"rekorBaseUrl", "schemaVersion", "state", "version", "vsaPayloadSha256"}
)
_JOURNAL_LOGGED_KEYS = frozenset(
    {"canonicalizedBody", "checkpointEnvelope", "inclusionProofHashes", "logId", "logIndex"}
)


def anchor_journal_path(out_dir: Path) -> Path:
    """The anchor journal is a sibling of the resolved bundle directory
    (D386-1), never inside it, so the bundle's file set does not change."""
    resolved = out_dir.resolve()
    if not resolved.name:
        raise MintError(
            "bundle directory has no name to place an anchor journal beside: "
            + str(resolved)
        )
    return resolved.parent / (resolved.name + ANCHOR_JOURNAL_SUFFIX)


def _journal_bytes(record: dict[str, Any]) -> bytes:
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_journal(path: Path, record: dict[str, Any]) -> None:
    data = _journal_bytes(record)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".anchor-journal-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(path.parent)


def _remove_journal(path: Path) -> None:
    os.unlink(str(path))
    _fsync_dir(path.parent)


def _is_sha256_hex(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _journal_problem(record: object) -> str:
    if not isinstance(record, dict):
        return "not a JSON object"
    state = record.get("state")
    if state == JOURNAL_ATTEMPTED:
        expected = _JOURNAL_BASE_KEYS
    elif state == JOURNAL_LOGGED:
        expected = _JOURNAL_BASE_KEYS | _JOURNAL_LOGGED_KEYS
    else:
        return "unknown state " + repr(state)
    keys = frozenset(record)
    if keys != expected:
        return "keys " + str(sorted(keys)) + " are not " + str(sorted(expected))
    schema = record["schemaVersion"]
    if type(schema) is not int or schema != ANCHOR_JOURNAL_SCHEMA_VERSION:
        return (
            "schemaVersion " + repr(schema) + " is not "
            + str(ANCHOR_JOURNAL_SCHEMA_VERSION)
        )
    if not isinstance(record["version"], str) or not record["version"]:
        return "version is not a non-empty string"
    if not _is_sha256_hex(record["vsaPayloadSha256"]):
        return "vsaPayloadSha256 is not a lowercase sha256 hex digest"
    if record["rekorBaseUrl"] is not None and not isinstance(record["rekorBaseUrl"], str):
        return "rekorBaseUrl is neither a string nor null"
    if state == JOURNAL_ATTEMPTED:
        return ""
    if type(record["logIndex"]) is not int or record["logIndex"] < 0:
        return "logIndex is not a non-negative integer"
    if record["logId"] is not None and not isinstance(record["logId"], str):
        return "logId is neither a string nor null"
    for key in ("canonicalizedBody", "checkpointEnvelope"):
        if not isinstance(record[key], str) or not record[key]:
            return key + " is not a non-empty string"
    hashes = record["inclusionProofHashes"]
    if not isinstance(hashes, list) or not all(isinstance(h, str) for h in hashes):
        return "inclusionProofHashes is not a list of strings"
    return ""


def _read_journal(path: Path) -> dict[str, Any] | None:
    if not (path.is_symlink() or path.exists()):
        return None
    try:
        record = json.loads(path.read_bytes().decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError(
            "anchor journal unreadable: " + str(path) + ": " + str(exc)
            + "; refusing with no network call"
        ) from exc
    problem = _journal_problem(record)
    if problem:
        raise MintError(
            "anchor journal unreadable: " + str(path) + ": " + problem
            + "; refusing with no network call"
        )
    return record


class _JournaledEntry:
    """The Rekor entry as the journal recorded it; duck-typed like
    rekor_anchor_v2.RekorAnchorV2 for assemble_rekor_bundle."""

    def __init__(self, record: dict[str, Any]) -> None:
        self.body_b64: str = str(record["canonicalizedBody"])
        self.checkpoint_envelope: str = str(record["checkpointEnvelope"])
        self.inclusion_proof_hashes: list[str] = [
            str(h) for h in record["inclusionProofHashes"]
        ]
        self.log_index: int = int(record["logIndex"])


def _logged_journal(attempted: dict[str, Any], anchor_obj: Any) -> dict[str, Any]:
    log_id = getattr(anchor_obj, "log_id", None)
    logged = dict(attempted)
    logged.update(
        {
            "canonicalizedBody": str(anchor_obj.body_b64),
            "checkpointEnvelope": str(anchor_obj.checkpoint_envelope),
            "inclusionProofHashes": [str(h) for h in anchor_obj.inclusion_proof_hashes],
            "logId": None if log_id is None else str(log_id),
            "logIndex": int(anchor_obj.log_index),
            "state": JOURNAL_LOGGED,
        }
    )
    return logged


def _bundle_journal_mismatch(bundle: Any, entry: _JournaledEntry) -> str:
    """bundle is Any: it is parsed JSON of unchecked shape."""
    try:
        tle = bundle["transparency_log_entry"]
        body = tle["canonicalized_body"]
        log_index = tle["log_index"]
    except (KeyError, TypeError):
        return "the bundle has no transparency_log_entry with canonicalized_body and log_index"
    if body != entry.body_b64:
        return "canonicalized_body differs from the journal's"
    if type(log_index) is not int or log_index != entry.log_index:
        return "log_index " + repr(log_index) + " is not the journal's " + str(entry.log_index)
    return ""


# __s172_p0b2_anchor_orchestrator_v1__
def anchor(
    version: str,
    out_dir: Path,
    *,
    pins_dir: Path,
    anchor_fn: Any = None,
    timestamp_fn: Any = None,
    verify_fn: Any = None,
    rekor_base_url: str | None = None,
    tsa_base_url: str | None = None,
) -> int:
    """Anchor a minted release-VSA bundle to Rekor v2 (IRREVERSIBLE) + index.

    anchor_fn / timestamp_fn / verify_fn are injectable seams (defaults = the
    live rekor_anchor_v2 / tsa_client / cli_verify_release functions) so this
    orchestrator is testable offline. The single irreversible act is the one
    Rekor POST inside anchor_fn.

    An anchor journal beside the bundle directory records the attempt before
    the POST and the entry after it (docs/ANCHOR_JOURNAL_DESIGN.md, D386-1 to
    D386-6). A rerun resumes from a LOGGED journal without a second POST and
    refuses on an ATTEMPTED one. The journal is local operator state, not
    evidence.
    """
    _s485_root_prepare("anchor")  # __s485_root_guard_v1__
    _s485_own_dir(out_dir, "anchor: the dir", create=False)  # __s485h_root_paths_v1__

    import datetime as _dt

    import httpx
    import rekor_anchor

    if anchor_fn is None:
        import rekor_anchor_v2

        anchor_fn = rekor_anchor_v2.anchor_manifest_to_rekor_v2
        if rekor_base_url is None:
            rekor_base_url = rekor_anchor_v2.REKOR_V2_DEFAULT_BASE_URL
    if timestamp_fn is None:
        import tsa_client

        timestamp_fn = tsa_client.anchor_timestamp
        if tsa_base_url is None:
            tsa_base_url = tsa_client.TSA_DEFAULT_URL
    if verify_fn is None:
        import cli_verify_release

        verify_fn = cli_verify_release.verify_convergence

    vsa_name = "nous_lang-" + version + ".build-vsa.intoto.json"
    bundle_name = "nous_lang-" + version + ".rekor-v2-bundle.json"
    verifier_name = "verify_build_vsa_offline.py"
    verifier_key_name = "release-verifier-key.json"

    vsa_path = out_dir / vsa_name
    if not vsa_path.is_file():
        raise MintError("minted VSA not found (run mint first): " + str(vsa_path))
    alias_path = out_dir / VERIFIER_VSA_FILENAME  # __s236_p1_anchor_alias_gate_v1__
    if not alias_path.is_file():
        raise MintError(
            "bundle does not ship " + VERIFIER_VSA_FILENAME + ", the only "
            "filename its offline verifier reads; a stranger running the "
            "published procedure would get rc 2. Re-run mint. Refusing to anchor."
        )
    if alias_path.read_bytes() != vsa_path.read_bytes():
        raise MintError(
            VERIFIER_VSA_FILENAME + " and " + vsa_name + " differ; the bundle "
            "would verify bytes other than the ones it names. Refusing to anchor."
        )
    if not (out_dir / verifier_name).is_file():
        raise MintError("offline verifier not found in dir: " + verifier_name)
    if not (out_dir / verifier_key_name).is_file():
        raise MintError("release verifier key not found in dir: " + verifier_key_name)
    tr = pins_dir / "trusted_root.json"
    tsa = pins_dir / "tsa_chain.pem"
    if not tr.is_file():
        raise MintError("durable pin not found: " + str(tr))
    if not tsa.is_file():
        raise MintError("durable pin not found: " + str(tsa))

    bundle_path = out_dir / bundle_name
    index_path = out_dir / "index.json"
    journal_path = anchor_journal_path(out_dir)
    journal = _read_journal(journal_path)
    resumable_bundle = (
        journal is not None
        and journal["state"] == JOURNAL_LOGGED
        and not index_path.exists()
    )
    if bundle_path.exists() and not resumable_bundle:
        raise MintError(
            "rekor bundle already exists; refusing to re-anchor (a second "
            "Rekor write would create a divergent entry): " + str(bundle_path)
        )

    try:
        envelope = json.loads(vsa_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise MintError("cannot read minted VSA: " + str(exc)) from exc
    canonical = canonical_bytes_to_anchor(envelope)
    vsa_sha = vsa_payload_sha256(envelope)
    statement = decode_build_vsa_statement(envelope)

    if journal is not None and (
        journal["version"] != version or journal["vsaPayloadSha256"] != vsa_sha
    ):
        raise MintError(
            "anchor journal is for another VSA: " + str(journal_path)
            + " records version " + str(journal["version"])
            + " vsaPayloadSha256 " + str(journal["vsaPayloadSha256"])[:16]
            + "..., this run is version " + version
            + " vsaPayloadSha256 " + vsa_sha[:16]
            + "...; refusing with no network call"
        )

    if journal is None:
        attempted: dict[str, Any] = {
            "rekorBaseUrl": rekor_base_url,
            "schemaVersion": ANCHOR_JOURNAL_SCHEMA_VERSION,
            "state": JOURNAL_ATTEMPTED,
            "version": version,
            "vsaPayloadSha256": vsa_sha,
        }
        try:
            _write_journal(journal_path, attempted)
        except OSError as exc:
            tail = "; a rerun starts fresh"
            if journal_path.exists():
                try:
                    _remove_journal(journal_path)
                except OSError:
                    tail = (
                        "; the journal " + str(journal_path) + " is left "
                        "ATTEMPTED and a rerun refuses; no request was made, "
                        "so it can be deleted by hand"
                    )
            raise MintError(
                "cannot write the anchor journal " + str(journal_path) + ": "
                + str(exc) + "; no Rekor request was made" + tail
            ) from exc

        print("ANCHOR: submitting VSA payload digest to Rekor v2 (IRREVERSIBLE)")
        print("  version:          " + version)
        print("  vsaPayloadSha256: " + vsa_sha)
        print("  journal:          " + str(journal_path))
        try:
            if rekor_base_url is not None:
                anchor_obj = anchor_fn(canonical, base_url=rekor_base_url)
            else:
                anchor_obj = anchor_fn(canonical)
        except rekor_anchor.RekorUnavailable as exc:
            cause = exc.__cause__
            if isinstance(cause, (httpx.ConnectError, httpx.ConnectTimeout)):
                head = (
                    "rekor submit failed before any request left the host ("
                    + type(cause).__name__ + "): " + str(exc)
                )
                try:
                    _remove_journal(journal_path)
                except OSError as rm_exc:
                    raise MintError(
                        head + "; the anchor journal " + str(journal_path)
                        + " could not be removed (" + str(rm_exc) + "): it "
                        "stays ATTEMPTED and a rerun refuses; no entry was "
                        "created, so it can be deleted by hand"
                    ) from exc
                raise MintError(
                    head + "; anchor journal removed; a rerun submits afresh"
                ) from exc
            raise MintError(
                "rekor outcome unknown (RekorUnavailable"
                + ("" if cause is None else ", cause " + type(cause).__name__)
                + "): " + str(exc) + "; an entry may exist; anchor journal "
                "ATTEMPTED at " + str(journal_path)
                + "; a rerun refuses with no network call"
            ) from exc
        except (rekor_anchor.RekorRejected, httpx.HTTPError, OSError) as exc:
            raise MintError(
                "rekor outcome unknown (" + type(exc).__name__ + "): " + str(exc)
                + "; an entry may exist; anchor journal ATTEMPTED at "
                + str(journal_path) + "; a rerun refuses with no network call"
            ) from exc
        print("  log_index:        " + str(anchor_obj.log_index))
        logged = _logged_journal(attempted, anchor_obj)
        try:
            _write_journal(journal_path, logged)
        except OSError as exc:
            raise MintError(
                "cannot record the Rekor entry in the anchor journal "
                + str(journal_path) + ": " + str(exc) + "; the entry exists "
                "(log_index " + str(logged["logIndex"]) + "); a rerun refuses "
                "if the journal still reads ATTEMPTED and resumes if it reads LOGGED"
            ) from exc
    elif journal["state"] == JOURNAL_ATTEMPTED:
        raise MintError(
            "rekor outcome unknown from an earlier run: anchor journal "
            + str(journal_path) + " is ATTEMPTED; an entry may exist; refusing "
            "with no network call; the tool never submits again for this journal"
        )
    else:
        logged = journal
        print("ANCHOR: resuming from the anchor journal (no Rekor POST)")
        print("  version:          " + version)
        print("  vsaPayloadSha256: " + vsa_sha)
        print("  journal:          " + str(journal_path))
        print("  log_index:        " + str(logged["logIndex"]))

    entry = _JournaledEntry(logged)
    resume_note = (
        "; anchor journal LOGGED at " + str(journal_path)
        + " (log_index " + str(entry.log_index) + ")"
    )
    anchored = _anchored_digest_hex(entry.body_b64)
    if anchored != vsa_sha:
        raise MintError(
            "journaled rekor entry does not bind this VSA: anchored digest "
            + anchored[:16] + "... != vsaPayloadSha256 " + vsa_sha[:16] + "..."
            + resume_note + "; no further network call; a rerun refuses the same way"
        )

    if bundle_path.exists():
        sidecar = bundle_path.with_name(bundle_path.name + ".sha256")
        try:
            bundle_bytes = bundle_path.read_bytes()
            bundle = json.loads(bundle_bytes.decode("utf-8"))
            sidecar_bytes = sidecar.read_bytes() if sidecar.exists() else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MintError(
                "rekor bundle unreadable: " + str(bundle_path) + ": " + str(exc)
                + resume_note + "; refusing with no network call"
            ) from exc
        mismatch = _bundle_journal_mismatch(bundle, entry)
        if mismatch:
            raise MintError(
                "rekor bundle does not match the anchor journal: " + mismatch
                + resume_note + "; refusing with no network call"
            )
        sidecar_line = (
            _sha256_hex(bundle_bytes) + "  " + bundle_path.name + "\n"
        ).encode("ascii")
        if sidecar_bytes is None:
            try:
                _atomic_write(sidecar, sidecar_line)
            except OSError as exc:
                raise MintError(
                    "cannot write the rekor bundle sidecar: " + str(exc)
                    + resume_note + "; a rerun resumes at the self-verify"
                ) from exc
        elif sidecar_bytes != sidecar_line:
            raise MintError(
                "rekor bundle sidecar does not match the bundle: " + str(sidecar)
                + resume_note + "; refusing with no network call"
            )
        print("  bundle present; resuming at the self-verify (no network)")
    else:
        entry_sig_b64 = _derive_entry_signature(entry.body_b64)
        entry_sig_raw = base64.b64decode(entry_sig_b64, validate=True)
        try:
            if tsa_base_url is not None:
                token_der = timestamp_fn(
                    timestamped_data=entry_sig_raw, base_url=tsa_base_url
                )
            else:
                token_der = timestamp_fn(timestamped_data=entry_sig_raw)
        except (
            rekor_anchor.RekorUnavailable,
            rekor_anchor.RekorRejected,
            httpx.HTTPError,
            OSError,
        ) as exc:
            raise MintError(
                "TSA timestamp failed: " + str(exc) + resume_note
                + "; a rerun resumes without a Rekor POST"
            ) from exc

        bundle = assemble_rekor_bundle(entry, token_der)
        bundle_bytes = json.dumps(bundle, sort_keys=True, indent=2).encode("utf-8")
        try:
            _write_with_sidecar(bundle_path, bundle_bytes)
        except OSError as exc:
            raise MintError(
                "cannot write the rekor bundle: " + str(exc) + resume_note
                + "; a rerun resumes without a Rekor POST"
            ) from exc

    try:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "build-vsa.intoto.json").write_bytes(vsa_path.read_bytes())
            (tdir / "rekor-v2-bundle.json").write_bytes(bundle_bytes)
            (tdir / "trusted_root.json").write_bytes(tr.read_bytes())
            (tdir / "tsa_chain.pem").write_bytes(tsa.read_bytes())
            result = verify_fn(str(tdir), str(tdir))
    except OSError as exc:
        raise MintError(
            "cannot stage the post-anchor self-verify: " + str(exc) + resume_note
            + "; a rerun resumes at the self-verify"
        ) from exc

    convergence = str(result.get("convergence"))
    if convergence != "PASS":
        legs = result.get("legs", {})
        detail = ""
        if isinstance(legs, dict):
            detail = "; ".join(
                str(k) + "=" + str(v.get("status"))
                for k, v in legs.items()
                if isinstance(v, dict)
            )
        raise MintError(
            "post-anchor dual-root self-verify did NOT converge (convergence="
            + convergence + "); index NOT written. legs: " + detail
            + resume_note + "; a rerun resumes at the self-verify"
        )
    gen_time = str(result.get("evidence", {}).get("rfc3161_gen_time"))

    emitted_at = (
        _dt.datetime.now(_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    index = build_release_index(
        version,
        out_dir,
        statement=statement,
        bundle=bundle,
        bundle_filename=bundle_name,
        vsa_filename=vsa_name,
        verifier_filename=verifier_name,
        verifier_key_filename=verifier_key_name,
        operator_pin_b64=COMMITTED_RELEASE_PIN_B64,
        vsa_payload_sha256_hex=vsa_sha,
        rfc3161_gen_time=gen_time,
        emitted_at=emitted_at,
    )
    index_bytes = json.dumps(index, sort_keys=True, indent=2).encode("utf-8")
    try:
        _write_with_sidecar(index_path, index_bytes)
    except OSError as exc:
        raise MintError(
            "cannot write index.json: " + str(exc) + resume_note
            + "; a rerun resumes at the self-verify if index.json was not "
            "written, and refuses if it was"
        ) from exc

    ip = bundle["transparency_log_entry"]["inclusion_proof"]
    print("ANCHOR complete for nous-lang " + version)
    print("  bundle:      " + bundle_name)
    print("  index:       index.json")
    print("  log_index:   " + str(entry.log_index))
    print("  tree_size:   " + str(ip["tree_size"]))
    print("  gen_time:    " + gen_time)
    print("  convergence: PASS (offline dual-root)")
    print("  journal:     " + str(journal_path) + " (LOGGED, operator state, not evidence)")
    print()
    print(
        "Reversible from here: stage <dir> to /var/www + website/ mirror, "
        "commit. The Rekor entry is permanent."
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mint_release_vsa",
        description="Release-VSA MINT (Phase 1, reversible). No Rekor write.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("mint", help="Mint the partial release-VSA bundle (no anchor)")
    m.add_argument("version", help="Published version, e.g. 5.63.0")
    m.add_argument("--out", required=True, help="Output bundle directory")
    m.add_argument(
        "--key-path",
        default=DEFAULT_OPERATOR_KEY,
        help="Operator Ed25519 seed (default: " + DEFAULT_OPERATOR_KEY + ")",
    )
    m.add_argument(
        "--work-dir",
        default=None,
        help="Scratch dir for artifact downloads (default: a temp dir under --out)",
    )
    m.add_argument(
        "--backfill",
        action="store_true",
        help="Mark this VSA as a backfill minted later than release; "
        "injects a signed backfill disclosure. Omit for release-time mints.",
    )
    a = sub.add_parser(
        "anchor",
        help="Anchor a minted bundle to Rekor v2 (IRREVERSIBLE) + write index",
    )
    a.add_argument("version", help="Published version, e.g. 5.64.0")
    a.add_argument(
        "--dir", required=True, help="Minted bundle directory (from mint --out)"
    )
    a.add_argument(
        "--pins-dir",
        required=True,
        help="Durable operator pins dir (trusted_root.json + tsa_chain.pem)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command == "mint":
        out_dir = Path(args.out)
        work_dir = (
            Path(args.work_dir) if args.work_dir else out_dir / ".mint-work"
        )
        try:
            rc = mint(
                args.version,
                out_dir,
                key_path=Path(args.key_path),
                work_dir=work_dir,
                backfill=args.backfill,
            )
        except MintError as exc:
            print("MINT REFUSED: " + str(exc) + _s485_kept(exc), file=sys.stderr)
            return 2
        except _S485GuardImportError as exc:
            print("MINT REFUSED: " + str(exc), file=sys.stderr)
            return 2
        except Exception as exc:
            if not _s485_refused():
                raise
            return _s485_after("MINT", 2, exc)
        except SystemExit as exc:
            if not _s485_refused():
                raise
            return _s485_after("MINT", 2, exc)
        return _s485_after("MINT", rc)
    if args.command == "anchor":
        try:
            rc = anchor(
                args.version,
                Path(args.dir),
                pins_dir=Path(args.pins_dir),
            )
        except MintError as exc:
            print("ANCHOR REFUSED: " + str(exc) + _s485_kept(exc), file=sys.stderr)
            return 2
        except _S485GuardImportError as exc:
            print("ANCHOR REFUSED: " + str(exc), file=sys.stderr)
            return 2
        except Exception as exc:
            if not _s485_refused():
                raise
            return _s485_after("ANCHOR", 2, exc)
        except SystemExit as exc:
            if not _s485_refused():
                raise
            return _s485_after("ANCHOR", 2, exc)
        return _s485_after("ANCHOR", rc)
    print("usage: mint_release_vsa {mint,anchor} ...", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
