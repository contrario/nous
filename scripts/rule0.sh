#!/usr/bin/env bash
# NOUS RULE 0 -- session startup sanity check, auto-enumerating TAG..HEAD.
# __nous_rule0_runner_v1__
#
# Design (S139): every stage runs INDEPENDENTLY. There is deliberately NO
# `set -e`: one failed stage must not blank the rest (S138 pipe-collapse
# footgun). The B-health tag echo is a separate stage from the B-health JSON
# so a non-JSON tag line is never fed into `python3 -m json.tool` (S138).
#
# The AHEAD stage lets git compute the commit delta since the latest tag and
# lists every commit, so seal-count drift cannot be undercounted by a human
# author: the operator reconciles the printed list against the prior seal.
REPO=/opt/aetherlang_agents/nous
SERVER_B=46.224.188.209

cd "$REPO" || { echo "FATAL: cannot cd $REPO"; exit 2; }

echo "=== RULE 0 (scripts/rule0.sh __nous_rule0_runner_v1__) ==="

echo "=== HEAD ==="
git log --oneline -6

echo "=== TAG ==="
git describe --tags

echo "=== AHEAD OF LATEST TAG (auto-enumerated) ==="
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
if [ -n "$LATEST_TAG" ]; then
    AHEAD_COUNT=$(git rev-list --count "${LATEST_TAG}..HEAD")
    echo "latest tag: ${LATEST_TAG}"
    echo "commits ahead of ${LATEST_TAG}: ${AHEAD_COUNT}"
    git log --oneline "${LATEST_TAG}..HEAD"
    echo "-- reconcile EVERY commit above against the prior seal; any unlisted commit is drift --"
else
    echo "no tag found"
fi

echo "=== HEALTH A ==="
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool

echo "=== B TAG ==="
ssh -o BatchMode=yes root@${SERVER_B} "cd /opt/neuroaether/nous && git describe --tags --abbrev=0"

echo "=== HEALTH B ==="
ssh -o BatchMode=yes root@${SERVER_B} "curl -s http://127.0.0.1:8000/v1/health" | python3 -m json.tool

echo "=== PYTEST ==="
python3 -m pytest tests/ -q 2>&1 | tail -3

echo "=== FLOOR ==="
grep -n "PYTEST_FLOOR: int" scripts/release.py | head -1

echo "=== PIP ==="
pip show nous-lang 2>&1 | head -2

echo "=== ASKLEPIOS ==="
sqlite3 /var/lib/asklepios/state.db "SELECT service,status,http_code,consecutive_fails,last_check_utc FROM probes WHERE service LIKE 'nous%'"
