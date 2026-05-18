---
id: weekly-repo-hygiene-review-2026-05-17
title: Weekly Repo Hygiene Review Evidence 2026-05-17
role: dev_rel
status: ready
created_at: 2026-05-17
updated_at: 2026-05-17
author: codex
target_repo: Synapse-Network-Growing
---

# Weekly Repo Hygiene Review Evidence

## Scope

- Automation: `weekly_repo_hygiene_review`
- Date: `2026-05-17`
- Worktree: `/Users/cliff/.codex/worktrees/bb4b/Synapse-Network-Growing-agent-b`
- Week key: `2026-W20`

## Repo Scan Findings

The read-only scan reproduced the repo's weekly hygiene findings under the documented local PostgreSQL dev environment.

- Root markdown review items remain: `CLAUDE.md`, `GEMINI.md`, `harness-engineering.md`
- Docs metadata items remain: missing frontmatter in
  `docs/design-docs/company-ops-latest-architecture.md`,
  `docs/design-docs/context-loading-map.md`,
  `docs/design-docs/current-feature-inventory.md`,
  `docs/design-docs/system-design-principles.md`,
  `docs/plans/README.md`
- PR template newline hygiene is already present
- Ops stale-state findings: none in the local database snapshot

## Safe Cleanup Selected

One low-risk mechanical cleanup item was safe to apply:

- Fix `server/services/scheduling/repo_hygiene_scan.py` so TODO/FIXME detection only matches actual source comments, not embedded string literals in scanner code.

Why this item:

- It removed a self-referential false positive from the weekly scan.
- It did not touch production resources, secrets, auth, deployments, Docker, caches, funds, or settlement flows.
- No duplicate weekly cleanup candidate or requirement existed for `2026-W20` in the local Ops database.

## Verification

Commands run:

```bash
export OPS_DATABASE_URL="postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing_local"
export PYTHONPATH=.
/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q tests/test_weekly_repo_hygiene_review.py
/Users/cliff/workspace/agent/.venv/bin/python - <<'PY'
from server.services.scheduling.repo_hygiene_scan import scan_repo_hygiene_payload
import json
print(json.dumps(scan_repo_hygiene_payload(), ensure_ascii=False, indent=2, default=str))
PY
git diff --check
```

Results:

- `tests/test_weekly_repo_hygiene_review.py`: `8 passed`
- `git diff --check`: clean
- Weekly scan finding count dropped from `9` to `8`
- Removed false-positive finding: `todo:server/services/scheduling/repo_hygiene_scan.py`

## Delivery

- Publish path: small cleanup PR only
- Auto-merge: disabled
