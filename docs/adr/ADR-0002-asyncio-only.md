# ADR-0002: asyncio only

Status: Accepted

## Context

NOUS codegen targets a Python runtime, and the runtime is the concurrency surface
on which generated code executes. A single concurrency model was fixed at project
inception (it appears as a hard stack invariant in the Project Instructions: "no
threads, no multiprocessing, ever").

The original session-time rationale for this choice is not fully recoverable from
the available record (handoffs and commits). What follows states the decision and
the alternatives that were on the table, and labels the reasoning as reconstructed
inference where the original argument is not preserved.

## Decision

asyncio only. Generated code and the runtime use cooperative asyncio concurrency.
Threads and multiprocessing are never used; `time.sleep` in async paths is banned in
favor of `await asyncio.sleep`.

## Alternatives rejected

- Threads. Rejected (reconstructed): the GIL limits threads for CPU-bound work, and
  preemptive scheduling complicates the deterministic-evidence model that the rest
  of the architecture depends on.
- Multiprocessing. Rejected (reconstructed): serialization overhead and a
  multi-process footprint complicate the single-process evidence and health model.
- trio. Rejected (reconstructed): a capable competing async framework, but the
  surrounding stack (httpx, FastAPI) standardizes on asyncio, and asyncio is the
  codegen target; a second scheduler would add a dependency for no evidence gain.

The alternatives above are the ones structurally consistent with the invariant; the
specific weighing done at the deciding session is not recoverable.

## Tradeoffs / consequences

Cooperative scheduling means a blocking call anywhere stalls the loop, so every I/O
and sleep path must be async-native. CPU-bound work cannot be parallelized in-process
and must be kept off the loop. The upside is a single, inspectable execution model.

## Evidence Ledger

- Held across the entire project history as an unrelitigated invariant; no regression
  has forced a revisit.

## Still true?

YES -- reason: the invariant has never been contradicted by a concrete failure case,
and the whole runtime is built on it. Last reviewed: S204.
