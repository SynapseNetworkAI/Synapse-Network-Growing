---
created_at: 2026-03-28
updated_at: 2026-03-28
doc_status: active
description: >
  Project-local overlay generated for the python-service profile.
  Keep repo-specific workflow notes here and regenerate with amem profile-render.
applyTo: "**"
---

# Python Service Local Contract

- Active profile: python-service
- Preferred Python executable: python3
- Preferred tests directory: tests
- Python project detected: true
- Pytest-style config detected: false
- Tests layout detected: true

## Local Expectations

1. Use `python3` for repo-local verification examples.
2. Keep automated tests rooted under `tests` unless the repo has a stronger existing contract.
3. Re-run `amem profile-render .` after changing project structure that affects profile detectors.