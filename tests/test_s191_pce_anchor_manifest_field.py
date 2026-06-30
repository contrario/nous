"""S191 4b: manifest pce_anchor_sha256 drop-when-None field is declared.

Mirrors the S190 pce_sha256 field test. Library-only schema extension: the
field binds a pre-commitment receipt (pce.anchor.json) sha into the signed
manifest. Drop-when-None keeps existing manifests (field absent) byte-identical
-- guarded by the rest of the suite serializing manifests without it.

Class-name-agnostic: the manifest dataclass is located by its sibling
pce_sha256 field, not by a hard-coded class name.
"""
from __future__ import annotations

import dataclasses
import inspect

import manifest


def _manifest_dataclasses() -> list:
    out = []
    for name in dir(manifest):
        obj = getattr(manifest, name)
        if dataclasses.is_dataclass(obj) and isinstance(obj, type):
            fnames = {f.name for f in dataclasses.fields(obj)}
            if "pce_sha256" in fnames:
                out.append((name, obj))
    return out


def test_s191_pce_anchor_sha256_field_declared() -> None:
    found = _manifest_dataclasses()
    assert found, "no dataclass carrying pce_sha256 found in manifest"
    for name, cls in found:
        fnames = {f.name for f in dataclasses.fields(cls)}
        assert "pce_anchor_sha256" in fnames, (
            name + " is missing pce_anchor_sha256"
        )


def test_s191_pce_anchor_sha256_default_is_none() -> None:
    for name, cls in _manifest_dataclasses():
        fld = {f.name: f for f in dataclasses.fields(cls)}["pce_anchor_sha256"]
        assert fld.default is None, (
            name + ".pce_anchor_sha256 default is not None"
        )


def test_s191_pce_anchor_sha256_canonical_drop_when_none() -> None:
    src = inspect.getsource(manifest)
    assert "if self.pce_anchor_sha256 is not None:" in src, (
        "pce_anchor_sha256 canonical guard (drop-when-None) not found"
    )
    assert 'd["pce_anchor_sha256"] = self.pce_anchor_sha256' in src, (
        "pce_anchor_sha256 canonical assignment not found"
    )


def test_s191_pce_anchor_sha256_parsed_from_doc() -> None:
    src = inspect.getsource(manifest)
    assert src.count('pce_anchor_sha256=doc.get("pce_anchor_sha256")') >= 2, (
        "expected pce_anchor_sha256 parsed at both manifest parse sites"
    )
