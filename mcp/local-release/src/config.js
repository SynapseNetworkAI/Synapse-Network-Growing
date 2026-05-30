import fs from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");

export function loadConfig(env = process.env) {
  const dotenv = readDotenv(path.join(REPO_ROOT, ".env"));
  const get = (key, fallback = "") => firstNonEmpty(env[key], dotenv[key], fallback);
  return {
    repoRoot: REPO_ROOT,
    opsBaseUrl: trimTrailingSlash(get("OPS_BASE_URL", "http://127.0.0.1:9600")),
    dashboardBaseUrl: trimTrailingSlash(get("OPS_DASHBOARD_BASE_URL", "http://localhost:9700")),
    deployToken: get("OPS_AGENT_DEPLOY_API_TOKEN", "")
  };
}

export function readDotenv(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const values = {};
  for (const line of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const equals = trimmed.indexOf("=");
    if (equals <= 0) continue;
    const key = trimmed.slice(0, equals).trim();
    values[key] = stripQuotes(trimmed.slice(equals + 1).trim());
  }
  return values;
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (String(value ?? "").trim()) return String(value).trim();
  }
  return "";
}

function stripQuotes(value) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

function trimTrailingSlash(value) {
  return String(value || "").replace(/\/+$/, "");
}
