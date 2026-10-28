#!/usr/bin/env python3
"""Run mint_vsa_vector.py with the wall clock pinned, to reproduce v1.

The mint harness pins keys, timestamps and the program but not the date
NOUS reads to decide whether a price is too old for --smt (90 days).
This shim pins that date in the two modules that read it (pricing,
smt_emit) and then runs the harness unchanged.

Measured 2026-10-27: from a checkout of commit c2d9680 with _version.py
set to 5.73.0 (the version that minted v1; c2d9680 itself bumped it to
5.73.1), run from the checkout root with PYTHONPATH set to it and a
HOME that holds no NOUS price layer:

  python3 website/.well-known/nous/vsa-vectors/v1/pin_clock.py \\
      2026-07-10 \\
      website/.well-known/nous/vsa-vectors/v1/mint_vsa_vector.py \\
      website/.well-known/nous/vsa-vectors/v1/vsa_conformance_vector_v1.nous \\
      <out_dir>

gives all nine digests of index.json byte-equal. Any date on or before
2026-09-27 does (2026-06-28, 2026-06-29, 2026-07-10, 2026-09-27
measured); 2026-09-28 is refused, the price being 91 days old.

usage: pin_clock.py YYYY-MM-DD HARNESS SOURCE OUT
"""
import datetime as _dt
import runpy
import sys

_DAY = _dt.date.fromisoformat(sys.argv[1])


class _Pinned(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(_DAY.year, _DAY.month, _DAY.day, 12, 0, 0, tzinfo=tz)


import pricing  # noqa: E402
import smt_emit  # noqa: E402

pricing.datetime = _Pinned
smt_emit.datetime = _Pinned
sys.argv = [sys.argv[2], sys.argv[3], sys.argv[4]]
runpy.run_path(sys.argv[0], run_name="__main__")
