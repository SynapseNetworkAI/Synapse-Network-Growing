---
created_at: 2026-04-08
updated_at: 2026-04-08
doc_status: active
---

# Validation Route

## Required Checks

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile $(find agents_memory scripts -name '*.py' -print)
python3 scripts/memory.py docs-check .
```

## Task-Specific Checks

- 写下本任务额外需要跑的命令

## Review Notes

- docs diff:
- code diff:
- test diff:

## Onboarding Verification
- primary verification command: `amem doctor .`
- expected completion: No pending onboarding steps remain.

## State Snapshot
```json
{
  "project_bootstrap_ready": true,
  "project_bootstrap_complete": true,
  "recommended_next_command": "amem doctor .",
  "recommended_verify_command": "amem doctor ."
}
```
