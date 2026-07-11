import { getV2, postV2 } from "../core/api.js";
import { renderSyncPanel } from "./sync.js";

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function bytesText(value) {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) return "—";
  const bytes = value;
  if (bytes < 1024) return `${Math.floor(bytes)} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function countText(value) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? String(value) : "—";
}

function metric(label, value, detail = "") {
  const card = element("article", "health-metric");
  card.append(element("span", "health-metric__label", label), element("strong", "health-metric__value", value));
  if (detail) card.append(element("span", "health-metric__detail", detail));
  return card;
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function observedCount(value) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function renderHealthMetrics(root, mediaPayload, diagnosticsPayload, { mediaSettled = false, diagnosticsSettled = false } = {}) {
  root.replaceChildren();
  const media = objectValue(mediaPayload);
  const diagnostics = objectValue(diagnosticsPayload);
  const mediaAssets = objectValue(media.assets);
  const diagnosticAssets = objectValue(diagnostics.media_totals);
  const assetTotal = observedCount(mediaAssets.total) ?? observedCount(diagnosticAssets.assets_total);
  const assetBytes = observedCount(mediaAssets.bytes) ?? observedCount(diagnosticAssets.bytes);
  const cacheBytes = observedCount(diagnostics.cache_bytes);
  const provider = objectValue(diagnostics.provider_attempt_health);
  const providerAttempts = provider.basis === "historical_attempts" ? observedCount(provider.attempts_total) : null;
  const audit = objectValue(diagnostics.media_audit);
  const auditTotal = observedCount(audit.total);
  const auditReady = observedCount(audit.ready);
  const auditDetails = [
    ["降级", observedCount(audit.degraded)],
    ["歧义", observedCount(audit.ambiguous)],
    ["缺失", observedCount(audit.missing)],
    ["错图候选", observedCount(audit.wrong_identity_candidates)],
  ].filter((entry) => entry[1] !== null).map(([label, count]) => `${label} ${count}`).join(" · ");
  const appVersion = typeof diagnostics.app_version === "string" && diagnostics.app_version && diagnostics.app_version !== "unknown"
    ? diagnostics.app_version
    : null;

  root.append(
    metric("本地素材", countText(assetTotal), assetBytes === null ? (mediaSettled ? "尚未提供" : "正在读取") : bytesText(assetBytes)),
    metric("缓存占用", cacheBytes === null ? "—" : bytesText(cacheBytes), cacheBytes === null ? (diagnosticsSettled ? "尚未提供" : "正在读取") : "只读统计"),
    metric("交付边界", media.delivery === "local-only" ? "仅本地" : "—", typeof media.delivery === "string" && media.delivery ? media.delivery : "尚未提供"),
    metric("Provider attempts", providerAttempts === null ? "—" : countText(providerAttempts), providerAttempts === null ? "尚未提供" : "历史 attempts"),
    metric("媒体审计", auditTotal !== null && auditReady !== null ? `${auditReady} / ${auditTotal}` : "—", auditDetails || "尚未提供"),
    metric("Diagnostics", appVersion || "—", appVersion ? "应用版本" : "尚未提供"),
  );
  const persistentQueue = objectValue(diagnostics.persistent_queue_states);
  const mediaJobs = objectValue(media.jobs);
  const jobs = Object.keys(persistentQueue).length ? persistentQueue : mediaJobs;
  const jobCard = element("article", "health-metric health-metric--jobs");
  jobCard.append(element("span", "health-metric__label", Object.keys(persistentQueue).length ? "持久媒体队列" : "媒体任务状态"));
  const entries = Object.entries(jobs).filter(([, count]) => observedCount(count) === null || count > 0);
  if (entries.length) {
    for (const [state, count] of entries) jobCard.append(element("span", "health-job-state", `${state} ${countText(count)}`));
  } else {
    const settled = Object.keys(persistentQueue).length ? diagnosticsSettled : mediaSettled;
    jobCard.append(element("span", "health-metric__detail", settled ? "尚无媒体任务" : "正在读取"));
  }
  root.append(jobCard);
}

let activeController = null;

export function renderHealth(root, {
  fetchJson = getV2,
  postJson = postV2,
  syncState = {},
  onSyncStateChange = () => {},
  setTimer,
  clearTimer,
  pollInterval,
} = {}) {
  if (!root) throw new TypeError("Health requires a root element");
  activeController?.dispose();
  const controller = new AbortController();
  let disposed = false;
  const section = element("section", "space space--health");
  section.dataset.space = "health";
  const header = element("header", "space-header");
  const copy = element("div", "space-header__copy");
  copy.append(element("p", "eyebrow", "HEALTH / LOCAL SERVICES"), element("h1", "space-title", "健康与同步"));
  header.append(copy, element("p", "space-summary", "健康是第五个顶级空间，并在此管理同步。缺失诊断保持未知。"));
  const mediaRoot = element("div", "health-grid");
  renderHealthMetrics(mediaRoot, null, null);
  const syncRoot = element("div", "health-sync");
  section.append(header, mediaRoot, syncRoot);
  root.replaceChildren(section);

  const sync = renderSyncPanel(syncRoot, {
    fetchJson,
    postJson,
    knownJobIds: Array.isArray(syncState.knownJobIds) ? syncState.knownJobIds : [],
    profile: syncState.profile || "",
    options: syncState.options || {},
    onStateChange: onSyncStateChange,
    ...(setTimer ? { setTimer } : {}),
    ...(clearTimer ? { clearTimer } : {}),
    ...(pollInterval ? { pollInterval } : {}),
  });

  const healthState = {
    media: null,
    diagnostics: null,
    mediaSettled: false,
    diagnosticsSettled: false,
  };
  const refreshHealth = () => {
    if (disposed || controller.signal.aborted) return;
    renderHealthMetrics(mediaRoot, healthState.media, healthState.diagnostics, healthState);
  };
  const readHealth = (path, key, settledKey) => Promise.resolve()
    .then(() => fetchJson(path, { signal: controller.signal }))
    .then((payload) => {
      healthState[key] = payload;
      healthState[settledKey] = true;
      refreshHealth();
      return payload;
    })
    .catch(() => {
      healthState[settledKey] = true;
      refreshHealth();
      return null;
    });
  const mediaReady = readHealth("/api/v2/media/health", "media", "mediaSettled");
  const diagnosticsReady = readHealth("/api/v2/diagnostics", "diagnostics", "diagnosticsSettled");

  const api = {
    ready: Promise.all([mediaReady, diagnosticsReady, sync.ready]),
    sync,
    dispose() {
      if (disposed) return;
      disposed = true;
      controller.abort();
      sync.dispose();
      if (activeController === api) activeController = null;
    },
  };
  activeController = api;
  return api;
}

export function destroyHealth() {
  if (!activeController) return false;
  const controller = activeController;
  controller.dispose();
  if (activeController === controller) activeController = null;
  return true;
}
