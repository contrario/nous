#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/aetherlang_agents/nous"
WEBSITE_DIR="${REPO_DIR}/website"
LIVE_DIR="/var/www/nous-lang.org"
BACKUP_ROOT="/var/www/backups/nous-lang.org"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${TS}"

DRY_RUN=0
SKIP_BACKUP=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --no-backup) SKIP_BACKUP=1 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--dry-run] [--no-backup]

Deploys ${WEBSITE_DIR} → ${LIVE_DIR}.
- Creates timestamped backup in ${BACKUP_ROOT} unless --no-backup.
- --dry-run: prints rsync plan without applying.
- Excludes *.bak* files.
- Verifies SHA256 on all deployed files.
EOF
            exit 0
            ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

if [ ! -d "$WEBSITE_DIR" ]; then
    echo "ERROR: ${WEBSITE_DIR} does not exist" >&2
    exit 1
fi
if [ ! -d "$LIVE_DIR" ]; then
    echo "ERROR: ${LIVE_DIR} does not exist" >&2
    exit 1
fi

RSYNC_FLAGS=(-av --delete --exclude='*.bak*' --exclude='backups/')

if [ "$DRY_RUN" -eq 1 ]; then
    echo "=== DRY RUN ==="
    rsync -n "${RSYNC_FLAGS[@]}" "${WEBSITE_DIR}/" "${LIVE_DIR}/"
    exit 0
fi

if [ "$SKIP_BACKUP" -eq 0 ]; then
    echo "=== backup → ${BACKUP_DIR} ==="
    mkdir -p "$BACKUP_DIR"
    rsync -a --exclude='*.bak*' "${LIVE_DIR}/" "${BACKUP_DIR}/"
fi

echo "=== deploy ==="
rsync "${RSYNC_FLAGS[@]}" "${WEBSITE_DIR}/" "${LIVE_DIR}/"

echo "=== SHA256 verification ==="
FAIL=0
while IFS= read -r -d '' f; do
    rel="${f#${WEBSITE_DIR}/}"
    src_sum="$(sha256sum "$f" | awk '{print $1}')"
    dst="${LIVE_DIR}/${rel}"
    if [ ! -f "$dst" ]; then
        echo "FAIL  missing on live: ${rel}"
        FAIL=1
        continue
    fi
    dst_sum="$(sha256sum "$dst" | awk '{print $1}')"
    if [ "$src_sum" != "$dst_sum" ]; then
        echo "FAIL  checksum mismatch: ${rel}"
        FAIL=1
    fi
done < <(find "$WEBSITE_DIR" -type f ! -name "*.bak*" -print0)

if [ "$FAIL" -ne 0 ]; then
    echo "=== deployment FAILED ===" >&2
    exit 1
fi

echo "=== deployed OK (${TS}) ==="
if [ "$SKIP_BACKUP" -eq 0 ]; then
    echo "rollback: rsync -av --delete ${BACKUP_DIR}/ ${LIVE_DIR}/"
fi
