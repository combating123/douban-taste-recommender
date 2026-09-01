import { getV2, postV2 } from "./api.js";

const TERMINAL_STATES = new Set(["complete", "partial", "failed", "needs_cookie"]);

function textValue(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function positiveNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function installDoubanReturnSync({
  windowTarget = globalThis.window,
  documentTarget = globalThis.document,
  api = { getV2, postV2 },
  now = () => Date.now(),
  minIntervalMs = 60_000,
  pollIntervalMs = 1_500,
  maxPolls = 240,
  setTimer = (callback, delay) => setTimeout(callback, delay),
  clearTimer = (timerId) => clearTimeout(timerId),
  onSettled = () => {},
  onError = () => {},
} = {}) {
  const throttleMs = positiveNumber(minIntervalMs, 60_000);
  const pollDelay = positiveNumber(pollIntervalMs, 1_500);
  const pollLimit = Math.max(1, Math.floor(positiveNumber(maxPolls, 240)));
  const sleepers = new Map();
  let disposed = false;
  let inFlight = null;
  let lastAttemptAt = Number.NEGATIVE_INFINITY;

  const visible = () => documentTarget?.visibilityState !== "hidden";

  const waitForPoll = () => new Promise((resolve) => {
    if (disposed) {
      resolve(false);
      return;
    }
    const timerId = setTimer(() => {
      sleepers.delete(timerId);
      resolve(!disposed);
    }, pollDelay);
    sleepers.set(timerId, resolve);
  });

  const pollJob = async (jobId, initial = {}) => {
    let current = initial && typeof initial === "object" ? initial : {};
    for (let attempt = 0; attempt < pollLimit && !disposed; attempt += 1) {
      const state = textValue(current.state).toLowerCase();
      if (TERMINAL_STATES.has(state)) return current;
      current = await api.getV2(`/api/v2/sync/jobs/${encodeURIComponent(jobId)}`);
      if (TERMINAL_STATES.has(textValue(current?.state).toLowerCase())) return current;
      if (attempt + 1 < pollLimit && !(await waitForPoll())) return null;
    }
    return null;
  };

  const execute = async (reason) => {
    const settings = await api.getV2("/api/v2/sync/settings");
    if (disposed || !settings?.enabled || !textValue(settings?.user_id)) return null;
    const created = await api.postV2("/api/v2/sync/run-now", {});
    const jobId = textValue(created?.job_id) || textValue(created?.id);
    if (!jobId || disposed) return null;
    const terminal = await pollJob(jobId, created);
    if (!terminal || disposed) return terminal;
    await onSettled(terminal, { reason, jobId, reused: Boolean(created?.reused) });
    return terminal;
  };

  const trigger = (reason = "return") => {
    if (disposed || !visible()) return Promise.resolve(null);
    if (inFlight) return inFlight;
    const timestamp = Number(now());
    const safeTimestamp = Number.isFinite(timestamp) ? timestamp : Date.now();
    if (safeTimestamp - lastAttemptAt < throttleMs) return Promise.resolve(null);
    lastAttemptAt = safeTimestamp;
    const operation = Promise.resolve()
      .then(() => execute(reason))
      .catch((error) => {
        onError(error, { reason });
        return null;
      })
      .finally(() => {
        if (inFlight === operation) inFlight = null;
      });
    inFlight = operation;
    return operation;
  };

  const onFocus = () => trigger("focus");
  const onVisibilityChange = () => (visible() ? trigger("visibilitychange") : Promise.resolve(null));
  windowTarget?.addEventListener?.("focus", onFocus);
  documentTarget?.addEventListener?.("visibilitychange", onVisibilityChange);

  const dispose = () => {
    if (disposed) return;
    disposed = true;
    windowTarget?.removeEventListener?.("focus", onFocus);
    documentTarget?.removeEventListener?.("visibilitychange", onVisibilityChange);
    for (const [timerId, resolve] of sleepers) {
      clearTimer(timerId);
      resolve(false);
    }
    sleepers.clear();
  };

  return {
    trigger,
    dispose,
    snapshot: () => ({
      disposed,
      pending: Boolean(inFlight),
      lastAttemptAt: Number.isFinite(lastAttemptAt) ? lastAttemptAt : null,
    }),
  };
}
