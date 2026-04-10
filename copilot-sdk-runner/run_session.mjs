import fs from "node:fs/promises";
import path from "node:path";

import { CopilotClient } from "@github/copilot-sdk";

const autoUserInputEnabled = ["1", "true", "yes", "on"].includes(
  String(process.env.COPILOT_SDK_AUTO_USER_INPUT ?? "true").toLowerCase(),
);
const autoUserInputText =
  process.env.COPILOT_SDK_AUTO_USER_INPUT_TEXT ||
  "Proceed automatically using best effort. Do not wait for additional user input.";
const interestingEvents = new Set([
  "session.created",
  "session.idle",
  "session.resume",
  "assistant.message",
  "assistant.message_delta",
  "assistant.usage",
  "permission.requested",
  "permission.completed",
  "user_input.requested",
  "user_input.completed",
  "elicitation.requested",
  "elicitation.completed",
  "subagent.selected",
  "subagent.started",
  "subagent.completed",
  "subagent.failed",
  "tool.user_requested",
  "tool.execution_start",
  "tool.execution_complete",
  "session.error",
  "session.info",
]);

function nowIso() {
  return new Date().toISOString();
}

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

async function ensureParent(filePath) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

async function writeJson(filePath, value) {
  await ensureParent(filePath);
  await fs.writeFile(filePath, JSON.stringify(value, null, 2), "utf8");
}

async function readJson(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function appendJsonl(filePath, value) {
  await ensureParent(filePath);
  await fs.appendFile(filePath, `${JSON.stringify(value)}\n`, "utf8");
}

async function readJsonl(filePath) {
  try {
    const raw = await fs.readFile(filePath, "utf8");
    return raw
      .split(/\r?\n/)
      .filter((line) => line.trim())
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
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
    case "session.resume":
      return event.data?.sessionId ?? "";
    case "permission.requested":
      return event.data?.permissionRequest?.kind ?? event.data?.requestId ?? "";
    case "permission.completed":
      return event.data?.result?.kind ?? event.data?.requestId ?? "";
    case "user_input.requested":
      return event.data?.question ?? event.data?.requestId ?? "";
    case "user_input.completed":
      return event.data?.requestId ?? "";
    case "elicitation.requested":
      return event.data?.message ?? event.data?.requestId ?? "";
    case "elicitation.completed":
      return event.data?.action ?? event.data?.requestId ?? "";
    case "tool.user_requested":
      return event.data?.toolName ?? "";
    case "tool.execution_start":
      return event.data?.toolCallId ?? "";
    case "tool.execution_complete":
      return event.data?.toolCallId ?? "";
    default:
      return "";
  }
}

function normalizeEvent(event, seq) {
  return {
    seq,
    type: event.type,
    detail: eventDetail(event),
    timestamp: event.timestamp ?? nowIso(),
  };
}

function createCommonSessionConfig(input, { includeModel }) {
  const config = {
    streaming: true,
    customAgents: input.customAgents,
    onPermissionRequest: async () => ({ kind: "approved" }),
    onElicitationRequest: async () => ({ action: "cancel" }),
    hooks: {
      onPreToolUse: async () => ({ permissionDecision: "allow" }),
    },
  };

  if (autoUserInputEnabled) {
    config.onUserInputRequest = async (request) => ({
      answer: request.choices?.[0] ?? autoUserInputText,
      wasFreeform: !request.choices?.length,
    });
  }

  if (includeModel) {
    config.sessionId = input.sessionId;
    config.model = input.model;
    if (input.preferredAgent) {
      config.agent = input.preferredAgent;
    }
  }

  return config;
}

function createClient(input) {
  const githubToken =
    process.env.COPILOT_GITHUB_TOKEN ||
    process.env.GH_TOKEN ||
    process.env.COPILOT_OAUTH_TOKEN ||
    process.env.GITHUB_TOKEN ||
    undefined;

  return new CopilotClient({
    cwd: input.cwd,
    logLevel: input.logLevel ?? "error",
    ...(githubToken
      ? { githubToken, useLoggedInUser: false }
      : { useLoggedInUser: true }),
  });
}

async function getExistingFinalResponse(session, alreadyIdle = false) {
  const messages = await session.getMessages();
  let finalUserMessageIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].type === "user.message") {
      finalUserMessageIndex = index;
      break;
    }
  }

  const currentTurnMessages =
    finalUserMessageIndex < 0 ? messages : messages.slice(finalUserMessageIndex);

  const currentTurnError = currentTurnMessages.find((message) => message.type === "session.error");
  if (currentTurnError) {
    const error = new Error(currentTurnError.data?.message ?? "session error");
    error.stack = currentTurnError.data?.stack;
    throw error;
  }

  const sessionIdleMessageIndex = alreadyIdle
    ? currentTurnMessages.length
    : currentTurnMessages.findIndex((message) => message.type === "session.idle");
  if (sessionIdleMessageIndex !== -1) {
    for (let index = sessionIdleMessageIndex - 1; index >= 0; index -= 1) {
      if (currentTurnMessages[index].type === "assistant.message") {
        return currentTurnMessages[index];
      }
    }
  }

  return undefined;
}

function createFutureFinalResponse(session, timeoutMs) {
  let unsubscribe = () => {};
  let timeoutId;

  const cleanup = () => {
    unsubscribe();
    unsubscribe = () => {};
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
      timeoutId = undefined;
    }
  };

  const promise = new Promise((resolve, reject) => {
    let finalAssistantMessage;
    unsubscribe = session.on((event) => {
      if (event.type === "assistant.message") {
        finalAssistantMessage = event;
      } else if (event.type === "session.idle") {
        cleanup();
        resolve(finalAssistantMessage);
      } else if (event.type === "session.error") {
        const error = new Error(event.data?.message ?? "session error");
        error.stack = event.data?.stack;
        cleanup();
        reject(error);
      }
    });

    if (typeof timeoutMs === "number" && timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        cleanup();
        reject(new Error(`Timeout after ${timeoutMs}ms waiting for session.idle`));
      }, timeoutMs);
    }
  });

  return { promise, cleanup };
}

async function waitForFinalAssistantMessage(session, { sendPrompt, timeoutMs, alreadyIdle = false } = {}) {
  const future = createFutureFinalResponse(session, timeoutMs);
  try {
    if (typeof sendPrompt === "string") {
      await session.send({ prompt: sendPrompt });
    }

    const existing = await getExistingFinalResponse(session, alreadyIdle);
    if (existing) {
      return existing;
    }
    if (alreadyIdle) {
      return undefined;
    }
    return await future.promise;
  } finally {
    future.cleanup();
  }
}

function createRecorder(input) {
  const outputDir = input.outputDir ?? input.cwd ?? process.cwd();
  const statePath = input.statePath ?? path.join(outputDir, "copilot-session-state.json");
  const eventsPath = input.eventsPath ?? path.join(outputDir, "copilot-session-events.jsonl");
  const outputPath = path.join(outputDir, "output.md");
  const metadataPath = path.join(outputDir, "metadata.json");
  const runtimeEventsPath = path.join(outputDir, "runtime-events.json");
  const startedAtMs = Date.now();

  let state = {
    action: input.action,
    status: "starting",
    sessionId: input.sessionId ?? null,
    model: input.model ?? null,
    selectedAgent: input.preferredAgent ?? null,
    tokensUsed: 0,
    startedAt: nowIso(),
    heartbeatAt: nowIso(),
    updatedAt: nowIso(),
    lastSeq: 0,
  };
  let seq = 0;
  let writeChain = Promise.resolve();

  const queue = (task) => {
    writeChain = writeChain.catch(() => {}).then(task);
    return writeChain;
  };

  const writeState = async (patch = {}) => {
    state = { ...state, ...patch, updatedAt: nowIso() };
    await writeJson(statePath, state);
  };

  return {
    async init() {
      const existing = await readJson(statePath);
      if (existing && typeof existing === "object") {
        state = {
          ...existing,
          ...state,
          startedAt: existing.startedAt ?? state.startedAt,
          selectedAgent: existing.selectedAgent ?? state.selectedAgent,
          tokensUsed: Number(existing.tokensUsed ?? state.tokensUsed ?? 0),
          lastSeq: Number(existing.lastSeq ?? state.lastSeq ?? 0),
        };
        seq = Number(existing.lastSeq ?? 0);
      }
      await writeState({ status: existing?.status === "running" ? "running" : "starting" });
    },
    recordSyntheticEvent(type, detail = "") {
      return queue(async () => {
        const normalized = { seq: seq + 1, type, detail, timestamp: nowIso() };
        seq += 1;
        await appendJsonl(eventsPath, normalized);
        await writeState({
          lastSeq: seq,
          lastEventType: normalized.type,
          heartbeatAt: nowIso(),
        });
      });
    },
    recordEvent(event) {
      if (!interestingEvents.has(event.type)) {
        return;
      }

      queue(async () => {
        const normalized = normalizeEvent(event, seq + 1);
        seq += 1;
        const patch = {
          lastSeq: seq,
          lastEventType: normalized.type,
          heartbeatAt: nowIso(),
        };
        if (event.type === "subagent.selected") {
          patch.selectedAgent = event.data?.agentName ?? state.selectedAgent ?? null;
        }
        if (event.type === "assistant.usage") {
          patch.tokensUsed = event.data?.totalTokens ?? state.tokensUsed ?? 0;
        }
        if (event.type === "session.created" || event.type === "session.resume") {
          patch.sessionId = event.data?.sessionId ?? state.sessionId ?? null;
        }

        await appendJsonl(eventsPath, normalized);
        await writeState(patch);
      });
    },
    heartbeat(extra = {}) {
      return queue(async () => {
        await writeState({ heartbeatAt: nowIso(), ...extra });
      });
    },
    async finalizeSuccess({ sessionId, selectedAgent, tokensUsed, model, content }) {
      await queue(async () => {});
      const executionTimeMs = Date.now() - startedAtMs;
      await fs.mkdir(outputDir, { recursive: true });
      await fs.writeFile(outputPath, content ?? "", "utf8");
      await writeJson(runtimeEventsPath, await readJsonl(eventsPath));
      await writeJson(metadataPath, {
        status: "completed",
        sessionId,
        selectedAgent,
        tokensUsed,
        model,
        executionTimeMs,
        outputPath,
      });
      await writeState({
        status: "completed",
        finishedAt: nowIso(),
        heartbeatAt: nowIso(),
        sessionId,
        selectedAgent,
        tokensUsed,
        model,
        executionTimeMs,
        error: null,
      });
    },
    async finalizeFailure({ sessionId, selectedAgent, tokensUsed, model, error, content }) {
      await queue(async () => {});
      const executionTimeMs = Date.now() - startedAtMs;
      await fs.mkdir(outputDir, { recursive: true });
      await fs.writeFile(outputPath, content ?? "", "utf8");
      await writeJson(runtimeEventsPath, await readJsonl(eventsPath));
      await writeJson(metadataPath, {
        status: "failed",
        sessionId,
        selectedAgent,
        tokensUsed,
        model,
        executionTimeMs,
        error,
        outputPath,
      });
      await writeState({
        status: "failed",
        finishedAt: nowIso(),
        heartbeatAt: nowIso(),
        sessionId,
        selectedAgent,
        tokensUsed,
        model,
        executionTimeMs,
        error,
      });
    },
  };
}

async function runOneShot(client, input) {
  let selectedAgent = input.preferredAgent ?? null;
  let content = "";
  let tokensUsed = 0;
  const events = [];

  const session = await client.createSession(createCommonSessionConfig(input, { includeModel: true }));
  const unsubscribe = session.on((event) => {
    if (event.type === "assistant.message_delta") {
      content += event.data.deltaContent ?? "";
    }
    if (event.type === "subagent.selected") {
      selectedAgent = event.data.agentName;
    }
    if (event.type === "assistant.usage") {
      tokensUsed = event.data?.totalTokens ?? tokensUsed ?? 0;
    }
    if (interestingEvents.has(event.type)) {
      events.push({
        type: event.type,
        detail: eventDetail(event),
        timestamp: event.timestamp,
      });
    }
  });

  try {
    const response = await session.sendAndWait(
      { prompt: input.prompt },
      typeof input.timeoutMs === "number" && input.timeoutMs > 0 ? input.timeoutMs : undefined,
    );
    return {
      success: true,
      sessionId: input.sessionId,
      selectedAgent,
      tokensUsed,
      content: response?.data?.content ?? content,
      events,
    };
  } finally {
    unsubscribe?.();
    if (typeof session.disconnect === "function") {
      await session.disconnect().catch(() => {});
    }
  }
}

async function runDetachedWorker(client, input) {
  const recorder = createRecorder(input);
  await recorder.init();

  let session;
  let selectedAgent = input.preferredAgent ?? null;
  let content = "";
  let tokensUsed = 0;
  let heartbeatTimer;
  let liveUnsubscribe = () => {};

  try {
    if (input.action === "resume") {
      session = await client.resumeSession(
        input.sessionId,
        createCommonSessionConfig(input, { includeModel: false }),
      );
      await recorder.recordSyntheticEvent("session.resume", input.sessionId);
    } else {
      session = await client.createSession(createCommonSessionConfig(input, { includeModel: true }));
      await recorder.recordSyntheticEvent("session.created", session.sessionId);
    }

    liveUnsubscribe = session.on((event) => {
      if (event.type === "assistant.message_delta") {
        content += event.data.deltaContent ?? "";
      }
      if (event.type === "assistant.message") {
        content = event.data?.content ?? content;
      }
      if (event.type === "subagent.selected") {
        selectedAgent = event.data.agentName;
      }
      if (event.type === "assistant.usage") {
        tokensUsed = event.data?.totalTokens ?? tokensUsed ?? 0;
      }
      recorder.recordEvent(event);
    });

    await recorder.heartbeat({
      status: "running",
      sessionId: session.sessionId,
      model: input.model ?? null,
      selectedAgent,
      tokensUsed,
    });
    heartbeatTimer = setInterval(() => {
      recorder.heartbeat({
        status: "running",
        sessionId: session.sessionId,
        selectedAgent,
        tokensUsed,
      });
    }, 5000);
    heartbeatTimer.unref?.();

    const finalAssistantMessage = await waitForFinalAssistantMessage(session, {
      sendPrompt: input.prompt || undefined,
      timeoutMs: typeof input.timeoutMs === "number" && input.timeoutMs > 0 ? input.timeoutMs : undefined,
      alreadyIdle: Boolean(input.assumeAlreadyIdle),
    });

    const finalContent = finalAssistantMessage?.data?.content ?? content;
    await recorder.finalizeSuccess({
      sessionId: session.sessionId,
      selectedAgent,
      tokensUsed,
      model: input.model ?? null,
      content: finalContent,
    });
  } catch (error) {
    await recorder.finalizeFailure({
      sessionId: input.sessionId,
      selectedAgent,
      tokensUsed,
      model: input.model ?? null,
      error: error instanceof Error ? error.message : String(error),
      content,
    });
    throw error;
  } finally {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
    }
    liveUnsubscribe?.();
    if (session && typeof session.disconnect === "function") {
      await session.disconnect().catch(() => {});
    }
  }
}

const raw = await readStdin();
const input = JSON.parse(raw || "{}");
const client = createClient(input);

try {
  if (input.action === "start" || input.action === "resume") {
    await runDetachedWorker(client, input);
  } else {
    process.stdout.write(JSON.stringify(await runOneShot(client, input)));
  }
  if (typeof client.stop === "function") {
    await client.stop();
  }
} catch (error) {
  if (input.action === "start" || input.action === "resume") {
    if (typeof client.stop === "function") {
      try {
        await client.stop();
      } catch {
        // ignore cleanup errors
      }
    }
    process.exit(1);
  }

  process.stdout.write(
    JSON.stringify({
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  if (typeof client.stop === "function") {
    try {
      await client.stop();
    } catch {
      // ignore cleanup errors
    }
  }
  process.exit(1);
}