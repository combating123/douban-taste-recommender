import { backendChannel, postV2 } from "../core/api.js";
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
  api: { postV2 },
  root: null,
  openCommandLens: null,
};
const batchOperations = new Map(CHANNELS.map((channel) => [channel.slug, {
  generation: 0,
  pending: false,
  sessionId: null,
  message: "",
  tone: "neutral",
  controls: null,
}]));

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

function renderChannelTabs(recommendation) {
  const tabs = element("nav", "tonight-channels");
  tabs.setAttribute("aria-label", "今晚频道");
  const active = activeChannelFor(recommendation);
  for (const channel of CHANNELS) {
    const link = element("a", "tonight-channel", channel.label);
    link.href = channel.route;
    link.setAttribute("href", channel.route);
    link.setAttribute("data-route", "");
    if (active.slug === channel.slug) link.setAttribute("aria-current", "page");
    tabs.append(link);
  }
  return tabs;
}

function renderHero(recommendation, channel) {
  const state = channelState(recommendation, channel);
  const item = batchItems(state)[0];
  const hero = element("section", "tonight-hero motion-enter");
  hero.setAttribute("aria-labelledby", "tonight-hero-title");

  const media = element("div", "tonight-hero__media");
  if (item) media.append(renderMediaFrame(adaptRecommendationMedia(item)));
  else media.append(renderMediaFrame({ kind: "poster", title: `${channel.label}待选`, status: "missing" }));

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

function renderShelves(recommendation) {
  const shelves = element("div", "tonight-shelves");
  for (const channel of CHANNELS) {
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
}

export function renderTonight(state = dependencies.store?.getState?.() || {}) {
  const recommendation = recommendationState(state);
  const activeChannel = activeChannelFor(recommendation);
  const page = element("div", "tonight-page");

  const intro = element("header", "tonight-intro");
  const introCopy = element("div", "tonight-intro__copy");
  introCopy.append(
    element("p", "eyebrow", "AI CURATION / 今晚"),
    element("h1", "tonight-intro__title", "今晚，只看值得开始的。"),
    element("p", "tonight-intro__deck", "一个会记住频道、批次与撤回路径的本地策展台。"),
  );
  intro.append(introCopy, renderChannelTabs(recommendation));
  page.append(intro, renderHero(recommendation, activeChannel), renderBatchToolbar(recommendation, activeChannel), renderShelves(recommendation));

  if (dependencies.root) dependencies.root.replaceChildren(page);
  return page;
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
