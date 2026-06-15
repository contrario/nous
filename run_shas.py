"""NOUS run subject-binding hashes.

Computes the three SHA-256 digests that bind a runtime trace to its
source, cost model, and constraint system:

    source_sha256    -- sha256 of the .nous source bytes (UTF-8)
    smt_spec_sha256  -- SMTSpec.sha256() over the canonical SD:/SA:/PS: form
    pricing_sha256   -- PricingTable.sha256() of the active cost model

These are the trace envelope's subject binding (in-toto / SLSA subject
pattern: digests that pin the artifact the evidence is about). They are
computed exactly as the dossier / verify path computes them -- same
parse, same pricing load, same emit_smt call -- so a trace's subject is
byte-identical to the dossier manifest's for the same source and cost
model. Any divergence here would silently decouple a run's evidence from
its compliance dossier.

Dependency direction: this module sits above the core transform layer
(parser, pricing, smt_emit) and below its callers (the trace recorder
and the CLI run/verify surfaces). It imports core modules only; nothing
core imports it. This keeps the dependency graph acyclic.

# __nous_run_shas_module_v1__
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional


class RunShasError(Exception):
    """Raised when subject-binding hashes cannot be derived."""


def compute_run_shas(
    source_text: str,
    custom_pricing_path: Optional[Path] = None,
    today: Optional[date] = None,
) -> tuple[str, str, str]:
    """Return (source_sha256, smt_spec_sha256, pricing_sha256).

    source_text must be the exact .nous source bytes decoded as UTF-8.
    An empty source is refused: the SMT emitter maps a None/absent source
    to the sentinel "unknown", which is not a 64-hex SHA and would be
    rejected by the trace envelope. Refuse over guess.
    """
    if not isinstance(source_text, str) or not source_text:
        raise RunShasError(
            "source_text must be a non-empty string; an empty source "
            "cannot produce a valid 64-hex source_sha256"
        )

    from parser import parse_nous
    from pricing import load_pricing
    from smt_emit import emit_smt

    try:
        program = parse_nous(source_text)
    except Exception as exc:
        raise RunShasError(f"parse failed: {exc}") from exc

    pricing = load_pricing(custom_pricing_path)
    spec = emit_smt(program, pricing, source_text=source_text, today=today)

    source_sha256 = spec.source_sha256
    smt_spec_sha256 = spec.sha256()
    pricing_sha256 = spec.pricing_sha256

    for name, value in (
        ("source_sha256", source_sha256),
        ("smt_spec_sha256", smt_spec_sha256),
        ("pricing_sha256", pricing_sha256),
    ):
        if not isinstance(value, str) or len(value) != 64:
            raise RunShasError(
                f"{name} is not a 64-hex SHA-256 (got {value!r}); "
                f"refusing to return an ill-formed subject binding"
            )

    return source_sha256, smt_spec_sha256, pricing_sha256


def compute_run_gated_actions(  # __s142_u3_gated_helper_v1__
    source_text: str,
    custom_pricing_path: Optional[Path] = None,
    today: Optional[date] = None,
) -> tuple[str, ...]:
    """Return the signed gated-action set for a NOUS source.

    Derived from the SAME emit_smt path that compute_run_shas
    hashes into smt_spec_sha256 and that the conformance verifier
    re-derives, so the producer's emission and the verifier's
    check agree by construction. Refuse over guess on empty input.
    """
    if not isinstance(source_text, str) or not source_text:
        raise RunShasError(
            "source_text must be a non-empty string; cannot "
            "derive a gated-action set from an empty source"
        )
    from parser import parse_nous
    from pricing import load_pricing
    from smt_emit import emit_smt
    try:
        program = parse_nous(source_text)
    except Exception as exc:
        raise RunShasError(f"parse failed: {exc}") from exc
    pricing = load_pricing(custom_pricing_path)
    spec = emit_smt(
        program, pricing, source_text=source_text, today=today
    )
    return tuple(spec.gated_actions)
