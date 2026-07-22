"""NOUS-TRACE v0.2.1 Producer bridge.  # __nous_trace_bridge_v1__

Runtime evidence layer for compiled NOUS runs. Emits the per-event signed
chain defined in trace/SPEC.md and produces an evidence pack verifiable by
trace/reference/verifier.py. Complements (does not replace) the end-of-run
TraceEnvelope in nous_trace.py.

Honest boundary:
  - Events are EVIDENCE (Ed25519 signatures over domain-tagged JCS hashes).
    Nothing here PROVES; the only PROVES legs remain Z3 and Farkas.
  - The DEFAULT anchor backend is "rfc3161-sim" (spec E5, TEST ONLY): a local
    Ed25519 key simulating a TSA. It evidences monotone ordering WITHIN the
    bundle and nothing about real time to an external auditor; Verifiers flag
    it unless the pack is marked test_vector (SPEC 10.1). Pass
    ``anchoring="rfc3161"`` for the production backend: an RFC 3161 token over
    the checkpoint Merkle root, whose genTime the Verifier recovers FROM the
    token -- the Producer never declares the time, which is the point. The
    Verifier resolves TSA roots auditor-pinned first (NOUS_TSA_ROOTS or
    tsa_roots.pem) and downgrades its report when they are operator-supplied.
    On TSA failure the checkpoint is emitted unanchored and the gap reported
    (SPEC 10.2) rather than failing the run. The `rekor` backend is not
    implemented.
  - The default Signer is IN-PROCESS. Pass ``signer_socket`` to delegate
    runtime signing (both per-event TAG_EVENT and checkpoint-root TAG_CKPT) to
    a standalone signer (signer_main.py) over UDS + SO_PEERCRED, so the runtime
    private key never enters this process. Signatures are byte-identical either
    way (same _Key, same domain-tagged JCS hashes; Ed25519 is deterministic),
    and the client cannot distinguish the two except by latency -- an
    observable drop-in. The standalone signer does NOT reuse InProcessSigner's
    in-memory gate: it enforces the same monotonic contract (and the same error
    messages) through a durable write-ahead counter store, so the gate survives
    restarts and refuses a second signature for any (trace_id, seq)
    (SPEC 7.4). SO_PEERCRED is a runtime custody control, NOT an evidence
    property: a verifier sees only a valid Ed25519 signature and cannot prove a
    UDS boundary was used.
  - The Deployment Key is on this host (keys_dir) ONLY in the default mode.
    Pass ``policy_pack`` to load an identity manifest (keys.json) and a policy
    manifest (obligations.json) pre-signed by an OFFLINE Deployment Key
    (signerctl.py export-identity -> deploy_sign.py on an air-gapped host):
    deployment.pem is then never loaded and dep.sign is never called, so the
    Deployment private key is absent from the runtime host, per the spec's
    two-tier model (SPEC 4.2). Startup then REFUSES unless the live signer's
    identity (key_id + algorithm + public_key) equals the deployment-approved
    runtime identity in the signed keys.json -- the active signer must be the
    approved signer before any evidence is produced.
"""
from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SPEC = "0.2.0"
TAG_EVENT = b"NOUS-TRACE/v0.2/event"
TAG_CKPT = b"NOUS-TRACE/v0.2/checkpoint-root"
TAG_OBL = b"NOUS-TRACE/v0.2/obligation-manifest"
TAG_KEYS = b"NOUS-TRACE/v0.2/keys-manifest"
TAG_ANCH = b"NOUS-TRACE/v0.2/anchor-sim"
MAX_INT = 2 ** 53 - 1


class TraceBridgeError(RuntimeError):
    pass


def _jcs_str(s):
    out = ['"']
    for ch in s:
        c = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\b':
            out.append('\\b')
        elif ch == '\t':
            out.append('\\t')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\f':
            out.append('\\f')
        elif ch == '\r':
            out.append('\\r')
        elif c < 0x20:
            out.append('\\u%04x' % c)
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def jcs(obj):
    if obj is None:
        return 'null'
    if obj is True:
        return 'true'
    if obj is False:
        return 'false'
    if isinstance(obj, int):
        if abs(obj) > MAX_INT:
            raise TraceBridgeError("INT_RANGE: " + str(obj))
        return str(obj)
    if isinstance(obj, float):
        raise TraceBridgeError("FLOAT_IN_SIGNED: floats are forbidden in signed objects")
    if isinstance(obj, str):
        return _jcs_str(obj)
    if isinstance(obj, list):
        return '[' + ','.join(jcs(x) for x in obj) + ']'
    if isinstance(obj, dict):
        ks = sorted(obj.keys(), key=lambda k: k.encode('utf-16-be'))
        return '{' + ','.join(_jcs_str(k) + ':' + jcs(obj[k]) for k in ks) + '}'
    raise TraceBridgeError("JCS_TYPE: " + type(obj).__name__)


def _sha(b):
    import hashlib
    return hashlib.sha256(b).digest()


def jcs_hash(obj):
    return _sha(jcs(obj).encode('utf-8'))


def _kid(pub_raw):
    return _sha(pub_raw)[:8].hex()


def _now_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_offset(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class _Key:
    def __init__(self, sk: Ed25519PrivateKey):
        self.sk = sk
        self.pub = sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.kid = _kid(self.pub)

    @classmethod
    def generate(cls):
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, path):
        if os.path.exists(path):
            with open(path, 'rb') as f:
                sk = serialization.load_pem_private_key(f.read(), password=None)
            return cls(sk)
        sk = Ed25519PrivateKey.generate()
        pem = sk.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(pem)
        return cls(sk)

    def sign(self, tag, obj_hash):
        return self.sk.sign(tag + b"\x00" + obj_hash).hex()


class InProcessSigner:
    """Same monotonicity contract as the future standalone Signer:
    refuses non-monotonic seq and prev_hash mismatch per trace_id."""

    def __init__(self, key: _Key):
        self.key = key
        self.state = {}

    def sign_event(self, ev_core):
        tid, seq = ev_core["trace_id"], ev_core["seq"]
        last_seq, last_hash = self.state.get(tid, (-1, "0" * 64))
        if seq != last_seq + 1:
            raise TraceBridgeError("signer: non-monotonic seq refused")
        if ev_core["prev_hash"] != last_hash:
            raise TraceBridgeError("signer: prev_hash mismatch refused")
        eh = jcs_hash(ev_core)
        self.state[tid] = (seq, eh.hex())
        return eh, self.key.sign(TAG_EVENT, eh)


class _RuntimeKeyProxy:
    """Stands in for the runtime _Key when signing is delegated to a standalone
    UDS signer. Holds NO private key: only kid + pub (learned via HELLO) and a
    handle to the signer client. .sign() delegates ONLY TAG_CKPT (the checkpoint
    root path at TraceBridge.checkpoint); event signing goes through
    self.signer.sign_event, never here."""

    def __init__(self, key_id_hex, pub_raw, signer_client):
        self.kid = key_id_hex
        self.pub = pub_raw
        self._signer = signer_client

    def sign(self, tag, obj_hash):
        if tag == TAG_CKPT:
            return self._signer.sign_checkpoint(obj_hash)
        raise TraceBridgeError(
            "runtime key proxy: only TAG_CKPT is delegated to the UDS signer; "
            "tag " + repr(tag) + " must be signed via sign_event")


class _EvalError(Exception):
    pass


def _ev(node, env):
    if not isinstance(node, dict):
        raise _EvalError()
    if "var" in node:
        if node["var"] not in env:
            raise _EvalError()
        return env[node["var"]]
    if "int" in node:
        if type(node["int"]) is not int:
            raise _EvalError()
        return node["int"]
    if "str" in node:
        if type(node["str"]) is not str:
            raise _EvalError()
        return node["str"]
    if "bool" in node:
        if type(node["bool"]) is not bool:
            raise _EvalError()
        return node["bool"]
    if "set" in node:
        if not isinstance(node["set"], list) or not all(
                type(x) is str for x in node["set"]):
            raise _EvalError()
        return frozenset(node["set"])
    op = node.get("op")
    if op == "and":
        return all(_eb(_ev(a, env)) for a in node["args"])
    if op == "or":
        return any(_eb(_ev(a, env)) for a in node["args"])
    if op == "not":
        return not _eb(_ev(node["arg"], env))
    if op in ("+", "-", "*"):
        l, r = _ei(_ev(node["left"], env)), _ei(_ev(node["right"], env))
        return l + r if op == "+" else l - r if op == "-" else l * r
    if op in ("=", "!="):
        l, r = _ev(node["left"], env), _ev(node["right"], env)
        if type(l) is not type(r) or isinstance(l, frozenset):
            raise _EvalError()
        return (l == r) if op == "=" else (l != r)
    if op in ("<", "<=", ">", ">="):
        l, r = _ei(_ev(node["left"], env)), _ei(_ev(node["right"], env))
        return {"<": l < r, "<=": l <= r, ">": l > r, ">=": l >= r}[op]
    if op == "prefix_of":
        l, r = _es(_ev(node["left"], env)), _es(_ev(node["right"], env))
        return r.startswith(l)
    if op == "in":
        l = _es(_ev(node["left"], env))
        r = _ev(node["right"], env)
        if not isinstance(r, frozenset):
            raise _EvalError()
        return l in r
    raise _EvalError()


def _eb(v):
    if type(v) is not bool:
        raise _EvalError()
    return v


def _ei(v):
    if type(v) is not int or type(v) is bool:
        raise _EvalError()
    return v


def _es(v):
    if type(v) is not str:
        raise _EvalError()
    return v


def evaluate_predicate(pred, env):
    try:
        return "pass" if _eb(_ev(pred, env)) else "fail"
    except _EvalError:
        return "error"


class TraceBridge:
    """Producer for one run. Streams signed events to trace.ndjson with
    fsync per event, so a crash yields INTEGRITY-OK/INCOMPLETE (adverse
    finding), never a silently editable log.

    obligations: list of dicts:
      {"label": str, "predicate": NOUS-EXPR AST, "variables": [{"name","type"}],
       "assurance": "proved"|"declared", "proof_artifact": bytes|None,
       "dossier_ref": str|None}
    """

    def __init__(self, pack_dir, actor, obligations, keys_dir,
                 dossier_ref=None, tolerance_s=600,
                 producer="nous-trace-bridge/0.1.0",
                 runtime_key_validity_s=86400,
                 signer_socket=None,
                 policy_pack=None,
                 anchoring="rfc3161-sim",
                 tsa_url=None,
                 tsa_timeout_s=30):
        if not isinstance(tolerance_s, int) or tolerance_s > 3600:
            raise TraceBridgeError("tolerance_s must be int <= 3600")
        if anchoring not in ("rfc3161-sim", "rfc3161"):
            raise TraceBridgeError(
                "unsupported anchoring backend: " + repr(anchoring)
                + " (expected 'rfc3161-sim' or 'rfc3161')")
        self._anchoring = anchoring
        self._tsa_url = tsa_url
        self._tsa_timeout_s = tsa_timeout_s
        self.anchor_failures = []
        self.pack = pack_dir
        self.actor = actor
        self.tolerance_s = tolerance_s
        self.producer = producer
        self.trace_id = str(uuid.uuid4())
        os.makedirs(self.pack, exist_ok=True)
        os.makedirs(keys_dir, exist_ok=True)

        self._policy_pack = policy_pack
        if policy_pack is None:
            self.dep = _Key.load_or_create(
                os.path.join(keys_dir, "deployment.pem"))
        else:
            self.dep = None
            if signer_socket is None:
                raise TraceBridgeError(
                    "policy_pack requires signer_socket: the "
                    "deployment-approved runtime identity is verified "
                    "against the live signer, which must own a persistent key")
        self.anch = _Key.load_or_create(os.path.join(keys_dir, "anchor_sim.pem"))
        if signer_socket is None:
            self.rt = _Key.generate()
            self._signer_client = None
        else:
            from uds_signer_client import UdsSignerClient
            self._signer_client = UdsSignerClient(signer_socket)
            self.rt = _RuntimeKeyProxy(
                self._signer_client.key_id,
                bytes.fromhex(self._signer_client.public_key_hex),
                self._signer_client)

        self._salts = set()
        self._events = []
        self._ehashes = []
        self._prev = "0" * 64
        self._last_ckpt_seq = 0
        self._obligations_by_label = {}
        self._finalized = False

        if policy_pack is not None:
            self._load_signed_policy_pack(policy_pack)
        else:
            self._build_and_sign_manifests(obligations, runtime_key_validity_s)

        if self._signer_client is None:
            self.signer = InProcessSigner(self.rt)
        else:
            self.signer = self._signer_client
        self._trace_f = open(os.path.join(self.pack, "trace.ndjson"), 'a')

        self._emit("run_start", {
            "obligation_manifest_hash": self._obl_hash.hex(),
            "keys_manifest_hash": self._keys_hash.hex(),
            "dossier_ref": dossier_ref,
            "producer": producer,
            "anchoring": self._anchoring,
            "tolerance_s": tolerance_s})

    def _build_and_sign_manifests(self, obligations,
                                  runtime_key_validity_s):
        obl_entries = []
        for o in obligations:
            pred = o["predicate"]
            oid = jcs_hash(pred).hex()
            assurance = o.get("assurance", "declared")
            proof_hash = None
            if assurance == "proved":
                blob = o.get("proof_artifact")
                if not blob:
                    raise TraceBridgeError(
                        "assurance=proved requires proof_artifact bytes for "
                        + o["label"])
                pdir = os.path.join(self.pack, "proofs")
                os.makedirs(pdir, exist_ok=True)
                proof_hash = _sha(blob).hex()
                with open(os.path.join(pdir, proof_hash), 'wb') as f:
                    f.write(blob)
            elif assurance != "declared":
                raise TraceBridgeError("assurance must be proved|declared")
            entry = {"obligation_id": oid, "label": o["label"],
                     "predicate": pred, "variables": o["variables"],
                     "assurance": assurance,
                     "proof_artifact_hash": proof_hash,
                     "dossier_ref": o.get("dossier_ref")}
            obl_entries.append(entry)
            self._obligations_by_label[o["label"]] = entry

        obl_core = {"obligations": obl_entries}
        self._obl_hash = jcs_hash(obl_core)
        with open(os.path.join(self.pack, "obligations.json"), 'w') as f:
            json.dump({"obligations": obl_entries,
                       "sig": self.dep.sign(TAG_OBL, self._obl_hash)}, f)

        keys = [{"key_id": self.rt.kid, "public_key": self.rt.pub.hex(),
                 "role": "runtime", "not_before": _ts_offset(-300),
                 "not_after": _ts_offset(runtime_key_validity_s)},
                {"key_id": self.dep.kid, "public_key": self.dep.pub.hex(),
                 "role": "deployment", "not_before": _ts_offset(-31536000),
                 "not_after": _ts_offset(315360000)}]
        keys_core = {"keys": keys}
        self._keys_hash = jcs_hash(keys_core)
        with open(os.path.join(self.pack, "keys.json"), 'w') as f:
            json.dump({"keys": keys,
                       "sig": self.dep.sign(TAG_KEYS, self._keys_hash)}, f)

        hashes = {}
        for fn in ("keys.json", "obligations.json"):
            with open(os.path.join(self.pack, fn), 'rb') as f:
                hashes[fn] = _sha(f.read()).hex()
        with open(os.path.join(self.pack, "manifest.json"), 'w') as f:
            json.dump({"spec_version": SPEC,
                       "anchoring": self._anchoring,
                       "tolerance_s": self.tolerance_s,
                       "trust_anchors": {"deployment_pub": self.dep.pub.hex(),
                                         "anchor_pub": self.anch.pub.hex()},
                       "hashes": hashes}, f)

    def _load_signed_policy_pack(self, policy_pack):
        # Load pre-signed keys.json + obligations.json VERBATIM, prove the
        # active signer matches the deployment-approved runtime identity, set
        # the same fields the online build would. No run_start here; the shared
        # __init__ tail emits it once.
        import shutil as _shutil
        src_keys = os.path.join(policy_pack, "keys.json")
        src_obl = os.path.join(policy_pack, "obligations.json")
        if not (os.path.isfile(src_keys) and os.path.isfile(src_obl)):
            raise TraceBridgeError(
                "policy_pack missing keys.json or obligations.json: "
                + policy_pack)
        with open(src_keys, "rb") as f:
            keys_bytes = f.read()
        with open(src_obl, "rb") as f:
            obl_bytes = f.read()
        keys_doc = json.loads(keys_bytes.decode("utf-8"))
        obl_doc = json.loads(obl_bytes.decode("utf-8"))
        self._keys_hash = jcs_hash({"keys": keys_doc["keys"]})
        self._obl_hash = jcs_hash({"obligations": obl_doc["obligations"]})

        rt_entries = [k for k in keys_doc["keys"] if k.get("role") == "runtime"]
        if len(rt_entries) != 1:
            raise TraceBridgeError(
                "policy_pack keys.json must carry exactly one runtime entry")
        approved = rt_entries[0]
        if (approved.get("key_id") != self.rt.kid
                or approved.get("public_key") != self.rt.pub.hex()):
            raise TraceBridgeError(
                "runtime identity mismatch: the active signer (key_id "
                + self.rt.kid + ") is not the deployment-approved runtime key "
                "(key_id " + str(approved.get("key_id")) + ") in the signed "
                "policy pack; refusing to produce evidence")
        if approved.get("algorithm", "ed25519") != "ed25519":
            raise TraceBridgeError(
                "policy_pack runtime entry declares unsupported algorithm "
                + repr(approved.get("algorithm")))

        dep_entries = [k for k in keys_doc["keys"]
                       if k.get("role") == "deployment"]
        if len(dep_entries) != 1:
            raise TraceBridgeError(
                "policy_pack keys.json must carry exactly one deployment entry")
        self._deployment_pub_hex = dep_entries[0]["public_key"]

        for entry in obl_doc["obligations"]:
            self._obligations_by_label[entry["label"]] = entry

        with open(os.path.join(self.pack, "keys.json"), "wb") as f:
            f.write(keys_bytes)
        with open(os.path.join(self.pack, "obligations.json"), "wb") as f:
            f.write(obl_bytes)
        src_proofs = os.path.join(policy_pack, "proofs")
        if os.path.isdir(src_proofs):
            _shutil.copytree(src_proofs, os.path.join(self.pack, "proofs"),
                             dirs_exist_ok=True)

        hashes = {}
        for fn in ("keys.json", "obligations.json"):
            with open(os.path.join(self.pack, fn), "rb") as f:
                hashes[fn] = _sha(f.read()).hex()
        with open(os.path.join(self.pack, "manifest.json"), "w") as f:
            json.dump({"spec_version": SPEC,
                       "anchoring": self._anchoring,
                       "tolerance_s": self.tolerance_s,
                       "trust_anchors": {
                           "deployment_pub": self._deployment_pub_hex,
                           "anchor_pub": self.anch.pub.hex()},
                       "hashes": hashes}, f)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._finalized:
            return False
        if exc_type is not None:
            try:
                self.error(kind=exc_type.__name__, message=str(exc)[:500])
                self.finalize(outcome="error")
            except Exception:
                pass
            return False
        self.finalize(outcome="completed")
        return False

    def _emit(self, etype, body, payload_refs=None, obligation_ref=None):
        if self._finalized:
            raise TraceBridgeError("bridge finalized; no further events")
        core = {"spec_version": SPEC, "trace_id": self.trace_id,
                "seq": len(self._events), "ts_wall": _now_ts(),
                "event_type": etype, "actor": self.actor, "body": body,
                "payload_refs": payload_refs or [],
                "obligation_ref": obligation_ref, "prev_hash": self._prev,
                "key_id": self.rt.kid}
        eh, sig = self.signer.sign_event(core)
        core["sig"] = sig
        self._events.append(core)
        self._ehashes.append(eh)
        self._prev = eh.hex()
        self._trace_f.write(json.dumps(core, separators=(',', ':')) + "\n")
        self._trace_f.flush()
        os.fsync(self._trace_f.fileno())
        return core

    def store_payload(self, cls, data: bytes, media_type="application/json"):
        if cls not in ("content", "evidence"):
            raise TraceBridgeError("payload class must be content|evidence")
        while True:
            salt = secrets.token_bytes(16)
            if salt not in self._salts:
                break
        self._salts.add(salt)
        h = _sha(salt + data).hex()
        d = os.path.join(self.pack, "payloads", cls)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, h), 'w') as f:
            json.dump({"salt": salt.hex(), "media_type": media_type,
                       "data": __import__("base64").b64encode(data).decode()}, f)
        return h

    def llm_call(self, model, provider, params_hash, input_bytes=None,
                 output_bytes=None):
        refs = []
        if input_bytes is not None:
            refs.append({"role": "input", "class": "content",
                         "hash": self.store_payload("content", input_bytes)})
        if output_bytes is not None:
            refs.append({"role": "output", "class": "content",
                         "hash": self.store_payload("content", output_bytes)})
        return self._emit("llm_call", {"model": model, "provider": provider,
                                       "params_hash": params_hash}, refs)

    def tool_call(self, tool, adapter, input_bytes=None, output_bytes=None):
        refs = []
        if input_bytes is not None:
            refs.append({"role": "input", "class": "content",
                         "hash": self.store_payload("content", input_bytes)})
        if output_bytes is not None:
            refs.append({"role": "output", "class": "content",
                         "hash": self.store_payload("content", output_bytes)})
        return self._emit("tool_call", {"tool": tool, "adapter": adapter}, refs)

    def policy_check(self, label, assignment, checker="nous-trace-bridge"):
        """Evaluates the obligation predicate over `assignment` itself and
        records that verdict, so recorded == recomputed by construction."""
        o = self._obligations_by_label.get(label)
        if o is None:
            raise TraceBridgeError("unknown obligation label: " + label)
        declared = {v["name"]: v["type"] for v in o["variables"]}
        if set(assignment.keys()) != set(declared.keys()):
            raise TraceBridgeError("assignment vars mismatch for " + label)
        for name, t in declared.items():
            v = assignment[name]
            ok = ((t == "int" and type(v) is int)
                  or (t == "bool" and type(v) is bool)
                  or (t == "string" and type(v) is str))
            if not ok:
                raise TraceBridgeError(
                    "assignment type mismatch for %s.%s" % (label, name))
        verdict = evaluate_predicate(o["predicate"], assignment)
        ah = self.store_payload("evidence", jcs(assignment).encode('utf-8'))
        self._emit("policy_check", {"checker": checker},
                   [{"role": "assignment", "class": "evidence", "hash": ah}],
                   {"obligation_id": o["obligation_id"], "verdict": verdict,
                    "assignment_hash": ah})
        return verdict

    def human_override(self, decision, operator_evidence: dict):
        h = self.store_payload("evidence", jcs(operator_evidence).encode('utf-8'))
        return self._emit("human_override", {"decision": decision},
                          [{"role": "decision", "class": "evidence", "hash": h}])

    def error(self, kind, message):
        return self._emit("error", {"kind": kind, "message": message})

    def _make_anchor(self, root):
        """Build the checkpoint anchor for the declared backend.

        rfc3161-sim (E5, TEST ONLY): a pinned local key signs
        SHA-256(root || gen_time). Evidences monotone ordering inside the
        bundle; nothing about real time to an external auditor.

        rfc3161 (production): an RFC 3161 token over the Merkle root itself.
        The time is the TSA's genTime, recovered by the Verifier FROM the
        token -- the Producer never declares it, which is the whole point.

        SPEC 10.2: on TSA failure return None (unanchored checkpoint); the
        run continues and the gap is reported, rather than losing the run.
        """
        if self._anchoring == "rfc3161-sim":
            gt = _now_ts()
            return {"type": "rfc3161-sim", "gen_time": gt,
                    "token": self.anch.sign(TAG_ANCH,
                                            _sha(root + gt.encode()))}
        import base64 as _b64
        try:
            from tsa_client import anchor_timestamp, TSA_DEFAULT_URL
            tok = anchor_timestamp(
                timestamped_data=root,
                base_url=self._tsa_url or TSA_DEFAULT_URL,
                timeout_seconds=self._tsa_timeout_s)
        except Exception as exc:  # network/TSA failure is not a run failure
            self.anchor_failures.append(
                {"from_seq": self._last_ckpt_seq, "error": repr(exc)})
            return None
        return {"type": "rfc3161",
                "token_b64": _b64.b64encode(tok).decode()}

    def checkpoint(self):
        fr = self._last_ckpt_seq
        to = len(self._events) - 1
        leaves = self._ehashes[fr:to + 1]
        root = self._merkle(leaves)
        body = {"range": {"from_seq": fr, "to_seq": to},
                "merkle_root": root.hex(),
                "root_sig": self.rt.sign(TAG_CKPT, root),
                "anchor": self._make_anchor(root)}
        ev = self._emit("checkpoint", body)
        self._last_ckpt_seq = ev["seq"]
        return ev

    @staticmethod
    def _merkle(leaves):
        if not leaves:
            return _sha(b'')
        if len(leaves) == 1:
            return _sha(b'\x00' + leaves[0])
        k = 1
        while k * 2 < len(leaves):
            k *= 2
        return _sha(b'\x01' + TraceBridge._merkle(leaves[:k])
                    + TraceBridge._merkle(leaves[k:]))

    def finalize(self, outcome="completed"):
        if self._finalized:
            return self.pack
        self._emit("run_end", {"outcome": outcome,
                               "events_total": len(self._events)})
        self.checkpoint()
        self._finalized = True
        self._trace_f.close()
        return self.pack

    def erase_content(self, payload_hash):
        """GDPR erasure: content payloads only. Evidence is non-erasable
        by construction (spec B4)."""
        p = os.path.join(self.pack, "payloads", "content", payload_hash)
        if not os.path.exists(p):
            raise TraceBridgeError("content payload not found: " + payload_hash)
        os.remove(p)
