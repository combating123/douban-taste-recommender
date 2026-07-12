import { backendChannel, getV2, postV2 } from "../core/api.js";
import { adaptRecommendationMedia } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";
import { renderShelf } from "../components/shelf.js";
import { titleRouteForItem } from "../components/title-card.js";

export const MAX_INITIAL_CARDS = 9;

const CHANNELS = Object.freeze([
  { slug: "movie", backend: "电影", label: "电影", route: "/tonight/movie" },
  { slug: "series", backend: "电视剧", label: "剧集", route: "/tonight/series" },
  { slug: "anime-series", backend: "动漫", label: "动画剧集", route: "/tonight/anime-series" },
]);

let dependencies = {
  store: null,
  api: { postV2, getV2 },
  root: null,
  openCommandLens: null,
  navigate: null,
  setTimer: (callback, delay) => setTimeout(callback, delay),
  clearTimer: (id) => clearTimeout(id),
  mediaPollInterval: 1200,
};
const mediaJobsByIdentity = new Map();
const TERMINAL_MEDIA_STATES = new Set(["ready", "degraded", "failed", "unavailable"]);
const POLLABLE_MEDIA_STATES = new Set(["queued", "pending", "processing", "resolving", "downloading", "validating"]);

const batchOperations = new Map(CHANNELS.map((channel) => [channel.slug, {
  generation: 0,
  pending: false,
  sessionId: null,
  message: "",
  tone: "neutral",
  controls: null,
}]));
let mountedTonight = null;

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function numberValue(value) {
  return Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0;
}

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function recommendationState(state) {
  return state?.recommendation && typeof state.recommendation === "object"
    ? state.recommendation
    : {};
}

function channelState(recommendation, channel) {
  const channels = recommendation.channels && typeof recommendation.channels === "object"
    ? recommendation.channels
    : {};
  return channels[channel.slug] || channels[channel.backend] || {};
}

function batchItems(state) {
  const items = state?.batch?.items;
  return Array.isArray(items) ? items : [];
}

function itemReason(item) {
  return textValue(item?.short_reason) || textValue(item?.reason) || textValue(item?.summary);
}

function displayItem(item = {}) {
  const metadata = [
    Number.isFinite(item.year) ? String(item.year) : "",
    Number.isFinite(item.douban_rating) ? `豆瓣 ${item.douban_rating}` : "",
    textValue(item.media_type),
  ].filter(Boolean);
  return {
    ...item,
    metadata,
    reason: itemReason(item),
  };
}

function countValue(state, key) {
  if (Number.isFinite(state?.[key])) return numberValue(state[key]);
  return numberValue(state?.batch?.[key]);
}

function renderCount(label, value, modifier, { unknownWhenMissing = false } = {}) {
  const count = element("p", `tonight-count tonight-count--${modifier}`);
  const displayValue = unknownWhenMissing && !Number.isFinite(value) ? "—" : numberValue(value);
  count.textContent = `${label} ${displayValue}`;
  return count;
}

function activeChannelFor(recommendation) {
  return CHANNELS.find((channel) => channel.slug === recommendation.activeChannel) || CHANNELS[0];
}

function personalizationCopy(recommendation) {
  const profile = recommendation?.personalization && typeof recommendation.personalization === "object"
    ? recommendation.personalization
    : {};
  const watched = numberValue(profile.watched_count);
  const wish = numberValue(profile.wish_count);
  if (profile.source === "douban-sync" && (watched || wish)) {
    return `基于你的 ${watched} 部看过 · ${wish} 部想看，兼顾高口碑、剧情完成度与近期新鲜度。`;
  }
  if (profile.source === "local-library" && (watched || wish)) {
    return `基于本地片库的 ${watched} 部看过 · ${wish} 部想看，持续随反馈校准。`;
  }
  return "描述片长、情绪或类型，CineScope 会建立可换批、可撤回的私人片单。";
}

export function selectTonightChannel(slug, { replace = false } = {}) {
  const channel = CHANNELS.find((entry) => entry.slug === slug);
  const store = dependencies.store;
  if (!channel || !store?.getState) return false;
  const current = activeChannelFor(recommendationState(store.getState?.() || {}));
  if (current.slug === channel.slug) return true;
  if (typeof dependencies.navigate === "function") {
    return dependencies.navigate(channel.route, { replace });
  }
  return false;
}


function renderChannelTabs(recommendation) {
  const tabs = element("nav", "tonight-channels");
  tabs.setAttribute("aria-label", "今晚频道");
  tabs.setAttribute("role", "tablist");
  const active = activeChannelFor(recommendation);
  for (const channel of CHANNELS) {
    const button = element("button", "tonight-channel", channel.label);
    button.type = "button";
    button.dataset.channel = channel.slug;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", active.slug === channel.slug ? "true" : "false");
    if (active.slug === channel.slug) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => selectTonightChannel(channel.slug));
    tabs.append(button);
  }
  return tabs;
}

function renderHero(recommendation, channel) {
  const state = channelState(recommendation, channel);
  const item = batchItems(state)[0];
  const hero = element("section", "tonight-hero");
  hero.setAttribute("aria-labelledby", "tonight-hero-title");

  const media = element("div", "tonight-hero__media");
  const mediaModel = item
    ? adaptRecommendationMedia(item)
    : { kind: "poster", title: `${channel.label}待选`, status: "missing" };
  const backdrop = element("div", "tonight-hero__backdrop");
  const poster = element("div", "tonight-hero__poster");
  backdrop.append(renderMediaFrame(mediaModel));
  poster.append(renderMediaFrame(mediaModel));
  media.append(backdrop, poster);

  const copy = element("div", "tonight-hero__copy");
  copy.append(element("p", "eyebrow", `TONIGHT / ${channel.label}`));
  const title = element("h1", "tonight-hero__title", textValue(item?.title, "把今晚交给你的口味线索"));
  title.id = "tonight-hero-title";
  copy.append(title);
  copy.append(element(
    "p",
    "tonight-hero__reason",
    item ? itemReason(item) || "从当前匹配池中选出的首席候选。" : "按 Ctrl+K 描述片长、情绪或类型，生成一组可回退的本地推荐。",
  ));

  const metadata = displayItem(item || {}).metadata;
  if (metadata.length) copy.append(element("p", "tonight-hero__metadata", metadata.join(" · ")));

  const actions = element("div", "tonight-hero__actions");
  const detailRoute = titleRouteForItem(item || {});
  if (detailRoute) {
    const detail = element("a", "tonight-button tonight-button--detail", "打开作品详情");
    detail.setAttribute("href", detailRoute);
    detail.setAttribute("data-route", "");
    actions.append(detail);
  }
  const command = element("button", "tonight-button tonight-button--primary", item ? "重新描述今晚" : "描述今晚");
  command.type = "button";
  command.addEventListener("click", () => dependencies.openCommandLens?.(""));
  actions.append(command);
  copy.append(actions);
  hero.append(media, copy);
  return hero;
}

function renderBatchToolbar(recommendation, channel) {
  const state = channelState(recommendation, channel);
  const candidateCounts = state.candidate_counts && typeof state.candidate_counts === "object"
    ? state.candidate_counts
    : {};
  const toolbar = element("section", "tonight-batch-toolbar");
  toolbar.setAttribute("aria-label", `${channel.label}批次工具栏`);

  const counts = element("div", "tonight-counts");
  counts.append(
    renderCount("目标", candidateCounts.target_size, "target", { unknownWhenMissing: true }),
    renderCount("实际返回", candidateCounts.returned_size, "returned"),
    renderCount("候选池", countValue(state, "pool_size"), "pool"),
    renderCount("匹配", countValue(state, "matched_size"), "matched"),
    renderCount("本批可见", countValue(state, "visible_size"), "visible"),
    renderCount("当前批次", state.active_batch || state.batch?.index, "batch"),
  );

  const controls = element("div", "tonight-batch-controls");
  const reason = document.createElement("input");
  reason.className = "tonight-reason";
  reason.type = "text";
  reason.maxLength = 120;
  reason.placeholder = "换一批的原因，例如：更轻松、更冷门";
  reason.setAttribute("aria-label", "换一批原因");

  const previous = element("button", "tonight-button", "撤回上一批");
  previous.type = "button";
  const previousBaseDisabled = numberValue(state.active_batch || state.batch?.index) <= 1;
  previous.disabled = previousBaseDisabled;
  previous.addEventListener("click", () => {
    void restorePreviousBatch(channel.slug);
  });

  const next = element("button", "tonight-button tonight-button--signal", "按原因换一批");
  next.type = "button";
  next.addEventListener("click", () => {
    void requestNextBatch(channel.slug, reason.value);
  });
  controls.append(reason, previous, next);
  const status = element("p", "tonight-batch-status");
  status.setAttribute("aria-live", "polite");
  toolbar.append(counts, controls, status);
  const operation = batchOperation(channel.slug);
  operation.controls = { reason, previous, previousBaseDisabled, next, status };
  applyBatchOperationUi(channel.slug);
  return toolbar;
}

function renderShelves(recommendation, channels = CHANNELS) {
  const shelves = element("div", "tonight-shelves");
  for (const channel of channels) {
    const state = channelState(recommendation, channel);
    const items = batchItems(state).slice(0, MAX_INITIAL_CARDS).map(displayItem);
    shelves.append(renderShelf({
      title: channel.label,
      items,
      batchState: {
        poolSize: countValue(state, "pool_size"),
        matchedSize: countValue(state, "matched_size"),
        visibleSize: countValue(state, "visible_size"),
      },
    }));
  }
  return shelves;
}

export function configureTonight(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    api: options.api || dependencies.api,
  };
  if (mountedTonight && options.root && mountedTonight.root !== options.root) mountedTonight = null;
}

function createTonightPage(recommendation) {
  const page = element("div", "tonight-page");
  const intro = element("header", "tonight-intro");
  const introCopy = element("div", "tonight-intro__copy");
  const deck = element("p", "tonight-intro__deck");
  introCopy.append(
    element("p", "eyebrow", "AI CURATION / 今晚"),
    element("h1", "tonight-intro__title", "今晚，只看值得开始的。"),
    deck,
  );
  const tabs = renderChannelTabs(recommendation);
  const stage = element("div", "tonight-stage");
  const hero = element("section", "tonight-hero");
  hero.setAttribute("aria-labelledby", "tonight-hero-title");
  const toolbar = element("section", "tonight-batch-toolbar");
  const shelves = element("div", "tonight-shelves");
  stage.append(hero, toolbar, shelves);
  intro.append(introCopy, tabs);
  page.append(intro, stage);
  return { page, deck, tabs, stage, hero, toolbar, shelves };
}

function replaceIntoStable(target, fresh) {
  target.className = fresh.className;
  for (const [key, value] of Object.entries(fresh.dataset || {})) target.dataset[key] = value;
  target.replaceChildren(...(fresh.children || []));
}

function updateStableHero(mount, recommendation, channel) {
  replaceIntoStable(mount.hero, renderHero(recommendation, channel));
}

function updateStableToolbar(mount, recommendation, channel) {
  const state = channelState(recommendation, channel);
  const candidateCounts = state.candidate_counts && typeof state.candidate_counts === "object" ? state.candidate_counts : {};
  const toolbar = mount.toolbar;
  toolbar.className = "tonight-batch-toolbar";
  toolbar.setAttribute("aria-label", `${channel.label}批次工具栏`);
  let controls = toolbar._stableControls;
  if (!controls) {
    const counts = element("div", "tonight-counts");
    const controlsNode = element("div", "tonight-batch-controls");
    const reason = document.createElement("input");
    reason.className = "tonight-reason";
    reason.type = "text";
    reason.maxLength = 120;
    reason.placeholder = "换一批的原因，例如：更轻松、更冷门";
    reason.setAttribute("aria-label", "换一批原因");
    const previous = element("button", "tonight-button", "撤回上一批");
    previous.type = "button";
    previous.addEventListener("click", () => { void restorePreviousBatch(channel.slug); });
    const next = element("button", "tonight-button tonight-button--signal", "按原因换一批");
    next.type = "button";
    next.addEventListener("click", () => { void requestNextBatch(channel.slug, reason.value); });
    controlsNode.append(reason, previous, next);
    const status = element("p", "tonight-batch-status");
    status.setAttribute("aria-live", "polite");
    toolbar.append(counts, controlsNode, status);
    controls = { counts, controlsNode, reason, previous, next, status };
    toolbar._stableControls = controls;
  }
  controls.counts.replaceChildren(
    renderCount("目标", candidateCounts.target_size, "target", { unknownWhenMissing: true }),
    renderCount("实际返回", candidateCounts.returned_size, "returned"),
    renderCount("候选池", countValue(state, "pool_size"), "pool"),
    renderCount("匹配", countValue(state, "matched_size"), "matched"),
    renderCount("本批可见", countValue(state, "visible_size"), "visible"),
    renderCount("当前批次", state.active_batch || state.batch?.index, "batch"),
  );
  controls.previousBaseDisabled = numberValue(state.active_batch || state.batch?.index) <= 1;
  const operation = batchOperation(channel.slug);
  operation.controls = controls;
  applyBatchOperationUi(channel.slug);
}

function updateStableShelves(mount, recommendation, activeChannel) {
  mount.shelves.replaceChildren();
  for (const channel of [activeChannel]) {
    const state = channelState(recommendation, channel);
    const items = batchItems(state).slice(0, MAX_INITIAL_CARDS).map(displayItem);
    mount.shelves.append(renderShelf({
      title: channel.label,
      items,
      batchState: {
        poolSize: countValue(state, "pool_size"),
        matchedSize: countValue(state, "matched_size"),
        visibleSize: countValue(state, "visible_size"),
      },
    }));
  }
}

function updateTonightPage(mount, recommendation) {
  const activeChannel = activeChannelFor(recommendation);
  mount.deck.textContent = personalizationCopy(recommendation);
  for (const tab of mount.tabs.children || []) {
    const active = tab.dataset?.channel === activeChannel.slug;
    tab.setAttribute?.("aria-selected", active ? "true" : "false");
    if (active) tab.setAttribute?.("aria-current", "page");
    else tab.removeAttribute?.("aria-current");
  }
  updateStableHero(mount, recommendation, activeChannel);
  updateStableToolbar(mount, recommendation, activeChannel);
  updateStableShelves(mount, recommendation, activeChannel);
  mount.page.dataset.channel = activeChannel.slug;
  ensureVisibleMediaJobs(recommendation, activeChannel);
  return mount.page;
}

export function renderTonight(state = dependencies.store?.getState?.() || {}) {
  const recommendation = recommendationState(state);
  const root = dependencies.root;
  const mountedInRoot = Boolean(root && mountedTonight?.root === root && (root.children ? [...root.children].includes(mountedTonight.page) : mountedTonight.page?.isConnected));
  if (!mountedInRoot) {
    const mount = createTonightPage(recommendation);
    mountedTonight = root ? { ...mount, root } : null;
    updateTonightPage(mount, recommendation);
    if (root) root.replaceChildren(mount.page);
    return mount.page;
  }
  return updateTonightPage(mountedTonight, recommendation);
}

function itemIdentity(item = {}) {
  return textValue(item.item_key) || textValue(item.id) || textValue(item.douban_id);
}

function mediaJobKey(kind, identity) {
  return `${kind}:${identity}`;
}

function mediaJobApiGet(path) {
  if (typeof dependencies.api.getV2 === "function") return dependencies.api.getV2(path);
  return fetch(path, { method: "GET", headers: { Accept: "application/json" } }).then((response) => {
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
  });
}

function scheduleMediaPoll(key, jobId, sessionId) {
  const record = mediaJobsByIdentity.get(key);
  if (!record || record.timer) return;
  record.timer = dependencies.setTimer(async () => {
    record.timer = null;
    try {
      const job = await mediaJobApiGet(`/api/v2/media/jobs/${encodeURIComponent(jobId)}`);
      const state = textValue(job?.state).toLowerCase();
      if (state === "ready" || state === "degraded") {
        record.state = state;
        const session = await mediaJobApiGet(`/api/v2/recommend/sessions/${encodeURIComponent(sessionId)}`);
        dependencies.store?.dispatch?.({ type: "recommendation/sessionReceived", session, source: "media-refresh", expectedSessionId: sessionId });
        return;
      }
      if (POLLABLE_MEDIA_STATES.has(state)) scheduleMediaPoll(key, jobId, sessionId);
      else record.state = state || "failed";
    } catch {
      record.state = "failed";
    }
  }, dependencies.mediaPollInterval);
}

function enqueueMediaJob(item, channel, sessionId) {
  const media = adaptRecommendationMedia(item);
  const identity = itemIdentity(item);
  if (!identity || media.status === "ready") return;
  const key = mediaJobKey("poster", identity);
  const existing = mediaJobsByIdentity.get(key);
  if (existing && (existing.inFlight || existing.state === "ready" || existing.state === "degraded")) return;
  const record = { inFlight: true, state: "queued", timer: null };
  mediaJobsByIdentity.set(key, record);
  Promise.resolve(dependencies.api.postV2("/api/v2/media/jobs", {
    kind: "poster",
    identity_key: identity,
    title: textValue(item.title),
    year: Number.isFinite(item.year) ? item.year : undefined,
    media_type: textValue(item.media_type),
    priority: 0,
  })).then((job) => {
    record.inFlight = false;
    const jobId = textValue(job?.job_id) || textValue(job?.id);
    const state = textValue(job?.state, "queued").toLowerCase();
    record.state = state;
    if (jobId && !TERMINAL_MEDIA_STATES.has(state)) scheduleMediaPoll(key, jobId, sessionId);
    if (jobId && (state === "ready" || state === "degraded")) scheduleMediaPoll(key, jobId, sessionId);
  }).catch(() => {
    record.inFlight = false;
    record.state = "failed";
  });
}

function ensureVisibleMediaJobs(recommendation, channel) {
  const sessionId = textValue(channelState(recommendation, channel).sessionId) || textValue(recommendation.sessionId);
  if (!sessionId || typeof dependencies.api?.postV2 !== "function") return;
  const state = channelState(recommendation, channel);
  const seen = new Set();
  for (const item of batchItems(state).slice(0, MAX_INITIAL_CARDS)) {
    const identity = itemIdentity(item);
    if (!identity || seen.has(identity)) continue;
    seen.add(identity);
    enqueueMediaJob(item, channel, sessionId);
  }
}


function configuredStore() {
  if (!dependencies.store?.getState || !dependencies.store?.dispatch) {
    throw new Error("Tonight requires a configured store");
  }
  return dependencies.store;
}

function sessionIdFor(channel) {
  const state = configuredStore().getState();
  const recommendation = recommendationState(state);
  const perChannel = channelState(recommendation, CHANNELS.find((entry) => entry.slug === channel) || CHANNELS[0]);
  return textValue(perChannel.sessionId) || textValue(recommendation.sessionId);
}

export function syncTonightSessionState(state = dependencies.store?.getState?.() || {}) {
  const recommendation = recommendationState(state);
  for (const channel of CHANNELS) {
    const operation = batchOperation(channel.slug);
    const currentSessionId = textValue(channelState(recommendation, channel).sessionId)
      || textValue(recommendation.sessionId)
      || null;
    if (operation.sessionId && operation.sessionId !== currentSessionId) {
      operation.generation += 1;
      operation.pending = false;
      operation.sessionId = null;
      operation.message = "";
      operation.tone = "neutral";
      applyBatchOperationUi(channel.slug);
    }
  }
}

async function runBatchOperation(channel, endpoint, payload, workingMessage, successMessage) {
  const store = configuredStore();
  const operation = batchOperation(channel);
  const generation = operation.generation + 1;
  operation.generation = generation;
  operation.pending = true;
  operation.message = workingMessage;
  operation.tone = "working";
  applyBatchOperationUi(channel);

  const sessionId = sessionIdFor(channel);
  if (!sessionId) {
    operation.pending = false;
    operation.message = "请先创建今晚推荐会话。";
    operation.tone = "error";
    applyBatchOperationUi(channel);
    return null;
  }
  operation.sessionId = sessionId;

  try {
    const batch = await dependencies.api.postV2(
      `/api/v2/recommend/sessions/${encodeURIComponent(sessionId)}/${endpoint}`,
      payload,
    );
    if (
      operation.generation !== generation
      || sessionIdFor(channel) !== sessionId
      || (textValue(batch?.session_id) && batch.session_id !== sessionId)
    ) return null;
    store.dispatch({ type: "recommendation/batchReceived", channel, batch, expectedSessionId: sessionId });
    operation.message = successMessage;
    operation.tone = "success";
    return batch;
  } catch {
    if (operation.generation !== generation) return null;
    operation.message = endpoint === "previous" ? "撤回上一批失败，请稍后重试。" : "换批失败，请稍后重试。";
    operation.tone = "error";
    return null;
  } finally {
    if (operation.generation === generation) {
      operation.pending = false;
      applyBatchOperationUi(channel);
    }
  }
}

export async function requestNextBatch(channel, reason = "") {
  return runBatchOperation(
    channel,
    "batch",
    { channel: backendChannel(channel), reason: textValue(reason) },
    "正在按原因生成下一批…",
    "下一批已就绪。",
  );
}

export async function restorePreviousBatch(channel) {
  return runBatchOperation(
    channel,
    "previous",
    { channel: backendChannel(channel) },
    "正在撤回到上一批…",
    "已恢复上一批。",
  );
}

export async function restoreTonightSession(sessionId, { signal } = {}) {
  const cleanId = textValue(sessionId);
  if (!cleanId) return null;
  const response = await fetch(`/api/v2/recommend/sessions/${encodeURIComponent(cleanId)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

export async function restoreLatestTonightSession({ signal } = {}) {
  const response = await fetch("/api/v2/recommend/sessions/latest", {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

function batchOperation(channel) {
  return batchOperations.get(channel) || batchOperations.get("movie");
}

function applyBatchOperationUi(channel) {
  const operation = batchOperation(channel);
  const controls = operation.controls;
  if (!controls) return;
  controls.reason.disabled = operation.pending;
  controls.previous.disabled = operation.pending || controls.previousBaseDisabled;
  controls.next.disabled = operation.pending;
  controls.status.dataset.tone = operation.tone;
  controls.status.textContent = operation.message;
}
