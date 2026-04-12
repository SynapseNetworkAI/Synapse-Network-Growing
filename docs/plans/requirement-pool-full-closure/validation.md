---
created_at: 2026-04-09
updated_at: 2026-04-09
doc_status: active
---

# Validation

## Automated

- `pytest`
- `cd dashboard && npm test`
- `cd dashboard && npm run build`
- `cd dashboard && npx playwright test`

## Manual Checks

- Create a requirement with dependencies and verify it remains blocked until upstream work is done.
- Submit a requirement revision and verify the requirement can be replanned on a new version.
- Open the homepage and verify the operator dashboard renders without org-tree content.
