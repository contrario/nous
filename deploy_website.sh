#!/usr/bin/env bash
# __s242_deploy_retired_v1__
# RETIRED (S242). The former body ran 'rsync --delete' from website/ into
# /var/www/nous-lang.org/, deleting served-only artifacts (the demo chain)
# that are intentionally untracked, while preserving stale *.bak* files via
# an exclude. Superseded by the additive deployer scripts/deploy_website.sh
# (no --delete; dry-run by default; refuses on a dirty tree or off main).
# Old bytes: git history of this path.
set -euo pipefail
echo "REFUSED: ./deploy_website.sh is retired (S242)." >&2
echo "It used 'rsync --delete' and would remove served-only demo artifacts." >&2
echo "Use the additive deployer instead:" >&2
echo "  scripts/deploy_website.sh            # dry-run: show what would change" >&2
echo "  scripts/deploy_website.sh --apply    # perform the deploy" >&2
exit 2
