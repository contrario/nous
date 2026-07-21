#!/usr/bin/env python3
import subprocess, json, sys, os

EXPECT = {
    "golden": (0, "VALID"),
    "t01_edited_body": (20, "INVALID(SIG_INVALID)"),
    "t02_dropped_event": (20, "INVALID(SEQ_ORDER)"),
    "t03_reordered": (20, "INVALID(SEQ_ORDER)"),
    "t04_post_anchor_forgery": (20, "INVALID(ANCHOR_INVALID)"),
    "t05_reused_salt": (20, "INVALID(SALT_REUSE)"),
    "t06_verdict_mismatch": (20, "INVALID(VERDICT_MISMATCH)"),
    "t07_missing_evidence": (20, "INVALID(ASSIGNMENT_MISSING)"),
    "t08_wrong_tag": (20, "INVALID(SIG_INVALID)"),
    "t09_expired_key": (20, "INVALID(KEY_EXPIRED)"),
    "t10_backdated": (20, "INVALID(TIME_BOUND_VIOLATION)"),
    "t11_float_signed": (20, "INVALID(FLOAT_IN_SIGNED)"),
    "t12_truncated_tail": (10, "INTEGRITY-OK/INCOMPLETE"),
}


def main():
    root = "vectors"
    results, failed = [], 0
    for name, (exp_code, exp_verdict) in EXPECT.items():
        pack = os.path.join(root, name)
        p = subprocess.run([sys.executable, "verifier.py", pack],
                           capture_output=True, text=True)
        try:
            rep = json.loads(p.stdout)
            verdict = rep.get("verdict", "?")
        except json.JSONDecodeError:
            verdict = "CRASH: " + (p.stderr.strip().splitlines()[-1] if p.stderr else "?")
        ok = (p.returncode == exp_code and verdict == exp_verdict)
        if not ok:
            failed += 1
        results.append((name, exp_verdict, verdict, p.returncode, exp_code, ok))
    w = max(len(r[0]) for r in results)
    for name, expv, gotv, gc, ec, ok in results:
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {name.ljust(w)}  expected={expv}/{ec}  got={gotv}/{gc}")
    print(f"\n{len(results) - failed}/{len(results)} vectors passing")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
