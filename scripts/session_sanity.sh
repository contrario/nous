#!/usr/bin/env bash
# NOUS session sanity check.
#
# Canonical command set to run at the start of every session before
# any work begins. Extends the inline command set documented in the
# project instructions Section 12 with Server B git HEAD drift
# detection (added S83 #3 after Session 83 observed Server B's git
# checkout was 12 commits behind origin while its installed package
# matched the current release; the running service used the venv,
# not the checkout, so health-check alone did not detect the drift).
#
# Usage:
#   bash /opt/aetherlang_agents/nous/scripts/session_sanity.sh
#
# Exit code is always 0 (informational tool; flags drift in stdout).
#
# Marker: __session83_server_b_drift_detect_v1__

set -u

REPO_A="/opt/aetherlang_agents/nous"
SERVER_B="46.224.188.209"
REPO_B="/opt/neuroaether/nous"

cd "${REPO_A}"

echo "=== HEAD A ==="
git log --oneline -5

echo "=== TAG ==="
git describe --tags --abbrev=0

echo "=== HEALTH A ==="
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool

echo "=== HEALTH B ==="
ssh -o BatchMode=yes root@${SERVER_B} \
    "curl -s http://127.0.0.1:8000/v1/health" | python3 -m json.tool

echo "=== GIT DRIFT B ==="
HEAD_A=$(git rev-parse HEAD)
HEAD_B=$(ssh -o BatchMode=yes root@${SERVER_B} \
    "cd ${REPO_B} && git rev-parse HEAD" 2>/dev/null || true)
if [ -z "${HEAD_B}" ]; then
    echo "WARN: could not fetch Server B HEAD via SSH"
elif [ "${HEAD_A}" = "${HEAD_B}" ]; then
    echo "OK: Server A and B at same HEAD ${HEAD_A:0:7}"
else
    echo "DRIFT: A=${HEAD_A:0:7} B=${HEAD_B:0:7}"
    echo "  Reconcile: ssh root@${SERVER_B} \\"
    echo "    'cd ${REPO_B} && git fetch --tags --force && \\"
    echo "     git pull --ff-only origin main'"
fi

echo "=== PYTEST ==="
python3 -m pytest tests/ -q 2>&1 | tail -3

echo "=== PIP ==="
pip show nous-lang 2>&1 | head -3

echo "=== ASKLEPIOS ==="
sqlite3 /var/lib/asklepios/state.db \
    "SELECT service,status,http_code,consecutive_fails,last_check_utc \
     FROM probes WHERE service LIKE 'nous%'"
