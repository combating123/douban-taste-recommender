export const V2_SCHEMA_VERSION = 2;
export const CHANNEL_KEYS = Object.freeze({
  movie: "电影",
  series: "电视剧",
  "anime-series": "动漫",
});

function normaliseV2Path(path) {
  const origin = globalThis.location?.origin;
  const candidate = typeof path === "string" ? path.trim() : "";
  if (!origin || origin === "null" || !candidate || candidate.startsWith("//")) {
    throw new TypeError("V2 requests require a same-origin /api/v2/ path");
  }

  let target;
  try {
    target = new URL(candidate, origin);
  } catch {
    throw new TypeError("V2 requests require a valid same-origin URL");
  }
  if (target.origin !== origin || !target.pathname.startsWith("/api/v2/")) {
    throw new TypeError("V2 requests require a same-origin /api/v2/ path");
  }
  return `${target.pathname}${target.search}`;
}

export class ApiError extends Error {
  constructor(status, message, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = Number(status) || 0;
    this.publicMessage = message;
    this.payload = payload;
  }
}

async function request(path, { method = "GET", body, headers = {}, signal } = {}) {
  const options = { method, headers: { ...headers } };
  if (signal) options.signal = signal;
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  if (response.status === 204) {
    if (!response.ok) throw new ApiError(response.status, `Request failed: ${response.status}`);
    return {};
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message = typeof payload?.error === "string" && payload.error.trim()
      ? payload.error.trim()
      : `Request failed: ${response.status}`;
    throw new ApiError(response.status, message, payload);
  }
  return payload ?? {};
}

export function getV2(path, { signal } = {}) {
  return request(normaliseV2Path(path), { method: "GET", signal });
}

export function postV2(path, payload = {}, { signal } = {}) {
  const body = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  return request(normaliseV2Path(path), {
    method: "POST",
    body: { ...body, schema_version: V2_SCHEMA_VERSION },
    signal,
  });
}

export function backendChannel(routeSlug) {
  const channel = CHANNEL_KEYS[routeSlug];
  if (!channel) throw new TypeError(`Unsupported channel: ${routeSlug}`);
  return channel;
}
