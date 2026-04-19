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

## Refactor Verification
- primary verification command: `amem doctor .`
- expected outcome: `scripts/generate_architecture_graph.py::detect_import_edges` is no longer the first hotspot, or its issue list is smaller.

## Hotspot Snapshot
```json
{
  "identifier": "scripts/generate_architecture_graph.py::detect_import_edges",
  "rank_token": "hotspot-0e89c9d2bec2",
  "relative_path": "scripts/generate_architecture_graph.py",
  "function_name": "detect_import_edges",
  "qualified_name": "detect_import_edges",
  "line": 307,
  "status": "WARN",
  "effective_lines": 56,
  "branches": 19,
  "nesting": 5,
  "local_vars": 16,
  "has_guiding_comment": false,
  "issues": [
    "lines=56>40",
    "branches=19>5",
    "nesting=5>=4",
    "locals=16>8",
    "missing_guiding_comment"
  ],
  "score": 41
}
```
