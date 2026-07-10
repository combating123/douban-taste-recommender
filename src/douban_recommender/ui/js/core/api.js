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

async function request(path, { method = "GET", body, headers = {} } = {}) {
  const options = { method, headers: { ...headers } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.status === 204 ? {} : response.json();
}

export function postV2(path, payload = {}) {
  const body = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  return request(normaliseV2Path(path), {
    method: "POST",
    body: { ...body, schema_version: V2_SCHEMA_VERSION },
  });
}

export function backendChannel(routeSlug) {
  const channel = CHANNEL_KEYS[routeSlug];
  if (!channel) throw new TypeError(`Unsupported channel: ${routeSlug}`);
  return channel;
}
