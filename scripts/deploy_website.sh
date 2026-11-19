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
#   - refuses if rsync would serve a file no commit holds, an ignored one
#     too; the claim gate lints an export of HEAD's commit (FG-S481-J)
#   - prints an rsync dry-run diff and, without --apply, stops there
#   - excludes *.bak* from the copy (history is git, not .bak files)
#   - excludes __pycache__/ and *.pyc: a test run writes bytecode beside
#     a vector's mint harness; it is not site content (NT-GATE-1 V3 F10)
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

# __nt_v3_deploy_bytecode_v1__
RSYNC_OPTS=(-rc --exclude='*.bak*' --exclude='__pycache__/' --exclude='*.pyc' --chmod=D0755,F0644)

# __s485_deploy_commit_bound_v1__ (FG-S481-J) the gate reads the commit,
# not the working tree: ignored scratch in the tree neither moves the
# lint's count nor refuses a deploy, and a file rsync would serve that no
# commit holds refuses it. Both functions run in the repo root.
untracked_served() {
    # $1 the rsync source directory, $2 its path in the repo, with "/".
    # Prints each file rsync would copy that git does not track; rc 3 if
    # rsync or git fails, so a failure is never read as a clean list.
    local t
    t="$(mktemp -d)" || return 3
    mkdir "${t}/empty" || { rm -rf "${t}"; return 3; }
    if ! rsync "${RSYNC_OPTS[@]}" -n --out-format='%n' "$1" "${t}/empty/" > "${t}/served"; then
        rm -rf "${t}"; return 3
    fi
    if ! git -c core.quotePath=false ls-files -- "$2" > "${t}/tracked"; then
        rm -rf "${t}"; return 3
    fi
    grep -v '/$' "${t}/served" | LC_ALL=C sort > "${t}/s" || true
    sed "s#^$2##" "${t}/tracked" | LC_ALL=C sort > "${t}/g"
    LC_ALL=C comm -23 "${t}/s" "${t}/g"
    rm -rf "${t}"
}

lint_commit() {
    # Lints an export of HEAD's commit with that commit's own claim lint
    # and config, --anchor the commit; rc 3 if the export fails.
    local head exp rc=0
    head="$(git rev-parse --verify HEAD)" || return 3
    exp="$(mktemp -d)" || return 3
    if ! git archive --format=tar "${head}" | tar -x -C "${exp}"; then
        rm -rf "${exp}"; return 3
    fi
    python3 -B "${exp}/scripts/claim_lint.py" --config "${exp}/claims.toml" \
        --root "${exp}" --anchor "${head}" || rc=$?
    rm -rf "${exp}"
    return "${rc}"
}
# __s485_deploy_commit_bound_end_v1__

extra="$(untracked_served "${SRC}" website/)" || {
    echo "REFUSED: could not list what rsync would serve" >&2
    exit 2
}
if [ -n "${extra}" ]; then
    echo "REFUSED: rsync would serve file(s) that no commit holds:" >&2
    echo "${extra}" >&2
    exit 2
fi

if [ "${APPLY}" -eq 0 ]; then
    echo "=== DRY RUN (no changes). Re-run with --apply to deploy. ==="
    echo "    ${SRC} -> ${DST} (additive, no --delete, excludes *.bak*, __pycache__/, *.pyc)"
    echo "--- files that WOULD change ---"
    rsync "${RSYNC_OPTS[@]}" -n -i "${SRC}" "${DST}" || true
    echo "--- end dry run ---"
    exit 0
fi

# __s248_deploy_claim_lint_gate_v1__ claim-boundary gate before serving
echo "=== CLAIM BOUNDARY GATE (claim_lint on HEAD's commit, exported) ==="
if ! lint_commit; then
    echo "REFUSED: claim-boundary violation(s) present; refusing to serve" >&2
    exit 2
fi

echo "=== APPLYING deploy ${SRC} -> ${DST} ==="
rsync "${RSYNC_OPTS[@]}" -i "${SRC}" "${DST}"
echo "=== deploy complete ==="
echo "verify served byte-identity, e.g.:"
echo "  sha256sum ${DST}index.html ${REPO}/website/index.html"
