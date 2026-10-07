"""Declared cost display on the cost-cap leg (S402).

docs/COST_BOUND_DISPLAY_DESIGN.md D400-2 to D400-8 with D401-1 and D401-2.
__s402_cost_bound_display_tests_v1__

Every figure the display prints is read from the cost-cap certificate; the
tests recompute each one from the certificate of the same run. The goldens in
G were captured by running the code at 7f8ca01, with the run-dependent parts
(temporary path, elapsed time, solver version, pricing and spec digests)
replaced by placeholders that each test fills from its own run. Tests named
*_invariant hold on 7f8ca01 by construction: they pin output the change must
leave byte-identical. Every other test is red on 7f8ca01. New names are
reached through the module at call time, so a missing name fails one test,
not the whole file. G is typed dict[str, Any] because the goldens are JSON
with values of more than one shape.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

import cli_verify
import coverage_farkas
import cost_farkas
import smt_verify
from parser import parse_nous
from pricing import load_pricing
from smt_emit import SMTSpec, emit_smt
from verifier import VerificationItem, verify_program

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

ROOT = Path(__file__).resolve().parent.parent
AML = ROOT / "aml_transaction_governance.nous"
SEQ = ROOT / "templates" / "sequence_law_demo.nous"
CAP_OLD = "cost_cap: 0.50 USD"
CAP_REFUTED = "cost_cap: 0.001 USD"
FIXED_TS = "2026-01-01T00:00:00+00:00"
FIXED_SOLVER = "z3 0.0.0-golden"
FIXED_MS = 7
FORBIDDEN = ("spend", "prove", "<=", "\u2264", "$")
PER_RUN = ("elapsed_ms", "timestamp_utc", "signature")
NOTE = "NOTE: declared total_cost not shown: "
VR003_NOTE = " Declared total_cost not shown: "
RULE = "\u2500" * 60
BOUNDED_1 = "  bounded by: 1 soul(s) \u00d7 1 ticks"
BOUNDED_SEQ = "  bounded by: 3 soul(s) \u00d7 5 ticks"
OLD_NOTE_PREFIX = "NOTE: cost-cap Farkas certificate not extracted (z3 cost proof stands): "
INJECTED = "injected by test_s400_cost_bound_display"
ZERO_WEIGHT_ROW_CAUSE = "variable cancellation: constraints[4] is not a constraint row with readable coefficients"

LINES_AML_M0 = (
    '  declared total_cost = 0.0015 USD (3/2000) = cost_cap 1/2 - certificate residual 997/2000',
    '  headroom = 0.4985 USD (997/2000), the certificate residual',
    '    Screener: 500 in x 1.00/M + 200 out x 5.00/M = 3/2000 per tick x 1 ticks',
)
LINES_AML_M10 = (
    '  declared total_cost = 0.0015 USD (3/2000) = effective cap 9/20 (cost_cap 1/2, margin 10%) - certificate residual 897/2000',
    '  headroom = 0.4485 USD (897/2000), the certificate residual',
    '    Screener: 500 in x 1.00/M + 200 out x 5.00/M = 3/2000 per tick x 1 ticks',
)
VR003_SUFFIX_AML = ' Declared total_cost 0.0015 USD (3/2000) = cost_cap 1/2 minus the Farkas certificate residual 997/2000 (the headroom); basis: declared tokens x table price x max_ticks.'
LINES_RATIONAL_ONLY = (
    '  declared total_cost = 7/6000 USD = cost_cap 1/2 - certificate residual 2993/6000',
    '  headroom = 2993/6000 USD, the certificate residual',
    '    Screener: 500 in x 1/3/M + 200 out x 5.00/M = 7/6000 per tick x 1 ticks',
)
LINES_REASONING_MULT = (
    '  declared total_cost = 0.0025 USD (1/400) = cost_cap 1/2 - certificate residual 199/400',
    '  headroom = 0.4975 USD (199/400), the certificate residual',
    '    Screener: 500 in x 1.00/M + 200 out x 5.00/M x 2.0 = 1/400 per tick x 1 ticks',
)
G: dict[str, Any] = {
    'cli_aml_m0': {
        'files': ['cost.farkas.json', 'm.json'],
        'has_cost_sha': True,
        'rc': 0,
        'text': 'Parsed aml_transaction_governance.nous: world=AMLTransactionGovernance, souls=1\nLoaded pricing: layer <<LAYER>>, <<NMODELS>> models, sha256 <<PRICING16>>\u2026\nEmitted SMT-LIB: spec sha256 <<SPEC16>>\u2026\nRunning solver (timeout 30000ms)...\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       <<SOLVER>>\nElapsed:      <<MS>>ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.5 USD across all execution paths.\n  bounded by: 1 soul(s) \xd7 1 ticks\nCost-cap Farkas certificate extracted (sha256 3ca7142eb580aff0...)\nCost-cap Farkas written: <<TMP>>/o/cost.farkas.json\n\nManifest signed: <<TMP>>/o/m.json\n  key:    <<TMP>>/k.key\n  sha256 spec: <<SPEC64>>\n',
        'verdict': 'proven',
    },
    'cli_aml_m10': {
        'files': ['cost.farkas.json', 'm.json'],
        'has_cost_sha': True,
        'rc': 0,
        'text': 'Parsed aml_transaction_governance.nous: world=AMLTransactionGovernance, souls=1\nLoaded pricing: layer <<LAYER>>, <<NMODELS>> models, sha256 <<PRICING16>>\u2026\nEmitted SMT-LIB: spec sha256 <<SPEC16>>\u2026\nRunning solver (timeout 30000ms)...\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       <<SOLVER>>\nElapsed:      <<MS>>ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.45 USD across all execution paths.\n  Declared cap: $0.5 USD, safety margin: 10%.\n  bounded by: 1 soul(s) \xd7 1 ticks\nCost-cap Farkas certificate extracted (sha256 e87d7801196033ee...)\nCost-cap Farkas written: <<TMP>>/o/cost.farkas.json\n\nManifest signed: <<TMP>>/o/m.json\n  key:    <<TMP>>/k.key\n  sha256 spec: <<SPEC64>>\n',
        'verdict': 'proven',
    },
    'cli_missing_none': {
        'files': ['m.json'],
        'has_cost_sha': False,
        'rc': 0,
        'text': 'Parsed aml_transaction_governance.nous: world=AMLTransactionGovernance, souls=1\nLoaded pricing: layer <<LAYER>>, <<NMODELS>> models, sha256 <<PRICING16>>\u2026\nEmitted SMT-LIB: spec sha256 <<SPEC16>>\u2026\nRunning solver (timeout 30000ms)...\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       <<SOLVER>>\nElapsed:      <<MS>>ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.5 USD across all execution paths.\n  bounded by: 1 soul(s) \xd7 1 ticks\n\nManifest signed: <<TMP>>/o/m.json\n  key:    <<TMP>>/k.key\n  sha256 spec: <<SPEC64>>\n',
        'verdict': 'proven',
    },
    'cli_missing_raise': {
        'files': ['m.json'],
        'has_cost_sha': False,
        'rc': 0,
        'text': 'Parsed aml_transaction_governance.nous: world=AMLTransactionGovernance, souls=1\nLoaded pricing: layer <<LAYER>>, <<NMODELS>> models, sha256 <<PRICING16>>\u2026\nEmitted SMT-LIB: spec sha256 <<SPEC16>>\u2026\nRunning solver (timeout 30000ms)...\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       <<SOLVER>>\nElapsed:      <<MS>>ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.5 USD across all execution paths.\n  bounded by: 1 soul(s) \xd7 1 ticks\nNOTE: cost-cap Farkas certificate not extracted (z3 cost proof stands): injected by the S402 golden capture\n\nManifest signed: <<TMP>>/o/m.json\n  key:    <<TMP>>/k.key\n  sha256 spec: <<SPEC64>>\n',
        'verdict': 'proven',
    },
    'cli_refuted': {
        'files': ['m.json'],
        'has_cost_sha': False,
        'rc': 1,
        'text': "Parsed aml_refuted.nous: world=AMLTransactionGovernance, souls=1\nLoaded pricing: layer <<LAYER>>, <<NMODELS>> models, sha256 <<PRICING16>>\u2026\nEmitted SMT-LIB: spec sha256 <<SPEC16>>\u2026\nRunning solver (timeout 30000ms)...\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       <<SOLVER>>\nElapsed:      <<MS>>ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nREFUTED: SMT solver found a counterexample.\n\nPer-soul cost breakdown:\n  Screener             (claude-haiku-4-5        )  per-call $0.001500  \xd7 1 ticks  =  $0.001500\n\n  total_cost  =  $0.001500\n  cap         =  $0.001\n  overage     =  $0.000500  (50.0% over)\n  largest contributor: 'Screener'\n\nSuggested fixes (any one):\n  1. Raise cost_cap to >= $0.0015 USD\n  2. max_ticks reduction insufficient; even 1 tick exceeds cap\n  3. Reduce tokens on soul 'Screener' (largest cost driver)\n\nManifest signed: <<TMP>>/o/m.json\n  key:    <<TMP>>/k.key\n  sha256 spec: <<SPEC64>>\n",
        'verdict': 'refuted',
    },
    'cli_seq': {
        'files': ['cost.farkas.json', 'm.json'],
        'has_cost_sha': True,
        'rc': 0,
        'text': 'Parsed sequence_law_demo.nous: world=OrderPipeline, souls=3\nLoaded pricing: layer <<LAYER>>, <<NMODELS>> models, sha256 <<PRICING16>>\u2026\nEmitted SMT-LIB: spec sha256 <<SPEC16>>\u2026\nRunning solver (timeout 30000ms)...\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        OrderPipeline\nSolver:       <<SOLVER>>\nElapsed:      <<MS>>ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.5 USD across all execution paths.\n  bounded by: 3 soul(s) \xd7 5 ticks\nCost-cap Farkas certificate extracted (sha256 871c6e2907649693...)\nCost-cap Farkas written: <<TMP>>/o/cost.farkas.json\n\nManifest signed: <<TMP>>/o/m.json\n  key:    <<TMP>>/k.key\n  sha256 spec: <<SPEC64>>\n',
        'verdict': 'proven',
    },
    'fv_error': '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       z3 0.0.0-golden\nElapsed:      7ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nERROR: injected error for the S402 golden capture',
    'fv_proven_m0': '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       z3 0.0.0-golden\nElapsed:      7ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.5 USD across all execution paths.\n  bounded by: 1 soul(s) \xd7 1 ticks',
    'fv_proven_m10': '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       z3 0.0.0-golden\nElapsed:      7ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nPROVEN: total_cost \u2264 $0.45 USD across all execution paths.\n  Declared cap: $0.5 USD, safety margin: 10%.\n  bounded by: 1 soul(s) \xd7 1 ticks',
    'fv_refuted': "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       z3 0.0.0-golden\nElapsed:      7ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nREFUTED: SMT solver found a counterexample.\n\nPer-soul cost breakdown:\n  Screener             (claude-haiku-4-5        )  per-call $0.001500  \xd7 1 ticks  =  $0.001500\n\n  total_cost  =  $0.001500\n  cap         =  $0.001\n  overage     =  $0.000500  (50.0% over)\n  largest contributor: 'Screener'\n\nSuggested fixes (any one):\n  1. Raise cost_cap to >= $0.0015 USD\n  2. max_ticks reduction insufficient; even 1 tick exceeds cap\n  3. Reduce tokens on soul 'Screener' (largest cost driver)",
    'fv_unknown': '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nWorld:        AMLTransactionGovernance\nSolver:       z3 0.0.0-golden\nElapsed:      7ms\nSpec sha256:  <<SPEC16>>\u2026\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nUNKNOWN: injected unknown for the S402 golden capture\n  Try: --timeout-ms 60000 (longer budget) or simplify the program.',
    'vr003_aml': {
        'category': 'resource_bound',
        'location': 'world',
        'message': 'Total declared cost provably <= world cost_cap 0.5 USD (Z3/Farkas over declared pricing). This binds the WORLD cost_cap, which is distinct from the law cost ceiling bound by VR001/VR002.',
        'severity': 'PROVEN',
        'tier': 'PROVEN',
    },
    'vr003_refuted': {
        'category': 'resource_bound',
        'detail': 'declared total_cost 0.0015 USD can exceed world cost_cap 0.001 USD (overage 0.0005 USD); minimum sufficient world cost_cap = 0.0015 USD',
        'location': 'world',
        'message': 'Cost bound UNPROVEN: declared total cost can exceed world cost_cap 0.001 USD (the WORLD cost_cap, distinct from the law cost ceiling bound by VR001/VR002).',
        'severity': 'ERROR',
        'tier': None,
    },
}


class _Args:
    smt = True
    prices = None
    timeout_ms = 30000
    no_manifest = False
    smt_margin = 0
    no_lint = True
    lint_strict = False
    lint_error_on = None
    supersedes = None
    chain_coverage = None
    gap_witness = False
    coverage_threshold = None
    materiality_against = None
    materiality_threshold_pct = 10.0

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


@dataclasses.dataclass(frozen=True)
class _Run:
    rc: int
    text: str
    man: dict
    files: dict
    tmp: Path


def _fill(tpl: str, tmp: Path, man: dict) -> str:
    t = load_pricing()
    return (
        tpl.replace("<<TMP>>", str(tmp))
        .replace("<<MS>>", str(man["elapsed_ms"]))
        .replace("<<SOLVER>>", man["solver_version"])
        .replace("<<SPEC64>>", man["smt_spec_sha256"])
        .replace("<<SPEC16>>", man["smt_spec_sha256"][:16])
        .replace("<<LAYER>>", str(t.layer_index))
        .replace("<<NMODELS>>", str(len(t.model_names())))
        .replace("<<PRICING16>>", t.sha256()[:16])
    )


def _cli(run_dir: Path, capsys: pytest.CaptureFixture[str], src: Path = AML, margin: int = 0) -> _Run:
    out = run_dir / "o"
    out.mkdir(parents=True)
    capsys.readouterr()
    saved = sys.stderr
    sys.stderr = sys.stdout
    try:
        rc = cli_verify.cmd_verify(
            _Args(
                file=str(src),
                manifest_out=str(out / "m.json"),
                key_path=str(run_dir / "k.key"),
                smt_margin=margin,
            )
        )
    finally:
        sys.stderr = saved
    text = capsys.readouterr().out
    man = json.loads((out / "m.json").read_text(encoding="utf-8"))
    files = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
    return _Run(rc, text, man, files, run_dir)


def _second_run_dir(tmp: Path, first: _Run, name: str) -> Path:
    d = tmp / name
    d.mkdir()
    (d / "k.key").write_bytes((first.tmp / "k.key").read_bytes())
    return d


def _strip(man: dict, drop: tuple[str, ...] = ()) -> dict:
    return {k: v for k, v in man.items() if k not in PER_RUN and k not in drop}


def _insert_after(text: str, anchor: str, lines: tuple[str, ...]) -> str:
    parts = text.split("\n")
    idx = [i for i, line in enumerate(parts) if line == anchor]
    assert len(idx) == 1, "anchor line occurs " + str(len(idx)) + " times: " + repr(anchor)
    return "\n".join(parts[: idx[0] + 1] + list(lines) + parts[idx[0] + 1:])


def _note_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith(NOTE)]


def _without_note(text: str) -> tuple[str, bool]:
    parts = text.split("\n")
    idx = [i for i, line in enumerate(parts) if line.startswith(NOTE)]
    assert len(idx) == 1, "declared-cost note lines: " + str(len(idx))
    i = idx[0]
    placed = i + 1 < len(parts) and parts[i + 1] == RULE
    return "\n".join(parts[:i] + parts[i + 1:]), placed


def _residual(doc: dict) -> Fraction:
    total = Fraction(0)
    for m, c in zip(doc["multipliers"], doc["constraints"]):
        total += Fraction(m) * Fraction(c["coeffs"].get("", "0"))
    return total


def _new_lines(text: str, golden: str) -> list[str]:
    old = set(golden.split("\n"))
    return [line for line in text.split("\n") if line not in old]


def _wording_violations(text: str) -> list[str]:
    low = text.lower()
    bad = [w for w in FORBIDDEN if w in low]
    if not all(ord(ch) < 128 for ch in text):
        bad.append("non-ASCII")
    if "declared" not in low:
        bad.append("no 'declared'")
    return bad


def _src_text(src: Path = AML) -> str:
    return src.read_text(encoding="utf-8")


def _refuted_text() -> str:
    s = _src_text()
    assert s.count(CAP_OLD) == 1
    return s.replace(CAP_OLD, CAP_REFUTED)


def _refuted_src(tmp: Path) -> Path:
    p = tmp / "aml_refuted.nous"
    p.write_text(_refuted_text(), encoding="utf-8")
    return p


def _spec(text: str, margin: int = 0) -> SMTSpec:
    return emit_smt(parse_nous(text), load_pricing(), source_text=text, margin_pct=margin)


def _fixed(r: smt_verify.VerifyResult) -> smt_verify.VerifyResult:
    return dataclasses.replace(r, elapsed_ms=FIXED_MS, timestamp_utc=FIXED_TS, solver_version=FIXED_SOLVER)


def _proven(spec: SMTSpec) -> smt_verify.VerifyResult:
    return smt_verify.VerifyResult(
        verdict="proven", spec=spec, solver_name="z3", solver_version=FIXED_SOLVER,
        elapsed_ms=FIXED_MS, timestamp_utc=FIXED_TS,
    )


def _fv_case(name: str) -> tuple[smt_verify.VerifyResult, str]:
    if name == "refuted":
        spec = _spec(_refuted_text())
        r = _fixed(smt_verify.verify(spec, timeout_ms=30000))
        assert r.verdict == "refuted"
    elif name in ("unknown", "error"):
        spec = _spec(_src_text())
        r = smt_verify.VerifyResult(
            verdict=name, spec=spec, solver_name="z3", solver_version=FIXED_SOLVER,
            elapsed_ms=FIXED_MS, timestamp_utc=FIXED_TS,
            error="injected " + name + " for the S402 golden capture",
        )
    else:
        spec = _spec(_src_text(), 10 if name == "proven_m10" else 0)
        r = _fixed(smt_verify.verify(spec, timeout_ms=30000))
        assert r.verdict == "proven"
    return r, G["fv_" + name].replace("<<SPEC16>>", spec.sha256()[:16])


def _aml_cert() -> dict:
    doc = cost_farkas.cost_certificate_from_smtspec(_spec(_src_text()))
    assert doc is not None
    return doc


def _edit_per_call(d: dict) -> None:
    c = d["constraints"][0]["coeffs"]
    c[""] = str(Fraction(c[""]) / 3)


def _edit_mult_x2(d: dict) -> None:
    d["multipliers"] = [str(Fraction(m) * 2) for m in d["multipliers"]]


def _edit_cost_cap(d: dict) -> None:
    d["cost_cap"] = "1"


def _edit_max_ticks(d: dict) -> None:
    d["max_ticks"] = 5


def _edit_contradiction(d: dict) -> None:
    d["contradiction"] = "0 < 0"


def _edit_fragment(d: dict) -> None:
    d["fragment"] = "linear-real-cost-cap-edited"


def _edit_zero_multipliers(d: dict) -> None:
    d["multipliers"] = ["0"] * len(d["multipliers"])


def _edit_zero_weight_row(d: dict) -> None:
    d["constraints"].append("not a constraint row")
    d["multipliers"].append("0")


EDITS: dict[str, tuple[Callable[[dict], None], str, tuple[bool, bool]]] = {
    "per_call_constant": (_edit_per_call, "check_serialized_cost", (True, False)),
    "multipliers_x2": (_edit_mult_x2, "byte equality", (True, True)),
    "cost_cap_1": (_edit_cost_cap, "byte equality", (True, True)),
    "max_ticks_5": (_edit_max_ticks, "byte equality", (True, True)),
    "contradiction_0": (_edit_contradiction, "byte equality", (True, True)),
    "fragment": (_edit_fragment, "byte equality", (True, True)),
    "zero_multipliers": (_edit_zero_multipliers, "check_serialized", (False, False)),
    "zero_weight_row": (_edit_zero_weight_row, "variable cancellation", (True, False)),
}
BYTE_EQUALITY_EDITS = ["multipliers_x2", "cost_cap_1", "max_ticks_5", "contradiction_0", "fragment"]


def _edited(name: str, doc: dict) -> dict:
    fn, _cause, graders = EDITS[name]
    d = copy.deepcopy(doc)
    fn(d)
    spec = _spec(_src_text())
    got = (
        coverage_farkas.check_serialized(d),
        cost_farkas.check_serialized_cost(
            d, cost_farkas.souls_from_smtspec(spec), spec.max_ticks,
            spec.cost_cap_amount, spec.cost_cap_margin_pct,
        ),
    )
    assert got == graders, "edit " + name + " graded " + repr(got) + ", expected " + repr(graders)
    return d


def _cli_tamper(tmp: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, name: str) -> tuple[_Run, _Run, list[bool]]:
    u = _cli(tmp / "u", capsys)
    real = cli_verify.format_verdict
    calls: list[bool] = []

    def wrapper(result: smt_verify.VerifyResult, **kw: Optional[dict]) -> str:
        doc = kw.get("cost_certificate")
        calls.append(doc is not None)
        if doc is not None:
            kw["cost_certificate"] = _edited(name, doc)
        return real(result, **kw)

    monkeypatch.setattr(cli_verify, "format_verdict", wrapper)
    t = _cli(_second_run_dir(tmp, u, "t"), capsys)
    return u, t, calls


def _assert_cli_refused(u: _Run, t: _Run, calls: list[bool], cause: str) -> None:
    notes = _note_lines(t.text)
    ok = len(notes) == 1 and notes[0].startswith(NOTE + cause + ": ")
    assert ok, "declared-cost note lines " + repr(notes) + ", expected one naming " + repr(cause)
    assert True in calls, "cli_verify never handed format_verdict a certificate: " + repr(calls)
    rest, placed = _without_note(t.text)
    assert placed, "the note is not the line before the verdict block"
    same = rest == _fill(G["cli_aml_m0"]["text"], t.tmp, t.man)
    assert same, "output without the note differs from 7f8ca01: new lines " + repr(
        _new_lines(rest, _fill(G["cli_aml_m0"]["text"], t.tmp, t.man)))
    assert (t.rc, t.man["verdict"]) == (u.rc, u.man["verdict"]) == (0, "proven")
    assert _strip(t.man) == _strip(u.man)
    assert sorted(t.files) == sorted(u.files) == ["cost.farkas.json", "m.json"]
    assert t.files["cost.farkas.json"] == u.files["cost.farkas.json"]


def _vr003_item(text: str) -> VerificationItem:
    res = verify_program(parse_nous(text), load_pricing())
    items = [i for i in res.items if i.code == "VR003"]
    assert len(items) == 1, "VR003 items: " + str(len(items))
    return items[0]


def _synthetic(row: tuple[str, str, int, int, str, str, str]) -> tuple[SMTSpec, dict]:
    spec = dataclasses.replace(_spec(_src_text()), soul_assumptions=(row,))
    doc = cost_farkas.cost_certificate_from_smtspec(spec)
    assert doc is not None
    return spec, doc


def test_d400_5_cli_aml_prints_the_three_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = _cli(tmp_path / "r", capsys)
    want = _insert_after(_fill(G["cli_aml_m0"]["text"], r.tmp, r.man), BOUNDED_1, LINES_AML_M0)
    same = r.text == want
    assert same, "new lines " + repr(_new_lines(r.text, _fill(G["cli_aml_m0"]["text"], r.tmp, r.man)))
    assert r.rc == 0


def test_d400_8_cli_figures_equal_the_certificate_of_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = _cli(tmp_path / "r", capsys)
    doc = json.loads(r.files["cost.farkas.json"])
    res = _residual(doc)
    cap = Fraction(doc["cost_cap"])
    lines = r.text.split("\n")
    dl = [line for line in lines if line.startswith("  declared total_cost = ")]
    hl = [line for line in lines if line.startswith("  headroom = ")]
    assert len(dl) == 1 and len(hl) == 1, "declared lines " + repr(dl) + " headroom lines " + repr(hl)
    d_dec, d_rat = dl[0].split(" = ")[1].split(" USD (")
    d_rat = d_rat.split(")")[0]
    h_dec, h_rat = hl[0].split(" = ")[1].split(" USD (")
    h_rat = h_rat.split(")")[0]
    assert Fraction(d_rat) == Fraction(d_dec) == cap - res
    assert Fraction(h_rat) == Fraction(h_dec) == res
    assert dl[0].endswith(" - certificate residual " + str(res))


def test_d400_8_smt_margin_10_reads_the_certificate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = _cli(tmp_path / "r", capsys, margin=10)
    doc = json.loads(r.files["cost.farkas.json"])
    assert (Fraction(doc["cost_cap"]), _residual(doc)) == (Fraction(9, 20), Fraction(897, 2000))
    want = _insert_after(_fill(G["cli_aml_m10"]["text"], r.tmp, r.man), BOUNDED_1, LINES_AML_M10)
    same = r.text == want
    assert same, "new lines " + repr(_new_lines(r.text, _fill(G["cli_aml_m10"]["text"], r.tmp, r.man)))


def test_d400_8_sequence_law_demo_per_soul_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = _cli(tmp_path / "r", capsys, src=SEQ)
    doc = json.loads(r.files["cost.farkas.json"])
    golden = _fill(G["cli_seq"]["text"], r.tmp, r.man)
    new = _new_lines(r.text, golden)
    souls = [line for line in new if line.startswith("    ")]
    assert len(souls) == 3, "per-soul lines " + repr(souls) + " in new lines " + repr(new)
    rows = [c["coeffs"] for c in doc["constraints"]]
    per_call = [(k[len("cost_"):-len("_per_call")], -Fraction(c[""])) for c in rows
                for k in c if k.endswith("_per_call") and len(c) == 2]
    spec = _spec(_src_text(SEQ))
    assumed = {a[0]: a for a in spec.soul_assumptions}
    total = Fraction(0)
    for line, (name, k) in zip(souls, per_call):
        head, tail = line.strip().split(": ", 1)
        assert head == name
        a = assumed[name]
        terms = (str(a[2]) + " in x " + a[4] + "/M + " + str(a[3]) + " out x " + a[5] + "/M")
        lhs, rhs = tail.split(" = ")
        assert lhs == terms
        per_tick, ticks = rhs.split(" per tick x ")
        assert Fraction(per_tick) == k
        assert ticks == str(doc["max_ticks"]) + " ticks"
        total += Fraction(per_tick)
    dl = [line for line in new if line.startswith("  declared total_cost = ")]
    assert len(dl) == 1
    declared = Fraction(dl[0].split(" USD (")[1].split(")")[0])
    assert total * doc["max_ticks"] == declared == Fraction(doc["cost_cap"]) - _residual(doc)
    rest = "\n".join(line for line in r.text.split("\n") if line not in new)
    assert rest == golden
    assert r.text.split("\n").index(new[0]) == r.text.split("\n").index(BOUNDED_SEQ) + 1


def test_d400_5_wording_of_the_declared_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    new: list[str] = []
    for name, src, margin in (("cli_aml_m0", AML, 0), ("cli_aml_m10", AML, 10), ("cli_seq", SEQ, 0)):
        r = _cli(tmp_path / name, capsys, src=src, margin=margin)
        new += _new_lines(r.text, _fill(G[name]["text"], r.tmp, r.man))
    msg = _vr003_item(_src_text()).message
    suffix = msg[len(G["vr003_aml"]["message"]):] if msg.startswith(G["vr003_aml"]["message"]) else msg
    text = "\n".join(new) + "\n" + suffix
    assert new and suffix, "new CLI lines " + repr(new) + " VR003 suffix " + repr(suffix)
    assert _wording_violations(text) == []


def test_d401_1_wording_of_the_notes(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    real_fv = cli_verify.format_verdict
    real_cli_cert = cli_verify.cost_certificate_from_smtspec
    real = cost_farkas.cost_certificate_from_smtspec
    _u, t, _c = _cli_tamper(tmp_path, capsys, monkeypatch, "multipliers_x2")
    monkeypatch.setattr(cli_verify, "format_verdict", real_fv)
    monkeypatch.setattr(cli_verify, "cost_certificate_from_smtspec", lambda spec: None)
    m = _cli(tmp_path / "m", capsys)
    monkeypatch.setattr(cli_verify, "cost_certificate_from_smtspec", real_cli_cert)
    monkeypatch.setattr(cost_farkas, "cost_certificate_from_smtspec",
                        lambda spec: _edited("multipliers_x2", real(spec)))
    v = _vr003_item(_src_text()).message[len(G["vr003_aml"]["message"]):]
    notes = _note_lines(t.text) + _note_lines(m.text)
    assert len(notes) == 2 and v, "CLI notes " + repr(notes) + " VR003 suffix " + repr(v)
    for n in notes + [v]:
        assert _wording_violations(n) == [], repr(n)


@pytest.mark.parametrize("name", ["proven_m0", "proven_m10", "refuted", "unknown", "error"])
def test_d400_7_format_verdict_without_keyword_invariant(name: str) -> None:
    r, golden = _fv_case(name)
    same = smt_verify.format_verdict(r) == golden
    assert same


@pytest.mark.parametrize("name", ["refuted", "unknown", "error"])
def test_d401_2_keyword_ignored_when_not_proven(name: str) -> None:
    r, golden = _fv_case(name)
    same = smt_verify.format_verdict(r, cost_certificate=_aml_cert()) == golden
    assert same


def test_d400_7_format_verdict_keyword_adds_the_lines() -> None:
    r, golden = _fv_case("proven_m0")
    got = smt_verify.format_verdict(r, cost_certificate=_aml_cert())
    same = got == _insert_after(golden, BOUNDED_1, LINES_AML_M0)
    assert same, repr(got[len(golden):])


def test_d401_2_refuted_cli_output_invariant(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = _cli(tmp_path / "r", capsys, src=_refuted_src(tmp_path))
    same = r.text == _fill(G["cli_refuted"]["text"], r.tmp, r.man)
    assert same
    assert (r.rc, r.man["verdict"], sorted(r.files)) == (1, "refuted", ["m.json"])
    assert "cost_farkas_sha256" not in r.man


@pytest.mark.parametrize("name", list(EDITS))
def test_d401_1_edits_grade_as_recorded_invariant(name: str) -> None:
    _edited(name, _aml_cert())


def test_d400_8_cli_tampered_per_call_constant(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u, t, calls = _cli_tamper(tmp_path, capsys, monkeypatch, "per_call_constant")
    _assert_cli_refused(u, t, calls, "check_serialized_cost")


@pytest.mark.parametrize("name", BYTE_EQUALITY_EDITS)
def test_d401_1_cli_edit_names_byte_equality(name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u, t, calls = _cli_tamper(tmp_path, capsys, monkeypatch, name)
    _assert_cli_refused(u, t, calls, "byte equality")


def test_d401_1_cli_multipliers_x2_prints_no_negative_figure(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u, t, calls = _cli_tamper(tmp_path, capsys, monkeypatch, "multipliers_x2")
    absent = "-497/1000" not in t.text and "-0.497" not in t.text
    assert absent
    _assert_cli_refused(u, t, calls, "byte equality")


def test_d401_1_cli_zero_multipliers_names_check_serialized(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u, t, calls = _cli_tamper(tmp_path, capsys, monkeypatch, "zero_multipliers")
    _assert_cli_refused(u, t, calls, "check_serialized")


def test_d401_1_cli_zero_weight_row_names_variable_cancellation(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u, t, calls = _cli_tamper(tmp_path, capsys, monkeypatch, "zero_weight_row")
    _assert_cli_refused(u, t, calls, "variable cancellation")
    assert _note_lines(t.text) == [NOTE + ZERO_WEIGHT_ROW_CAUSE]


def test_d401_2_cli_missing_certificate(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u = _cli(tmp_path / "u", capsys)
    monkeypatch.setattr(cli_verify, "cost_certificate_from_smtspec", lambda spec: None)
    t = _cli(_second_run_dir(tmp_path, u, "t"), capsys)
    notes = _note_lines(t.text)
    ok = len(notes) == 1 and notes[0].startswith(NOTE + "no certificate: ")
    assert ok, "declared-cost note lines " + repr(notes)
    rest, placed = _without_note(t.text)
    assert placed, "the note is not the line before the verdict block"
    same = rest == _fill(G["cli_missing_none"]["text"], t.tmp, t.man)
    assert same
    assert (t.rc, t.man["verdict"]) == (u.rc, u.man["verdict"]) == (0, "proven")
    assert sorted(t.files) == ["m.json"]
    assert _strip(t.man) == _strip(u.man, ("cost_farkas_sha256",))


def test_d401_2_cli_costfarkaserror_prints_both_notes(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    u = _cli(tmp_path / "u", capsys)

    def _raise(spec: object) -> None:
        raise cost_farkas.CostFarkasError("injected by the S402 golden capture")

    monkeypatch.setattr(cli_verify, "cost_certificate_from_smtspec", _raise)
    t = _cli(_second_run_dir(tmp_path, u, "t"), capsys)
    notes = _note_lines(t.text)
    ok = len(notes) == 1 and notes[0].startswith(NOTE + "no certificate: ")
    assert ok, "declared-cost note lines " + repr(notes)
    old = [line for line in t.text.split("\n") if line.startswith(OLD_NOTE_PREFIX)]
    assert old == [OLD_NOTE_PREFIX + "injected by the S402 golden capture"]
    rest, placed = _without_note(t.text)
    assert placed, "the note is not the line before the verdict block"
    same = rest == _fill(G["cli_missing_raise"]["text"], t.tmp, t.man)
    assert same
    assert (t.rc, t.man["verdict"]) == (u.rc, u.man["verdict"]) == (0, "proven")
    assert sorted(t.files) == ["m.json"]
    assert _strip(t.man) == _strip(u.man, ("cost_farkas_sha256",))


def test_d400_8_vr003_keeps_its_text_and_appends_the_figures() -> None:
    i = _vr003_item(_src_text())
    g = G["vr003_aml"]
    same = i.message == g["message"] + VR003_SUFFIX_AML
    assert same, repr(i.message[len(g["message"]):])
    assert (i.severity, i.tier, i.category, i.location) == (g["severity"], g["tier"], g["category"], g["location"])


VR003_CASES = list(EDITS) + ["missing_none", "missing_raise"]


@pytest.mark.parametrize("name", VR003_CASES)
def test_d401_2_vr003_refusal_appends_the_cause(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    real = cost_farkas.cost_certificate_from_smtspec
    calls: list[int] = []

    def fake(spec: SMTSpec) -> Optional[dict]:
        calls.append(1)
        if name == "missing_none":
            return None
        if name == "missing_raise":
            raise cost_farkas.CostFarkasError(INJECTED)
        return _edited(name, real(spec))

    monkeypatch.setattr(cost_farkas, "cost_certificate_from_smtspec", fake)
    i = _vr003_item(_src_text())
    g = G["vr003_aml"]
    cause = "no certificate" if name.startswith("missing") else EDITS[name][1]
    suffix = i.message[len(g["message"]):] if i.message.startswith(g["message"]) else None
    ok = suffix is not None and suffix.startswith(VR003_NOTE + cause + ": ") and suffix.endswith(".")
    assert ok, "VR003 suffix " + repr(suffix) + ", expected the cause " + repr(cause)
    assert calls, "VR003 did not call cost_farkas.cost_certificate_from_smtspec"
    assert (i.severity, i.tier, i.category, i.location) == (g["severity"], g["tier"], g["category"], g["location"])
    if name == "zero_weight_row":
        assert suffix == VR003_NOTE + ZERO_WEIGHT_ROW_CAUSE + "."
    doc = real(_spec(_src_text()))
    res = _residual(doc)
    for fig in (str(res), str(Fraction(doc["cost_cap"]) - res), "-497/1000", "-0.497", "0.0015", "0.4985"):
        assert fig not in suffix, fig


def test_d400_1_vr003_refuted_invariant() -> None:
    i = _vr003_item(_refuted_text())
    g = G["vr003_refuted"]
    got = {"message": i.message, "severity": i.severity, "tier": i.tier,
           "category": i.category, "location": i.location, "detail": i.detail}
    assert got == g


def test_d400_6_rational_only_when_the_decimal_does_not_terminate() -> None:
    spec, doc = _synthetic(("Screener", "claude-haiku-4-5", 500, 200, "1/3", "5.00", "1.0"))
    golden = G["fv_proven_m0"].replace("<<SPEC16>>", spec.sha256()[:16])
    got = smt_verify.format_verdict(_proven(spec), cost_certificate=doc)
    same = got == _insert_after(golden, BOUNDED_1, LINES_RATIONAL_ONLY)
    assert same, repr(got[len(golden):])


def test_d400_5_reasoning_multiplier_is_shown() -> None:
    spec, doc = _synthetic(("Screener", "claude-haiku-4-5", 500, 200, "1.00", "5.00", "2.0"))
    golden = G["fv_proven_m0"].replace("<<SPEC16>>", spec.sha256()[:16])
    got = smt_verify.format_verdict(_proven(spec), cost_certificate=doc)
    same = got == _insert_after(golden, BOUNDED_1, LINES_REASONING_MULT)
    assert same, repr(got[len(golden):])


def test_d400_7_helper_types_and_typed_refusal() -> None:
    helper = getattr(smt_verify, "declared_cost_display")
    err = getattr(smt_verify, "CostDisplayError")
    shape = getattr(smt_verify, "DeclaredCostDisplay")
    assert issubclass(err, ValueError)
    assert dataclasses.is_dataclass(shape) and shape.__dataclass_params__.frozen
    spec = _spec(_src_text())
    doc = _aml_cert()
    assert isinstance(helper(spec, doc), shape)
    with pytest.raises(err) as ei:
        helper(spec, _edited("multipliers_x2", doc))
    assert str(ei.value).startswith("byte equality: ")


@pytest.mark.parametrize("how", ["none", "raise"])
def test_d401_1_rederivation_refusal_names_byte_equality(how: str, monkeypatch: pytest.MonkeyPatch) -> None:
    helper = getattr(smt_verify, "declared_cost_display")
    err = getattr(smt_verify, "CostDisplayError")
    spec = _spec(_src_text())
    doc = _aml_cert()
    calls: list[int] = []

    def fake(*a: object, **k: object) -> Optional[dict]:
        calls.append(1)
        if how == "raise":
            raise cost_farkas.CostFarkasError(INJECTED)
        return None

    monkeypatch.setattr(cost_farkas, "extract_cost_certificate", fake)
    with pytest.raises(err) as ei:
        helper(spec, doc)
    want = {
        "none": "byte equality: the spec re-derives no certificate",
        "raise": "byte equality: re-derivation from the spec raised CostFarkasError",
    }[how]
    assert str(ei.value) == want
    assert calls == [1]


@pytest.mark.parametrize("which", ["proven", "refuted"])
def test_d401_2_cli_extracts_once_invariant(which: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    real = cli_verify.cost_certificate_from_smtspec
    calls: list[int] = []

    def counted(spec: SMTSpec) -> Optional[dict]:
        calls.append(1)
        return real(spec)

    monkeypatch.setattr(cli_verify, "cost_certificate_from_smtspec", counted)
    src = AML if which == "proven" else _refuted_src(tmp_path)
    r = _cli(tmp_path / "r", capsys, src=src)
    assert r.man["verdict"] == which
    assert calls == [1], "extractions: " + str(len(calls))
