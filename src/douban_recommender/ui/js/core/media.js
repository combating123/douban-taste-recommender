const MEDIA_PREFIX = "/media/";
const MEDIA_TIMEOUT_MS = 6000;
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
    return url.origin === location.origin && url.pathname.startsWith(MEDIA_PREFIX);
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
 * Loads and decodes a local image while it remains outside the document. The
 * returned value is the exact decoded Image instance, or null on every failure.
 */
export function preloadLocalMedia(value) {
  const url = localMediaPath(value);
  if (!url || typeof globalThis.Image !== "function") return Promise.resolve(null);

  const image = new Image();
  image.decoding = "async";

  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      image.onload = null;
      image.onerror = null;
      resolve(result);
    };
    const timeout = setTimeout(() => finish(null), MEDIA_TIMEOUT_MS);

    image.onload = async () => {
      try {
        await image.decode();
        finish(image.naturalWidth > 0 ? image : null);
      } catch {
        finish(null);
      }
    };
    image.onerror = () => finish(null);
    image.src = url;
  });
}
