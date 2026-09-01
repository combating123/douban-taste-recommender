const MEDIA_PREFIX = "/media/";
const IMAGE_PROXY_PATH = "/api/image-proxy";
const MEDIA_TIMEOUT_MS = 6000;
const DEFAULT_MEDIA_CONCURRENCY = 3;
const DEFAULT_BACKGROUND_CONCURRENCY = 2;
const DEFAULT_FOREGROUND_PRIORITY = 50;
const MEDIA_KINDS = new Set(["poster", "backdrop", "portrait"]);
const MEDIA_STATUS_PRESENTATION = Object.freeze({
  ready: "ready",
  pending: "pending",
  processing: "pending",
  queued: "pending",
  resolving: "pending",
  downloading: "pending",
  validating: "pending",
  "designed-fallback": "missing",
  missing: "missing",
  degraded: "unverified",
  ambiguous: "unverified",
  unverified: "unverified",
  failed: "unavailable",
  unavailable: "unavailable",
});

export const MEDIA_LOAD_PRIORITY = Object.freeze({
  background: -20,
  standard: 0,
  visible: 20,
  interaction: 80,
  foreground: 100,
});

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function localMediaPath(value) {
  if (!isLocalMediaUrl(value)) return null;

  const url = new URL(value, location.origin);
  return url.pathname + url.search + url.hash;
}

function trustedAppImagePath(value) {
  if (typeof value !== "string" || !value.trim() || !globalThis.location?.origin) return null;
  try {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin) return null;
    if (!url.pathname.startsWith(MEDIA_PREFIX) && url.pathname !== IMAGE_PROXY_PATH) return null;
    return url.pathname + url.search + url.hash;
  } catch {
    return null;
  }
}

function scheduleMicrotask(callback) {
  if (typeof globalThis.queueMicrotask === "function") globalThis.queueMicrotask(callback);
  else void Promise.resolve().then(callback);
}

function numericPriority(value, fallback = MEDIA_LOAD_PRIORITY.standard) {
  const priority = Number(value);
  return Number.isFinite(priority) ? priority : fallback;
}

function positiveInteger(value, fallback) {
  const number = Math.floor(Number(value));
  return Number.isFinite(number) && number > 0 ? number : fallback;
}

/**
 * Coordinates same-origin proxy image requests so background media cannot
 * consume every browser connection needed by JSON navigation. One slot is
 * reserved for foreground work by default, queued work is priority ordered,
 * and both queued and active tasks are cancellable.
 */
export function createMediaLoadCoordinator({
  maxConcurrent = DEFAULT_MEDIA_CONCURRENCY,
  maxBackgroundConcurrent = DEFAULT_BACKGROUND_CONCURRENCY,
  foregroundPriority = DEFAULT_FOREGROUND_PRIORITY,
} = {}) {
  const concurrency = positiveInteger(maxConcurrent, DEFAULT_MEDIA_CONCURRENCY);
  const backgroundConcurrency = Math.max(
    0,
    Math.min(concurrency, Math.floor(Number(maxBackgroundConcurrent) || 0)),
  );
  const foregroundThreshold = numericPriority(foregroundPriority, DEFAULT_FOREGROUND_PRIORITY);
  const queue = [];
  let activeCount = 0;
  let activeBackgroundCount = 0;
  let sequence = 0;
  let pumpScheduled = false;
  const isBackgroundTask = (task) => (
    task.backgroundOnly || task.priority < foregroundThreshold
  );

  const releaseActive = (task) => {
    activeCount = Math.max(0, activeCount - 1);
    if (isBackgroundTask(task)) {
      activeBackgroundCount = Math.max(0, activeBackgroundCount - 1);
    }
  };

  const requestPump = () => {
    if (pumpScheduled) return;
    pumpScheduled = true;
    scheduleMicrotask(() => {
      pumpScheduled = false;
      pump();
    });
  };

  const complete = (task) => {
    if (task.state !== "active") return false;
    releaseActive(task);
    task.state = "settled";
    task.abort = null;
    requestPump();
    return true;
  };

  const startTask = (task) => {
    task.state = "active";
    activeCount += 1;
    if (isBackgroundTask(task)) activeBackgroundCount += 1;
    const done = () => complete(task);
    task.done = done;
    try {
      const abort = task.start(done);
      if (task.state === "active" && typeof abort === "function") task.abort = abort;
    } catch {
      done();
    }
  };

  function pump() {
    if (!queue.length || activeCount >= concurrency) return;
    queue.sort((left, right) => right.priority - left.priority || left.sequence - right.sequence);
    while (queue.length && activeCount < concurrency) {
      const nextIndex = queue.findIndex((task) => (
        !isBackgroundTask(task) || activeBackgroundCount < backgroundConcurrency
      ));
      if (nextIndex < 0) break;
      const [task] = queue.splice(nextIndex, 1);
      if (task.state !== "queued") continue;
      startTask(task);
    }
  }

  const schedule = (start, {
    priority = MEDIA_LOAD_PRIORITY.standard,
    backgroundOnly = false,
  } = {}) => {
    if (typeof start !== "function") throw new TypeError("Media load task requires a start callback");
    const task = {
      start,
      priority: numericPriority(priority),
      backgroundOnly: backgroundOnly === true,
      sequence: sequence += 1,
      state: "queued",
      abort: null,
      done: null,
    };
    queue.push(task);
    requestPump();

    return {
      cancel() {
        if (task.state === "queued") {
          const index = queue.indexOf(task);
          if (index >= 0) queue.splice(index, 1);
          task.state = "cancelled";
          requestPump();
          return true;
        }
        if (task.state !== "active") return false;
        const abort = task.abort;
        releaseActive(task);
        task.state = "cancelled";
        task.abort = null;
        try {
          abort?.();
        } finally {
          requestPump();
        }
        return true;
      },
      promote(nextPriority) {
        if (task.state !== "queued" && task.state !== "active") return false;
        const promotedPriority = numericPriority(nextPriority, task.priority);
        if (promotedPriority <= task.priority) return false;
        const wasBackground = isBackgroundTask(task);
        task.priority = promotedPriority;
        if (task.state === "active" && wasBackground && !isBackgroundTask(task)) {
          activeBackgroundCount = Math.max(0, activeBackgroundCount - 1);
        }
        requestPump();
        return true;
      },
      get state() {
        return task.state;
      },
    };
  };

  return Object.freeze({ schedule });
}

const sharedProxyMediaCoordinator = createMediaLoadCoordinator();

function isProxyMediaPath(value) {
  const path = trustedAppImagePath(value);
  if (!path) return false;
  try {
    return new URL(path, location.origin).pathname === IMAGE_PROXY_PATH;
  } catch {
    return false;
  }
}

function abortImageRequest(image) {
  if (!image) return;
  if (typeof image.removeAttribute === "function") {
    try {
      image.removeAttribute("src");
      return;
    } catch {
      // Fall through to the property assignment used by lightweight DOMs.
    }
  }
  try {
    image.src = "";
  } catch {
    // A detached or synthetic image may expose a read-only src property.
  }
}

function emptyMediaHandle() {
  return { cancel() { return false; }, promote() { return false; } };
}

export function mediaRetryUrl(value, attempt = 1) {
  const path = trustedAppImagePath(value);
  if (!path) return "";
  const url = new URL(path, location.origin);
  url.searchParams.set("_cs_retry", String(Math.max(1, Number(attempt) || 1)));
  return url.pathname + url.search + url.hash;
}

/**
 * Mount a trusted app image with bounded cache-busting retries. Proxy-backed
 * images are admitted through the shared coordinator; local /media assets keep
 * their immediate path. Cancelling active proxy work aborts the underlying img.
 */
export function attachResilientImage(image, value, options = {}) {
  const source = trustedAppImagePath(value);
  const onFailure = typeof options.onFailure === "function" ? options.onFailure : () => {};
  const maxRetries = Math.max(0, Math.min(4, Number(options.maxRetries) || 0));
  if (!image || !source || typeof image.addEventListener !== "function") {
    onFailure();
    return emptyMediaHandle();
  }

  const coordinator = options.coordinator?.schedule
    ? options.coordinator
    : sharedProxyMediaCoordinator;
  const priority = numericPriority(options.priority);
  let attempts = 0;
  let settled = false;
  let releaseSlot = () => {};
  let queueHandle = null;
  let abortActive = null;

  const releaseNetworkSlot = () => {
    const release = releaseSlot;
    releaseSlot = () => {};
    release();
  };
  const cleanup = () => {
    image.removeEventListener?.("load", handleLoad);
    image.removeEventListener?.("error", handleError);
  };
  const handleLoad = () => {
    if (settled) return;
    settled = true;
    if (image.dataset) image.dataset.mediaRetries = String(attempts);
    cleanup();
    releaseNetworkSlot();
  };
  const handleError = () => {
    if (settled) return;
    if (attempts >= maxRetries) {
      settled = true;
      cleanup();
      releaseNetworkSlot();
      onFailure();
      return;
    }
    attempts += 1;
    if (image.dataset) image.dataset.mediaRetries = String(attempts);
    const retryUrl = mediaRetryUrl(source, attempts);
    scheduleMicrotask(() => {
      if (!settled && retryUrl) image.src = retryUrl;
    });
  };
  const start = (done) => {
    if (settled) {
      done();
      return null;
    }
    releaseSlot = done;
    image.addEventListener("load", handleLoad);
    image.addEventListener("error", handleError);
    try {
      image.src = source;
    } catch {
      handleError();
    }
    return () => {
      cleanup();
      abortImageRequest(image);
    };
  };

  if (isProxyMediaPath(source)) {
    queueHandle = coordinator.schedule(start, {
      priority,
      backgroundOnly: options.backgroundOnly === true,
    });
  } else {
    abortActive = start(() => {});
  }

  return {
    cancel() {
      if (settled) return false;
      settled = true;
      cleanup();
      const cancelled = queueHandle ? queueHandle.cancel() : true;
      if (!queueHandle) abortActive?.();
      releaseNetworkSlot();
      return cancelled;
    },
    promote(nextPriority) {
      return queueHandle?.promote?.(nextPriority) || false;
    },
  };
}

function mediaCandidate(payload, fields) {
  const record = objectValue(payload);
  const nested = objectValue(record.media);

  for (const field of fields) {
    if (record[field] !== undefined) return record[field];
    if (nested[field] !== undefined) return nested[field];
  }

  if (nested.localUrl || nested.url || nested.path || nested.src) return nested;
  if (record.localUrl || record.mediaUrl) return record;
  return null;
}

function candidateUrl(candidate) {
  if (typeof candidate === "string") return candidate;

  const record = objectValue(candidate);
  return textValue(record.localUrl) || textValue(record.url) || textValue(record.path) || textValue(record.src);
}

function statusText(value, kind) {
  if (typeof value === "string") return value.trim().toLowerCase() || null;

  const record = objectValue(value);
  return textValue(record[kind]).toLowerCase() || textValue(record.status).toLowerCase() || null;
}

function statusFor(candidate, payload, kind) {
  const media = objectValue(candidate);
  const record = objectValue(payload);
  const candidates = [
    media.media_status,
    media.mediaStatus,
    media.status,
    record[kind + "_status"],
    record[kind + "Status"],
    objectValue(record.media_status)[kind],
    objectValue(record.mediaStatus)[kind],
    record.status,
  ];

  for (const value of candidates) {
    const rawStatus = statusText(value, kind);
    if (rawStatus !== null) return MEDIA_STATUS_PRESENTATION[rawStatus] || "unverified";
  }
  return null;
}

function createAsset({ localUrl, kind, title, status, source }) {
  const safeKind = MEDIA_KINDS.has(kind) ? kind : "poster";
  const safeLocalUrl = localMediaPath(localUrl);
  const fallbackTitle = safeKind === "portrait" ? "未具名人物" : "未命名作品";
  const safeStatus = statusFor({ status }, {}, safeKind);
  const resolvedStatus = safeStatus || (safeLocalUrl ? "unverified" : "missing");

  return Object.freeze({
    localUrl: safeLocalUrl,
    kind: safeKind,
    title: textValue(title, fallbackTitle),
    status: safeLocalUrl ? resolvedStatus : resolvedStatus === "ready" ? "missing" : resolvedStatus,
    source: textValue(source, "local"),
  });
}

/**
 * Returns true only for a current-origin resource inside the /media/ namespace.
 * It deliberately rejects protocol-relative, data, blob, and lookalike paths.
 */
export function isLocalMediaUrl(value = "") {
  if (typeof value !== "string" || !value.trim() || !globalThis.location?.origin) return false;

  try {
    const url = new URL(value, location.origin);
    const sameOrigin = url.origin === location.origin;
    if (!sameOrigin) return false;
    if (url.pathname.startsWith(MEDIA_PREFIX)) return true;
    return url.pathname === IMAGE_PROXY_PATH && Boolean(url.searchParams.get("url"));
  } catch {
    return false;
  }
}

/**
 * Canonical media shape for a recommendation flat item. It only adapts data and
 * never requests a resource.
 */
export function adaptRecommendationMedia(item = {}) {
  const candidate = mediaCandidate(item, ["poster", "posterMedia", "image", "cover"]);
  const record = objectValue(item);
  return createAsset({
    localUrl: candidateUrl(candidate),
    kind: "poster",
    title: textValue(record.title) || textValue(record.name),
    status: statusFor(candidate, record, "poster"),
    source: record.source,
  });
}

/**
 * Canonical media shape for catalog poster and backdrop payloads. It only adapts
 * fields and never performs a network request.
 */
export function adaptCatalogMedia(record = {}, kind = "poster") {
  const safeKind = kind === "backdrop" ? "backdrop" : "poster";
  const payload = objectValue(record);
  const candidate = mediaCandidate(payload, [safeKind, safeKind + "Media"]);

  return createAsset({
    localUrl: candidateUrl(candidate),
    kind: safeKind,
    title: textValue(payload.title) || textValue(payload.name),
    status: statusFor(candidate, payload, safeKind),
    source: payload.source,
  });
}

/**
 * Canonical media shape for a person portrait payload. It only adapts fields and
 * never performs a network request.
 */
export function adaptPersonMedia(person = {}) {
  const payload = objectValue(person);
  const candidate = mediaCandidate(payload, ["portrait", "portraitMedia", "avatar"]);

  return createAsset({
    localUrl: candidateUrl(candidate),
    kind: "portrait",
    title: textValue(payload.name) || textValue(payload.title),
    status: statusFor(candidate, payload, "portrait"),
    source: payload.source,
  });
}

export function normalizeMediaAsset(asset = {}) {
  const payload = objectValue(asset);
  return createAsset({
    localUrl: payload.localUrl,
    kind: payload.kind,
    title: payload.title,
    status: payload.status,
    source: payload.source,
  });
}

/**
 * Loads and decodes a local image. When a mount node is supplied the image is
 * attached as a visually hidden child so browsers still schedule the request
 * while the visible fallback remains stable. The returned value is the exact
 * decoded Image instance, or null on every failure.
 */
function cancellableMediaPromise(promise, cancel, promote) {
  Object.defineProperties(promise, {
    cancel: { value: cancel, configurable: true },
    promote: { value: promote, configurable: true },
  });
  return promise;
}

function resolvedMediaPromise(value = null) {
  return cancellableMediaPromise(Promise.resolve(value), () => false, () => false);
}

/**
 * Loads and decodes a trusted current-origin image. Proxy paths share the same
 * bounded coordinator as visible images. The returned Promise also exposes
 * cancel() and promote() without breaking existing await/then callers.
 */
export function preloadLocalMedia(value, mountNode = null, options = {}) {
  const url = localMediaPath(value);
  if (!url || typeof globalThis.Image !== "function") return resolvedMediaPromise(null);

  const image = new Image();
  image.hidden = true;
  image.decoding = "async";
  const coordinator = options.coordinator?.schedule
    ? options.coordinator
    : sharedProxyMediaCoordinator;
  const priority = numericPriority(options.priority, MEDIA_LOAD_PRIORITY.background);
  let settled = false;
  let timeout = null;
  let releaseSlot = () => {};
  let queueHandle = null;
  let abortActive = null;
  let resolveResult = () => {};

  const promise = new Promise((resolve) => {
    resolveResult = resolve;
  });
  const releaseNetworkSlot = () => {
    const release = releaseSlot;
    releaseSlot = () => {};
    release();
  };
  const finish = (result, { abort = false } = {}) => {
    if (settled) return false;
    settled = true;
    if (timeout !== null) clearTimeout(timeout);
    timeout = null;
    image.onload = null;
    image.onerror = null;
    if (abort) abortImageRequest(image);
    releaseNetworkSlot();
    resolveResult(result);
    return true;
  };
  const start = (done) => {
    if (settled) {
      done();
      return null;
    }
    releaseSlot = done;
    timeout = setTimeout(() => finish(null, { abort: true }), MEDIA_TIMEOUT_MS);
    image.onload = () => {
      // The browser connection is free once load fires; decoding should not keep
      // an artificial network slot occupied.
      releaseNetworkSlot();
      const acceptLoadedPixels = () => finish(image.naturalWidth > 0 ? image : null);
      let decoding;
      try {
        decoding = typeof image.decode === "function" ? image.decode() : null;
      } catch {
        finish(null);
        return;
      }

      if (!decoding || typeof decoding.then !== "function") {
        acceptLoadedPixels();
        return;
      }

      Promise.resolve(decoding).then(acceptLoadedPixels, () => finish(null));
      // Chromium can leave decode() pending forever for already cached local
      // images even after onload and intrinsic pixels are available.
      scheduleMicrotask(() => {
        if (!settled && image.naturalWidth > 0) finish(image);
      });
    };
    image.onerror = () => finish(null);
    if (mountNode && typeof mountNode.appendChild === "function") {
      image.className = "media-frame__preload";
      image.setAttribute?.("aria-hidden", "true");
      mountNode.appendChild(image);
    }
    try {
      image.src = url;
    } catch {
      finish(null);
    }
    return () => finish(null, { abort: true });
  };

  if (isProxyMediaPath(url)) {
    queueHandle = coordinator.schedule(start, {
      priority,
      backgroundOnly: options.backgroundOnly === true,
    });
  } else {
    abortActive = start(() => {});
  }

  return cancellableMediaPromise(
    promise,
    () => {
      if (settled) return false;
      const cancelled = queueHandle ? queueHandle.cancel() : true;
      if (!queueHandle) abortActive?.();
      if (!settled) finish(null, { abort: true });
      return cancelled;
    },
    (nextPriority) => queueHandle?.promote?.(nextPriority) || false,
  );
}
