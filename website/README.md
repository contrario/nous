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

The repo is the **source of truth**. The live directory `/var/www/nous-lang.org/` is deployed from here.

```bash
# preview changes without applying
./deploy_website.sh --dry-run

# deploy (creates timestamped backup first)
./deploy_website.sh

# deploy without backup (not recommended)
./deploy_website.sh --no-backup
```

The script:
1. Creates backup at `/var/www/backups/nous-lang.org/<timestamp>/`
2. `rsync -av --delete --exclude='*.bak*'` from `website/` → `/var/www/nous-lang.org/`
3. SHA256-verifies every deployed file
4. Exits non-zero on any checksum mismatch

## Rollback

```bash
rsync -av --delete /var/www/backups/nous-lang.org/<timestamp>/ /var/www/nous-lang.org/
```

## Editing Workflow

1. Edit file in `website/` on the repo
2. `./deploy_website.sh --dry-run` to preview
3. `./deploy_website.sh` to apply
4. `git add website/ && git commit -m "web: ..."` && `git push`

**Do not edit `/var/www/nous-lang.org/*` directly.** Changes there will be overwritten on next deploy and lost on next disk failure.

## Server B

Server B (46.224.188.209) currently runs uvicorn only (no nginx, port 80 occupied by neuro-frontend Docker). Website not served from Server B. Cloudflare DNS → Server A only.
