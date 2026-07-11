import {
  UI_SCHEMA_VERSION,
  UI_STATE_KEY,
  createEmptyUiState,
  normalizeUiState,
} from "./store.js";

export const MIGRATION_FINGERPRINT_KEY = "cinescope.ui.migration.v3";

const LEGACY_RECOMMENDATION_KEY = "CINESCOPE_LAST_RECOMMENDATION_V4";
const LEGACY_PREFS_KEY = "CINESCOPE_PREFS_V2";
const PLACEHOLDER_TITLE = /^(?:电影策展|剧集策展|动漫剧集策展)\d+$/;
const PROFILE_ID = /^[A-Za-z0-9._~-]{1,128}$/;
const EXTERNAL_URL = /^(?:https?:)?\/\//i;

function browserStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function parseObject(raw) {
  if (typeof raw !== "string" || !raw) return null;
  try {
    const value = JSON.parse(raw);
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

function validV3(raw) {
  const parsed = parseObject(raw);
  return parsed?.schemaVersion === UI_SCHEMA_VERSION ? parsed : null;
}

function normaliseProfileId(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (PROFILE_ID.test(text)) return text;
  try {
    const url = new URL(text);
    if (url.protocol !== "https:" || !/(^|\.)douban\.com$/i.test(url.hostname)) return "";
    const match = url.pathname.match(/^\/people\/([A-Za-z0-9._~-]{1,128})(?:\/|$)/);
    return match?.[1] || "";
  } catch {
    return "";
  }
}

function optionalCount(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 && number <= 1000000 ? number : null;
}

function projectSync(prefs) {
  if (!prefs) return null;
  const profile = normaliseProfileId(prefs.userInput ?? prefs.profile ?? prefs.profileId);
  const rawMaxPages = Number(prefs.maxPages);
  const hasOptions = ["maxPages", "includeWish", "includeDo", "expectedCollect", "expectedWish"]
    .some((key) => Object.hasOwn(prefs, key));
  if (!profile && !hasOptions) return null;
  return {
    profile,
    options: {
      maxPages: Number.isInteger(rawMaxPages) ? Math.max(1, Math.min(250, rawMaxPages)) : 250,
      includeWish: prefs.includeWish !== false,
      includeDo: Boolean(prefs.includeDo),
      expectedCollect: optionalCount(prefs.expectedCollect),
      expectedWish: optionalCount(prefs.expectedWish),
    },
    knownJobIds: [],
  };
}

function migrationStats(recommendationSnapshot) {
  const stats = { placeholderTitles: 0, premiumIds: 0, dataImages: 0, externalUrls: 0 };
  const visit = (value, depth = 0) => {
    if (depth > 8 || value === null || value === undefined) return;
    if (typeof value === "string") {
      if (PLACEHOLDER_TITLE.test(value)) stats.placeholderTitles += 1;
      if (/^premium-/i.test(value)) stats.premiumIds += 1;
      if (/^data:image/i.test(value)) stats.dataImages += 1;
      if (EXTERNAL_URL.test(value)) stats.externalUrls += 1;
      return;
    }
    if (Array.isArray(value)) {
      value.slice(0, 1000).forEach((entry) => visit(entry, depth + 1));
      return;
    }
    if (typeof value === "object") {
      Object.values(value).slice(0, 1000).forEach((entry) => visit(entry, depth + 1));
    }
  };
  visit(recommendationSnapshot);
  return stats;
}

function candidateFromLegacy(recommendationSnapshot, prefs) {
  const candidate = createEmptyUiState();
  let projected = false;
  if (typeof recommendationSnapshot?.railHidden === "boolean") {
    candidate.rail.mode = recommendationSnapshot.railHidden ? "hidden" : "expanded";
    projected = true;
  }
  const sync = projectSync(prefs);
  if (sync) {
    candidate.sync = sync;
    projected = true;
  }
  return projected ? normalizeUiState(candidate) : null;
}

function fingerprintFor(candidate) {
  const input = JSON.stringify(candidate);
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `v3-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function result(status, stats = { placeholderTitles: 0, premiumIds: 0, dataImages: 0, externalUrls: 0 }) {
  return { status, schemaVersion: UI_SCHEMA_VERSION, stats };
}

export function migrateLegacyClientState(storage = browserStorage()) {
  if (!storage || typeof storage.getItem !== "function" || typeof storage.setItem !== "function") {
    return result("storage-unavailable");
  }

  let currentRaw;
  let existingFingerprint;
  let recommendationRaw;
  let prefsRaw;
  try {
    currentRaw = storage.getItem(UI_STATE_KEY);
    existingFingerprint = storage.getItem(MIGRATION_FINGERPRINT_KEY);
    recommendationRaw = storage.getItem(LEGACY_RECOMMENDATION_KEY);
    prefsRaw = storage.getItem(LEGACY_PREFS_KEY);
  } catch {
    return result("storage-unavailable");
  }

  const recommendationSnapshot = parseObject(recommendationRaw);
  const prefs = parseObject(prefsRaw);
  const stats = migrationStats(recommendationSnapshot);
  const candidate = candidateFromLegacy(recommendationSnapshot, prefs);
  const existing = validV3(currentRaw);

  if (existing) {
    if (!candidate) return result("existing-v3", stats);
    const candidateRaw = JSON.stringify(candidate);
    const existingRaw = JSON.stringify(normalizeUiState(existing));
    if (existingRaw !== candidateRaw) return result("existing-v3", stats);
    const fingerprint = fingerprintFor(candidate);
    if (existingFingerprint === fingerprint) return result("already-migrated", stats);
    try {
      storage.setItem(MIGRATION_FINGERPRINT_KEY, fingerprint);
      return result("fingerprinted-existing-migration", stats);
    } catch {
      return result("fingerprint-write-failed", stats);
    }
  }

  if (!candidate) return result("no-safe-legacy-state", stats);
  const candidateRaw = JSON.stringify(candidate);
  try {
    storage.setItem(UI_STATE_KEY, candidateRaw);
    if (storage.getItem(UI_STATE_KEY) !== candidateRaw) return result("state-write-failed", stats);
  } catch {
    return result("state-write-failed", stats);
  }

  try {
    storage.setItem(MIGRATION_FINGERPRINT_KEY, fingerprintFor(candidate));
    return result("migrated", stats);
  } catch {
    return result("fingerprint-write-failed", stats);
  }
}
