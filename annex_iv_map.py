"""S135 -- Annex IV evidence-map sidecar (build + offline verify).

A signed, byte-deterministic sidecar that INDEXES a NOUS dossier's evidence
objects against the nine items of EU AI Act Annex IV. It is checkable offline
with cryptography + stdlib only (no Z3, no network, no NOUS install), reusing
the manifest's Ed25519 + canonical-JSON recipe verbatim. It adds NO new
cryptography and grows NO trust base.

WHAT THE SIDECAR PROVES (offline, fail-closed):
  1. The map is authored: Ed25519 signature over its own canonical body bytes.
  2. The map is bound to THIS dossier: map.manifest_canonical_sha256 equals the
     sha256 of the dossier manifest's canonical body (signature and
     transparency_log stripped) -- the same canonical identity every NOUS
     offline verifier computes.
  3. Every referenced evidence object is present AND authentic: the recorded
     sha256 equals sha256 of the file's raw bytes as they sit in the dossier.
  4. Indexing completeness: every one of the nine canonical Annex IV items
     appears as a key, with the canonical title and a clause kind consistent
     with its evidence (evidence-backed item carries >=1 reference;
     documentation-clause and operator-responsibility items carry zero, by
     design and without over-claim).

WHAT IT DOES NOT PROVE:
  - Legal sufficiency. Presence + authenticity + indexing is NOT adequacy.
  - That a referenced file actually satisfies its Annex IV item -- that is a
    human reviewer's judgement, never a hash check.
  - Content completeness or regulatory correctness of any artifact.
  - Anything about execution conformance.

DESIGN NOTES:
  - The canonical item->evidence correspondence is taken verbatim from the
    dossier's own self-describing table (dossier._annex_iv_readme); the sidecar
    INDEXES what the dossier already declares, it does not invent new mappings.
  - The map document is carried and validated as a plain dict, never re-typed
    through a Pydantic model, because re-typing could reorder keys or coerce
    fields, change the canonical body bytes, and break the Ed25519 signature
    (the lesson recorded in remedy_proof.py).
  - build_annex_iv_map takes an Ed25519 private key object; it performs NO key
    I/O. Key loading (load_or_create_keypair) belongs to the later CLI/emit
    unit, not to this pure core.

# __s135_annex_iv_map_module_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ANNEX_IV_MAP_SCHEMA_VERSION: int = 1

_MANIFEST_FILENAME: str = "manifest.json"
_MAP_FILENAME: str = "annex_iv_map.json"

# Clause kinds.
_EVIDENCE_BACKED: str = "evidence-backed"
_DOCUMENTATION_CLAUSE: str = "documentation-clause"
_OPERATOR_RESPONSIBILITY: str = "operator-responsibility"

_CLAUSE_KINDS: frozenset[str] = frozenset(
    {_EVIDENCE_BACKED, _DOCUMENTATION_CLAUSE, _OPERATOR_RESPONSIBILITY}
)

# Canonical nine-item table, verbatim from dossier._annex_iv_readme.
# Each entry: (item_id, title, candidate_evidence, clause_kind).
# candidate_evidence is a tuple of (filename, role); only candidates present
# in the dossier directory are indexed (drop-when-absent). An evidence-backed
# item with no present candidate is a missing-evidence error (fail-closed).
ANNEX_IV_ITEMS: tuple[
    tuple[str, str, tuple[tuple[str, str], ...], str], ...
] = (
    (
        "1",
        "General description",
        (("manifest.json", "primary"),),
        _EVIDENCE_BACKED,
    ),
    (
        "2",
        "Detailed description (development process)",
        (("source.nous", "primary"),),
        _EVIDENCE_BACKED,
    ),
    (
        "3",
        "Monitoring and control",
        (("manifest.json", "primary"),),
        _EVIDENCE_BACKED,
    ),
    (
        "4",
        "Performance metrics",
        (("manifest.json", "primary"),),
        _EVIDENCE_BACKED,
    ),
    (
        "5",
        "Risk management system (Article 9)",
        (("source.nous", "primary"), ("manifest.json", "supporting")),
        _EVIDENCE_BACKED,
    ),
    (
        "6",
        "Lifecycle changes",
        (("manifest.json", "primary"),),
        _EVIDENCE_BACKED,
    ),
    (
        "7",
        "Standards applied",
        (),
        _DOCUMENTATION_CLAUSE,
    ),
    (
        "8",
        "EU declaration of conformity",
        (),
        _OPERATOR_RESPONSIBILITY,
    ),
    (
        "9",
        "Post-market monitoring",
        (),
        _DOCUMENTATION_CLAUSE,
    ),
)


class AnnexIvMapError(RuntimeError):
    """Raised when an Annex IV map cannot be built. The message starts with
    the cause."""


def _canonical_body_bytes(doc: dict) -> bytes:
    """Canonical bytes of a sidecar document: signature stripped, sorted keys,
    no whitespace. The sidecar carries no transparency_log."""
    body = {k: v for k, v in doc.items() if k != "signature"}
    return json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _manifest_canonical_body_bytes(manifest: dict) -> bytes:
    """Canonical bytes of a dossier manifest: signature AND transparency_log
    stripped, sorted keys, no whitespace. Identical recipe to every NOUS
    offline dossier verifier."""
    body = {
        k: v for k, v in manifest.items()
        if k not in ("signature", "transparency_log")
    }
    return json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _public_key_b64(public_key: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_annex_iv_map(
    dossier_dir: Path,
    private_key: Ed25519PrivateKey,
) -> dict:
    """Build a signed Annex IV evidence-map dict for a dossier directory.

    Pure: reads the dossier files, signs with the supplied key, returns the
    map dict. Writes nothing. Raises AnnexIvMapError fail-closed on a missing
    manifest, an unreadable manifest, or an evidence-backed item whose
    candidate evidence is absent from the dossier.
    """
    dossier_dir = Path(dossier_dir)
    manifest_path = dossier_dir / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise AnnexIvMapError(
            "manifest.json not found in dossier directory: "
            + str(dossier_dir)
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise AnnexIvMapError(
            "manifest.json could not be parsed: " + str(exc)
        ) from exc
    if not isinstance(manifest, dict):
        raise AnnexIvMapError("manifest.json is not a JSON object")

    manifest_canonical_sha = hashlib.sha256(
        _manifest_canonical_body_bytes(manifest)
    ).hexdigest()

    items: dict[str, dict] = {}
    for item_id, title, candidates, clause_kind in ANNEX_IV_ITEMS:
        evidence: list[dict] = []
        for filename, role in candidates:
            fpath = dossier_dir / filename
            if not fpath.is_file():
                continue
            evidence.append(
                {
                    "file": filename,
                    "sha256": _file_sha256(fpath),
                    "role": role,
                }
            )
        evidence.sort(key=lambda e: (e["file"], e["role"]))
        if clause_kind == _EVIDENCE_BACKED and not evidence:
            raise AnnexIvMapError(
                "Annex IV item " + item_id + " (" + title + ") is "
                "evidence-backed but none of its candidate evidence files "
                "are present in the dossier (missing evidence): "
                + ", ".join(c[0] for c in candidates)
            )
        items[item_id] = {
            "title": title,
            "clause_kind": clause_kind,
            "evidence": evidence,
        }

    body = {
        "annex_iv_map_schema_version": ANNEX_IV_MAP_SCHEMA_VERSION,
        "manifest_canonical_sha256": manifest_canonical_sha,
        "items": items,
    }
    body_bytes = _canonical_body_bytes(body)
    signature = private_key.sign(body_bytes)
    body["signature"] = {
        "public_key_b64": _public_key_b64(private_key.public_key()),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    return body


def serialize_annex_iv_map(doc: dict) -> str:
    """Deterministic on-disk serialization: sorted keys, two-space indent,
    trailing newline. Mirrors sign_manifest's manifest serialization so the
    canonical body recomputed on read is byte-stable."""
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def _expected_clause_kind(item_id: str) -> Optional[str]:
    for cid, _title, _cands, kind in ANNEX_IV_ITEMS:
        if cid == item_id:
            return kind
    return None


def _expected_title(item_id: str) -> Optional[str]:
    for cid, title, _cands, _kind in ANNEX_IV_ITEMS:
        if cid == item_id:
            return title
    return None


def verify_annex_iv_map(dossier_dir: Path) -> tuple[bool, str]:
    """Offline, fail-closed verification of an Annex IV map against its
    dossier. Returns (ok, reason). reason is "" on success.

    Checks, in order:
      1. map Ed25519 signature over its canonical body bytes.
      2. map.manifest_canonical_sha256 == sha256(manifest canonical body).
      3. each evidence reference: file present AND sha256 matches file bytes.
      4. indexing completeness: exactly the nine canonical item ids appear,
         each with the canonical title and a clause kind consistent with its
         evidence count.
    """
    dossier_dir = Path(dossier_dir)
    map_path = dossier_dir / _MAP_FILENAME
    manifest_path = dossier_dir / _MANIFEST_FILENAME
    if not map_path.is_file():
        return (False, "annex_iv_map.json not found in " + str(dossier_dir))
    if not manifest_path.is_file():
        return (False, "manifest.json not found in " + str(dossier_dir))

    try:
        doc = json.loads(map_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return (False, "annex_iv_map.json parse error: " + str(exc))
    if not isinstance(doc, dict):
        return (False, "annex_iv_map.json is not a JSON object")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return (False, "manifest.json parse error: " + str(exc))
    if not isinstance(manifest, dict):
        return (False, "manifest.json is not a JSON object")

    # 1. signature over canonical body bytes.
    sig_block = doc.get("signature")
    if not isinstance(sig_block, dict):
        return (False, "map has no signature block")
    pub_b64 = sig_block.get("public_key_b64", "")
    sig_b64 = sig_block.get("signature_b64", "")
    if not pub_b64 or not sig_b64:
        return (False, "map signature block incomplete")
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pub_b64, validate=True)
        )
        pub.verify(
            base64.b64decode(sig_b64, validate=True),
            _canonical_body_bytes(doc),
        )
    except (InvalidSignature, ValueError) as exc:
        return (False, "map Ed25519 signature does NOT verify: " + str(exc))

    if int(doc.get("annex_iv_map_schema_version", 0)) != \
            ANNEX_IV_MAP_SCHEMA_VERSION:
        return (
            False,
            "unsupported annex_iv_map_schema_version: "
            + repr(doc.get("annex_iv_map_schema_version")),
        )

    # 2. map <-> dossier binding.
    expected_manifest_sha = hashlib.sha256(
        _manifest_canonical_body_bytes(manifest)
    ).hexdigest()
    if doc.get("manifest_canonical_sha256") != expected_manifest_sha:
        return (
            False,
            "map.manifest_canonical_sha256 does not match this dossier's "
            "manifest canonical body (map is not bound to this dossier)",
        )

    items = doc.get("items")
    if not isinstance(items, dict):
        return (False, "map has no items object")

    # 4a. exactly the canonical item ids, no more, no fewer.
    canonical_ids = {cid for cid, _t, _c, _k in ANNEX_IV_ITEMS}
    present_ids = set(items.keys())
    missing = canonical_ids - present_ids
    surplus = present_ids - canonical_ids
    if missing:
        return (
            False,
            "map omits Annex IV item id(s): " + ", ".join(sorted(missing)),
        )
    if surplus:
        return (
            False,
            "map carries non-canonical item id(s): "
            + ", ".join(sorted(surplus)),
        )

    # 3 + 4b. per-item evidence integrity and clause coherence.
    for item_id in sorted(canonical_ids):
        entry = items[item_id]
        if not isinstance(entry, dict):
            return (False, "item " + item_id + " is not an object")
        if entry.get("title") != _expected_title(item_id):
            return (
                False,
                "item " + item_id + " title does not match the canonical "
                "Annex IV title",
            )
        clause_kind = entry.get("clause_kind")
        if clause_kind != _expected_clause_kind(item_id):
            return (
                False,
                "item " + item_id + " clause_kind does not match the "
                "canonical clause kind",
            )
        evidence = entry.get("evidence")
        if not isinstance(evidence, list):
            return (False, "item " + item_id + " evidence is not a list")
        for ref in evidence:
            if not isinstance(ref, dict):
                return (
                    False,
                    "item " + item_id + " has a non-object evidence ref",
                )
            fname = ref.get("file")
            recorded = ref.get("sha256")
            if not isinstance(fname, str) or not isinstance(recorded, str):
                return (
                    False,
                    "item " + item_id + " evidence ref missing file or "
                    "sha256",
                )
            fpath = dossier_dir / fname
            if not fpath.is_file():
                return (
                    False,
                    "item " + item_id + " references " + fname
                    + " but the file is absent from the dossier (missing "
                    "evidence)",
                )
            if _file_sha256(fpath) != recorded:
                return (
                    False,
                    "item " + item_id + " evidence " + fname
                    + " sha256 does not match the recorded hash (tampered or "
                    "substituted)",
                )
        if clause_kind == _EVIDENCE_BACKED and not evidence:
            return (
                False,
                "item " + item_id + " is evidence-backed but indexes no "
                "evidence",
            )
        if clause_kind in (
            _DOCUMENTATION_CLAUSE,
            _OPERATOR_RESPONSIBILITY,
        ) and evidence:
            return (
                False,
                "item " + item_id + " is a " + str(clause_kind)
                + " clause but indexes evidence (over-claim)",
            )

    return (True, "")
