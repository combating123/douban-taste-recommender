const SAFE_PATH = /^\/(?!\/)[^?#]{0,511}$/;
const SAFE_ID = /^[A-Za-z0-9:._~-]{1,256}$/;
const SAFE_PARAM_KEY = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
const CHANNELS = ["movie", "series", "anime-series"];
const RAIL_MODES = new Set(["expanded", "collapsed", "hidden"]);
const LIBRARY_STATES = new Set(["all", "watched", "wish", "wanted", "candidate", "rated", "collect", "ready", "hidden", "archived"]);

let lastStableState = null;
let boundary = {
  root: null,
  getCurrentPath: () => "",
  getStableState: () => null,
  onRetry: () => {},
};
const renderGenerations = new WeakMap();

function clone(value) {
  return value === null || value === undefined ? value : JSON.parse(JSON.stringify(value));
}

function safePath(value) {
  return typeof value === "string" && SAFE_PATH.test(value) ? value : null;
}

function safeId(value, maxLength = 256) {
  return typeof value === "string" && value.length <= maxLength && SAFE_ID.test(value) ? value : "";
}

function safeParams(params) {
  if (!params || typeof params !== "object" || Array.isArray(params)) return {};
  const result = {};
  for (const [key, value] of Object.entries(params).slice(0, 20)) {
    if (!SAFE_PARAM_KEY.test(key)) continue;
    if (typeof value === "string") {
      const clean = safeId(value);
      if (clean) result[key] = clean;
    } else if (typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value))) {
      result[key] = value;
    }
  }
  return result;
}

function safeScroll(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result = {};
  for (const [path, position] of Object.entries(value).slice(0, 100)) {
    const cleanPath = safePath(path);
    if (cleanPath && Number.isFinite(position) && position >= 0) result[cleanPath] = Math.floor(position);
  }
  return result;
}

function safeChannels(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return Object.fromEntries(CHANNELS.map((channel) => {
    const entry = source[channel] && typeof source[channel] === "object" ? source[channel] : {};
    return [channel, {
      sessionId: safeId(entry.sessionId) || null,
      batchIndex: Number.isInteger(entry.batchIndex) && entry.batchIndex >= 0 ? entry.batchIndex : 0,
      batchIds: Array.isArray(entry.batchIds)
        ? [...new Set(entry.batchIds.map((item) => safeId(item)).filter(Boolean))].slice(-50)
        : [],
    }];
  }));
}

function profileId(value) {
  const direct = safeId(typeof value === "string" ? value.trim() : "", 128);
  if (direct) return direct;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !/(^|\.)douban\.com$/i.test(url.hostname)) return "";
    return safeId(url.pathname.match(/^\/people\/([^/]+)(?:\/|$)/)?.[1] || "", 128);
  } catch {
    return "";
  }
}

function optionalCount(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 && number <= 1000000 ? number : null;
}

function safeSync(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const options = source.options && typeof source.options === "object" && !Array.isArray(source.options) ? source.options : {};
  const maxPages = Number(options.maxPages);
  return {
    profile: profileId(source.profile),
    options: {
      maxPages: Number.isInteger(maxPages) ? Math.max(1, Math.min(250, maxPages)) : 250,
      includeWish: options.includeWish !== false,
      includeDo: Boolean(options.includeDo),
      expectedCollect: optionalCount(options.expectedCollect),
      expectedWish: optionalCount(options.expectedWish),
    },
    knownJobIds: Array.isArray(source.knownJobIds)
      ? [...new Set(source.knownJobIds.map((item) => safeId(item, 128)).filter(Boolean))].slice(-50)
      : [],
  };
}

export function sanitizeStableState(state = {}) {
  const source = state && typeof state === "object" && !Array.isArray(state) ? state : {};
  const recommendation = source.recommendation && typeof source.recommendation === "object" ? source.recommendation : {};
  const context = source.candidateTray?.context && typeof source.candidateTray.context === "object"
    ? source.candidateTray.context
    : {};
  const focusId = safeId(context.universeFocusId);
  const expandedIds = Array.isArray(context.expandedIds)
    ? [...new Set(context.expandedIds.map((item) => safeId(item)).filter(Boolean))].slice(-36)
    : [];
  return {
    activePath: safePath(source.activePath),
    activeParams: safeParams(source.activeParams),
    scrollByRoute: safeScroll(source.scrollByRoute),
    rail: { mode: RAIL_MODES.has(source.rail?.mode) ? source.rail.mode : "expanded" },
    recommendation: {
      activeChannel: CHANNELS.includes(recommendation.activeChannel) ? recommendation.activeChannel : "movie",
      channels: safeChannels(recommendation.channels),
    },
    candidateTray: { context: { ...(focusId ? { universeFocusId: focusId } : {}), ...(expandedIds.length ? { expandedIds } : {}) } },
    library: { state: LIBRARY_STATES.has(source.library?.state) ? source.library.state : "all" },
    sync: safeSync(source.sync),
  };
}

export function configureRecoveryBoundary(options = {}) {
  boundary = {
    root: options.root ?? boundary.root ?? globalThis.document?.getElementById?.("app-view") ?? null,
    getCurrentPath: typeof options.getCurrentPath === "function" ? options.getCurrentPath : boundary.getCurrentPath,
    getStableState: typeof options.getStableState === "function" ? options.getStableState : boundary.getStableState,
    onRetry: typeof options.onRetry === "function" ? options.onRetry : boundary.onRetry,
  };
  return boundary;
}

export function rememberLastStableState(state) {
  const stable = sanitizeStableState(state);
  if (stable.activePath) lastStableState = stable;
  return restoreLastStableState();
}

export function restoreLastStableState() {
  return clone(lastStableState);
}

function recoveryPanel(stableState) {
  if (typeof globalThis.document?.createElement !== "function") {
    return { className: "route-recovery", textContent: "恢复上次稳定状态", stableState: clone(stableState) };
  }
  const panel = document.createElement("section");
  panel.className = "route-recovery";
  panel.setAttribute?.("data-recovery-code", "route-render-failed");
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "CINESCOPE / RECOVERY";
  const heading = document.createElement("h1");
  heading.textContent = "此页面暂时无法显示";
  const copy = document.createElement("p");
  copy.textContent = "上一份稳定视图仍可恢复。";
  const retry = document.createElement("button");
  retry.type = "button";
  retry.textContent = "恢复上次稳定状态";
  retry.addEventListener("click", () => {
    const restored = restoreLastStableState() || sanitizeStableState(stableState);
    if (restored?.activePath) boundary.onRetry(restored);
  });
  panel.append(eyebrow, heading, copy, retry);
  return panel;
}

export function renderRecoveryBoundary(error, stableState) {
  void error;
  const root = boundary.root ?? globalThis.document?.getElementById?.("app-view") ?? null;
  const safeStable = stableState ? sanitizeStableState(stableState) : restoreLastStableState();
  const panel = recoveryPanel(safeStable);
  if (root?.replaceChildren) root.replaceChildren(panel);
  return panel;
}

function rootChildren(root) {
  if (!root) return [];
  if (root.childNodes && typeof root.childNodes[Symbol.iterator] === "function") return [...root.childNodes];
  return Array.isArray(root.children) ? [...root.children] : [];
}

function reportRecovery(path) {
  try {
    globalThis.console?.error?.("CineScope route recovery", {
      code: "route-render-failed",
      route: safePath(path),
    });
  } catch {
    // Diagnostics must never interfere with the recovery commit.
  }
}

export async function renderSafely(route, renderer, options = {}) {
  if (typeof renderer !== "function") throw new TypeError("renderSafely requires a renderer");
  const root = options.root ?? boundary.root ?? globalThis.document?.getElementById?.("app-view") ?? null;
  const getCurrentPath = typeof options.getCurrentPath === "function" ? options.getCurrentPath : boundary.getCurrentPath;
  const getStableState = typeof options.getStableState === "function" ? options.getStableState : boundary.getStableState;
  const expectedPath = safePath(route?.path);
  const previousNodes = rootChildren(root);
  const previousStable = restoreLastStableState() || sanitizeStableState(getStableState?.() || {});
  const generation = root ? (renderGenerations.get(root) || 0) + 1 : 1;
  if (root) renderGenerations.set(root, generation);
  const isCurrent = () => (
    (!root || renderGenerations.get(root) === generation)
    && (!expectedPath || getCurrentPath?.() === expectedPath)
  );

  try {
    const value = await Promise.resolve().then(renderer);
    if (!isCurrent()) return { ok: false, recovered: false, stale: true, value: null };
    const state = getStableState?.();
    if (state) rememberLastStableState(state);
    return { ok: true, recovered: false, stale: false, value };
  } catch (error) {
    if (!isCurrent()) return { ok: false, recovered: false, stale: true, value: null };
    reportRecovery(expectedPath);
    if (root && rootChildren(root).length === 0 && previousNodes.length) root.replaceChildren(...previousNodes);
    renderRecoveryBoundary(error, previousStable);
    return { ok: false, recovered: true, stale: false, value: null };
  }
}
