import { CopilotClient } from "@github/copilot-sdk";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function eventDetail(event) {
  switch (event.type) {
    case "subagent.selected":
      return event.data.tools
        ? `${event.data.agentName} tools=${event.data.tools.join(",")}`
        : event.data.agentName;
    case "subagent.started":
      return `${event.data.agentName} ${event.data.agentDescription ?? ""}`.trim();
    case "subagent.completed":
      return event.data.agentName;
    case "subagent.failed":
      return `${event.data.agentName}: ${event.data.error ?? "failed"}`;
    case "assistant.message":
      return (event.data.content ?? "").slice(0, 400);
    case "assistant.message_delta":
      return (event.data.deltaContent ?? "").slice(0, 200);
    case "session.created":
      return event.data?.sessionId ?? "";
    case "tool.user_requested":
      return event.data?.toolName ?? "";
    case "tool.execution_complete":
      return event.data?.toolCallId ?? "";
    default:
      return "";
  }
}

function normalizeEvent(event) {
  return {
    type: event.type,
    detail: eventDetail(event),
    timestamp: event.timestamp,
  };
}

const raw = await readStdin();
const input = JSON.parse(raw || "{}");
const githubToken =
  process.env.COPILOT_GITHUB_TOKEN ||
  process.env.GH_TOKEN ||
  process.env.COPILOT_OAUTH_TOKEN ||
  process.env.GITHUB_TOKEN ||
  undefined;
const client = new CopilotClient({
  cwd: input.cwd,
  logLevel: input.logLevel ?? "error",
  ...(githubToken
    ? { githubToken, useLoggedInUser: false }
    : { useLoggedInUser: true }),
});

let selectedAgent = input.preferredAgent ?? null;
let content = "";
let tokensUsed = 0;
const events = [];

try {
  const session = await client.createSession({
    sessionId: input.sessionId,
    model: input.model,
    streaming: true,
    customAgents: input.customAgents,
    ...(input.preferredAgent ? { agent: input.preferredAgent } : {}),
    onPermissionRequest: async () => ({ kind: "approved" }),
  });

  const unsubscribe = session.on((event) => {
    if (event.type === "assistant.message_delta") {
      content += event.data.deltaContent ?? "";
    }
    if (event.type === "subagent.selected") {
      selectedAgent = event.data.agentName;
    }
    if (event.type === "assistant.usage") {
      const usage = event.data ?? {};
      tokensUsed = usage.totalTokens ?? tokensUsed ?? 0;
    }

    const interesting = new Set([
      "session.created",
      "session.idle",
      "assistant.message",
      "assistant.message_delta",
      "assistant.usage",
      "subagent.selected",
      "subagent.started",
      "subagent.completed",
      "subagent.failed",
      "tool.user_requested",
      "tool.execution_complete",
      "session.error",
      "session.info",
    ]);

    if (interesting.has(event.type)) {
      events.push(normalizeEvent(event));
    }
  });

  const response = await session.sendAndWait(
    { prompt: input.prompt },
    input.timeoutMs ?? 300_000,
  );
  unsubscribe?.();

  const finalContent = response?.data?.content ?? content;
  process.stdout.write(JSON.stringify({
    success: true,
    sessionId: input.sessionId,
    selectedAgent,
    tokensUsed,
    content: finalContent,
    events,
  }));
  if (typeof client.stop === "function") {
    await client.stop();
  }
} catch (error) {
  process.stdout.write(JSON.stringify({
    success: false,
    error: error instanceof Error ? error.message : String(error),
    selectedAgent,
    events,
  }));
  if (typeof client.stop === "function") {
    try {
      await client.stop();
    } catch {
      // ignore stop errors during failure cleanup
    }
  }
  process.exit(1);
}