---
created_at: 2026-04-19
updated_at: 2026-04-19
doc_status: active
---

# Spec

## Task

Planning onboarding: planning_bundle

## Problem

- 当前问题是什么？

## Goal

- 这次变更要达成什么结果？

## Non-Goals

- 这次不解决什么？

## Acceptance Criteria

- [ ] 有明确可验证的功能结果
- [ ] 有对应 docs / code / tests 同步要求
- [ ] 验收标准可被测试或命令验证

## Onboarding Inputs
- state file: `.agents-memory/onboarding-state.json`

```json
[
  {
    "name": "Core",
    "status": "HEALTHY",
    "summary": "Core status=HEALTHY (ok=7, warn=0, fail=0, info=0)",
    "checks": [
      {
        "status": "OK",
        "key": "registry",
        "detail": "registered as 'synapse-network-growing'"
      },
      {
        "status": "OK",
        "key": "active",
        "detail": "active=true"
      },
      {
        "status": "OK",
        "key": "root",
        "detail": "."
      },
      {
        "status": "OK",
        "key": "python3.12",
        "detail": "/opt/homebrew/bin/python3.12"
      },
      {
        "status": "OK",
        "key": "mcp_package",
        "detail": "mcp import OK"
      },
      {
        "status": "OK",
        "key": "profile_manifest",
        "detail": "applied profile 'python-service'"
      },
      {
        "status": "OK",
        "key": "profile_consistency",
        "detail": "profile 'python-service' consistency OK"
      }
    ]
  },
  {
    "name": "Planning",
    "status": "ATTENTION",
    "summary": "Planning status=ATTENTION (ok=1, warn=0, fail=1, info=0)",
    "checks": [
      {
        "status": "OK",
        "key": "planning_root",
        "detail": "present: ./docs/plans"
      },
      {
        "status": "FAIL",
        "key": "planning_bundle",
        "detail": "docs/plans/ai-company-ops-roadmap/README.md missing required phrases: planning bundle"
      }
    ]
  },
  {
    "name": "Integration",
    "status": "HEALTHY",
    "summary": "Integration status=HEALTHY (ok=2, warn=0, fail=0, info=0)",
    "checks": [
      {
        "status": "OK",
        "key": "bridge_instruction",
        "detail": "./.github/instructions/agents-memory-bridge.instructions.md"
      },
      {
        "status": "OK",
        "key": "mcp_config",
        "detail": "agents-memory server configured -> ./.vscode/mcp.json"
      }
    ]
  },
  {
    "name": "Optional",
    "status": "WATCH",
    "summary": "Optional status=WATCH (ok=2, warn=5, fail=0, info=0)",
    "checks": [
      {
        "status": "OK",
        "key": "copilot_activation",
        "detail": "Agents-Memory activation block present -> ./.github/copilot-instructions.md"
      },
      {
        "status": "OK",
        "key": "agents_read_order",
        "detail": "AGENTS.md references current bridge and 8 managed standard(s)"
      },
      {
        "status": "WARN",
        "key": "refactor_watch",
        "detail": "scripts/generate_architecture_graph.py::detect_import_edges high complexity (lines=56>40, branches=19>5, nesting=5>=4, locals=16>8, missing_guiding_comment)"
      },
      {
        "status": "WARN",
        "key": "refactor_watch",
        "detail": "server/services/workflows/agent_first.py::reconcile_execution_state high complexity (lines=148>40, branches=23>5, nesting=10>=4, locals=25>8, missing_guiding_comment)"
      },
      {
        "status": "WARN",
        "key": "refactor_watch",
        "detail": "server/services/reviews/company_review.py::_cross_project_bug_recoveries high complexity (lines=64>40, branches=7>5, nesting=4>=4, locals=14>8, missing_guiding_comment)"
      },
      {
        "status": "WARN",
        "key": "refactor_watch",
        "detail": "server/services/workflows/orchestrator/__init__.py::_soft_delete_requirement_tree high complexity (lines=57>40, branches=12>5, nesting=4>=4, locals=12>8, missing_guiding_comment)"
      },
      {
        "status": "WARN",
        "key": "refactor_watch",
        "detail": "server/services/scheduling/portfolio_scheduler.py::execute_portfolio_rebalance high complexity (lines=61>40, branches=8>5, nesting=4>=4, locals=14>8, missing_guiding_comment)"
      }
    ]
  }
]
```
