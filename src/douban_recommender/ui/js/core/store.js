export const UI_STATE_KEY = "cinescope.ui.state";
export const UI_SCHEMA_VERSION = 3;

const CHANNEL_SLUGS = ["movie", "series", "anime-series"];
const RAIL_MODES = new Set(["expanded", "collapsed", "hidden"]);
const SENSITIVE_KEY = /(?:cookie|api[_-]?key|authorization|headers?|token|secret|password)/i;
const EXTERNAL_URL = /^(?:https?:)?\/\//i;

function emptyChannelState() {
  return { sessionId: null, batchIndex: 0, batchIds: [] };
}

export function createEmptyUiState() {
  return {
    schemaVersion: 3,
    activePath: null,
    activeParams: {},
    recommendation: {
      sessionId: null,
      activeChannel: "movie",
      channels: Object.fromEntries(CHANNEL_SLUGS.map((slug) => [slug, emptyChannelState()])),
    },
    scrollByRoute: {},
    candidateTray: { itemIds: [], context: {} },
    commandLens: { draft: "", chips: [] },
    rail: { mode: "expanded" },
  };
}

function browserStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function isSafeText(value, maxLength = 512) {
  return typeof value === "string" && value.length <= maxLength && !EXTERNAL_URL.test(value);
}

function safeText(value, fallback = "", maxLength = 512) {
  return isSafeText(value, maxLength) ? value : fallback;
}

function isSafePath(value) {
  return typeof value === "string" && value.startsWith("/") && value.length <= 512 && !EXTERNAL_URL.test(value);
}

function isSafeKey(key) {
  return typeof key === "string" && /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(key) && !SENSITIVE_KEY.test(key);
}

function sanitizeValue(value, depth = 0) {
  if (depth > 5 || value === null) return null;
  if (typeof value === "string") return isSafeText(value) ? value : null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) {
    return value
      .slice(0, 50)
      .map((entry) => sanitizeValue(entry, depth + 1))
      .filter((entry) => entry !== null);
  }
  if (typeof value !== "object") return null;

  const result = {};
  for (const [key, entry] of Object.entries(value).slice(0, 50)) {
    if (!isSafeKey(key)) continue;
    const sanitized = sanitizeValue(entry, depth + 1);
    if (sanitized !== null) result[key] = sanitized;
  }
  return result;
}

function sanitizeParams(params) {
  if (!params || typeof params !== "object" || Array.isArray(params)) return {};

  const result = {};
  for (const [key, value] of Object.entries(params)) {
    if (!isSafeKey(key)) continue;
    const sanitized = sanitizeValue(value);
    if (sanitized !== null) result[key] = sanitized;
  }
  return result;
}

function sanitizeBatchIds(ids) {
  if (!Array.isArray(ids)) return [];
  return ids.slice(0, 200).filter((value) => isSafeText(value, 256));
}

function sanitizeChannels(channels) {
  const source = channels && typeof channels === "object" ? channels : {};
  return Object.fromEntries(CHANNEL_SLUGS.map((slug) => {
    const channel = source[slug] && typeof source[slug] === "object" ? source[slug] : {};
    const batchIndex = Number.isInteger(channel.batchIndex) && channel.batchIndex >= 0
      ? channel.batchIndex
      : 0;
    return [slug, {
      sessionId: safeText(channel.sessionId, "", 256) || null,
      batchIndex,
      batchIds: sanitizeBatchIds(channel.batchIds),
    }];
  }));
}

function sanitizeScrollByRoute(scrollByRoute) {
  if (!scrollByRoute || typeof scrollByRoute !== "object" || Array.isArray(scrollByRoute)) return {};

  const result = {};
  for (const [path, position] of Object.entries(scrollByRoute).slice(0, 100)) {
    if (!isSafePath(path)) continue;
    if (!Number.isFinite(position) || position < 0) continue;
    result[path] = Math.floor(position);
  }
  return result;
}

function sanitizeChips(chips) {
  if (!Array.isArray(chips)) return [];
  return chips.slice(0, 20).flatMap((chip) => {
    if (!chip || typeof chip !== "object" || Array.isArray(chip)) return [];
    const key = safeText(chip.key, "", 64);
    const label = safeText(chip.label, "", 160);
    const value = sanitizeValue(chip.value);
    if (!key || !label || value === null) return [];
    return [{ key, label, value, removable: Boolean(chip.removable) }];
  });
}

export function normalizeUiState(state = {}) {
  const source = state && typeof state === "object" ? state : {};
  const recommendation = source.recommendation && typeof source.recommendation === "object"
    ? source.recommendation
    : {};
  const candidateTray = source.candidateTray && typeof source.candidateTray === "object"
    ? source.candidateTray
    : {};
  const commandLens = source.commandLens && typeof source.commandLens === "object"
    ? source.commandLens
    : {};
  const rail = source.rail && typeof source.rail === "object" ? source.rail : {};
  const activeChannel = CHANNEL_SLUGS.includes(recommendation.activeChannel)
    ? recommendation.activeChannel
    : "movie";

  return {
    schemaVersion: 3,
    activePath: isSafePath(source.activePath)
      ? source.activePath
      : null,
    activeParams: sanitizeParams(source.activeParams),
    recommendation: {
      sessionId: safeText(recommendation.sessionId, "", 256) || null,
      activeChannel,
      channels: sanitizeChannels(recommendation.channels),
    },
    scrollByRoute: sanitizeScrollByRoute(source.scrollByRoute),
    candidateTray: {
      itemIds: sanitizeBatchIds(candidateTray.itemIds),
      context: sanitizeValue(candidateTray.context) || {},
    },
    commandLens: {
      draft: safeText(commandLens.draft, "", 2000),
      chips: sanitizeChips(commandLens.chips),
    },
    rail: { mode: RAIL_MODES.has(rail.mode) ? rail.mode : "expanded" },
  };
}

export function persistUiState(state, storage = browserStorage()) {
  const persisted = normalizeUiState(state);
  if (!storage) return persisted;

  try {
    storage.setItem(UI_STATE_KEY, JSON.stringify(persisted));
  } catch {
    // Local storage is optional: the active UI remains usable in private modes.
  }
  return persisted;
}

export function restoreUiState(storage = browserStorage()) {
  if (!storage) return createEmptyUiState();

  try {
    const raw = storage.getItem(UI_STATE_KEY);
    if (!raw) return createEmptyUiState();
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.schemaVersion !== UI_SCHEMA_VERSION) return createEmptyUiState();
    return normalizeUiState(parsed);
  } catch {
    return createEmptyUiState();
  }
}

export function saveScroll(routeKey, y = globalThis.window?.scrollY ?? 0) {
  if (typeof routeKey !== "string" || !routeKey.startsWith("/")) return;
  const state = restoreUiState();
  state.scrollByRoute[routeKey] = Number.isFinite(y) && y >= 0 ? Math.floor(y) : 0;
  persistUiState(state);
}

export function createStore(initialState, reducer) {
  if (typeof reducer !== "function") throw new TypeError("createStore requires a reducer");

  let state = initialState;
  const listeners = new Set();

  return {
    getState() {
      return state;
    },
    dispatch(action) {
      const nextState = reducer(state, action);
      if (nextState === undefined) throw new TypeError("Store reducer must return the next state");
      state = nextState;
      listeners.forEach((listener) => listener(state, action));
      return action;
    },
    subscribe(listener) {
      if (typeof listener !== "function") throw new TypeError("Store listener must be a function");
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
