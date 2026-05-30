# Local Release MCP

Local-only MCP server for Codex/agents to operate Growing release tasks through allowlisted tools.

## Boundaries

- Does not run shell.
- Does not call `gcloud`.
- Does not accept raw image digests.
- Does not delete or modify deployment evidence.
- Does not bypass production gates.
- Real deployment execution remains in `scripts/local/run_deploy_worker.py`.

## Tools

1. `list_release_targets`
2. `create_release_task`
3. `request_staging_deploy`
4. `request_production_promotion`
5. `get_release_task_status`
6. `get_deployment_events`

## Local Registration

Codex should launch this server over stdio:

```toml
[mcp_servers.growing_release]
command = "node"
args = ["/Users/cliff/workspace/agent/Synapse-Network-Growing/mcp/local-release/src/index.js"]
startup_timeout_sec = 30
```

The server loads `OPS_BASE_URL` and `OPS_AGENT_DEPLOY_API_TOKEN` from process env first, then the repo `.env`.
Do not put the token in Codex config.

## Deployment Flow

The MCP can create a ReleaseTask and request a DeploymentRecord. It returns the runner command as evidence:

```bash
PYTHONPATH=. .venv/bin/python scripts/local/run_deploy_worker.py --once --deployment-record-id <id>
```

An operator or a separate local runner process must execute that command. Production promotion requires `confirm_phrase=YES` plus matching same-project, same-service, same-commit staging evidence.
