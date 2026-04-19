---
created_at: 2026-04-19
updated_at: 2026-04-19
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
- primary verification command: `amem plan-check .`
- expected completion: `amem doctor .` shows `[OK] planning_bundle`.

## State Snapshot
```json
{
  "project_bootstrap_ready": false,
  "project_bootstrap_complete": false,
  "recommended_next_command": "amem plan-check .",
  "recommended_verify_command": "amem plan-check ."
}
```
