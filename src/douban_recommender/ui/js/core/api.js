export const V2_SCHEMA_VERSION = 2;
export const CHANNEL_KEYS = Object.freeze({
  movie: "电影",
  series: "电视剧",
  "anime-series": "动漫",
});

export const MAX_GET_CACHE_ENTRIES = 128;
const DEFAULT_GET_TTL_MS = 45_000;
const SESSION_CACHE_PREFIX = "cinescope:v2:get:";
export const STABLE_SESSION_ROUTES = Object.freeze([
  /^\/api\/v2\/titles\/(?!search(?:\?|$))[^?]+(?:\?.*)?$/,
  /^\/api\/v2\/titles\/search(?:\?|$)/,
  /^\/api\/v2\/discovery\/similar(?:\?|$)/,
  /^\/api\/v2\/discovery\/multi(?:\?|$)/,
  /^\/api\/v2\/discovery\/latest(?:\?|$)/,
  /^\/api\/v2\/observatory(?:\?|$)/,
  /^\/api\/v2\/universe(?:\?|$)/,
]);

const getCache = new Map();
const getInFlight = new Map();

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

function nowMs() {
  return Date.now();
}

function routeTtl(path, override) {
  if (Number.isFinite(override) && override >= 0) return Math.floor(override);
  if (/^\/api\/v2\/titles\/(?!search(?:\?|$))/.test(path)) return 15 * 60_000;
  if (/^\/api\/v2\/(?:titles\/search|discovery\/(?:similar|multi|latest)|observatory|universe)(?:\?|$)/.test(path)) return 5 * 60_000;
  if (/^\/api\/v2\/(?:catalog|taste|media\/health|diagnostics)(?:\/|\?|$)/.test(path)) return 90_000;
  return DEFAULT_GET_TTL_MS;
}

function isStableSessionRoute(path) {
  return STABLE_SESSION_ROUTES.some((pattern) => pattern.test(path));
}

function sessionKey(path) {
  return `${SESSION_CACHE_PREFIX}${encodeURIComponent(path)}`;
}

function safeSessionStorage() {
  try {
    const storage = globalThis.sessionStorage;
    if (!storage || typeof storage.getItem !== "function" || typeof storage.setItem !== "function") return null;
    return storage;
  } catch {
    return null;
  }
}

function readSessionEntry(path, currentTime = nowMs()) {
  if (!isStableSessionRoute(path)) return null;
  const storage = safeSessionStorage();
  if (!storage) return null;
  const key = sessionKey(path);
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const entry = JSON.parse(raw);
    if (!entry || typeof entry !== "object" || !Number.isFinite(entry.expiresAt) || entry.expiresAt <= currentTime) {
      storage.removeItem?.(key);
      return null;
    }
    return { value: entry.value ?? {}, expiresAt: entry.expiresAt };
  } catch {
    try { storage.removeItem?.(key); } catch { /* storage can be unavailable in privacy mode */ }
    return null;
  }
}

function writeSessionEntry(path, entry) {
  if (!isStableSessionRoute(path)) return;
  const storage = safeSessionStorage();
  if (!storage) return;
  try {
    storage.setItem(sessionKey(path), JSON.stringify(entry));
  } catch {
    // Session persistence is an optional warm tier; memory caching remains available.
  }
}

function touchMemoryEntry(path, entry) {
  getCache.delete(path);
  getCache.set(path, entry);
  while (getCache.size > MAX_GET_CACHE_ENTRIES) {
    const oldest = getCache.keys().next().value;
    if (oldest === undefined) break;
    getCache.delete(oldest);
  }
}

function readMemoryEntry(path, currentTime = nowMs()) {
  const entry = getCache.get(path);
  if (!entry) return null;
  if (!Number.isFinite(entry.expiresAt) || entry.expiresAt <= currentTime) {
    getCache.delete(path);
    return null;
  }
  touchMemoryEntry(path, entry);
  return entry;
}

function abortError() {
  try {
    return new DOMException("The operation was aborted", "AbortError");
  } catch {
    const error = new Error("The operation was aborted");
    error.name = "AbortError";
    return error;
  }
}

function consumeShared(promise, signal) {
  if (!signal) return promise;
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener?.("abort", onAbort);
      callback(value);
    };
    const onAbort = () => finish(reject, abortError());
    signal.addEventListener?.("abort", onAbort, { once: true });
    promise.then(
      (value) => finish(resolve, value),
      (error) => finish(reject, error),
    );
  });
}

function pathMatches(path, matcher) {
  if (!matcher) return true;
  if (typeof matcher === "function") return Boolean(matcher(path));
  if (matcher instanceof RegExp) return matcher.test(path);
  if (typeof matcher === "string") return path === matcher || path.startsWith(matcher);
  if (Array.isArray(matcher)) return matcher.some((entry) => pathMatches(path, entry));
  return false;
}

function removeSessionMatches(matcher) {
  const storage = safeSessionStorage();
  if (!storage) return;
  const keys = [];
  try {
    for (let index = 0; index < Number(storage.length || 0); index += 1) {
      const key = storage.key?.(index);
      if (typeof key === "string" && key.startsWith(SESSION_CACHE_PREFIX)) keys.push(key);
    }
  } catch {
    return;
  }
  for (const key of keys) {
    let path = "";
    try { path = decodeURIComponent(key.slice(SESSION_CACHE_PREFIX.length)); } catch { path = ""; }
    if (!pathMatches(path, matcher)) continue;
    try { storage.removeItem?.(key); } catch { /* optional tier */ }
  }
}

export function invalidateV2GetCache(matcher = null, { includeSession = true } = {}) {
  for (const path of [...getCache.keys()]) {
    if (pathMatches(path, matcher)) getCache.delete(path);
  }
  if (includeSession) removeSessionMatches(matcher);
}

export function clearV2GetCache(options = {}) {
  getCache.clear();
  getInFlight.clear();
  if (options.includeSession !== false) removeSessionMatches(null);
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

export function getV2(path, { signal, force = false, ttlMs } = {}) {
  const target = normaliseV2Path(path);
  const currentTime = nowMs();
  if (!force) {
    const memoryEntry = readMemoryEntry(target, currentTime);
    if (memoryEntry) return consumeShared(Promise.resolve(memoryEntry.value), signal);
    const sessionEntry = readSessionEntry(target, currentTime);
    if (sessionEntry) {
      touchMemoryEntry(target, sessionEntry);
      return consumeShared(Promise.resolve(sessionEntry.value), signal);
    }
    const shared = getInFlight.get(target);
    if (shared) return consumeShared(shared, signal);
  }

  const promise = request(target, { method: "GET" }).then((value) => {
    const entry = { value, expiresAt: nowMs() + routeTtl(target, ttlMs) };
    touchMemoryEntry(target, entry);
    writeSessionEntry(target, entry);
    return value;
  }).finally(() => {
    if (getInFlight.get(target) === promise) getInFlight.delete(target);
  });
  getInFlight.set(target, promise);
  return consumeShared(promise, signal);
}

export async function postV2(path, payload = {}, { signal } = {}) {
  const body = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const result = await request(normaliseV2Path(path), {
    method: "POST",
    body: { ...body, schema_version: V2_SCHEMA_VERSION },
    signal,
  });
  invalidateV2GetCache();
  return result;
}

export async function putV2(path, payload = {}, { signal } = {}) {
  const body = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const result = await request(normaliseV2Path(path), {
    method: "PUT",
    body: { ...body, schema_version: V2_SCHEMA_VERSION },
    signal,
  });
  invalidateV2GetCache();
  return result;
}

export async function deleteV2(path, { signal } = {}) {
  const result = await request(normaliseV2Path(path), { method: "DELETE", signal });
  invalidateV2GetCache();
  return result;
}

export function backendChannel(routeSlug) {
  const channel = CHANNEL_KEYS[routeSlug];
  if (!channel) throw new TypeError(`Unsupported channel: ${routeSlug}`);
  return channel;
}
