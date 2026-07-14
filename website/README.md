# NOUS Website — nous-lang.org

Source of truth for the live site at **https://nous-lang.org**.

## Structure

```
website/
├── index.html                      landing page
├── ide.html                        Monaco-based IDE (5 tabs: Editor, Verify, Graph, Diff, Chat)
├── favicon.svg                     site favicon
├── og-image.png                    Open Graph social card
├── verify-fix.js                   small client-side patch for /verify tab
├── BehavioralDiffVisualizer.jsx    React component (reference, not bundled)
├── blog/index.html                 blog page
├── docs/index.html                 documentation page
└── examples/index.html             examples page
```

## IDE Features (ide.html)

- **Monaco editor** with NOUS language definition (63 keywords)
- **Autocomplete**: context-aware `CompletionItemProvider`
- **Hover tooltips**: description + usage + context for every keyword
- **SSE streaming chat**: `ReadableStream` + SSE parser + blinking cursor `❘`
- **5 tabs**: Editor, Verify (proofs), Graph (Cytoscape DAG), Diff (semantic), Chat

## Deployment
<!-- __s242_readme_deploy_v1__ -->

The repo is the **source of truth**. The live directory `/var/www/nous-lang.org/` is deployed from `website/` by `scripts/deploy_website.sh`.

```bash
# preview changes (dry-run is the default; makes no changes)
scripts/deploy_website.sh

# apply the deploy
scripts/deploy_website.sh --apply
```

The script:
1. Refuses unless run from the repo root, on branch `main`, with `website/` committed (a dirty `website/` is rejected)
2. `rsync -rc --exclude='*.bak*' --chmod=D0755,F0644` from `website/` -> `/var/www/nous-lang.org/`
3. Is **additive** (no `--delete`): served-only files not tracked in `website/` (the generated offline verifier, `blog/drafts/*`) are never removed
4. Prints an rsync `-i` change list; without `--apply` it stops at the dry-run

Verify served byte-identity after `--apply`, e.g. `sha256sum /var/www/nous-lang.org/index.html website/index.html`.

## Rollback

There is no separate backup directory; git is the rollback substrate. Revert the web change in git, then re-deploy the committed state:

```bash
git revert <web-commit>        # or: git checkout <good-commit> -- website/ && git commit
scripts/deploy_website.sh --apply
```

Because the deployer is additive, re-deploying an earlier state overwrites changed files but does not remove a file newly added to the served tree; remove any such file by hand.

## Editing Workflow

1. Edit the file in `website/` in the repo
2. `git add website/ && git commit -m "web: ..."` (the deployer refuses a dirty tree)
3. `scripts/deploy_website.sh` to preview, then `scripts/deploy_website.sh --apply`
4. `git push`

**Do not edit `/var/www/nous-lang.org/*` directly.** Changes there are not tracked and drift from the source of truth.

## Server B

Server B (46.224.188.209) currently runs uvicorn only (no nginx, port 80 occupied by neuro-frontend Docker). Website not served from Server B. Cloudflare DNS → Server A only.
