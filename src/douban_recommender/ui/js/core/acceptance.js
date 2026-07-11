import { CHANNEL_KEYS, getV2, postV2 } from "./api.js";
import { isLocalHookLocation } from "./audit.js";
import { stableTitleKey } from "../components/title-card.js";

const SAFE_ID = /^[A-Za-z0-9:._~-]+$/;
const CHANNEL_ORDER = [CHANNEL_KEYS.movie, CHANNEL_KEYS.series, CHANNEL_KEYS["anime-series"]];
// postV2 injects the required schema_version: 2 into this deterministic payload.
const PAYLOAD = Object.freeze({
  use_sample_ratings: true,
  use_sample_candidates: true,
  fetch_douban: false,
  include_movies: true,
  include_series: true,
  include_anime: true,
  batch_size: 24,
  limit: 160,
});

let currentOwner = null;
let nextGeneration = 0;

function acceptanceError(code) {
  const error = new Error(code);
  Object.defineProperty(error, "name", { value: "CineScopeAcceptanceError", configurable: true });
  Object.defineProperty(error, "code", { value: code, enumerable: true });
  error.stack = `CineScopeAcceptanceError: ${code}`;
  return error;
}

function isCurrent(owner) {
  return owner.active
    && currentOwner === owner
    && !owner.controller.signal.aborted
    && owner.generation === nextGeneration;
}

function requireCurrent(owner) {
  if (!isCurrent(owner)) throw acceptanceError("CINESCOPE_ACCEPTANCE_STALE");
}

async function request(owner, code, operation) {
  try {
    const result = await operation();
    requireCurrent(owner);
    return result;
  } catch (error) {
    if (!isCurrent(owner) || error?.name === "AbortError" || error?.code === "CINESCOPE_ACCEPTANCE_STALE") {
      throw acceptanceError("CINESCOPE_ACCEPTANCE_STALE");
    }
    throw acceptanceError(code);
  }
}

function safeId(value) {
  const clean = typeof value === "string" ? value.trim() : "";
  return clean !== "." && clean !== ".." && SAFE_ID.test(clean) ? clean : "";
}

function sessionWasCommitted(store, sessionId) {
  try {
    return safeId(store.getState()?.recommendation?.sessionId) === sessionId;
  } catch {
    return false;
  }
}

function candidateItems(session) {
  const seen = new Set();
  const items = [];
  for (const channelName of CHANNEL_ORDER) {
    const batchItems = session?.channels?.[channelName]?.batch?.items;
    for (const item of Array.isArray(batchItems) ? batchItems : []) {
      const titleId = safeId(stableTitleKey(item));
      if (!titleId || seen.has(titleId)) continue;
      seen.add(titleId);
      items.push({ item, titleId });
    }
  }
  return items;
}

async function seedAcceptance(owner) {
  const session = await request(owner, "CINESCOPE_ACCEPTANCE_SESSION_FAILED", () => (
    owner.api.postV2("/api/v2/recommend/sessions", PAYLOAD, { signal: owner.controller.signal })
  ));
  const sessionId = safeId(session?.id);
  if (!sessionId) throw acceptanceError("CINESCOPE_ACCEPTANCE_INVALID_SESSION");

  const candidates = candidateItems(session);
  if (!candidates.length) throw acceptanceError("CINESCOPE_ACCEPTANCE_NO_TITLE");

  for (const { titleId } of candidates) {
    const title = await request(owner, "CINESCOPE_ACCEPTANCE_TITLE_FAILED", () => (
      owner.api.getV2(`/api/v2/titles/${encodeURIComponent(titleId)}`, { signal: owner.controller.signal })
    ));
    const personId = (Array.isArray(title?.people) ? title.people : [])
      .map((person) => safeId(person?.id))
      .find(Boolean);
    if (!personId) continue;

    await request(owner, "CINESCOPE_ACCEPTANCE_PERSON_FAILED", () => (
      owner.api.getV2(`/api/v2/people/${encodeURIComponent(personId)}`, { signal: owner.controller.signal })
    ));
    requireCurrent(owner);
    try {
      owner.store.dispatch({ type: "recommendation/sessionReceived", session, source: "acceptance" });
    } catch (error) {
      if (!isCurrent(owner) || error?.code === "CINESCOPE_ACCEPTANCE_STALE") {
        throw acceptanceError("CINESCOPE_ACCEPTANCE_STALE");
      }
      if (!sessionWasCommitted(owner.store, sessionId)) {
        throw acceptanceError("CINESCOPE_ACCEPTANCE_COMMIT_FAILED");
      }
    }
    return Object.freeze({ sessionId, titleId, personId });
  }

  throw acceptanceError("CINESCOPE_ACCEPTANCE_NO_PERSON");
}

function deactivate(owner) {
  if (!owner.active) return;
  owner.active = false;
  owner.generation = -1;
  owner.controller.abort();
  owner.cached = null;
  owner.inFlight = null;
  if (owner.browser.__CINESCOPE_SEED_ACCEPTANCE__ === owner.hook) {
    delete owner.browser.__CINESCOPE_SEED_ACCEPTANCE__;
  }
  if (currentOwner === owner) {
    currentOwner = null;
    nextGeneration += 1;
  }
}

export function installAcceptanceHook({
  browser = globalThis.window,
  store,
  api = { getV2, postV2 },
} = {}) {
  if (!browser || !isLocalHookLocation(browser.location)) return () => {};
  if (!store?.getState || !store?.dispatch || !api?.getV2 || !api?.postV2) return () => {};

  if (currentOwner) deactivate(currentOwner);
  const owner = {
    active: true,
    api,
    browser,
    cached: null,
    controller: new AbortController(),
    generation: ++nextGeneration,
    hook: null,
    inFlight: null,
    store,
  };

  const hook = () => {
    if (!isCurrent(owner)) return Promise.reject(acceptanceError("CINESCOPE_ACCEPTANCE_STALE"));
    if (owner.cached) return Promise.resolve(owner.cached);
    if (owner.inFlight) return owner.inFlight;
    const operation = seedAcceptance(owner).then((result) => {
      requireCurrent(owner);
      owner.cached = result;
      return result;
    });
    const inFlight = operation.finally(() => {
      if (owner.inFlight === inFlight) owner.inFlight = null;
    });
    owner.inFlight = inFlight;
    return inFlight;
  };

  owner.hook = hook;
  currentOwner = owner;
  browser.__CINESCOPE_SEED_ACCEPTANCE__ = hook;

  // Same-page in-flight calls are deterministic. A response lost after the server
  // creates a session cannot be made idempotent by this browser-only helper.
  return () => deactivate(owner);
}
