export const ACTOR = "agent/local-release-mcp";

export const RELEASE_TARGETS = [
  {
    project_key: "synapse-network",
    project_display_name: "Synapse-Network",
    services: ["gateway", "gateway-admin", "admin-front", "user-front", "docs-front"],
    environments: ["staging", "production"]
  },
  {
    project_key: "synapse-network-provider",
    project_display_name: "Synapse-Network-Provider",
    services: ["provider-service"],
    environments: ["staging", "production"]
  }
];

export function dashboardUrl(config, path = "/releases?tab=tasks") {
  return `${config.dashboardBaseUrl}${path}`;
}

export function deploymentEventsUrl(config, deploymentRecordId) {
  return `${config.opsBaseUrl}/api/releases/deployments/${deploymentRecordId}/events`;
}

export function runnerCommand(deploymentRecordId) {
  return [
    "PYTHONPATH=.",
    ".venv/bin/python",
    "scripts/local/run_deploy_worker.py",
    "--once",
    "--deployment-record-id",
    String(deploymentRecordId)
  ].join(" ");
}

export function taskEvidence(config, task, extras = {}) {
  const deploymentRecordId = task?.deployment_record_id ?? null;
  return {
    task_id: task?.id ?? null,
    deployment_record_id: deploymentRecordId,
    project_key: task?.project_key ?? null,
    service_key: task?.service_key ?? null,
    environment: task?.environment ?? null,
    branch_name: task?.branch_name ?? null,
    commit_sha: task?.deployment_commit_sha || task?.target_commit_sha || null,
    status: task?.status ?? null,
    deployment_status: task?.deployment_status ?? null,
    health_status: task?.deployment_health_status ?? null,
    manifest_summary: manifestSummary(task?.deployment_metadata),
    smoke_result: smokeResult(task?.deployment_metadata, task?.deployment_health_status),
    failure_summary: isFailed(task) ? task?.deployment_failure_summary || null : null,
    runner_command: deploymentRecordId ? runnerCommand(deploymentRecordId) : null,
    events_url: deploymentRecordId ? deploymentEventsUrl(config, deploymentRecordId) : null,
    dashboard_url: dashboardUrl(config),
    ...extras
  };
}

export function bugIntakePayload({ tool, task, deploymentRecordId, summary, config }) {
  const projectKey = task?.project_key || "unknown";
  const serviceKey = task?.service_key || "unknown";
  const environment = task?.environment || "unknown";
  return {
    source_key: "delivery_blocker_bug",
    project_key: projectKey,
    title: `Local release MCP failure: ${serviceKey} ${environment}`,
    summary: summary || task?.deployment_failure_summary || "Release MCP operation failed.",
    severity: "high",
    environment,
    source_ref: deploymentRecordId ? `deployment_record:${deploymentRecordId}` : `release_task:${task?.id ?? "unknown"}`,
    log_excerpt: task?.deployment_failure_summary || null,
    metadata: {
      mcp_tool: tool,
      task_id: task?.id ?? null,
      deployment_record_id: deploymentRecordId ?? task?.deployment_record_id ?? null,
      service_key: serviceKey,
      events_url: deploymentRecordId ? deploymentEventsUrl(config, deploymentRecordId) : null
    }
  };
}

function manifestSummary(metadata) {
  const manifest = metadata?.manifest && typeof metadata.manifest === "object" ? metadata.manifest : metadata;
  return {
    image_digest: manifest?.image_digest || manifest?.imageDigest || null,
    revision: manifest?.revision || manifest?.cloud_run_revision || null,
    cloud_run_service: manifest?.cloud_run_service || manifest?.cloudRunService || null,
    smoke_status: manifest?.smoke_status || manifest?.smokeStatus || null
  };
}

function smokeResult(metadata, healthStatus) {
  const manifest = manifestSummary(metadata);
  return manifest.smoke_status || healthStatus || null;
}

function isFailed(task) {
  return task?.status === "failed" || task?.deployment_status === "failed";
}
