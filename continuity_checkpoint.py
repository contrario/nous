"""nous continuity checkpoint: ledger head as a C2SP tlog-checkpoint signed note.

S178 P1 of the C2SP arc (proposal alpha). __s178_p1_continuity_checkpoint_module_v1__

Turns a continuity-ledger head into a c2sp.org/tlog-checkpoint signed note: an
RFC 6962 Merkle root over the ledger's link digests, serialized as the standard
3-line checkpoint body (origin / decimal tree size / base64 root hash), Ed25519-
signed by a DEDICATED operator log key that is distinct from the manifest/trace
keys and from the counterparty key (tripartite key separation: workload key,
auditor key, operator transparency key never mix). Optionally carries a budget-
envelope extension line: an offline-reprovable aggregate cost bound over the
exact links the root commits to.

Honest boundary (inviolable). The checkpoint EVIDENCES a tamper-evident,
position-fixed Merkle head that the public witness network can cosign for
split-view protection. The budget extension, when present, lets a third party
PROVE offline (rational arithmetic, no solver) that the sum of the committed
links' declared cost caps is within an authorized budget B -- over EXACTLY the
links the root commits to. It PROVES nothing about runs that were never logged
(omission is not defeated) and adds no runtime guard. NOUS is a monitor.

A budget envelope is NEVER fabricated from absent data: a link with no usable
cost_cap_usd is a fail-closed refusal when --budget is requested, not a silent
zero. Without --budget the checkpoint is rail-only (root + log signature).

Primitive reuse (no reimplementation). The Merkle tree is built with
rekor_v2_offline (_naive_root / _naive_proof; RFC 6962 0x00 leaf, 0x01 node).
The signed-note key id is rekor_checkpoint.ed25519_key_id. The signed bytes are
the note text (body lines, each newline-terminated, before the blank
separator), byte-identical to what rekor_checkpoint.verify_checkpoint_ed25519
and rekor_v2_offline.verify_checkpoint_signature consume.
"""
from __future__ import annotations

import base64
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Optional

import continuity_ledger as cl
import rekor_v2_offline as rkt
from manifest import load_or_create_keypair
from rekor_checkpoint import ed25519_key_id, parse_checkpoint

CONTINUITY_ORIGIN_PREFIX: str = "nous-lang.org/continuity/"
BUDGET_EXTENSION_TAG: str = "nous.aggregate.cost.farkas"
BUDGET_EXTENSION_VERSION: str = "v1"
BUDGET_LEAF_PREFIX: bytes = b"nous.budget.leaf.v1\n"  # __s180_p1_budget_in_tree__
LOG_KEY_DEFAULT_PATH: Path = Path(
    "~/.local/share/nous/keys/continuity-log/log_ed25519.pem"
)
_SIG_LINE_PREFIX: str = "\u2014 "


class ContinuityCheckpointError(RuntimeError):
    """Raised cause-first when a checkpoint cannot be formed under the
    design-freeze rules: an unwalkable ledger, an unpriced link under
    --budget, a budget that does not hold, or a malformed cost figure."""


def _canonical_bytes(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _load_bundles(ledger_dir: Path) -> list[tuple[Path, dict]]:
    if not ledger_dir.is_dir():
        raise ContinuityCheckpointError(
            "ledger dir not found: " + str(ledger_dir)
        )
    link_dirs = sorted(
        [c for c in ledger_dir.iterdir()
         if c.is_dir() and (c / "link.json").is_file()],
        key=lambda c: c.name,
    )
    if not link_dirs:
        raise ContinuityCheckpointError(
            "no link subdirs under " + str(ledger_dir)
        )
    out: list[tuple[Path, dict]] = []
    for sub_d in link_dirs:
        try:
            bundle: dict = {
                "cert": json.loads(
                    (sub_d / "conformance.json").read_text(encoding="utf-8")
                ),
                "trace": json.loads(
                    (sub_d / "trace.json").read_text(encoding="utf-8")
                ),
                "manifest": json.loads(
                    (sub_d / "manifest.json").read_text(encoding="utf-8")
                ),
                "link": json.loads(
                    (sub_d / "link.json").read_text(encoding="utf-8")
                ),
            }
        except (OSError, json.JSONDecodeError) as e:
            raise ContinuityCheckpointError(
                "malformed link dir " + sub_d.name + ": " + str(e)
            )
        rp = sub_d / "receipt.jws"
        if rp.is_file():
            try:
                bundle["receipt"] = json.loads(
                    rp.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as e:
                raise ContinuityCheckpointError(
                    "malformed receipt in " + sub_d.name + ": " + str(e)
                )
        out.append((sub_d, bundle))
    return out


def _rational_usd(value: object) -> Optional[Fraction]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            return Fraction(str(value))
        except (ValueError, ZeroDivisionError):
            return None
    if isinstance(value, dict) and "amount" in value:
        return _rational_usd(value.get("amount"))
    return None


def _ordered_caps(
    order: list[str], digest_to_manifest: dict[str, dict]
) -> list[Fraction]:
    caps: list[Fraction] = []
    for d in order:
        man = digest_to_manifest.get(d)
        if man is None:
            raise ContinuityCheckpointError(
                "internal: no manifest for committed link " + d[:16]
            )
        cap = _rational_usd(man.get("cost_cap_usd"))
        if cap is None:
            raise ContinuityCheckpointError(
                "link " + d[:16] + " carries no usable cost_cap_usd; a "
                "budget envelope cannot be proven over an unpriced run "
                "(refusing; omit --budget for a rail-only checkpoint)"
            )
        if cap < 0:
            raise ContinuityCheckpointError(
                "link " + d[:16] + " has a negative cost_cap_usd"
            )
        caps.append(cap)
    return caps


def _budget_extension_line(
    order: list[str], caps: list[Fraction], budget: Fraction
) -> tuple[str, dict]:
    total = sum(caps, Fraction(0))
    if total > budget:
        raise ContinuityCheckpointError(
            "budget envelope does not hold: sum of declared caps "
            + str(total) + " exceeds budget " + str(budget)
            + " (refusing to emit a budget extension that cannot verify)"
        )
    sidecar: dict = {
        "fragment": BUDGET_EXTENSION_TAG,
        "version": BUDGET_EXTENSION_VERSION,
        "budget": str(budget),
        "leaf_digests": list(order),
        "caps": [str(c) for c in caps],
    }
    leaf_set_hex = hashlib.sha256(_canonical_bytes(list(order))).hexdigest()
    cert_hex = hashlib.sha256(_canonical_bytes(sidecar)).hexdigest()
    line = (
        BUDGET_EXTENSION_TAG + " " + BUDGET_EXTENSION_VERSION
        + " budget=" + str(budget)
        + " leaf_set=" + leaf_set_hex
        + " cert=" + cert_hex
    )
    return line, sidecar


def _budget_leaf_bytes(sidecar: dict) -> bytes:  # __s180_p1_budget_in_tree__
    cert_hex = hashlib.sha256(_canonical_bytes(sidecar)).hexdigest()
    return BUDGET_LEAF_PREFIX + bytes.fromhex(cert_hex)


def build_continuity_checkpoint(
    ledger_dir: Path,
    *,
    log_key_path: Optional[Path] = None,
    budget: Optional[str] = None,
    counterparty_public_key_pem: Optional[bytes] = None,
    expected_issuer: Optional[str] = None,
    expected_audience: Optional[str] = None,
    emit_inclusion: bool = False,
) -> dict:
    """Walk the ledger, build the RFC 6962 root over the committed link
    digests (plus, when priced, an in-tree budget-commitment leaf binding
    sha256(canonical sidecar) so the root commits the cost-cap proof, S180),
    serialize the C2SP checkpoint body, optionally append a budget
    extension, sign the note with the dedicated operator log key, and write
    checkpoint.note (plus optional per-link inclusion proofs) into ledger_dir.

    The order is established by continuity_ledger.walk_continuity_ledger
    (single genesis, single chain, fail-closed); the Merkle leaf sequence is
    that order, so the root is a deterministic commitment to the exact set.
    Witness additivity (F5): with no counterparty public key, receipts are
    stripped before the walk so chain + conformance still verify. Returns a
    summary dict. Raises ContinuityCheckpointError, cause-first."""
    loaded = _load_bundles(ledger_dir)
    bundles = [b for _sub, b in loaded]
    if counterparty_public_key_pem is None:
        for b in bundles:
            b.pop("receipt", None)
        cp_keys: Optional[dict] = None
    elif expected_issuer is not None:
        cp_keys = {expected_issuer: counterparty_public_key_pem}
    else:
        cp_keys = None
    try:
        report = cl.walk_continuity_ledger(
            bundles,
            counterparty_keys=cp_keys,
            expected_audience=expected_audience,
            expected_issuer=expected_issuer,
        )
    except cl.ContinuityLedgerError as e:
        raise ContinuityCheckpointError(
            "ledger does not walk fail-closed: " + str(e)
        )
    order: list[str] = list(report["order"])
    if not order:
        raise ContinuityCheckpointError("empty ledger order")

    digest_to_manifest: dict[str, dict] = {}
    for _sub, b in loaded:
        d = b["link"].get("this_link_digest")
        if isinstance(d, str):
            digest_to_manifest[d] = b["manifest"]

    link_leaves = [bytes.fromhex(d) for d in order]
    origin = CONTINUITY_ORIGIN_PREFIX + order[0]

    sidecar: Optional[dict] = None
    budget_str: Optional[str] = None
    ext_line: Optional[str] = None
    budget_leaf: Optional[bytes] = None
    if budget is not None:  # __s180_p1_budget_in_tree__
        try:
            budget_q = Fraction(str(budget))
        except (ValueError, ZeroDivisionError):
            raise ContinuityCheckpointError(
                "budget is not a rational USD value: " + repr(budget)
            )
        if budget_q < 0:
            raise ContinuityCheckpointError("budget must be non-negative")
        caps = _ordered_caps(order, digest_to_manifest)
        ext_line, sidecar = _budget_extension_line(order, caps, budget_q)
        budget_leaf = _budget_leaf_bytes(sidecar)
        budget_str = str(budget_q)

    leaves = link_leaves if budget_leaf is None else link_leaves + [budget_leaf]
    root = rkt._naive_root(leaves)
    body_lines: list[str] = [
        origin,
        str(len(leaves)),
        base64.b64encode(root).decode("ascii"),
    ]
    if ext_line is not None:
        body_lines.append(ext_line)

    note_text = "".join(ln + "\n" for ln in body_lines)

    priv, pub, resolved = load_or_create_keypair(
        log_key_path if log_key_path is not None else LOG_KEY_DEFAULT_PATH
    )
    key_id = ed25519_key_id(origin, pub)
    sig = priv.sign(note_text.encode("utf-8"))
    sig_line = (
        _SIG_LINE_PREFIX + origin + " "
        + base64.b64encode(key_id + sig).decode("ascii")
    )
    envelope = note_text + "\n" + sig_line + "\n"

    note_path = ledger_dir / "checkpoint.note"
    note_path.write_text(envelope, encoding="utf-8")
    written: list[str] = [str(note_path)]

    if sidecar is not None:
        sidecar_path = ledger_dir / "aggregate.cost.farkas.json"
        sidecar_path.write_bytes(_canonical_bytes(sidecar))
        written.append(str(sidecar_path))

    if emit_inclusion:
        inc_dir = ledger_dir / "inclusion"
        inc_dir.mkdir(parents=True, exist_ok=True)
        for i, d in enumerate(order):
            proof = rkt._naive_proof(leaves, i)
            doc = {
                "leaf_index": i,
                "tree_size": len(leaves),
                "this_link_digest": d,
                "proof": [
                    base64.b64encode(h).decode("ascii") for h in proof
                ],
            }
            p = inc_dir / (str(i).zfill(3) + ".proof.json")
            p.write_bytes(_canonical_bytes(doc))
            written.append(str(p))

    return {
        "origin": origin,
        "tree_size": len(leaves),
        "root_b64": base64.b64encode(root).decode("ascii"),
        "log_key_path": str(resolved),
        "log_key_id_hex": key_id.hex(),
        "budget": budget_str,
        "witnessed_ratio": report.get("witnessed_ratio"),
        "written": written,
    }


def build_continuity_proof(
    ledger_dir: Path,
    prior_checkpoint_path: Path,
    out_path: Path,
) -> dict:  # __s183_p1b_continuity_proof_producer_v1__
    """Emit an UNSIGNED RFC 9162 consistency proof binding a prior rail
    checkpoint to the current ledger head, so an offline auditor can detect
    rollback, rewrite/reorder, or truncation of already-witnessed rail
    records. Rail scope only: a priced (extension-bearing) prior is refused
    because the trailing budget leaf interleaves and naive prefix-consistency
    over priced signed roots does not hold (tree-reshape sub-arc).

    Honest boundary: the proof EVIDENCES append-only structure between two
    roots. It does NOT, alone, defeat split-view equivocation and does NOT
    detect never-logged omission. Refuses cause-first on any consistency
    violation; never emits a proof it cannot itself verify."""
    parsed = parse_checkpoint(
        prior_checkpoint_path.read_text(encoding="utf-8")
    )
    if parsed.extensions:
        raise ContinuityCheckpointError(
            "prior checkpoint carries extension line(s); continuity proofs "
            "are rail-only (priced-checkpoint continuity needs the tree-"
            "reshape sub-arc): refusing"
        )
    loaded = _load_bundles(ledger_dir)
    bundles = [b for _sub, b in loaded]
    for b in bundles:
        b.pop("receipt", None)
    try:
        report = cl.walk_continuity_ledger(bundles)
    except cl.ContinuityLedgerError as e:
        raise ContinuityCheckpointError(
            "current ledger does not walk fail-closed: " + str(e)
        )
    order: list[str] = list(report["order"])
    n = len(order)
    if n == 0:
        raise ContinuityCheckpointError("current ledger order is empty")
    leaves = [bytes.fromhex(d) for d in order]
    expected_origin = CONTINUITY_ORIGIN_PREFIX + order[0]
    if parsed.origin != expected_origin:
        raise ContinuityCheckpointError(
            "origin mismatch: prior checkpoint origin " + repr(parsed.origin)
            + " != expected " + repr(expected_origin)
            + " (different log / wrong genesis): refusing"
        )
    m = parsed.tree_size
    if m > n:
        raise ContinuityCheckpointError(
            "rollback: prior tree_size " + str(m) + " exceeds current "
            "ledger size " + str(n) + " (truncation/rollback): refusing"
        )
    if m < 1:
        raise ContinuityCheckpointError(
            "prior tree_size must be >= 1; got " + str(m)
        )
    prefix_root = rkt._naive_root(leaves[:m])
    if prefix_root != parsed.root_hash:
        raise ContinuityCheckpointError(
            "rewrite: the first " + str(m) + " current leaves do not "
            "reproduce the prior root (history rewritten/reordered): refusing"
        )
    current_root = rkt._naive_root(leaves)
    proof = rkt.naive_consistency_proof(leaves, m)
    rkt.verify_consistency(m, n, parsed.root_hash, current_root, proof)
    doc: dict = {
        "kind": "nous.continuity.consistency.v1",
        "origin": expected_origin,
        "prior_tree_size": m,
        "current_tree_size": n,
        "prior_root_b64": base64.b64encode(parsed.root_hash).decode("ascii"),
        "current_root_b64": base64.b64encode(current_root).decode("ascii"),
        "proof": [base64.b64encode(h).decode("ascii") for h in proof],
    }
    out_path.write_bytes(_canonical_bytes(doc))
    return doc
