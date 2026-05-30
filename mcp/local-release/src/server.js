import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { GrowingReleaseClient } from "./client.js";
import { loadConfig } from "./config.js";
import { createToolHandlers, schemas } from "./tools.js";

export function createServer(client = new GrowingReleaseClient(loadConfig()), config = loadConfig()) {
  const server = new McpServer({
    name: "growing-release",
    version: "0.1.0"
  });
  const handlers = createToolHandlers(client, config);

  server.registerTool(
    "list_release_targets",
    {
      title: "List Growing release targets",
      description: "Return the allowlisted release project/service matrix and production policy summary.",
      inputSchema: schemas.listReleaseTargets
    },
    handlers.listReleaseTargets
  );
  server.registerTool(
    "create_release_task",
    {
      title: "Create release task",
      description: "Create a durable Growing ReleaseTask. This does not deploy.",
      inputSchema: schemas.createReleaseTask
    },
    handlers.createReleaseTask
  );
  server.registerTool(
    "request_staging_deploy",
    {
      title: "Request staging deploy",
      description: "Create a local_deploy_runner DeploymentRecord for an existing staging task. Does not run shell.",
      inputSchema: schemas.requestStagingDeploy
    },
    handlers.requestStagingDeploy
  );
  server.registerTool(
    "request_production_promotion",
    {
      title: "Request production promotion",
      description: "Request production digest promotion only after YES and matching staging evidence.",
      inputSchema: schemas.requestProductionPromotion
    },
    handlers.requestProductionPromotion
  );
  server.registerTool(
    "get_release_task_status",
    {
      title: "Get release task status",
      description: "Read task/deployment status, manifest summary, health, and next action.",
      inputSchema: schemas.getReleaseTaskStatus
    },
    handlers.getReleaseTaskStatus
  );
  server.registerTool(
    "get_deployment_events",
    {
      title: "Get deployment events",
      description: "Read append-only local deploy runner events by cursor.",
      inputSchema: schemas.getDeploymentEvents
    },
    handlers.getDeploymentEvents
  );

  return server;
}

export async function runStdioServer() {
  const config = loadConfig();
  const server = createServer(new GrowingReleaseClient(config), config);
  await server.connect(new StdioServerTransport());
}
