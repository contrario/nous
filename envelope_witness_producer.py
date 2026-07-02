"""nous envelope witness producer: assemble envelope.witness.json (Inc D).

S196 of the PCE arc. __s196_incd_producer_module_v1__

COMPOSE-ONLY (no new crypto). Assembles the witness-quorum sidecar that the
S194 offline embed (dossier._ENVELOPE_WITNESS_CHECK_EMBED) verifies, from:

  - the log-signed envelope checkpoint note (envelope_ledger.build_envelope_
    checkpoint -> "envelope_note"), whose note_text_bytes the witnesses cosigned;
  - the fan, derived SOLELY from the operator's append-only store via
    envelope_ledger.load_fan_pairs (single source of truth; fan order == leaf
    order == checkpoint order by construction);
  - collected 0x04 Ed25519 cosignature lines from INDEPENDENT witnesses;
  - operator-pinned expected (name, Ed25519 public key) bindings.

COLLECTOR, NOT MINTER. This module holds only the log key (to build the
checkpoint). It NEVER holds or generates witness keys and NEVER self-cosigns.
An operator that mints its own witness keypairs and self-cosigns voids the
non-equivocation property entirely (the k-of-n count would then evidence
nothing about independence). Cosignatures are COLLECTED from parties other than
the operator, out-of-band; this module only assembles what it is handed.

VERIFY-BEFORE-INCLUDE. Every collected line is verified against exactly one
operator-pinned (name, key) via continuity_cosign.verify_cosignature_entry
BEFORE it enters the sidecar. A line matching no pin, or failing signature under
its pinned key, causes a typed refusal with ZERO writes. This is what makes
"collector not minter" true in practice, not only in this docstring.

HONEST BOUNDARY. Operator-side pinning here is a COLLECTION-TIME integrity
check; it does NOT establish witness independence. The sidecar carries the
operator-supplied witnesses as the offline verifier's DOWNGRADE fallback only;
the auditor's own witness_keys.json (or NOUS_WITNESS_KEYS) pin remains
authoritative and the verifier's operator-supplied downgrade is unchanged. A
verified cosignature EVIDENCES that a pinned-key holder attested exactly this
checkpoint head; it PROVES nothing (only Z3/Farkas prove). Monitor, not gate.

SPLIT-VIEW is refused at WITNESS time (each witness verifies RFC 9162
consistency before cosigning a successor). The offline verifier does NOT
re-check consistency, by shipped design; this producer likewise does not, and
its help says so, so no reader assumes the verifier catches split-view.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Optional, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from continuity_cosign import verify_cosignature_entry
from envelope_ledger import (
    ENVELOPE_LEAF_PREFIX,
    EnvelopeLog,
    build_envelope_checkpoint,
    envelope_commitment,
    load_fan_pairs,
)
from rekor_checkpoint import parse_checkpoint
import rekor_v2_offline as _rkt

WITNESS_SCHEMA_VERSION: int = 1


class WitnessProducerError(RuntimeError):
    """Raised cause-first on any assemble refusal: a malformed checkpoint note,
    an empty or mis-ordered fan, a fan that does not re-derive the checkpoint
    head, a malformed pin, a non-positive threshold, or a collected cosignature
    line that matches no operator-pinned (name, key). Refusal writes nothing."""


def _load_pins(pin_objs):
    pins = []
    seen = set()
    for obj in pin_objs:
        if not isinstance(obj, dict):
            raise WitnessProducerError("a witness pin is not an object")
        name = obj.get("name")
        pub_b64 = obj.get("pubkey_b64")
        if not isinstance(name, str) or not name or " " in name or "\n" in name:
            raise WitnessProducerError(
                "a witness pin has a missing or malformed name"
            )
        if name in seen:
            raise WitnessProducerError(
                "duplicate witness name " + repr(name) + " in the pin set"
            )
        seen.add(name)
        try:
            raw = base64.b64decode(pub_b64, validate=True)
        except Exception as exc:
            raise WitnessProducerError(
                "witness " + repr(name) + " pubkey_b64 is not valid base64"
            ) from exc
        if len(raw) != 32:
            raise WitnessProducerError(
                "witness " + repr(name) + " pubkey is not a 32-byte Ed25519 key"
            )
        try:
            pub = Ed25519PublicKey.from_public_bytes(raw)
        except Exception as exc:
            raise WitnessProducerError(
                "witness " + repr(name) + " pubkey is not a valid Ed25519 key"
            ) from exc
        pins.append((name, raw, pub))
    if not pins:
        raise WitnessProducerError("pin set is empty: no expected witnesses")
    return pins


def _fan_reproduces_head(fan_pairs, checkpoint_note):
    """Re-derive env_root from the store fan and confirm it reproduces the
    checkpoint head: len(fan) == tree_size AND naive_root(fan leaves) == root.
    Returns (tree_size, root_hash) on success, raises on any mismatch."""
    cp = parse_checkpoint(checkpoint_note)
    if not fan_pairs:
        raise WitnessProducerError(
            "fan is empty: the store has no committed envelopes to enumerate"
        )
    leaves = []
    for pce_sha256, pce_anchor_sha256 in fan_pairs:
        commitment = envelope_commitment(pce_sha256, pce_anchor_sha256)
        leaves.append(ENVELOPE_LEAF_PREFIX + commitment)
    if len(leaves) != cp.tree_size:
        raise WitnessProducerError(
            "fan length " + str(len(leaves)) + " != checkpoint tree_size "
            + str(cp.tree_size) + " (the store fan disagrees with the signed "
            "head; refusing to assemble)"
        )
    derived = _rkt._naive_root(leaves)
    if derived != cp.root_hash:
        raise WitnessProducerError(
            "re-derived env_root " + derived.hex()[:16] + "... != checkpoint "
            "root " + cp.root_hash.hex()[:16] + "... (the store fan does not "
            "reproduce the committed head; refusing to assemble)"
        )
    return cp


def assemble_witness_sidecar(
    checkpoint_note: str,
    cosig_lines: Sequence[str],
    pin_objs: Sequence[dict],
    threshold: int,
    *,
    store_path: Optional[Path] = None,
    fan_pairs=None,
) -> dict:
    """Assemble a witness-quorum sidecar dict, VERIFY-BEFORE-INCLUDE.

    fan is derived from the operator store via load_fan_pairs (single source);
    fan_pairs is accepted only for testing against a synthetic store copy. Each
    collected cosignature line is verified against exactly one operator-pinned
    (name, key); a line matching no pin -> WitnessProducerError, zero writes.
    """
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise WitnessProducerError(
            "threshold must be a positive int (got " + repr(threshold) + ")"
        )
    if not isinstance(checkpoint_note, str) or not checkpoint_note:
        raise WitnessProducerError("checkpoint_note must be a non-empty string")

    pins = _load_pins(pin_objs)
    if threshold > len(pins):
        raise WitnessProducerError(
            "threshold " + str(threshold) + " exceeds the number of pinned "
            "witnesses " + str(len(pins)) + "; the quorum can never be met"
        )

    if fan_pairs is None:
        fan_pairs = load_fan_pairs(store_path)
    cp = _fan_reproduces_head(fan_pairs, checkpoint_note)
    note_body = cp.note_text_bytes

    included = []
    included_names = set()
    for raw_line in cosig_lines:
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split(" ")
        if len(parts) < 3 or parts[0] != "\u2014":
            raise WitnessProducerError(
                "collected line is not a cosignature note line: " + repr(line)
            )
        try:
            blob = base64.b64decode(parts[2])
        except Exception as exc:
            raise WitnessProducerError(
                "collected line payload is not base64: " + repr(line)
            ) from exc
        line_name = parts[1]
        line_key_id = blob[:4]
        line_payload = blob[4:]
        matched = None
        for name, raw, pub in pins:
            if verify_cosignature_entry(
                note_body, name, pub, line_name, line_key_id, line_payload
            ):
                matched = name
                break
        if matched is None:
            raise WitnessProducerError(
                "collected cosignature line from " + repr(line_name) + " "
                "matches no operator-pinned (name, key) or fails verification; "
                "refusing to include it (collector, not minter): " + repr(line)
            )
        if matched not in included_names:
            included_names.add(matched)
        included.append(line)

    note = checkpoint_note
    if not note.endswith("\n"):
        note = note + "\n"
    note = note + "".join(ln + "\n" for ln in included)

    return {
        "witness_schema_version": WITNESS_SCHEMA_VERSION,
        "checkpoint_note": note,
        "fan": [[p, a] for (p, a) in fan_pairs],
        "threshold": threshold,
        "witnesses": [
            {"name": n, "pubkey_b64": base64.b64encode(r).decode("ascii")}
            for (n, r, _pub) in pins
        ],
    }


def write_witness_sidecar(sidecar: dict, out_path: Path) -> Path:
    data = json.dumps(sidecar, sort_keys=True, separators=(",", ":")).encode("utf-8")
    out_path.write_bytes(data)
    return out_path


def emit_add_checkpoint_body(
    log: EnvelopeLog, log_key: Ed25519PrivateKey, prev_size: int
) -> tuple[bytes, dict]:  # __s199_emit_add_checkpoint_v1__
    """Emit the C2SP tlog-witness add-checkpoint request body for the current
    envelope checkpoint: the emit half of the already-shipped --assemble-only.

    Body framing (each line U+000A-terminated):
        old <prev_size>          decimal, no leading zeros; "0" at genesis
        <b64(hash)>              0..63 RFC 6962 consistency-proof lines;
                                 MUST be empty iff prev_size == 0 (genesis)
        <empty line>
        <checkpoint note>        build_envelope_checkpoint()["envelope_note"]

    Pure: reads no store, writes nothing, contacts no network. No live caller
    (DARK): the --emit-request CLI wiring and the live-network round trip are
    deferred to the post-join increment.

    Honest boundary: this EVIDENCES nothing by itself. It emits a request; the
    witness cosignatures it later collects evidence append-only STRUCTURE
    (non-equivocation), not content correctness. Monitor, not guard; "proves"
    stays reserved for Z3/Farkas.
    """
    ckpt = build_envelope_checkpoint(log, log_key)
    env_size = ckpt["env_size"]
    if prev_size < 0 or prev_size > env_size:
        raise ValueError(
            "old size %d out of range for checkpoint size %d"
            % (prev_size, env_size)
        )
    proof = [] if prev_size == 0 else _rkt.naive_consistency_proof(
        log.leaves(), prev_size
    )
    proof_b64 = []
    for h in proof:
        if not isinstance(h, (bytes, bytearray)):
            raise TypeError("proof element is not bytes: " + repr(type(h)))
        proof_b64.append(base64.b64encode(bytes(h)).decode("ascii"))
    if len(proof_b64) > 63:
        raise ValueError("consistency proof exceeds 63 lines")
    head = "old %d\n" % prev_size + "".join(ln + "\n" for ln in proof_b64) + "\n"
    body = head.encode("ascii") + ckpt["envelope_note"].encode("utf-8")
    return body, ckpt
