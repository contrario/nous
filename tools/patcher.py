"""NOUS patch primitives: the single source of truth for patch-time invariants.

This module is the canonical home for the primitives every operational
``patch_*.py`` relies on. It exists so those invariants are defined once and
imported, never re-derived per patch. It is named ``patcher.py`` (not
``patch_*``) so the repo's ``patch_*.py`` ignore rule -- which keeps throwaway
operational patches out of git -- does not also ignore this permanent module.

The delta-only ASCII gate is seeded here first because it is the proven-
recurring footgun (re-fixed in S166 and S168); the remaining primitives -- the
atomic mkstemp/os.replace writer, anchor-count == 1 enforcement, the py_compile
gate, and the idempotent done-marker state machine -- migrate into this module
incrementally as later patches touch them. New primitives subclass
``PatchPrimitiveError``.

Contract: this module is import-side-effect-free. Importing it performs no I/O
and mutates no global state, including ``sys.path``.

Consumption from an operational patch. The repo root below is the Server A path
and is hardcoded; Server B lives at ``/opt/neuroaether/nous`` and would require a
different root::

    import sys
    sys.path.insert(0, "/opt/aetherlang_agents/nous")
    from tools.patcher import _require_ascii_inserted
"""

from __future__ import annotations

__all__ = ["PatchPrimitiveError", "AsciiGateError", "_require_ascii_inserted"]


class PatchPrimitiveError(Exception):
    """Base class for every patch-primitive refusal."""


class AsciiGateError(PatchPrimitiveError):
    """Raised when the inserted patch region contains a non-ASCII character."""


def _require_ascii_inserted(original: str, candidate: str) -> None:
    """Validate that the inserted delta between two texts is ASCII-only.

    The repo's ASCII invariant applies to newly inserted content, not to bytes
    that already exist in the target. Pre-existing (grandfathered) non-ASCII in
    the unchanged common prefix or suffix is ignored; only the changed window of
    ``candidate`` is checked. For a brand-new file (``original`` empty) the whole
    candidate is the inserted region and is validated end to end.

    Raises ``AsciiGateError`` on the first non-ASCII codepoint in the inserted
    region, performing no I/O.
    """
    orig_len = len(original)
    cand_len = len(candidate)
    bound = min(orig_len, cand_len)

    prefix = 0
    while prefix < bound and original[prefix] == candidate[prefix]:
        prefix += 1

    suffix = 0
    while suffix < (bound - prefix) and (
        original[orig_len - 1 - suffix] == candidate[cand_len - 1 - suffix]
    ):
        suffix += 1

    inserted = candidate[prefix:cand_len - suffix]
    for offset, char in enumerate(inserted):
        codepoint = ord(char)
        if codepoint > 0x7F:
            raise AsciiGateError(
                f"non-ASCII character U+{codepoint:04X} ({char!r}) in inserted "
                f"patch region at inserted offset {offset} (candidate offset "
                f"{prefix + offset}); the ASCII gate validates the inserted delta only"
            )
