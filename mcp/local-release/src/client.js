export class GrowingApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.name = "GrowingApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  toJSON() {
    return {
      status: this.status,
      code: this.code,
      message: this.message,
      details: this.details
    };
  }
}

export class GrowingReleaseClient {
  constructor(config, fetchImpl = globalThis.fetch) {
    this.config = config;
    this.fetch = fetchImpl;
  }

  async get(path) {
    return this.request("GET", path, undefined, { requireToken: false });
  }

  async mutate(path, body) {
    this.requireDeployToken();
    return this.request("POST", path, body, { requireToken: true });
  }

  requireDeployToken() {
    if (!this.config.deployToken) {
      throw new GrowingApiError(
        403,
        "DEPLOY_TOKEN_MISSING",
        "OPS_AGENT_DEPLOY_API_TOKEN is required for agent release mutations."
      );
    }
  }

  async request(method, path, body, options = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (options.requireToken) {
      headers["X-Growing-Agent-Deploy-Token"] = this.config.deployToken;
    }
    const response = await this.fetch(`${this.config.opsBaseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const payload = await parseJson(response);
    if (!response.ok) {
      throw new GrowingApiError(
        response.status,
        "GROWING_API_ERROR",
        errorMessage(payload, response.statusText),
        payload
      );
    }
    return payload;
  }
}

async function parseJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function errorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (typeof payload?.message === "string") return payload.message;
  return fallback || "Growing API request failed.";
}
