import assert from "node:assert/strict";
import test from "node:test";
import { createToolHandlers, TOOL_NAMES } from "../src/tools.js";
import { GrowingApiError } from "../src/client.js";

const config = {
  opsBaseUrl: "http://127.0.0.1:9600",
  dashboardBaseUrl: "http://localhost:9700",
  deployToken: "test-token"
};

test("tool list exposes exactly the allowlisted release tools", () => {
  assert.deepEqual(TOOL_NAMES, [
    "list_release_targets",
    "create_release_task",
    "request_staging_deploy",
    "request_production_promotion",
    "get_release_task_status",
    "get_deployment_events"
  ]);
});

test("input schemas reject forbidden image digest and shell arguments", async () => {
  const handlers = createToolHandlers(new FakeClient(), config);
  const result = await handlers.requestProductionPromotion({
    task_id: 1,
    confirm_phrase: "YES",
    staging_deployment_record_id: 2,
    commit_sha: "abcdef123456",
    project_key: "synapse-network",
    service_key: "docs-front",
    image_digest: "sha256:unsafe",
    shell: "gcloud run deploy"
  });

  assert.equal(result.isError, true);
  assert.match(result.structuredContent.message, /Unrecognized keys/);
});

test("missing deploy token fails closed before mutating APIs", async () => {
  const client = new FakeClient();
  client.mutate = async () => {
    throw new GrowingApiError(403, "DEPLOY_TOKEN_MISSING", "OPS_AGENT_DEPLOY_API_TOKEN is required.");
  };
  const handlers = createToolHandlers(client, { ...config, deployToken: "" });

  const result = await handlers.createReleaseTask({
    project_key: "synapse-network",
    service_key: "docs-front",
    branch_name: "main",
    environment: "staging"
  });

  assert.equal(result.isError, true);
  assert.equal(result.structuredContent.code, "DEPLOY_TOKEN_MISSING");
  assert.equal(client.calls.length, 0);
});

test("production without YES returns human gate and does not call deploy", async () => {
  const client = new FakeClient();
  const handlers = createToolHandlers(client, config);

  const result = await handlers.requestProductionPromotion({ task_id: 10 });

  assert.equal(result.structuredContent.data.status, "needs_human_gate");
  assert.deepEqual(client.calls, []);
});

test("production with mismatched staging evidence fails closed", async () => {
  const client = new FakeClient({
    "/api/releases/tasks/query?project_key=synapse-network&environment=staging&status=completed&limit=100&offset=0": {
      items: [stagingTask({ service_key: "gateway" })]
    }
  });
  const handlers = createToolHandlers(client, config);

  const result = await handlers.requestProductionPromotion({
    task_id: 20,
    confirm_phrase: "YES",
    staging_deployment_record_id: 99,
    commit_sha: "abcdef123456",
    project_key: "synapse-network",
    service_key: "docs-front"
  });

  assert.equal(result.isError, true);
  assert.equal(result.structuredContent.code, "STAGING_EVIDENCE_MISMATCH");
  assert.equal(client.calls.filter((call) => call.method === "POST").length, 0);
});

test("staging deploy returns deployment evidence and runner command only", async () => {
  const client = new FakeClient({
    "POST /api/releases/tasks/11/deploy-staging": releaseTask({
      id: 11,
      deployment_record_id: 42,
      deployment_status: "requested"
    })
  });
  const handlers = createToolHandlers(client, config);

  const result = await handlers.requestStagingDeploy({ task_id: 11 });

  assert.equal(result.structuredContent.data.deployment_record_id, 42);
  assert.match(result.structuredContent.data.runner_command, /run_deploy_worker\.py --once/);
  assert.equal(client.calls.length, 1);
});

test("successful deployment notes are not exposed as failure summary", async () => {
  const client = new FakeClient({
    "/api/releases/tasks/12": releaseTask({
      id: 12,
      status: "completed",
      deployment_status: "succeeded",
      deployment_failure_summary: "Local deploy succeeded."
    })
  });
  const handlers = createToolHandlers(client, config);

  const result = await handlers.getReleaseTaskStatus({ task_id: 12 });

  assert.equal(result.structuredContent.data.failure_summary, null);
});

function stagingTask(overrides = {}) {
  return releaseTask({
    id: 7,
    deployment_record_id: 99,
    status: "completed",
    deployment_status: "succeeded",
    deployment_health_status: "passed",
    deployment_commit_sha: "abcdef123456",
    ...overrides
  });
}

function releaseTask(overrides = {}) {
  return {
    id: 1,
    deployment_record_id: null,
    project_key: "synapse-network",
    service_key: "docs-front",
    branch_name: "main",
    environment: "staging",
    status: "requested",
    deployment_status: null,
    deployment_health_status: null,
    deployment_commit_sha: null,
    target_commit_sha: "abcdef123456",
    deployment_metadata: {},
    deployment_failure_summary: null,
    ...overrides
  };
}

class FakeClient {
  constructor(responses = {}) {
    this.responses = responses;
    this.calls = [];
  }

  async get(path) {
    this.calls.push({ method: "GET", path });
    return this.responses[path] || {};
  }

  async mutate(path, body) {
    this.calls.push({ method: "POST", path, body });
    return this.responses[`POST ${path}`] || releaseTask({ id: body?.task_id ?? 1 });
  }
}
