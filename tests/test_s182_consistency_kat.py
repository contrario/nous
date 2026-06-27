"""S182 consistency-primitive KAT: RFC 9162 consistency proofs verified
against _naive_root as the RFC 6962 MTH oracle, every (m, n) for sizes
1..32, with tamper-negatives. The verifier never sees the leaves; only
(m, n, root_m, root_n, proof). __s182_consistency_primitive_v1__
"""
from __future__ import annotations

import os

import rekor_v2_offline as rv


def test_consistency_kat_all_pairs_and_tamper() -> None:
    maxn = 32
    leaves_all = [os.urandom(24) for _ in range(maxn)]
    positives = 0
    negatives = 0
    for n in range(1, maxn + 1):
        leaves = leaves_all[:n]
        root_n = rv._naive_root(leaves)
        for m in range(1, n + 1):
            root_m = rv._naive_root(leaves[:m])
            proof = rv.naive_consistency_proof(leaves, m)
            rv.verify_consistency(m, n, root_m, root_n, proof)
            positives += 1
            if m < n:
                if proof:
                    bad = list(proof)
                    bad[0] = bytes(b ^ 0xFF for b in bad[0])
                    try:
                        rv.verify_consistency(m, n, root_m, root_n, bad)
                        raise AssertionError(
                            "tampered node accepted m=%d n=%d" % (m, n)
                        )
                    except rv.VerificationError:
                        negatives += 1
                    try:
                        rv.verify_consistency(
                            m, n, root_m, root_n, proof[:-1]
                        )
                        raise AssertionError(
                            "truncated proof accepted m=%d n=%d" % (m, n)
                        )
                    except rv.VerificationError:
                        negatives += 1
                bad_root = bytes((root_m[0] ^ 1,)) + root_m[1:]
                try:
                    rv.verify_consistency(m, n, bad_root, root_n, proof)
                    raise AssertionError(
                        "wrong first root accepted m=%d n=%d" % (m, n)
                    )
                except rv.VerificationError:
                    negatives += 1
    assert positives == sum(range(1, maxn + 1))
    assert negatives > 0


def test_consistency_refuses_rollback() -> None:
    leaves = [os.urandom(24) for _ in range(9)]
    root9 = rv._naive_root(leaves)
    root5 = rv._naive_root(leaves[:5])
    proof = rv.naive_consistency_proof(leaves, 5)
    try:
        rv.verify_consistency(9, 5, root9, root5, proof)
        raise AssertionError("rollback (first>second) accepted")
    except rv.VerificationError:
        pass
