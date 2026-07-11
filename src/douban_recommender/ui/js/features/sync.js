import { getV2, postV2 } from "../core/api.js";

export const COOKIE_SESSION_KEY = "cinescope.sync.cookie.tab";
const DEFAULT_MAX_PAGES = 250;
const TERMINAL_STATES = new Set(["complete", "partial", "failed", "needs_cookie"]);
const RESUMABLE_CLASSIFICATIONS = new Set(["network_error", "login_required", "security_check", "parse_failed_nonempty"]);
const SAFE_JOB_ID = /^[A-Za-z0-9_-]{1,128}$/;

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

function publicProfile(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (/^[A-Za-z0-9._~-]{1,128}$/.test(text)) return text;
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

function redactedText(value, secret = "") {
  const text = typeof value === "string" ? value : "";
  return secret ? text.split(secret).join("[已隐藏]") : text;
}

function publicDiagnostic(value, secret = "") {
  const diagnostic = value && typeof value === "object" ? value : {};
  return {
    status: typeof diagnostic.status === "string" ? diagnostic.status : "",
    start: Number.isInteger(diagnostic.start) ? diagnostic.start : null,
    classification: typeof diagnostic.classification === "string" ? diagnostic.classification : "",
    http_status: Number.isInteger(diagnostic.http_status) ? diagnostic.http_status : null,
    message: redactedText(diagnostic.message, secret),
  };
}

function canResumeJob(job) {
  if (!["partial", "failed", "needs_cookie"].includes(job.state)) return false;
  return job.diagnostics.some((diagnostic) => (
    RESUMABLE_CLASSIFICATIONS.has(diagnostic.classification)
    && diagnostic.status
    && Number.isInteger(diagnostic.start)
    && diagnostic.start >= 0
  ));
}

function publicJob(value = {}, secret = "") {
  const id = safeJobId(value.id || value.job_id);
  const countsSource = value.counts && typeof value.counts === "object" ? value.counts : null;
  const counts = countsSource ? {
    items: optionalCount(countsSource.items) ?? 0,
    collect_count: optionalCount(countsSource.collect_count) ?? 0,
    wish_count: optionalCount(countsSource.wish_count) ?? 0,
    pages_ok: optionalCount(countsSource.pages_ok) ?? 0,
    pages_failed: optionalCount(countsSource.pages_failed) ?? 0,
  } : null;
  const diagnostics = Array.isArray(value.diagnostics) ? value.diagnostics.map((diagnostic) => publicDiagnostic(diagnostic, secret)) : [];
  const state = typeof value.state === "string" && value.state ? value.state : "queued";
  const job = {
    id,
    state,
    user_id: typeof value.user_id === "string" ? value.user_id : "",
    counts,
    stopped_reason: redactedText(value.stopped_reason, secret),
    diagnostics,
    errors: Array.isArray(value.errors) ? value.errors.filter((error) => typeof error === "string").slice(0, 12).map((error) => redactedText(error, secret)) : [],
    incomplete: state === "complete" && !countsSource,
  };
  job.canResume = canResumeJob(job);
  return job;
}

function errorCopy(error, secret = "") {
  const status = Number(error?.status) || 0;
  let message = typeof error?.publicMessage === "string" ? error.publicMessage : (typeof error?.message === "string" ? error.message : "请求失败");
  if (secret) message = message.split(secret).join("[已隐藏]");
  return status ? `HTTP ${status} · ${message}` : message;
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
  let disposed = false;

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
    return {
      profile: publicProfile(profileInput.value),
      options: currentOptions(),
      knownJobIds: [...jobs.keys()],
    };
  }

  function emitState() {
    onStateChange(publicState());
  }

  function statusCopy(job) {
    if (job.incomplete) return "记录不完整，等待完整结果";
    if (job.state === "complete") return "同步完成";
    if (job.state === "partial") return "部分完成";
    if (job.state === "needs_cookie") return "需要登录态后继续";
    if (job.state === "failed") return "同步失败";
    if (job.state === "running") return "同步进行中";
    return "等待执行";
  }

  function renderJobs() {
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
        ? element("p", "sync-job__counts", `条目 ${job.counts.items} · 成功页 ${job.counts.pages_ok} · 失败页 ${job.counts.pages_failed}`)
        : element("p", "sync-job__counts", "结果字段尚未提供");
      card.append(title, stateNode, counts);
      if (job.stopped_reason) card.append(element("p", "sync-job__reason", job.stopped_reason));
      if (job.canResume) {
        const resumeButton = element("button", "sync-job__resume", "继续未完成分页");
        resumeButton.type = "button";
        resumeButton.addEventListener("click", () => { void resume(job.id); });
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

  function schedule(jobId) {
    const job = jobs.get(jobId);
    if (disposed || !job || TERMINAL_STATES.has(job.state) || timers.has(jobId)) return;
    const timer = setTimer(() => {
      timers.delete(jobId);
      void refreshJob(jobId);
    }, pollInterval);
    timers.set(jobId, timer);
  }

  function acceptJob(payload) {
    const job = publicJob(payload, secretInput.value);
    if (!job.id || disposed) return job;
    jobs.set(job.id, job);
    renderJobs();
    return job;
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
      const job = acceptJob({ ...payload, id: payload?.id || payload?.job_id || jobId });
      schedule(jobId);
      return job;
    } catch (error) {
      if (disposed || controller.signal.aborted || pollGenerations.get(jobId) !== requestGeneration) return null;
      errorNode.textContent = errorCopy(error);
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
    if (!visibleUser) {
      errorNode.textContent = "请输入豆瓣主页 URL 或用户 ID。";
      return null;
    }
    if (!user) {
      errorNode.textContent = "请输入有效的豆瓣主页 URL 或用户 ID。";
      return null;
    }
    try {
      if (secret) tabStorage?.setItem(COOKIE_SESSION_KEY, secret);
      else tabStorage?.removeItem?.(COOKIE_SESSION_KEY);
    } catch {
      // Session storage is optional; the visible field remains the source of truth.
    }
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
    submit.disabled = true;
    errorNode.textContent = "";
    try {
      const created = await startDoubanSync(payload, { postJson });
      if (disposed) return null;
      const job = acceptJob({ ...created, id: created?.job_id || created?.id });
      emitState();
      schedule(job.id);
      return job;
    } catch (error) {
      if (!disposed) errorNode.textContent = errorCopy(error, secret);
      return null;
    } finally {
      if (!disposed) submit.disabled = false;
    }
  }

  async function resume(rawJobId) {
    const jobId = safeJobId(rawJobId);
    const previous = jobs.get(jobId);
    if (!jobId || !previous?.canResume || disposed) return null;
    const secret = secretInput.value;
    try {
      if (secret) tabStorage?.setItem(COOKIE_SESSION_KEY, secret);
    } catch {
      // Keep the visible field usable if session storage is unavailable.
    }
    errorNode.textContent = "";
    try {
      const created = await resumeDoubanSync(jobId, { cookie: secret }, { postJson });
      if (disposed) return null;
      const resumed = acceptJob({ ...created, id: created?.job_id || created?.id });
      emitState();
      schedule(resumed.id);
      return resumed;
    } catch (error) {
      if (!disposed) errorNode.textContent = errorCopy(error, secret);
      return null;
    }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    form.removeEventListener("submit", onSubmit);
    for (const jobId of timers.keys()) clearJobTimer(jobId);
    for (const controller of polls.values()) controller.abort();
    polls.clear();
  }

  function onSubmit(event) {
    event.preventDefault();
    void start();
  }
  form.addEventListener("submit", onSubmit);
  renderJobs();

  const restoredIds = [...new Set(knownJobIds.map(safeJobId).filter(Boolean))];
  for (const id of restoredIds) jobs.set(id, publicJob({ id, state: "queued" }));
  renderJobs();
  const ready = Promise.all(restoredIds.map(refreshJob));

  return {
    ready,
    elements: { profile: profileInput, cookie: secretInput, includeWish, includeDo, error: errorNode },
    start,
    resume,
    refreshJob,
    acceptJob,
    dispose,
    snapshot: () => ({
      profile: publicProfile(profileInput.value),
      options: currentOptions(),
      knownJobIds: [...jobs.keys()],
      jobs: Object.fromEntries([...jobs].map(([id, job]) => [id, { ...job, diagnostics: job.diagnostics.map((diagnostic) => ({ ...diagnostic })) }])),
      disposed,
    }),
  };
}
