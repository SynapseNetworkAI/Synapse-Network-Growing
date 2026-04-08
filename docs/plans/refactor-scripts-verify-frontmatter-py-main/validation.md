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

## Refactor Verification
- primary verification command: `amem doctor .`
- expected outcome: `scripts/verify_frontmatter.py::main` is no longer the first hotspot, or its issue list is smaller.

## Hotspot Snapshot
```json
{
  "identifier": "scripts/verify_frontmatter.py::main",
  "rank_token": "hotspot-9c6441ed2adf",
  "relative_path": "scripts/verify_frontmatter.py",
  "function_name": "main",
  "qualified_name": "main",
  "line": 42,
  "status": "WARN",
  "effective_lines": 21,
  "branches": 6,
  "nesting": 4,
  "local_vars": 9,
  "has_guiding_comment": false,
  "issues": [
    "branches=6>5",
    "nesting=4>=4",
    "locals=9>8",
    "missing_guiding_comment"
  ],
  "score": 31
}
```
