export const UI_STATE_KEY = "cinescope.ui.state";
export const UI_SCHEMA_VERSION = 3;

const CHANNEL_SLUGS = ["movie", "series", "anime-series"];
const RAIL_MODES = new Set(["expanded", "collapsed", "hidden"]);
const LIBRARY_STATES = new Set(["all", "watched", "wish", "wanted", "candidate", "rated", "collect", "ready", "hidden", "archived"]);
const SENSITIVE_KEY = /(?:cookie|api[_-]?key|authorization|headers?|token|secret|password)/i;
const EXTERNAL_URL = /^(?:https?:)?\/\//i;
const EXTERNAL_URL_IN_PATH = /(?:https?:\/\/|\/\/)/i;
const SENSITIVE_ASSIGNMENT = /\b(?:auth(?:orization)?|cookie|session(?:id)?|sid|token|api[\s_-]?key|apikey|jwt|private[\s_-]?key|password|secret|credential|subscription|access[\s_-]?token|refresh[\s_-]?token)\b\s*[:=]\s*[^\s,;]+/i;
const DOUBAN_COOKIE_ASSIGNMENT = /(?:^|[\s;,])(?:bid|dbcl2|ck|push_noty_num|push_doumail_num)\s*[:=]/i;
const BEARER_SECRET = /\bbearer\s+[A-Za-z0-9._~+/=-]{6,}/i;
const PREFIXED_SECRET = /\bsk-[A-Za-z0-9_-]{8,}\b/i;
const SAFE_JOB_ID = /^[A-Za-z0-9_-]{1,128}$/;
const SAFE_CANDIDATE_ID = /^[A-Za-z0-9:._~-]{1,256}$/;
const MAX_CANDIDATE_TRAY_ITEMS = 24;

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
    library: { state: "all" },
    sync: {
      profile: "",
      options: { maxPages: 250, includeWish: true, includeDo: false, expectedCollect: null, expectedWish: null },
      knownJobIds: [],
    },
  };
}

function browserStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function containsSensitiveText(value) {
  return typeof value === "string" && (
    SENSITIVE_ASSIGNMENT.test(value)
    || DOUBAN_COOKIE_ASSIGNMENT.test(value)
    || BEARER_SECRET.test(value)
    || PREFIXED_SECRET.test(value)
  );
}

function isSafeText(value, maxLength = 512) {
  return typeof value === "string"
    && value.length <= maxLength
    && !EXTERNAL_URL.test(value)
    && !containsSensitiveText(value);
}

export function sanitizeNonSensitiveText(value, fallback = "", maxLength = 512) {
  return isSafeText(value, maxLength) ? value : fallback;
}

const safeText = sanitizeNonSensitiveText;

function isSafePath(value) {
  return typeof value === "string"
    && value.startsWith("/")
    && value.length <= 512
    && !EXTERNAL_URL_IN_PATH.test(value);
}

function isSafeKey(key) {
  return typeof key === "string" && /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(key) && !SENSITIVE_KEY.test(key);
}

export function sanitizeNonSensitiveValue(value, depth = 0) {
  if (depth > 5 || value === null) return null;
  if (typeof value === "string") return isSafeText(value) ? value : null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) {
    return value
      .slice(0, 50)
      .map((entry) => sanitizeNonSensitiveValue(entry, depth + 1))
      .filter((entry) => entry !== null);
  }
  if (typeof value !== "object") return null;

  const result = {};
  for (const [key, entry] of Object.entries(value).slice(0, 50)) {
    if (!isSafeKey(key)) continue;
    const sanitized = sanitizeNonSensitiveValue(entry, depth + 1);
    if (sanitized !== null) result[key] = sanitized;
  }
  return result;
}

function sanitizeParams(params) {
  if (!params || typeof params !== "object" || Array.isArray(params)) return {};

  const result = {};
  for (const [key, value] of Object.entries(params)) {
    if (!isSafeKey(key)) continue;
    const sanitized = sanitizeNonSensitiveValue(value);
    if (sanitized !== null) result[key] = sanitized;
  }
  return result;
}

function sanitizeBatchIds(ids) {
  if (!Array.isArray(ids)) return [];
  return ids.slice(0, 200).filter((value) => isSafeText(value, 256));
}

function sanitizeCandidateCounts(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    target_size: optionalCount(source.target_size),
    returned_size: optionalCount(source.returned_size),
  };
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
      candidate_counts: sanitizeCandidateCounts(channel.candidate_counts),
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

export function sanitizeCommandLensChips(chips) {
  if (!Array.isArray(chips)) return [];
  return chips.slice(0, 20).flatMap((chip) => {
    if (!chip || typeof chip !== "object" || Array.isArray(chip)) return [];
    const key = safeText(chip.key, "", 64);
    const label = safeText(chip.label, "", 160);
    const value = sanitizeNonSensitiveValue(chip.value);
    if (!key || !label || value === null) return [];
    return [{ key, label, value, removable: Boolean(chip.removable) }];
  });
}

function sanitizeCandidateIds(ids) {
  if (!Array.isArray(ids)) return [];
  return [...new Set(ids.filter((value) => typeof value === "string" && SAFE_CANDIDATE_ID.test(value)))]
    .slice(-MAX_CANDIDATE_TRAY_ITEMS);
}

function sanitizeLibraryState(value) {
  return LIBRARY_STATES.has(value) ? value : "all";
}

function sanitizeSyncProfile(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (/^[A-Za-z0-9._~-]{1,128}$/.test(text)) return text;
  try {
    const url = new URL(text);
    if (url.protocol !== "https:" || !/(^|\.)douban\.com$/i.test(url.hostname)) return "";
    const match = url.pathname.match(/^\/people\/([A-Za-z0-9._~-]{1,128})(?:\/|$)/);
    return match ? `https://www.douban.com/people/${match[1]}/` : "";
  } catch {
    return "";
  }
}

function optionalCount(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 && number <= 1000000 ? number : null;
}

function sanitizeSyncOptions(options) {
  const source = options && typeof options === "object" && !Array.isArray(options) ? options : {};
  const rawMaxPages = Number(source.maxPages);
  return {
    maxPages: Number.isInteger(rawMaxPages) ? Math.max(1, Math.min(250, rawMaxPages)) : 250,
    includeWish: source.includeWish !== false,
    includeDo: Boolean(source.includeDo),
    expectedCollect: optionalCount(source.expectedCollect),
    expectedWish: optionalCount(source.expectedWish),
  };
}

function sanitizeKnownJobIds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((jobId) => typeof jobId === "string" && SAFE_JOB_ID.test(jobId)))].slice(-50);
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
  const library = source.library && typeof source.library === "object" ? source.library : {};
  const sync = source.sync && typeof source.sync === "object" ? source.sync : {};
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
      itemIds: sanitizeCandidateIds(candidateTray.itemIds),
      context: sanitizeNonSensitiveValue(candidateTray.context) || {},
    },
    commandLens: {
      draft: safeText(commandLens.draft, "", 2000),
      chips: sanitizeCommandLensChips(commandLens.chips),
    },
    rail: { mode: RAIL_MODES.has(rail.mode) ? rail.mode : "expanded" },
    library: { state: sanitizeLibraryState(library.state) },
    sync: {
      profile: sanitizeSyncProfile(sync.profile),
      options: sanitizeSyncOptions(sync.options),
      knownJobIds: sanitizeKnownJobIds(sync.knownJobIds),
    },
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
