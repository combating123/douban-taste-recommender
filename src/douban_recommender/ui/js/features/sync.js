import { deleteV2, getV2, postV2, putV2 } from "../core/api.js";

export const COOKIE_SESSION_KEY = "cinescope.sync.cookie.tab";
const DEFAULT_MAX_PAGES = 250;
const MAX_POLL_RETRIES = 4;
const JOB_STATES = new Set(["queued", "running", "complete", "partial", "failed", "needs_cookie"]);
const POLLABLE_STATES = new Set(["queued", "running"]);
const AUTHORIZATION_POLLABLE_STATES = new Set(["opening_browser", "waiting_for_login", "authorized", "resuming"]);
const DIAGNOSTIC_STATUSES = new Set(["collect", "wish", "do"]);
const RESUMABLE_CLASSIFICATIONS = new Set(["network_error", "login_required", "security_check", "parse_failed_nonempty"]);
const CLASSIFICATION_COPY = Object.freeze({
  network_error: "网络请求失败",
  login_required: "豆瓣需要登录态",
  security_check: "豆瓣触发安全验证",
  parse_failed_nonempty: "页面结构暂时无法解析",
});
const STOP_REASON_COPY = new Map([
  ["已到达空白分页", "已到达列表末页"],
  ["部分分页抓取失败", "部分分页未完成"],
  ["豆瓣要求登录态或 Cookie", "豆瓣需要登录态"],
  ["同步任务失败", "同步任务失败"],
]);
const REQUIRED_COUNTS = ["items", "collect_count", "wish_count", "pages_ok", "pages_failed"];
const SAFE_JOB_ID = /^[A-Za-z0-9_-]{1,128}$/;
const SAFE_USER_ID = /^\d{1,20}$/;
const SAFE_PROFILE_ID = /^[A-Za-z0-9._~-]{1,128}$/;

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function safeStorage(storage) {
  if (storage) return storage;
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function safeJobId(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return SAFE_JOB_ID.test(text) ? text : "";
}

function safeUserId(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return SAFE_USER_ID.test(text) ? text : "";
}

function publicProfile(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (SAFE_PROFILE_ID.test(text)) return text;
  try {
    const url = new URL(text);
    if (url.protocol !== "https:" || !/(^|\.)douban\.com$/i.test(url.hostname)) return "";
    const match = url.pathname.match(/^\/people\/([A-Za-z0-9._~-]{1,128})(?:\/|$)/);
    return match ? `https://www.douban.com/people/${match[1]}/` : "";
  } catch {
    return "";
  }
}

function optionalCount(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : null;
}

function strictCount(value) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function publicOptions(value = {}) {
  const maxPages = Number(value.maxPages);
  return {
    maxPages: Number.isInteger(maxPages) ? Math.max(1, Math.min(DEFAULT_MAX_PAGES, maxPages)) : DEFAULT_MAX_PAGES,
    includeWish: value.includeWish !== false,
    includeDo: Boolean(value.includeDo),
    expectedCollect: optionalCount(value.expectedCollect),
    expectedWish: optionalCount(value.expectedWish),
  };
}

function fixedDiagnostic(value) {
  const diagnostic = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const classification = RESUMABLE_CLASSIFICATIONS.has(diagnostic.classification) ? diagnostic.classification : "unknown";
  return {
    status: DIAGNOSTIC_STATUSES.has(diagnostic.status) ? diagnostic.status : "unknown",
    start: typeof diagnostic.start === "number" && Number.isInteger(diagnostic.start) && diagnostic.start >= 0 ? diagnostic.start : null,
    classification,
    http_status: typeof diagnostic.http_status === "number" && Number.isInteger(diagnostic.http_status) && diagnostic.http_status >= 100 && diagnostic.http_status <= 599
      ? diagnostic.http_status
      : null,
    message: CLASSIFICATION_COPY[classification] || "未提供",
  };
}

function fixedCounts(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const counts = {};
  for (const field of REQUIRED_COUNTS) {
    const count = strictCount(value[field]);
    if (count === null) return null;
    counts[field] = count;
  }
  return counts;
}

function fixedStoppedReason(value, diagnostics) {
  if (typeof value === "string" && STOP_REASON_COPY.has(value)) return STOP_REASON_COPY.get(value);
  const diagnosticCopy = diagnostics.map((diagnostic) => CLASSIFICATION_COPY[diagnostic.classification]).find(Boolean);
  if (diagnosticCopy) return diagnosticCopy;
  return typeof value === "string" && value.trim() ? "已隐藏" : "";
}

function canResumeJob(job) {
  if (!["partial", "failed", "needs_cookie"].includes(job.state)) return false;
  return job.diagnostics.some((diagnostic) => (
    RESUMABLE_CLASSIFICATIONS.has(diagnostic.classification)
    && DIAGNOSTIC_STATUSES.has(diagnostic.status)
    && Number.isInteger(diagnostic.start)
    && diagnostic.start >= 0
  ));
}

function publicJob(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const diagnostics = Array.isArray(source.diagnostics) ? source.diagnostics.slice(0, 24).map(fixedDiagnostic) : [];
  const state = JOB_STATES.has(source.state) ? source.state : "unknown";
  const counts = fixedCounts(source.counts);
  const job = {
    id: safeJobId(source.id || source.job_id),
    state,
    user_id: safeUserId(source.user_id),
    counts,
    stopped_reason: fixedStoppedReason(source.stopped_reason, diagnostics),
    diagnostics,
    errors: Array.isArray(source.errors) ? source.errors.slice(0, 12).map(() => "已隐藏") : [],
    incomplete: state === "complete" && counts === null,
  };
  job.canResume = canResumeJob(job);
  return job;
}

function errorCopy(error, { retrying = false, exhausted = false } = {}) {
  const status = Number(error?.status) || 0;
  if (status === 400) return "HTTP 400 · 请求不可恢复";
  if (status === 404) return "HTTP 404 · 任务不存在";
  if (status >= 500) return exhausted ? `HTTP ${status} · 服务暂时不可用，重试已停止` : `HTTP ${status} · 服务暂时不可用${retrying ? "，将重试" : ""}`;
  return exhausted ? "网络暂时不可用，重试已停止" : `网络暂时不可用${retrying ? "，将重试" : ""}`;
}

function isTransientError(error) {
  const status = Number(error?.status) || 0;
  return status === 0 || status >= 500;
}

export function startDoubanSync(payload, { postJson = postV2, signal } = {}) {
  return postJson("/api/v2/sync/jobs", payload, { signal });
}

export function resumeDoubanSync(jobId, payload, { postJson = postV2, signal } = {}) {
  const id = safeJobId(jobId);
  if (!id) throw new TypeError("Invalid sync job ID");
  return postJson(`/api/v2/sync/jobs/${encodeURIComponent(id)}/resume`, payload, { signal });
}

export function renderSyncPanel(root, {
  fetchJson = getV2,
  postJson = postV2,
  putJson = putV2,
  deleteJson = deleteV2,
  autoSettings = false,
  storage,
  knownJobIds = [],
  profile = "",
  options = {},
  onStateChange = () => {},
  onAutomaticSettingsChange = () => {},
  now = () => Date.now(),
  setTimer = (callback, delay) => setTimeout(callback, delay),
  clearTimer = (id) => clearTimeout(id),
  pollInterval = 1500,
} = {}) {
  if (!root) throw new TypeError("Sync requires a root element");
  const tabStorage = safeStorage(storage);
  const jobs = new Map();
  const timers = new Map();
  const polls = new Map();
  const pollGenerations = new Map();
  const retryAttempts = new Map();
  const mutations = new Set();
  const jobListenerCleanups = [];
  let disposed = false;
  let api = null;
  let automaticSettings = null;
  let authorizationTimer = null;

  const panel = element("section", "sync-panel");
  panel.dataset.space = "sync";
  const header = element("div", "sync-panel__header");
  header.append(element("h2", "sync-panel__title", "豆瓣实时连接"), element("p", "sync-panel__copy", "已连接后由 CineScope 自动同步，无需重复粘贴主页或 Cookie；默认每 60 分钟检查一次。"));
  const automation = element("section", "sync-automation");
  automation.hidden = !autoSettings;
  const automationStatus = element("div", "sync-automation__status");
  const automationTitle = element("strong", "sync-automation__title", "正在读取豆瓣连接…");
  const automationMeta = element("span", "sync-automation__meta", "本地安全连接");
  automationStatus.append(automationTitle, automationMeta);
  const authorizationPanel = element("div", "sync-browser-auth");
  authorizationPanel.hidden = true;
  const authorizationStatus = element("div", "sync-browser-auth__status");
  const authorizationTitle = element("strong", "sync-browser-auth__title", "等待浏览器授权");
  const authorizationMeta = element("span", "sync-browser-auth__meta", "登录完成后将自动续传未完成分页。");
  authorizationStatus.append(authorizationTitle, authorizationMeta);
  const authorizeBrowser = element("button", "sync-submit sync-submit--authorize", "使用浏览器授权并自动继续");
  authorizeBrowser.type = "button";
  authorizationPanel.append(authorizationStatus, authorizeBrowser);
  const automationControls = element("div", "sync-automation__controls");
  const autoEnabled = element("input", "sync-option__control");
  autoEnabled.type = "checkbox";
  const autoEnabledLabel = element("label", "sync-option", "自动同步");
  autoEnabledLabel.append(autoEnabled);
  const intervalLabel = element("label", "sync-field sync-field--compact");
  intervalLabel.append(element("span", "sync-field__label", "同步间隔（分钟）"));
  const autoInterval = element("input", "sync-field__input sync-field__input--compact");
  autoInterval.type = "number";
  autoInterval.min = "15";
  autoInterval.max = "1440";
  autoInterval.value = "60";
  intervalLabel.append(autoInterval);
  const runNow = element("button", "sync-submit sync-submit--run-now", "立即同步");
  runNow.type = "button";
  automationControls.append(autoEnabledLabel, intervalLabel, runNow);
  automation.append(automationStatus, authorizationPanel, automationControls);
  const form = element("form", "sync-form");
  const profileLabel = element("label", "sync-field");
  profileLabel.append(element("span", "sync-field__label", "豆瓣主页 URL 或用户 ID"));
  const profileInput = element("input", "sync-field__input");
  profileInput.type = "text";
  profileInput.value = typeof profile === "string" ? profile : "";
  profileInput.setAttribute("autocomplete", "url");
  profileLabel.append(profileInput);

  const advanced = element("details", "sync-advanced");
  const advancedSummary = element("summary", "sync-advanced__summary", "高级手工恢复（仅在自动授权不可用时）");
  const advancedCopy = element("p", "sync-advanced__copy", "正常情况下请使用上方的一键浏览器授权。只有自动授权不可用时，才在这里手工粘贴 Cookie；它只保留在当前标签页会话中。");
  const secretLabel = element("label", "sync-field sync-field--secret");
  secretLabel.append(element("span", "sync-field__label", "Cookie（可选，当前标签页）"));
  const secretInput = element("textarea", "sync-field__input sync-field__input--secret");
  secretInput.setAttribute("aria-label", "豆瓣 Cookie");
  secretInput.setAttribute("autocomplete", "off");
  try { secretInput.value = tabStorage?.getItem(COOKIE_SESSION_KEY) || ""; } catch { secretInput.value = ""; }
  secretLabel.append(secretInput);
  const guide = element("ol", "sync-cookie-guide");
  for (const step of [
    "在浏览器登录豆瓣并打开自己的主页。",
    "按 F12，进入 Network / 网络，刷新页面。",
    "点开任意 douban.com 请求，在 Request Headers 中复制 Cookie 的完整值。",
    "粘贴到上方输入框后继续同步；同一标签页内会自动保留。",
  ]) guide.append(element("li", "sync-cookie-guide__step", step));
  advanced.append(advancedSummary, advancedCopy, secretLabel, guide);

  const safeOptions = publicOptions(options);
  const optionRow = element("div", "sync-options");
  const includeWish = element("input", "sync-option__control"); includeWish.type = "checkbox"; includeWish.checked = safeOptions.includeWish;
  const wishLabel = element("label", "sync-option", "包含想看"); wishLabel.append(includeWish);
  const includeDo = element("input", "sync-option__control"); includeDo.type = "checkbox"; includeDo.checked = safeOptions.includeDo;
  const doLabel = element("label", "sync-option", "包含在看"); doLabel.append(includeDo);
  optionRow.append(wishLabel, doLabel);
  const submit = element("button", "sync-submit", "开始自动同步"); submit.type = "submit";
  const errorNode = element("p", "sync-error"); errorNode.setAttribute("aria-live", "polite");
  form.append(profileLabel, advanced, optionRow, submit, errorNode);
  const manual = element("details", "sync-manual");
  const manualSummary = element("summary", "sync-manual__summary", "连接恢复与高级抓取");
  manual.append(
    manualSummary,
    element("p", "sync-manual__copy", "默认自动翻页到末页；安全上限 250 页。只有公开访问受限时才需要临时 Cookie。"),
    form,
  );
  const jobsRoot = element("div", "sync-jobs");
  const jobsToolbar = element("div", "sync-jobs__toolbar");
  const clearHistoryButton = element("button", "sync-history-clear", "\u6e05\u9664\u540c\u6b65\u8bb0\u5f55");
  clearHistoryButton.type = "button";
  jobsToolbar.append(clearHistoryButton);
  panel.append(header, automation, manual, jobsToolbar, jobsRoot);
  root.replaceChildren(panel);

  function currentOptions() {
    return { ...safeOptions, includeWish: Boolean(includeWish.checked), includeDo: Boolean(includeDo.checked) };
  }

  function publicState() {
    return { profile: publicProfile(profileInput.value), options: currentOptions(), knownJobIds: [...jobs.keys()] };
  }

  function emitState() {
    if (!disposed) onStateChange(publicState());
  }

  function momentCopy(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds <= 0) return "尚无记录";
    const currentMilliseconds = Number(now());
    const currentSeconds = Number.isFinite(currentMilliseconds) ? currentMilliseconds / 1000 : Date.now() / 1000;
    const deltaSeconds = seconds - currentSeconds;
    const distance = Math.abs(deltaSeconds);
    if (distance < 45) return deltaSeconds >= 0 ? "即将" : "刚刚";
    const units = [
      [30 * 24 * 60 * 60, "个月"],
      [24 * 60 * 60, "天"],
      [60 * 60, "小时"],
      [60, "分钟"],
    ];
    const [unitSeconds, unitLabel] = units.find(([size]) => distance >= size) || units.at(-1);
    const amount = Math.max(1, Math.round(distance / unitSeconds));
    return `约 ${amount} ${unitLabel}${deltaSeconds >= 0 ? "后" : "前"}`;
  }

  function renderBrowserAuthorization(settings = {}) {
    const authorization = settings.authorization && typeof settings.authorization === "object"
      ? settings.authorization
      : {};
    const state = typeof authorization.state === "string" ? authorization.state : "idle";
    const required = settings.last_state === "needs_cookie" || ["opening_browser", "waiting_for_login", "authorized", "resuming", "error"].includes(state);
    authorizationPanel.hidden = !required;
    authorizationPanel.dataset.state = state;
    if (!required) return;
    const copy = {
      opening_browser: ["正在打开专属登录窗口", "窗口打开后只需正常登录豆瓣，无需复制 Cookie。"],
      waiting_for_login: ["等待你在专属窗口完成登录", "检测到登录态后将安全保存，并自动续传未完成分页。"],
      authorized: ["登录态已安全保存", "正在恢复上次中断的分页任务。"],
      resuming: ["正在自动续传未完成分页", "无需再次点击，完成后同步记录会自动更新。"],
      error: ["浏览器授权暂未完成", "可再次打开专属窗口；原同步进度不会丢失。"],
      idle: ["等待浏览器授权", "登录完成后将自动续传未完成分页。"],
    }[state] || ["等待浏览器授权", "登录完成后将自动续传未完成分页。"];
    authorizationTitle.textContent = copy[0];
    authorizationMeta.textContent = copy[1];
    authorizeBrowser.textContent = state === "waiting_for_login" ? "重新聚焦登录窗口" : "使用浏览器授权并自动继续";
    authorizeBrowser.disabled = state === "opening_browser" || state === "authorized" || state === "resuming";
  }

  function renderAutomaticSettings(settings = {}) {
    if (!autoSettings || disposed) return;
    automaticSettings = settings && typeof settings === "object" ? { ...settings } : {};
    const userId = safeUserId(automaticSettings.user_id);
    const enabled = Boolean(automaticSettings.enabled && userId);
    autoEnabled.checked = enabled;
    autoEnabled.disabled = !userId;
    autoInterval.value = String(Math.max(15, Math.min(1440, Number(automaticSettings.interval_minutes) || 60)));
    autoInterval.disabled = !userId;
    runNow.disabled = !userId;
    if (userId && !profileInput.value.trim()) profileInput.value = userId;
    automation.dataset.state = userId ? (enabled ? "connected" : "paused") : "disconnected";
    automationTitle.textContent = userId
      ? `${enabled ? "自动同步已开启" : "自动同步已暂停"} · 用户 ${userId}`
      : "尚未连接豆瓣用户";
    automationMeta.textContent = userId
      ? `上次成功：${momentCopy(automaticSettings.last_success_at)} · 下次检查：${momentCopy(automaticSettings.next_run_at)}`
      : "展开“连接恢复与高级抓取”完成首次连接。";
    renderBrowserAuthorization(automaticSettings);
    onAutomaticSettingsChange({ ...automaticSettings, user_id: userId, enabled });
  }

  function clearAuthorizationTimer() {
    if (authorizationTimer !== null) clearTimer(authorizationTimer);
    authorizationTimer = null;
  }

  function scheduleAuthorizationPoll(status = {}) {
    clearAuthorizationTimer();
    const state = typeof status.state === "string" ? status.state : "idle";
    if (disposed || !AUTHORIZATION_POLLABLE_STATES.has(state)) return;
    authorizationTimer = setTimer(() => {
      authorizationTimer = null;
      void refreshBrowserAuthorization();
    }, Math.min(1000, pollInterval));
  }

  function adoptAuthorizationStatus(status = {}) {
    const cleanStatus = status && typeof status === "object" ? { ...status } : { state: "error" };
    automaticSettings = { ...(automaticSettings || {}), authorization: cleanStatus };
    renderAutomaticSettings(automaticSettings);
    const state = typeof cleanStatus.state === "string" ? cleanStatus.state : "idle";
    const jobId = safeJobId(cleanStatus.job_id);
    if (jobId && JOB_STATES.has(state)) {
      const job = acceptJob({ ...cleanStatus, id: jobId, state }, { replace: true });
      if (POLLABLE_STATES.has(job.state)) schedule(job.id);
      authorizationTitle.textContent = POLLABLE_STATES.has(job.state) ? "正在自动续传未完成分页" : statusCopy(job);
      authorizationMeta.textContent = POLLABLE_STATES.has(job.state)
        ? "登录态已安全接管，正在恢复上次中断的同步进度。"
        : "同步记录已更新。";
    }
    scheduleAuthorizationPoll(cleanStatus);
    return cleanStatus;
  }

  async function refreshBrowserAuthorization() {
    if (!autoSettings || disposed) return null;
    const controller = new AbortController();
    mutations.add(controller);
    try {
      const status = await fetchJson("/api/v2/sync/browser-auth", { signal: controller.signal });
      if (disposed || controller.signal.aborted) return null;
      return adoptAuthorizationStatus(status);
    } catch (error) {
      if (!disposed && !controller.signal.aborted) {
        errorNode.textContent = errorCopy(error, { retrying: true });
        scheduleAuthorizationPoll({ state: "waiting_for_login" });
      }
      return null;
    } finally {
      mutations.delete(controller);
    }
  }

  async function startBrowserAuthorization() {
    if (!autoSettings || disposed) return null;
    const controller = new AbortController();
    mutations.add(controller);
    errorNode.textContent = "";
    authorizationPanel.hidden = false;
    authorizationPanel.dataset.state = "opening_browser";
    authorizationTitle.textContent = "正在打开专属登录窗口";
    authorizationMeta.textContent = "窗口打开后只需正常登录豆瓣，无需复制 Cookie。";
    authorizeBrowser.disabled = true;
    try {
      const status = await postJson("/api/v2/sync/browser-auth", {}, { signal: controller.signal });
      if (disposed || controller.signal.aborted) return null;
      return adoptAuthorizationStatus(status);
    } catch (error) {
      if (!disposed && !controller.signal.aborted) {
        errorNode.textContent = errorCopy(error);
        renderBrowserAuthorization({ ...(automaticSettings || {}), last_state: "needs_cookie", authorization: { state: "error" } });
      }
      return null;
    } finally {
      mutations.delete(controller);
    }
  }

  async function loadAutomaticSettings() {
    if (!autoSettings || disposed) return null;
    try {
      const settings = await fetchJson("/api/v2/sync/settings");
      if (disposed) return null;
      renderAutomaticSettings(settings);
      const latestSuccessfulJobId = String(settings?.last_state || "") === "complete"
        ? safeJobId(settings?.last_job_id)
        : "";
      if (latestSuccessfulJobId && !jobs.has(latestSuccessfulJobId)) await refreshJob(latestSuccessfulJobId);
      return settings;
    } catch {
      if (!disposed) {
        automationTitle.textContent = "豆瓣自动连接暂时不可用";
        automationMeta.textContent = "仍可展开高级抓取手动重试。";
        automation.dataset.state = "error";
      }
      return null;
    }
  }

  async function saveAutomaticSettings() {
    if (!autoSettings || disposed || typeof putJson !== "function") return null;
    autoEnabled.disabled = true;
    autoInterval.disabled = true;
    try {
      const settings = await putJson("/api/v2/sync/settings", {
        enabled: Boolean(autoEnabled.checked),
        interval_minutes: Math.max(15, Math.min(1440, Number(autoInterval.value) || 60)),
      });
      if (!disposed) renderAutomaticSettings(settings);
      return settings;
    } catch (error) {
      if (!disposed) errorNode.textContent = errorCopy(error);
      return null;
    } finally {
      if (!disposed) renderAutomaticSettings(automaticSettings || {});
    }
  }

  async function runAutomaticSync() {
    if (!autoSettings || disposed) return null;
    runNow.disabled = true;
    errorNode.textContent = "";
    try {
      const created = await postJson("/api/v2/sync/run-now", {});
      if (disposed) return null;
      const job = acceptJob({ ...created, id: created?.job_id || created?.id }, { replace: true });
      automaticSettings = { ...(automaticSettings || {}), last_state: job.state };
      if (job.state === "needs_cookie" || created?.authorization_required) {
        renderAutomaticSettings(automaticSettings);
        await startBrowserAuthorization();
        return job;
      }
      schedule(job.id);
      automationTitle.textContent = created?.reused ? "同步已在进行中" : "已启动实时同步";
      automationMeta.textContent = "正在读取最新看过、想看和评分数据。";
      return job;
    } catch (error) {
      if (!disposed) errorNode.textContent = errorCopy(error);
      return null;
    } finally {
      if (!disposed) runNow.disabled = !safeUserId(automaticSettings?.user_id);
    }
  }

  function statusCopy(job) {
    if (job.incomplete) return "记录不完整，等待完整结果";
    if (job.state === "complete") return "同步完成";
    if (job.state === "partial") return "部分完成";
    if (job.state === "needs_cookie") return "等待浏览器授权";
    if (job.state === "failed") return "同步失败";
    if (job.state === "running") return "同步进行中";
    if (job.state === "queued") return "等待执行";
    return "状态未提供";
  }

  function clearJobListeners() {
    while (jobListenerCleanups.length) jobListenerCleanups.pop()();
  }

  function renderJobs() {
    if (disposed) return;
    clearJobListeners();
    jobsRoot.replaceChildren();
    clearHistoryButton.hidden = !jobs.size;
    if (!jobs.size) {
      jobsRoot.append(element("p", "space-empty", "\u6682\u65e0\u540c\u6b65\u8bb0\u5f55"));
      return;
    }
    for (const job of jobs.values()) {
      const card = element("article", "sync-job");
      card.dataset.jobId = job.id;
      const title = element("h3", "sync-job__title", job.user_id ? `用户 ${job.user_id}` : `任务 ${job.id}`);
      const stateNode = element("p", "sync-job__state", statusCopy(job));
      const counts = job.counts
        ? element("p", "sync-job__counts", `条目 ${job.counts.items} · 看过 ${job.counts.collect_count} · 想看 ${job.counts.wish_count} · 成功页 ${job.counts.pages_ok} · 失败页 ${job.counts.pages_failed}`)
        : element("p", "sync-job__counts", "结果数值未提供");
      card.append(title, stateNode, counts);
      if (job.stopped_reason) card.append(element("p", "sync-job__reason", job.stopped_reason));
      if (job.canResume) {
        const useBrowserAuthorization = autoSettings && job.state === "needs_cookie";
        const resumeButton = element(
          "button",
          "sync-job__resume",
          useBrowserAuthorization ? "使用浏览器授权并自动继续" : "继续未完成分页",
        );
        resumeButton.type = "button";
        const onResume = () => {
          if (useBrowserAuthorization) {
            automaticSettings = { ...(automaticSettings || {}), last_state: "needs_cookie", last_job_id: job.id };
            renderAutomaticSettings(automaticSettings);
            void startBrowserAuthorization();
          } else {
            void resume(job.id);
          }
        };
        resumeButton.addEventListener("click", onResume);
        jobListenerCleanups.push(() => resumeButton.removeEventListener("click", onResume));
        card.append(resumeButton);
      }
      jobsRoot.append(card);
    }
  }

  function clearJobTimer(jobId) {
    const timer = timers.get(jobId);
    if (timer !== undefined) clearTimer(timer);
    timers.delete(jobId);
  }

  function schedule(jobId, delay = pollInterval) {
    const job = jobs.get(jobId);
    if (disposed || !job || !POLLABLE_STATES.has(job.state) || timers.has(jobId)) return;
    const timer = setTimer(() => {
      timers.delete(jobId);
      void refreshJob(jobId);
    }, delay);
    timers.set(jobId, timer);
  }

  function discardKnownJobs() {
    for (const jobId of [...jobs.keys()]) clearJobTimer(jobId);
    for (const controller of polls.values()) controller.abort();
    polls.clear();
    retryAttempts.clear();
    pollGenerations.clear();
    jobs.clear();
  }

  function acceptJob(payload, { replace = false } = {}) {
    const job = publicJob(payload);
    if (!job.id || disposed) return job;
    if (replace) discardKnownJobs();
    jobs.set(job.id, job);
    renderJobs();
    return job;
  }

  async function clearHistory() {
    if (disposed || typeof deleteJson !== "function") return null;
    const controller = new AbortController();
    mutations.add(controller);
    clearHistoryButton.disabled = true;
    errorNode.textContent = "";
    try {
      const result = await deleteJson("/api/v2/sync/jobs", { signal: controller.signal });
      if (disposed || controller.signal.aborted) return null;
      discardKnownJobs();
      renderJobs();
      emitState();
      return result;
    } catch (error) {
      if (!disposed && !controller.signal.aborted) errorNode.textContent = errorCopy(error);
      return null;
    } finally {
      mutations.delete(controller);
      if (!disposed) clearHistoryButton.disabled = false;
    }
  }

  function syncVisibleCookie(secret) {
    try {
      if (secret) tabStorage?.setItem(COOKIE_SESSION_KEY, secret);
      else tabStorage?.removeItem?.(COOKIE_SESSION_KEY);
    } catch {
      // Same-tab storage is optional; the visible textarea remains usable.
    }
  }

  async function refreshJob(rawJobId) {
    const jobId = safeJobId(rawJobId);
    if (!jobId || disposed) return null;
    clearJobTimer(jobId);
    polls.get(jobId)?.abort();
    const controller = new AbortController();
    polls.set(jobId, controller);
    const requestGeneration = (pollGenerations.get(jobId) || 0) + 1;
    pollGenerations.set(jobId, requestGeneration);
    try {
      const payload = await fetchJson(`/api/v2/sync/jobs/${encodeURIComponent(jobId)}`, { signal: controller.signal });
      if (disposed || controller.signal.aborted || pollGenerations.get(jobId) !== requestGeneration) return null;
      retryAttempts.delete(jobId);
      errorNode.textContent = "";
      const job = acceptJob({ ...payload, id: payload?.id || payload?.job_id || jobId });
      schedule(jobId);
      return job;
    } catch (error) {
      if (disposed || controller.signal.aborted || pollGenerations.get(jobId) !== requestGeneration) return null;
      const job = jobs.get(jobId);
      if (isTransientError(error) && job && POLLABLE_STATES.has(job.state)) {
        const attempt = (retryAttempts.get(jobId) || 0) + 1;
        retryAttempts.set(jobId, attempt);
        const exhausted = attempt > MAX_POLL_RETRIES;
        errorNode.textContent = errorCopy(error, { retrying: !exhausted, exhausted });
        if (!exhausted) schedule(jobId, Math.min(30000, pollInterval * (2 ** (attempt - 1))));
      } else {
        retryAttempts.delete(jobId);
        errorNode.textContent = errorCopy(error);
      }
      return null;
    } finally {
      if (polls.get(jobId) === controller) polls.delete(jobId);
    }
  }

  async function start() {
    if (disposed) return null;
    const visibleUser = profileInput.value.trim();
    const user = publicProfile(visibleUser);
    const secret = secretInput.value;
    if (!visibleUser || !user) {
      errorNode.textContent = visibleUser ? "请输入有效的豆瓣主页 URL 或用户 ID。" : "请输入豆瓣主页 URL 或用户 ID。";
      return null;
    }
    syncVisibleCookie(secret);
    const selected = currentOptions();
    const payload = {
      user,
      cookie: secret,
      max_pages: selected.maxPages,
      include_wish: selected.includeWish,
      include_do: selected.includeDo,
      expected_collect: selected.expectedCollect,
      expected_wish: selected.expectedWish,
    };
    const controller = new AbortController();
    mutations.add(controller);
    submit.disabled = true;
    errorNode.textContent = "";
    try {
      const created = await startDoubanSync(payload, { postJson, signal: controller.signal });
      if (disposed || controller.signal.aborted) return null;
      const job = acceptJob({ ...created, id: created?.job_id || created?.id }, { replace: true });
      emitState();
      schedule(job.id);
      return job;
    } catch (error) {
      if (!disposed && !controller.signal.aborted) errorNode.textContent = errorCopy(error);
      return null;
    } finally {
      mutations.delete(controller);
      if (!disposed) submit.disabled = false;
    }
  }

  async function resume(rawJobId) {
    const jobId = safeJobId(rawJobId);
    const previous = jobs.get(jobId);
    if (!jobId || !previous?.canResume || disposed) return null;
    const secret = secretInput.value;
    syncVisibleCookie(secret);
    const controller = new AbortController();
    mutations.add(controller);
    errorNode.textContent = "";
    try {
      const created = await resumeDoubanSync(jobId, { cookie: secret }, { postJson, signal: controller.signal });
      if (disposed || controller.signal.aborted) return null;
      const resumed = acceptJob({ ...created, id: created?.job_id || created?.id }, { replace: true });
      emitState();
      schedule(resumed.id);
      return resumed;
    } catch (error) {
      if (!disposed && !controller.signal.aborted) errorNode.textContent = errorCopy(error);
      return null;
    } finally {
      mutations.delete(controller);
    }
  }

  function onSubmit(event) {
    event.preventDefault();
    void start();
  }
  const onProfileEdit = () => emitState();
  const onSecretEdit = () => syncVisibleCookie(secretInput.value);
  const onOptionsEdit = () => emitState();
  const onAutomaticEdit = () => { void saveAutomaticSettings(); };
  const onRunNow = () => { void runAutomaticSync(); };
  const onAuthorizeBrowser = () => { void startBrowserAuthorization(); };
  form.addEventListener("submit", onSubmit);
  profileInput.addEventListener("input", onProfileEdit);
  secretInput.addEventListener("input", onSecretEdit);
  includeWish.addEventListener("change", onOptionsEdit);
  includeDo.addEventListener("change", onOptionsEdit);
  autoEnabled.addEventListener("change", onAutomaticEdit);
  autoInterval.addEventListener("change", onAutomaticEdit);
  runNow.addEventListener("click", onRunNow);
  authorizeBrowser.addEventListener("click", onAuthorizeBrowser);
  clearHistoryButton.addEventListener("click", clearHistory);
  renderJobs();

  const restoredIds = [...new Set(knownJobIds.map(safeJobId).filter(Boolean))].slice(-1);
  for (const id of restoredIds) jobs.set(id, publicJob({ id, state: "queued" }));
  renderJobs();
  const ready = Promise.all([
    ...restoredIds.map(refreshJob),
    ...(autoSettings ? [loadAutomaticSettings()] : []),
  ]);

  function dispose() {
    if (disposed) return;
    syncVisibleCookie(secretInput.value);
    disposed = true;
    form.removeEventListener("submit", onSubmit);
    profileInput.removeEventListener("input", onProfileEdit);
    secretInput.removeEventListener("input", onSecretEdit);
    includeWish.removeEventListener("change", onOptionsEdit);
    includeDo.removeEventListener("change", onOptionsEdit);
    autoEnabled.removeEventListener("change", onAutomaticEdit);
    autoInterval.removeEventListener("change", onAutomaticEdit);
    runNow.removeEventListener("click", onRunNow);
    authorizeBrowser.removeEventListener("click", onAuthorizeBrowser);
    clearHistoryButton.removeEventListener("click", clearHistory);
    clearJobListeners();
    for (const jobId of [...timers.keys()]) clearJobTimer(jobId);
    clearAuthorizationTimer();
    for (const controller of polls.values()) controller.abort();
    for (const controller of mutations) controller.abort();
    polls.clear();
    mutations.clear();
    retryAttempts.clear();
    pollGenerations.clear();
    jobs.clear();
    secretInput.value = "";
    errorNode.textContent = "";
    jobsRoot.replaceChildren();
    root.replaceChildren();
    if (api) api.elements = null;
  }

  api = {
    ready,
    elements: {
      profile: profileInput,
      cookie: secretInput,
      includeWish,
      includeDo,
      autoEnabled,
      autoInterval,
      runNow,
      authorizeBrowser,
      clearHistory: clearHistoryButton,
      error: errorNode,
    },
    start,
    startBrowserAuthorization,
    refreshBrowserAuthorization,
    resume,
    clearHistory,
    refreshJob,
    acceptJob,
    dispose,
    snapshot: () => ({
      profile: disposed ? "" : publicProfile(profileInput.value),
      options: currentOptions(),
      knownJobIds: disposed ? [] : [...jobs.keys()],
      jobs: disposed ? {} : Object.fromEntries([...jobs].map(([id, job]) => [id, { ...job, diagnostics: job.diagnostics.map((diagnostic) => ({ ...diagnostic })) }])),
      automatic: disposed || !autoSettings || !automaticSettings ? null : {
        user_id: safeUserId(automaticSettings.user_id),
        enabled: Boolean(automaticSettings.enabled),
        interval_minutes: Number(automaticSettings.interval_minutes) || 60,
        last_state: typeof automaticSettings.last_state === "string" ? automaticSettings.last_state : "",
      },
      disposed,
    }),
  };
  return api;
}
