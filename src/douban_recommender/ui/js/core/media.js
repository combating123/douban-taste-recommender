const MEDIA_PREFIX = "/media/";
const MEDIA_TIMEOUT_MS = 6000;
const MEDIA_KINDS = new Set(["poster", "backdrop", "portrait"]);
const MEDIA_STATUSES = new Set(["ready", "pending", "processing", "unavailable", "unverified", "missing"]);

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

function candidateStatus(candidate, fallback) {
  const status = textValue(objectValue(candidate).status) || textValue(fallback);
  return MEDIA_STATUSES.has(status) ? status : "";
}

function createAsset({ localUrl, kind, title, status, source }) {
  const safeKind = MEDIA_KINDS.has(kind) ? kind : "poster";
  const safeLocalUrl = localMediaPath(localUrl);
  const fallbackTitle = safeKind === "portrait" ? "未具名人物" : "未命名作品";
  const safeStatus = candidateStatus({ status }, safeLocalUrl ? "ready" : "unavailable");

  return Object.freeze({
    localUrl: safeLocalUrl,
    kind: safeKind,
    title: textValue(title, fallbackTitle),
    status: safeLocalUrl && safeStatus === "ready" ? "ready" : safeLocalUrl ? safeStatus || "pending" : "unavailable",
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
  const candidate = mediaCandidate(item, ["poster", "posterMedia", "image"]);
  const record = objectValue(item);
  return createAsset({
    localUrl: candidateUrl(candidate),
    kind: "poster",
    title: textValue(record.title) || textValue(record.name),
    status: candidateStatus(candidate, record.posterStatus || record.mediaStatus || record.status),
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
    status: candidateStatus(candidate, payload[safeKind + "Status"] || payload.mediaStatus || payload.status),
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
    status: candidateStatus(candidate, payload.portraitStatus || payload.mediaStatus || payload.status),
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
