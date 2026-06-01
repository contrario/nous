"""Compiled-path conformance trace (S105 U4).

Runs a NOUS program through the codegen/compiled runtime and emits a signed
TraceEnvelope, using the same nous_trace recorder contract as the interpreter
path. Message events are recorded at the runtime ChannelRegistry.send
choke-point (wired in S105 U2); llm_call events and per-soul attribution are
authoritatively deferred (soul is the reserved "unknown_soul" sentinel).

The emitted module and codegen are not modified by this path; the recorder is
injected post-construction into the runtime built by build_runtime(), so the
57-template codegen byte-identity gate is unaffected.

# __s105_compiled_trace_module_v1__
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from nous_trace import TraceEnvelope


class CompiledTraceError(RuntimeError):
    """Raised when the compiled trace path cannot produce a trace."""


def run_compiled_with_trace(
    source: str,
    max_cycles: int = 1,
    private_key: "Optional[Ed25519PrivateKey]" = None,
    consult_memory: bool = False,
) -> "TraceEnvelope":
    """Compile source, run the compiled runtime bounded, return a signed trace.

    Drives each soul's real _instinct() for max_cycles. Hermetic: with no
    LLM keys present the compiled cognition completes without network calls.
    Raises CompiledTraceError on parse/validate/build failure.
    """
    if not isinstance(source, str) or len(source) < 1:
        raise CompiledTraceError("source must be a non-empty string")
    if not isinstance(max_cycles, int) or max_cycles < 1:
        raise CompiledTraceError("max_cycles must be a positive integer")

    from parser import parse_nous
    from validator import NousValidator
    from codegen import NousCodeGen
    from trace_recorder import TraceRecorder
    from run_shas import compute_run_shas
    import _version

    program = parse_nous(source)
    if program.world is None:
        raise CompiledTraceError("program declares no world")
    vresult = NousValidator(program).validate()
    if not vresult.ok:
        codes = ", ".join(e.code for e in vresult.errors)
        raise CompiledTraceError(f"validation failed: {codes}")

    code = NousCodeGen(program).generate()
    src_sha, smt_sha, pricing_sha = compute_run_shas(source)
    recorder = TraceRecorder(
        _version.__version__,
        program.world.name,
        src_sha,
        smt_sha,
        pricing_sha,
    )
    if consult_memory:  # __s107_u4_compiled_consult_v1__
        from pathlib import Path as _Path
        from run_identity import (
            MemoryConsultationError as _MCErr,
            build_run_consultation as _build_consult,
        )
        if len(program.souls) != 1:
            raise _MCErr(
                "Phase 1 memory consultation requires exactly 1 "
                "soul defined in the world (found "
                + str(len(program.souls)) + ")"
            )
        recorder.set_memory_consultation(
            consultation=_build_consult(
                program.world.name,
                program.souls[0].name,
                base_dir=_Path("/var/lib/nous"),
            )
        )

    fd, tmp = tempfile.mkstemp(suffix=".py", prefix="_compiled_trace_", dir=tempfile.gettempdir())
    os.close(fd)
    try:
        Path(tmp).write_text(code, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("_compiled_trace_mod", tmp)
        if spec is None or spec.loader is None:
            raise CompiledTraceError("could not load emitted module spec")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "build_runtime"):
            raise CompiledTraceError("emitted module has no build_runtime()")
        runtime = mod.build_runtime()
        runtime.channels._trace_ctx = recorder

        async def _drive() -> None:
            for _cycle in range(max_cycles):
                for runner in runtime._runners:
                    await runner._instinct()

        asyncio.run(_drive())
    finally:
        os.unlink(tmp)

    if private_key is None:  # __s105_u4_ephemeral_sign_v1__
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        private_key = Ed25519PrivateKey.generate()
    return recorder.finalize(private_key=private_key)


def anchor_compiled_run(
    source: str,
    max_cycles: int = 1,
    private_key: "Optional[Ed25519PrivateKey]" = None,
    *,
    client: "Optional[Any]" = None,
    _test_anchor: "Optional[Any]" = None,
) -> "tuple[Any, Any]":  # __s105_anchor_compiled_run_v1__
    """Run the compiled path, sign the trace, and anchor it to Rekor v2.

    Returns (TraceEnvelope, RekorAnchorV2). The envelope is signed (ephemeral
    Ed25519 when private_key is None); the anchor is detached. _test_anchor is
    a private hook forwarded to trace_anchor for offline testing.
    """
    from trace_anchor import anchor_trace_to_rekor_v2

    envelope = run_compiled_with_trace(
        source, max_cycles=max_cycles, private_key=private_key
    )
    anchor = anchor_trace_to_rekor_v2(
        envelope, client=client, _test_anchor=_test_anchor
    )
    return envelope, anchor
