import assert from "node:assert/strict";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [new URL("../src/index.js", import.meta.url).pathname],
  env: {
    ...process.env,
    OPS_AGENT_DEPLOY_API_TOKEN: process.env.OPS_AGENT_DEPLOY_API_TOKEN || "smoke-token"
  }
});

const client = new Client({ name: "growing-release-smoke", version: "0.1.0" });
await client.connect(transport);
const listed = await client.listTools();
const names = listed.tools.map((tool) => tool.name).sort();
assert.deepEqual(names, [
  "create_release_task",
  "get_deployment_events",
  "get_release_task_status",
  "list_release_targets",
  "request_production_promotion",
  "request_staging_deploy"
]);
await client.close();
console.log(JSON.stringify({ tools: names }, null, 2));
