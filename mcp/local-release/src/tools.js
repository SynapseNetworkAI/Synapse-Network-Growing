import { z } from "zod";
import { GrowingApiError } from "./client.js";
import { ACTOR, RELEASE_TARGETS, bugIntakePayload, taskEvidence } from "./evidence.js";

export const TOOL_NAMES = [
  "list_release_targets",
  "create_release_task",
  "request_staging_deploy",
  "request_production_promotion",
  "get_release_task_status",
  "get_deployment_events"
];

export const schemas = {
  listReleaseTargets: { project_key: z.string().trim().min(1).optional() },
  createReleaseTask: {
    project_key: z.string().trim().min(1),
    service_key: z.string().trim().min(1),
    branch_name: z.string().trim().min(1).default("main"),
    environment: z.enum(["staging", "production"]),
    note: z.string().trim().max(1000).optional()
  },
  requestStagingDeploy: {
    task_id: z.number().int().positive(),
    note: z.string().trim().max(1000).optional()
  },
  requestProductionPromotion: {
    task_id: z.number().int().positive(),
    confirm_phrase: z.string().trim().optional(),
    staging_deployment_record_id: z.number().int().positive().optional(),
    commit_sha: z.string().trim().min(7).max(80).optional(),
    project_key: z.string().trim().min(1).optional(),
    service_key: z.string().trim().min(1).optional()
  },
  getReleaseTaskStatus: { task_id: z.number().int().positive() },
  getDeploymentEvents: {
    deployment_record_id: z.number().int().positive(),
    after_sequence: z.number().int().min(0).default(0),
    limit: z.number().int().min(1).max(1000).default(200)
  }
};

export function createToolHandlers(client, config) {
  return {
    listReleaseTargets: async (args) => safeTool("list_release_targets", config, async () => {
      const input = parseStrict(schemas.listReleaseTargets, args);
      const targets = input.project_key
        ? RELEASE_TARGETS.filter((target) => target.project_key === input.project_key)
        : RELEASE_TARGETS;
      return result({
        targets,
        production_policy:
          "Production is staging-first digest promotion with confirm_phrase=YES and matching staging evidence.",
        forbidden_inputs: ["shell", "gcloud_args", "image_digest", "arbitrary_url"]
      });
    }),

    createReleaseTask: async (args) => safeTool("create_release_task", config, async () => {
      const input = parseStrict(schemas.createReleaseTask, args);
      const task = await client.mutate("/api/releases/tasks", {
        ...input,
        actor: ACTOR,
        source_type: "manual"
      });
      return result(taskEvidence(config, task, { task }));
    }),

    requestStagingDeploy: async (args) => safeTool("request_staging_deploy", config, async () => {
      const input = parseStrict(schemas.requestStagingDeploy, args);
      const task = await client.mutate(`/api/releases/tasks/${input.task_id}/deploy-staging`, {
        actor: ACTOR,
        note: input.note || "staging deployment requested by local release MCP"
      });
      return result(taskEvidence(config, task, { task }));
    }),

    requestProductionPromotion: async (args) =>
      safeTool("request_production_promotion", config, () =>
        requestProductionPromotion(client, config, args)
      ),

    getReleaseTaskStatus: async (args) => safeTool("get_release_task_status", config, async () => {
      const input = parseStrict(schemas.getReleaseTaskStatus, args);
      const task = await client.get(`/api/releases/tasks/${input.task_id}`);
      return result(taskEvidence(config, task, { task, next_action: nextAction(task) }));
    }),

    getDeploymentEvents: async (args) => safeTool("get_deployment_events", config, async () => {
      const input = parseStrict(schemas.getDeploymentEvents, args);
      const params = new URLSearchParams({
        after_sequence: String(input.after_sequence),
        limit: String(input.limit)
      });
      const page = await client.get(
        `/api/releases/deployments/${input.deployment_record_id}/events?${params}`
      );
      return result({ deployment_record_id: input.deployment_record_id, ...page });
    })
  };
}

async function requestProductionPromotion(client, config, args) {
  const input = parseStrict(schemas.requestProductionPromotion, args);
  const missing = requiredPromotionFields(input);
  if (input.confirm_phrase !== "YES" || missing.length) {
    return result({
      status: "needs_human_gate",
      message:
        "Production promotion requires confirm_phrase=YES plus matching staging evidence. No deploy request was sent.",
      missing_fields: input.confirm_phrase === "YES" ? missing : ["confirm_phrase=YES", ...missing],
      forbidden_inputs: ["image_digest"]
    });
  }
  const stagingTask = await findMatchingStagingTask(client, input);
  validateStagingEvidence(stagingTask, input);
  const task = await client.mutate(`/api/releases/tasks/${input.task_id}/deploy`, {
    actor: ACTOR,
    confirm_phrase: "YES",
    note: `production promotion via local release MCP from staging deployment ${input.staging_deployment_record_id}`
  });
  return result(taskEvidence(config, task, { task, staging_evidence: stagingTask }));
}

async function findMatchingStagingTask(client, input) {
  const params = new URLSearchParams({
    project_key: input.project_key,
    environment: "staging",
    status: "completed",
    limit: "100",
    offset: "0"
  });
  const page = await client.get(`/api/releases/tasks/query?${params}`);
  return (page.items || []).find(
    (task) => Number(task.deployment_record_id) === Number(input.staging_deployment_record_id)
  );
}

function validateStagingEvidence(task, input) {
  if (!task) throw policyError("STAGING_EVIDENCE_NOT_FOUND", "Matching staging task was not found.");
  if (task.project_key !== input.project_key || task.service_key !== input.service_key) {
    throw policyError("STAGING_EVIDENCE_MISMATCH", "Staging evidence project/service does not match production request.");
  }
  const commit = task.deployment_commit_sha || task.target_commit_sha;
  if (commit !== input.commit_sha) {
    throw policyError("STAGING_COMMIT_MISMATCH", "Staging evidence commit does not match production request.");
  }
  const healthy = ["passed", "healthy", "manual_verified"].includes(task.deployment_health_status);
  if (task.deployment_status !== "succeeded" || !healthy) {
    throw policyError("STAGING_NOT_HEALTHY", "Staging deployment must be succeeded and health passed.");
  }
}

function requiredPromotionFields(input) {
  return ["staging_deployment_record_id", "commit_sha", "project_key", "service_key"].filter(
    (key) => input[key] === undefined || input[key] === null || input[key] === ""
  );
}

function parseStrict(schema, args) {
  return z.object(schema).strict().parse(args || {});
}

function nextAction(task) {
  if (task.status === "completed" && task.deployment_status === "succeeded") return "verify smoke evidence or create production task";
  if (task.status === "deploying" && task.deployment_record_id) return "run local deploy worker, then poll status";
  if (task.status === "failed" || task.deployment_status === "failed") return "record delivery_blocker_bug and retry only this task after fix";
  return "request staging deploy or continue operator review";
}

function policyError(code, message) {
  return new GrowingApiError(400, code, message);
}

async function safeTool(tool, config, fn) {
  try {
    return await fn();
  } catch (error) {
    const payload = normalizeError(error);
    payload.bug_intake_payload = bugIntakePayload({
      tool,
      task: payload.details?.task,
      deploymentRecordId: payload.details?.deployment_record_id,
      summary: payload.message,
      config
    });
    return toolError(payload);
  }
}

function normalizeError(error) {
  if (error instanceof GrowingApiError) return error.toJSON();
  return {
    status: 500,
    code: "MCP_RELEASE_TOOL_ERROR",
    message: error instanceof Error ? error.message : String(error)
  };
}

export function result(data) {
  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
    structuredContent: { data }
  };
}

export function toolError(payload) {
  return {
    isError: true,
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    structuredContent: payload
  };
}
