import { getV2, postV2 } from "../core/api.js";

export const COOKIE_SESSION_KEY = "cinescope.sync.cookie.tab";
const DEFAULT_MAX_PAGES = 250;
const MAX_POLL_RETRIES = 4;
const JOB_STATES = new Set(["queued", "running", "complete", "partial", "failed", "needs_cookie"]);
const POLLABLE_STATES = new Set(["queued", "running"]);
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
  storage,
  knownJobIds = [],
  profile = "",
  options = {},
  onStateChange = () => {},
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

  const panel = element("section", "sync-panel");
  panel.dataset.space = "sync";
  const header = element("div", "sync-panel__header");
  header.append(element("h2", "sync-panel__title", "豆瓣同步"), element("p", "sync-panel__copy", "默认自动翻页到末页；安全上限 250 页。Cookie 仅保留在当前标签页会话中。"));
  const form = element("form", "sync-form");
  const profileLabel = element("label", "sync-field");
  profileLabel.append(element("span", "sync-field__label", "豆瓣主页 URL 或用户 ID"));
  const profileInput = element("input", "sync-field__input");
  profileInput.type = "text";
  profileInput.value = typeof profile === "string" ? profile : "";
  profileInput.setAttribute("autocomplete", "url");
  profileLabel.append(profileInput);

  const secretLabel = element("label", "sync-field");
  secretLabel.append(element("span", "sync-field__label", "Cookie（可选，当前标签页）"));
  const secretInput = element("textarea", "sync-field__input sync-field__input--secret");
  secretInput.setAttribute("aria-label", "豆瓣 Cookie");
  secretInput.setAttribute("autocomplete", "off");
  try { secretInput.value = tabStorage?.getItem(COOKIE_SESSION_KEY) || ""; } catch { secretInput.value = ""; }
  secretLabel.append(secretInput);

  const safeOptions = publicOptions(options);
  const optionRow = element("div", "sync-options");
  const includeWish = element("input", "sync-option__control"); includeWish.type = "checkbox"; includeWish.checked = safeOptions.includeWish;
  const wishLabel = element("label", "sync-option", "包含想看"); wishLabel.append(includeWish);
  const includeDo = element("input", "sync-option__control"); includeDo.type = "checkbox"; includeDo.checked = safeOptions.includeDo;
  const doLabel = element("label", "sync-option", "包含在看"); doLabel.append(includeDo);
  optionRow.append(wishLabel, doLabel);
  const submit = element("button", "sync-submit", "开始自动同步"); submit.type = "submit";
  const errorNode = element("p", "sync-error"); errorNode.setAttribute("aria-live", "polite");
  form.append(profileLabel, secretLabel, optionRow, submit, errorNode);
  const jobsRoot = element("div", "sync-jobs");
  panel.append(header, form, jobsRoot);
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

  function statusCopy(job) {
    if (job.incomplete) return "记录不完整，等待完整结果";
    if (job.state === "complete") return "同步完成";
    if (job.state === "partial") return "部分完成";
    if (job.state === "needs_cookie") return "需要登录态后继续";
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
    if (!jobs.size) {
      jobsRoot.append(element("p", "space-empty", "本客户端尚无已知同步任务。"));
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
        const resumeButton = element("button", "sync-job__resume", "继续未完成分页");
        resumeButton.type = "button";
        const onResume = () => { void resume(job.id); };
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

  function acceptJob(payload) {
    const job = publicJob(payload);
    if (!job.id || disposed) return job;
    jobs.set(job.id, job);
    renderJobs();
    return job;
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
      const job = acceptJob({ ...created, id: created?.job_id || created?.id });
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
      const resumed = acceptJob({ ...created, id: created?.job_id || created?.id });
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
  const onOptionsEdit = () => emitState();
  form.addEventListener("submit", onSubmit);
  profileInput.addEventListener("input", onProfileEdit);
  includeWish.addEventListener("change", onOptionsEdit);
  includeDo.addEventListener("change", onOptionsEdit);
  renderJobs();

  const restoredIds = [...new Set(knownJobIds.map(safeJobId).filter(Boolean))];
  for (const id of restoredIds) jobs.set(id, publicJob({ id, state: "queued" }));
  renderJobs();
  const ready = Promise.all(restoredIds.map(refreshJob));

  function dispose() {
    if (disposed) return;
    disposed = true;
    form.removeEventListener("submit", onSubmit);
    profileInput.removeEventListener("input", onProfileEdit);
    includeWish.removeEventListener("change", onOptionsEdit);
    includeDo.removeEventListener("change", onOptionsEdit);
    clearJobListeners();
    for (const jobId of [...timers.keys()]) clearJobTimer(jobId);
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
    elements: { profile: profileInput, cookie: secretInput, includeWish, includeDo, error: errorNode },
    start,
    resume,
    refreshJob,
    acceptJob,
    dispose,
    snapshot: () => ({
      profile: disposed ? "" : publicProfile(profileInput.value),
      options: currentOptions(),
      knownJobIds: disposed ? [] : [...jobs.keys()],
      jobs: disposed ? {} : Object.fromEntries([...jobs].map(([id, job]) => [id, { ...job, diagnostics: job.diagnostics.map((diagnostic) => ({ ...diagnostic })) }])),
      disposed,
    }),
  };
  return api;
}
