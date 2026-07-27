#!/usr/bin/env bash
# Deterministic website deploy: repo website/ -> /var/www/nous-lang.org/
#
# GAP 2b. Replaces in-place editing of the served tree. Source of truth is
# the git-tracked website/ directory; this script stages it to the served
# path. It is ADDITIVE (no --delete): served-only files that are
# intentionally not tracked in the repo -- blog/drafts/* (unpublished) -- are
# never removed. The standalone verify_offline.py download was withdrawn in S264
# (docs/adr/ADR-0009); it is no longer a served-only exception.  __s264_leg_a_v1__
#
# Safety:
#   - refuses unless run from the repo root on branch main
#   - refuses if the working tree is dirty (website/ must be committed)
#   - prints an rsync dry-run diff and, without --apply, stops there
#   - excludes *.bak* from the copy (history is git, not .bak files)
#   - normalizes modes: dirs 0755, files 0644
#
# Usage:
#   scripts/deploy_website.sh            # dry-run: show what would change
#   scripts/deploy_website.sh --apply    # perform the deploy
set -euo pipefail

REPO="/opt/aetherlang_agents/nous"
SRC="${REPO}/website/"
DST="/var/www/nous-lang.org/"

APPLY=0
if [ "${1:-}" = "--apply" ]; then
    APPLY=1
elif [ -n "${1:-}" ]; then
    echo "REFUSED: unknown argument '${1}' (use --apply or no argument)" >&2
    exit 2
fi

cd "${REPO}"

branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "${branch}" != "main" ]; then
    echo "REFUSED: not on main (on '${branch}')" >&2
    exit 2
fi

if [ -n "$(git status --porcelain website/)" ]; then
    echo "REFUSED: website/ has uncommitted changes; commit before deploy" >&2
    git status --porcelain website/ >&2
    exit 2
fi

if [ ! -d "${SRC}" ]; then
    echo "REFUSED: source not found: ${SRC}" >&2
    exit 2
fi
if [ ! -d "${DST}" ]; then
    echo "REFUSED: served dir not found: ${DST}" >&2
    exit 2
fi

RSYNC_OPTS=(-rc --exclude='*.bak*' --chmod=D0755,F0644)

if [ "${APPLY}" -eq 0 ]; then
    echo "=== DRY RUN (no changes). Re-run with --apply to deploy. ==="
    echo "    ${SRC} -> ${DST} (additive, no --delete, excludes *.bak*)"
    echo "--- files that WOULD change ---"
    rsync "${RSYNC_OPTS[@]}" -n -i "${SRC}" "${DST}" || true
    echo "--- end dry run ---"
    exit 0
fi

# __s248_deploy_claim_lint_gate_v1__ claim-boundary gate before serving
echo "=== CLAIM BOUNDARY GATE (claim_lint --root .) ==="
if ! python3 scripts/claim_lint.py --config claims.toml --root .; then
    echo "REFUSED: claim-boundary violation(s) present; refusing to serve" >&2
    exit 2
fi

echo "=== APPLYING deploy ${SRC} -> ${DST} ==="
rsync "${RSYNC_OPTS[@]}" -i "${SRC}" "${DST}"
echo "=== deploy complete ==="
echo "verify served byte-identity, e.g.:"
echo "  sha256sum ${DST}index.html ${REPO}/website/index.html"
