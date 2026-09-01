import { getV2, postV2, putV2 } from "../core/api.js";
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

const JOB_STATE_LABELS = Object.freeze({
  queued: "排队",
  pending: "等待",
  processing: "处理中",
  resolving: "解析中",
  downloading: "下载中",
  validating: "校验中",
  ready: "已就绪",
  degraded: "已降级",
  failed: "失败",
  unavailable: "不可用",
  missing: "缺失",
  ambiguous: "需确认",
});

function jobStateLabel(value) {
  const state = typeof value === "string" ? value.trim().toLowerCase() : "";
  return JOB_STATE_LABELS[state] || "其他状态";
}

function renderDiscoveryStatus(value) {
  const discovery = objectValue(value);
  const counts = objectValue(discovery.source_counts);
  const config = objectValue(discovery.config);
  const labels = { tmdb: "TMDb", omdb: "IMDb", tvmaze: "TVMaze", anilist: "AniList", jikan: "MAL", apple_movies: "Apple TV" };
  const panel = element("section", "discovery-health");
  const heading = element("div", "discovery-health__heading");
  const statusLabels = {
    complete: "在线补充已就绪",
    partial: "部分在线来源已就绪",
    failed: "在线来源暂不可用",
    unavailable: "等待配置在线来源",
    disabled: "在线补充未启用",
    "local-index": "当前仅使用本机片库",
  };
  heading.append(
    element("div", "discovery-health__copy", "在线候选源与本地片库"),
    element("span", "discovery-health__status", statusLabels[discovery.status] || "尚未创建推荐会话"),
  );

  const metrics = element("div", "discovery-health__metrics");
  metrics.append(
    element("strong", "discovery-health__metric", `本机片库 ${countText(discovery.local_index_size)}`),
    element("strong", "discovery-health__metric", `本次在线补充 ${countText(discovery.live_size)}`),
  );

  const flow = element("div", "discovery-health__flow");
  const flowSteps = [
    ["在线来源", "创建推荐或资料缺失时按需请求"],
    ["身份与质量筛选", "先核对同名作品、媒介与图片身份"],
    ["本次推荐", "只让通过筛选的候选参与排序"],
    ["本地片库与图片缓存", "结果、映射与验证图片留在本机"],
  ];
  for (const [index, [title, copy]] of flowSteps.entries()) {
    const step = element("article", "discovery-health__step");
    step.append(
      element("span", "discovery-health__step-index", String(index + 1).padStart(2, "0")),
      element("strong", "discovery-health__step-title", title),
      element("span", "discovery-health__step-copy", copy),
    );
    flow.append(step);
  }

  const sourceGroup = element("div", "discovery-health__source-group");
  sourceGroup.append(element("strong", "discovery-health__source-label", "本次在线来源"));
  const sources = element("div", "discovery-health__sources");
  for (const [source, count] of Object.entries(counts)) {
    if (!Number.isInteger(count) || count < 0) continue;
    sources.append(element("span", "discovery-health__source", `${labels[source] || source} ${count}`));
  }
  if (!sources.children.length) {
    sources.append(element("span", "discovery-health__source", "创建一次推荐后，这里会显示本次在线补充了多少候选。"));
  }
  sourceGroup.append(sources);

  const keyState = [];
  if (config.tmdb_configured === true) keyState.push("TMDb 已配置");
  if (config.omdb_configured === true) keyState.push("OMDb / IMDb 已配置");
  panel.append(
    heading,
    element(
      "p",
      "discovery-health__intro",
      "搜索和详情主体优先读取本机 SQLite 片库；只有创建推荐、补齐缺失资料或首次读取尚未缓存的图片时才按需联网。",
    ),
    metrics,
    flow,
    sourceGroup,
    element("p", "discovery-health__note", keyState.length
      ? `${keyState.join(" · ")}；TVMaze、AniList、MAL 无需 API Key。`
      : "TVMaze、AniList、MAL 可免 Key 使用；配置免费 TMDb / OMDb Key 后可扩展电影与 IMDb 候选。"),
    element(
      "p",
      "discovery-health__storage-note",
      "身份映射、推荐会话和已验证图片缓存保存在本机；在线候选不会未经筛选直接写入片库。",
    ),
  );
  return panel;
}

const WAITING_JOB_STATES = Object.freeze(["queued", "pending", "processing", "resolving", "downloading", "validating"]);
const FAILED_JOB_STATES = Object.freeze(["failed", "unavailable", "missing"]);

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function hasOwn(value, key) {
  return isRecord(value) && Object.prototype.hasOwnProperty.call(value, key);
}

function observedKindCount(byKind, aliases, known) {
  if (!known) return null;
  for (const alias of aliases) {
    if (!hasOwn(byKind, alias)) continue;
    return observedCount(byKind[alias]);
  }
  return 0;
}

function observedStateTotal(jobs, states, known) {
  if (!known) return null;
  let total = 0;
  for (const state of states) {
    if (!hasOwn(jobs, state)) continue;
    const count = observedCount(jobs[state]);
    if (count === null) return null;
    total += count;
  }
  return total;
}

function assetMetric(label, value, detail, tone = "neutral") {
  const card = element("article", `health-asset-card health-asset-card--${tone}`);
  card.append(
    element("span", "health-asset-card__label", label),
    element("strong", "health-asset-card__value", value),
    element("span", "health-asset-card__detail", detail),
  );
  return card;
}

function renderHealthMetrics(root, mediaPayload, diagnosticsPayload, {
  mediaSettled = false,
  diagnosticsSettled = false,
  onRepairAssets = null,
  onAuthorizeBrowser = null,
} = {}) {
  root.replaceChildren();
  const media = objectValue(mediaPayload);
  const diagnostics = objectValue(diagnosticsPayload);
  const mediaAssets = objectValue(media.assets);
  const diagnosticAssets = objectValue(diagnostics.media_totals);
  const byKind = objectValue(mediaAssets.by_kind);
  const byKindKnown = hasOwn(mediaAssets, "by_kind") && isRecord(mediaAssets.by_kind);
  const posterCount = observedKindCount(byKind, ["poster"], byKindKnown);
  const backdropCount = observedKindCount(byKind, ["backdrop", "still"], byKindKnown);
  const assetTotal = observedCount(mediaAssets.total) ?? observedCount(diagnosticAssets.assets_total);
  const assetBytes = observedCount(mediaAssets.bytes) ?? observedCount(diagnosticAssets.bytes);
  const cacheBytes = observedCount(diagnostics.cache_bytes);

  const persistentQueue = objectValue(diagnostics.persistent_queue_states);
  const mediaJobs = objectValue(media.jobs);
  const persistentQueueKnown = hasOwn(diagnostics, "persistent_queue_states") && isRecord(diagnostics.persistent_queue_states);
  const mediaJobsKnown = hasOwn(media, "jobs") && isRecord(media.jobs);
  const usePersistentQueue = Object.keys(persistentQueue).length > 0 || (!mediaJobsKnown && persistentQueueKnown);
  const jobs = usePersistentQueue ? persistentQueue : mediaJobs;
  const jobsKnown = usePersistentQueue ? persistentQueueKnown : mediaJobsKnown;
  const jobsSettled = usePersistentQueue ? diagnosticsSettled : mediaSettled;
  const waitingTotal = observedStateTotal(jobs, WAITING_JOB_STATES, jobsKnown);
  const failedTotal = observedStateTotal(jobs, FAILED_JOB_STATES, jobsKnown);

  const provider = objectValue(diagnostics.provider_attempt_health);
  const providerAttempts = provider.basis === "historical_attempts" ? observedCount(provider.attempts_total) : null;
  const audit = objectValue(diagnostics.media_audit);
  const observabilityLimits = objectValue(diagnostics.observability_limits);
  const auditWindow = objectValue(observabilityLimits.media_audit_window);
  const auditTotal = observedCount(audit.total);
  const auditReady = observedCount(audit.ready);
  const auditWindowRows = observedCount(auditWindow.rows_audited);
  const auditWindowBatches = observedCount(auditWindow.selected_batches);
  const auditWindowKnown = auditWindow.scope === "recent_recommendation_batches"
    && auditWindowRows !== null
    && auditWindowRows === auditTotal;
  const auditDetails = auditWindowKnown ? [
    ["降级", observedCount(audit.degraded)],
    ["歧义", observedCount(audit.ambiguous)],
    ["缺失", observedCount(audit.missing)],
  ].filter((entry) => entry[1] !== null).map(([label, count]) => `${label} ${count}`) : [];
  if (auditWindowKnown) {
    auditDetails.push(`${auditWindowBatches === null ? "—" : auditWindowBatches} 个最近批次`, `${auditWindowRows} 行`);
    if (auditWindow.truncated === true) auditDetails.push("窗口已截断");
    auditDetails.push("仅供历史排查，不代表当前页面缺图");
  }
  const wrongIdentityScopeKnown = observabilityLimits.wrong_identity_candidates_scope === "global_historical_identity_rejected_hard_conflicts"
    && observabilityLimits.recommendation_media_identity_attribution === "unavailable_without_stable_foreign_key";
  const wrongIdentityCandidates = wrongIdentityScopeKnown ? observedCount(audit.wrong_identity_candidates) : null;
  const appVersion = typeof diagnostics.app_version === "string" && diagnostics.app_version && diagnostics.app_version !== "unknown"
    ? diagnostics.app_version
    : null;

  const header = element("div", "health-assets__header");
  const copy = element("div", "health-assets__copy");
  copy.append(
    element("p", "health-assets__eyebrow", "MEDIA READINESS"),
    element("h2", "health-assets__title", "素材可用度"),
  );
  header.append(
    copy,
    element("p", "health-assets__meta", "优先呈现当前片库状态；历史样本与内部队列默认折叠。"),
  );

  const grid = element("div", "health-assets__grid");
  grid.append(
    assetMetric(
      "海报可用",
      countText(posterCount),
      posterCount === null ? (mediaSettled ? "尚未提供" : "正在读取") : "已绑定本地可用海报",
      "ready",
    ),
    assetMetric(
      "剧照可用",
      countText(backdropCount),
      backdropCount === null ? (mediaSettled ? "尚未提供" : "正在读取") : "已绑定本地可用剧照",
      "ready",
    ),
    assetMetric(
      "本地缓存",
      countText(assetTotal),
      `素材 ${assetBytes === null ? (mediaSettled ? "尚未提供" : "正在读取") : bytesText(assetBytes)} · 运行缓存 ${cacheBytes === null ? (diagnosticsSettled ? "尚未提供" : "正在读取") : bytesText(cacheBytes)}`,
      "cache",
    ),
    assetMetric(
      "等待修复",
      countText(waitingTotal),
      waitingTotal === null ? (jobsSettled ? "尚未提供" : "正在读取") : (waitingTotal > 0 ? "排队、解析或下载中的任务" : "当前没有待处理任务"),
      waitingTotal && waitingTotal > 0 ? "attention" : "calm",
    ),
    assetMetric(
      "确认失效",
      countText(failedTotal),
      failedTotal === null ? (jobsSettled ? "尚未提供" : "正在读取") : (failedTotal > 0 ? "失败、不可用或缺失的任务" : "当前没有确认失效素材"),
      failedTotal && failedTotal > 0 ? "danger" : "calm",
    ),
  );

  const actions = element("div", "health-assets__actions");
  const repair = element("a", "health-assets__action health-assets__action--primary", "检查并修复素材");
  repair.setAttribute("href", "/library");
  repair.setAttribute("data-route", "");
  repair.addEventListener("click", (event) => {
    if (typeof onRepairAssets !== "function") return;
    event.preventDefault?.();
    onRepairAssets();
  });
  const authorize = element("button", "health-assets__action health-assets__action--secondary", "浏览器授权并自动续传");
  authorize.type = "button";
  authorize.addEventListener("click", () => {
    if (typeof onAuthorizeBrowser === "function") onAuthorizeBrowser();
  });
  actions.append(repair, authorize);

  const advanced = element("details", "health-advanced");
  advanced.open = false;
  advanced.append(element("summary", "health-advanced__summary", "高级诊断"));
  const advancedGrid = element("div", "health-advanced__grid");
  advancedGrid.append(
    metric(
      "历史审计",
      auditWindowKnown && auditReady !== null ? `${auditReady} / ${auditTotal}` : "—",
      auditDetails.join(" · ") || (diagnosticsSettled ? "尚未提供" : "正在读取"),
    ),
    metric(
      "身份冲突",
      wrongIdentityCandidates === null ? "—" : countText(wrongIdentityCandidates),
      wrongIdentityCandidates === null ? (diagnosticsSettled ? "尚未提供" : "正在读取") : "历史聚合，无法归属当前推荐卡片",
    ),
    metric(
      "图源尝试",
      providerAttempts === null ? "—" : countText(providerAttempts),
      providerAttempts === null ? (diagnosticsSettled ? "尚未提供" : "正在读取") : "历史请求记录",
    ),
  );
  const jobCard = element("article", "health-metric health-metric--jobs");
  jobCard.append(element("span", "health-metric__label", "任务明细"));
  const entries = Object.entries(jobs).filter(([, count]) => observedCount(count) === null || count > 0);
  if (entries.length) {
    for (const [state, count] of entries) jobCard.append(element("span", "health-job-state", `${jobStateLabel(state)} ${countText(count)}`));
  } else {
    jobCard.append(element("span", "health-metric__detail", jobsKnown ? "尚无媒体任务" : (jobsSettled ? "尚未提供" : "正在读取")));
  }
  advancedGrid.append(
    jobCard,
    metric(
      "版本信息",
      appVersion || "—",
      appVersion
        ? (media.delivery === "local-only" ? "本机素材服务 · 应用版本" : "应用版本")
        : (media.delivery === "local-only" ? "素材仅在本机保存和提供" : (diagnosticsSettled ? "尚未提供" : "正在读取")),
    ),
  );
  advanced.append(advancedGrid);
  root.append(header, grid, actions, advanced);
}

let activeController = null;

export function renderHealth(root, {
  fetchJson = getV2,
  postJson = postV2,
  putJson = putV2,
  autoSyncSettings = false,
  syncState = {},
  personalization = {},
  discovery = {},
  onSyncStateChange = () => {},
  onRepairAssets = null,
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
  copy.append(element("p", "eyebrow", "本地服务状态"), element("h1", "space-title", "健康与同步"));
  header.append(copy, element("p", "space-summary", "同步入口与本地素材诊断集中在这里。遇到登录限制时会打开专属浏览器并自动续传，缺失诊断始终保持未知。"));
  const connected = element("section", "sync-connected");
  const knownUserId = typeof personalization?.user_id === "string" && /^\d{1,20}$/.test(personalization.user_id)
    ? personalization.user_id
    : "";
  const watched = Number.isInteger(personalization?.watched_count) && personalization.watched_count >= 0 ? personalization.watched_count : null;
  const wish = Number.isInteger(personalization?.wish_count) && personalization.wish_count >= 0 ? personalization.wish_count : null;
  const renderConnected = (rawUserId = "") => {
    const userId = typeof rawUserId === "string" && /^\d{1,20}$/.test(rawUserId) ? rawUserId : "";
    connected.replaceChildren();
    if (userId) {
      connected.dataset.state = "connected";
      connected.append(
        element("span", "sync-connected__signal", "已连接豆瓣"),
        element("strong", "sync-connected__identity", `用户 ${userId}`),
        element("span", "sync-connected__counts", `${watched ?? "—"} 部看过 · ${wish ?? "—"} 部想看`),
      );
      return;
    }
    connected.dataset.state = "idle";
    connected.append(
      element("span", "sync-connected__signal", "等待连接"),
      element("span", "sync-connected__counts", "连接豆瓣用户后即可自动同步；需要登录时会打开专属浏览器。"),
    );
  };
  renderConnected(knownUserId);
  const mediaRoot = element("section", "health-assets");
  const syncRoot = element("div", "health-sync");
  let sync = null;
  const authorizeBrowser = () => {
    void sync?.startBrowserAuthorization?.();
  };
  const renderOptions = () => ({
    mediaSettled: healthState.mediaSettled,
    diagnosticsSettled: healthState.diagnosticsSettled,
    onRepairAssets,
    onAuthorizeBrowser: authorizeBrowser,
  });
  const healthState = {
    media: null,
    diagnostics: null,
    mediaSettled: false,
    diagnosticsSettled: false,
  };
  renderHealthMetrics(mediaRoot, null, null, renderOptions());
  section.append(header, connected, renderDiscoveryStatus(discovery), mediaRoot, syncRoot);
  root.replaceChildren(section);

  sync = renderSyncPanel(syncRoot, {
    fetchJson,
    postJson,
    putJson,
    autoSettings: autoSyncSettings,
    knownJobIds: Array.isArray(syncState.knownJobIds) ? syncState.knownJobIds : [],
    profile: syncState.profile || knownUserId,
    options: syncState.options || {},
    onStateChange: onSyncStateChange,
    onAutomaticSettingsChange: (settings) => {
      const settingsUserId = typeof settings?.user_id === "string" ? settings.user_id : "";
      renderConnected(settingsUserId || knownUserId);
    },
    ...(setTimer ? { setTimer } : {}),
    ...(clearTimer ? { clearTimer } : {}),
    ...(pollInterval ? { pollInterval } : {}),
  });

  const refreshHealth = () => {
    if (disposed || controller.signal.aborted) return;
    renderHealthMetrics(mediaRoot, healthState.media, healthState.diagnostics, renderOptions());
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
