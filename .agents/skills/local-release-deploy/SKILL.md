---
name: local-release-deploy
description: Safely create and trigger Growing local deploy runner release tasks for staging and production promotion.
metadata:
  version: 1.0.0
---

# Local Release Deploy

Use this skill when a Codex session or internal agent needs to deploy a Synapse service through Growing.

## Hard Boundaries

- Do not run `gcloud run deploy` directly.
- Do not use GitHub Actions.
- Do not manually mark a deployment successful.
- Do not write production directly.
- Do not run `gcloud config set impersonate-service-account`.
- Production is always same-service, same-commit staging digest promotion.

## Required Local Auth

Agent calls must set a non-human actor such as `codex/<thread>` or `agent/<name>` and include:

```text
X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN
```

If the token is missing, stop. UI/operator calls use `actor=operator` and do not need this header.

## Staging Flow

1. Confirm the target repository change is merged to `main`.
2. Create a release task:

```bash
curl -sS -X POST "$OPS_BASE_URL/api/releases/tasks" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN" \
  -d '{
    "project_key": "synapse-network",
    "service_key": "docs-front",
    "branch_name": "main",
    "environment": "staging",
    "source_type": "manual",
    "actor": "codex/<thread-or-task>"
  }'
```

3. Request staging deploy:

```bash
curl -sS -X POST "$OPS_BASE_URL/api/releases/tasks/<task_id>/deploy-staging" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN" \
  -d '{"actor":"codex/<thread-or-task>","note":"staging via local deploy runner"}'
```

4. Run the local deploy runner:

```bash
PYTHONPATH=. .venv/bin/python scripts/local/run_deploy_worker.py --once --deployment-record-id <deployment_record_id>
```

5. Verify:

- `ReleaseTask.status=completed`
- `DeploymentRecord.status=succeeded`
- `health_status=passed`
- manifest has `image_digest`, `revision`, and smoke result

## Production Flow

1. Create a production release task for the same `project_key`, `service_key`, and `main`.
2. Request production deploy:

```bash
curl -sS -X POST "$OPS_BASE_URL/api/releases/tasks/<task_id>/deploy" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN" \
  -d '{"actor":"codex/<thread-or-task>","confirm_phrase":"YES","note":"promote successful staging digest"}'
```

3. Run the local deploy runner with the returned `deployment_record_id`.
4. Verify production smoke and `/releases?tab=online`.

## Failure Policy

- Do not retry the whole release train.
- Do not mark success manually.
- Preserve `deployment_events`.
- Fix root cause, then retry the failed task or create a new task.
- If a run is stuck, use the UI/API reset with confirmation phrase `RESET_LOCAL_DEPLOY`.

## MCP Policy

Do not expose this as public MCP. A future local-only MCP may wrap only allowlisted release tools: list targets, create task, request staging deploy, request production promotion, read task status, and read deployment events. It must not expose shell or gcloud.
