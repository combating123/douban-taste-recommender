import { getV2, postV2 } from "../core/api.js";
import { renderSyncPanel } from "./sync.js";

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function bytesText(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${Math.floor(bytes)} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function metric(label, value, detail = "") {
  const card = element("article", "health-metric");
  card.append(element("span", "health-metric__label", label), element("strong", "health-metric__value", value));
  if (detail) card.append(element("span", "health-metric__detail", detail));
  return card;
}

function renderMediaHealth(root, payload) {
  root.replaceChildren();
  const assets = payload?.assets && typeof payload.assets === "object" ? payload.assets : {};
  root.append(
    metric("本地素材", Number.isFinite(Number(assets.total)) ? String(Number(assets.total)) : "—", bytesText(assets.bytes)),
    metric("交付边界", payload?.delivery === "local-only" ? "仅本地" : "—", payload?.delivery || "尚未提供"),
    metric("Provider latency", "—", "尚未提供"),
    metric("Provider backoff", "—", "尚未提供"),
    metric("Diagnostics", "—", "尚未提供"),
  );
  const jobs = payload?.jobs && typeof payload.jobs === "object" ? payload.jobs : {};
  const jobCard = element("article", "health-metric health-metric--jobs");
  jobCard.append(element("span", "health-metric__label", "媒体任务状态"));
  const entries = Object.entries(jobs);
  if (entries.length) {
    for (const [state, count] of entries) jobCard.append(element("span", "health-job-state", `${state} ${Number(count) || 0}`));
  } else {
    jobCard.append(element("span", "health-metric__detail", "尚无媒体任务"));
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
  mediaRoot.append(metric("本地素材", "—", "正在读取"), metric("Provider diagnostics", "—", "尚未提供"));
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

  const healthReady = fetchJson("/api/v2/media/health", { signal: controller.signal })
    .then((payload) => {
      if (!disposed && !controller.signal.aborted) renderMediaHealth(mediaRoot, payload);
      return payload;
    })
    .catch(() => {
      if (!disposed && !controller.signal.aborted) {
        mediaRoot.replaceChildren(metric("媒体健康", "—", "暂时无法读取"), metric("Provider diagnostics", "—", "尚未提供"));
      }
      return null;
    });

  const api = {
    ready: Promise.all([healthReady, sync.ready]),
    sync,
    dispose() {
      if (disposed) return;
      disposed = true;
      controller.abort();
      sync.dispose();
    },
  };
  activeController = api;
  return api;
}

export function destroyHealth() {
  activeController?.dispose();
  activeController = null;
}
