import { backendChannel, getV2, postV2 } from "../core/api.js";
import { adaptCatalogMedia, adaptRecommendationMedia, preloadLocalMedia } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";
import { renderShelf } from "../components/shelf.js";
import { candidateOrigin } from "../components/candidate-origin.js";
import { renderCinemaCarousel } from "../components/cinema-carousel.js";
import { displayTitle, needsLocalizedSummary, titleRouteForItem } from "../components/title-card.js";

export const MAX_INITIAL_CARDS = 12;
export const DISCOVERY_DEBOUNCE_MS = 420;

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
  preloadMedia: preloadLocalMedia,
  mediaPollInterval: 1200,
};
const mediaJobsByIdentity = new Map();
const metadataJobsByIdentity = new Map();
const metadataJobQueue = [];
const prewarmedHeroUrls = new Set();
const heroSelectionByChannel = new Map();
const sourceFilterByChannel = new Map();
const heroPeopleWarmups = new Map();
const portraitWarmupsByIdentity = new Map();
const feedbackOperations = new Map();
const MAX_HERO_PEOPLE_PREFETCH = 4;
const MAX_VISIBLE_METADATA_JOBS = 2;
const METADATA_RETRY_AFTER_MS = 120_000;
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
let feedbackToast = null;
let feedbackToastTimer = null;
let heroResizeHandler = null;
let activeMetadataJobs = 0;
let discoveryRequestSequence = 0;
let activeDiscoveryComposer = null;

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

function visibleBatchItems(state, originFilter = "all") {
  const items = batchItems(state);
  const filter = ["catalog", "online"].includes(originFilter) ? originFilter : "all";
  const filtered = filter === "all" ? items : items.filter((item) => candidateOrigin(item).kind === filter);
  return filtered.slice(0, MAX_INITIAL_CARDS);
}

function itemGenres(item) {
  const direct = Array.isArray(item?.genres)
    ? item.genres.map((genre) => textValue(genre)).filter(Boolean).slice(0, 3)
    : [];
  if (direct.length) return direct;
  const nested = Array.isArray(item?.item?.genres)
    ? item.item.genres.map((genre) => textValue(genre)).filter(Boolean).slice(0, 3)
    : [];
  if (nested.length) return nested;
  const mediaType = textValue(item?.media_type) || textValue(item?.format);
  return mediaType ? [mediaType] : [];
}

function itemMediaType(item) {
  return textValue(item?.media_type) || textValue(item?.format) || "媒体类型待补全";
}

function publicRatingLabels(item = {}) {
  const labels = [];
  const seen = new Set();
  const add = (provider, label, value) => {
    let score = Number(value);
    if (!Number.isFinite(score) || score <= 0 || seen.has(provider)) return;
    if (score > 10 && score <= 100) score /= 10;
    if (score > 10) return;
    seen.add(provider);
    labels.push(`${label} ${Math.round(score * 10) / 10}`);
  };
  add("douban", "豆瓣", item.douban_rating);
  const ratings = item.source_ratings && typeof item.source_ratings === "object" ? item.source_ratings : {};
  const names = { imdb: "IMDb", tmdb: "TMDb", tvmaze: "TVMaze", anilist: "AniList", jikan: "MAL", apple_movies: "Apple TV" };
  Object.entries(ratings).forEach(([provider, score]) => add(provider, names[provider] || provider, score));
  return labels.slice(0, 3);
}

function findHeroTitle(root) {
  if (!root) return null;
  if (root.className === "tonight-hero__title") return root;
  for (const child of root.children || []) {
    const match = findHeroTitle(child);
    if (match) return match;
  }
  return null;
}

function fitHeroTitle(title) {
  if (!title?.style || typeof title.scrollWidth !== "number" || typeof title.clientWidth !== "number") return;
  if (title.clientWidth <= 0) return;

  if (typeof title.style.removeProperty === "function") title.style.removeProperty("font-size");
  else title.style.fontSize = "";

  const computed = typeof globalThis.getComputedStyle === "function" ? globalThis.getComputedStyle(title) : null;
  let fontSize = Number.parseFloat(computed?.fontSize || title.style.fontSize || "");
  if (!Number.isFinite(fontSize) || fontSize <= 0) return;

  const minimumFontSize = 16;
  let attempts = 0;
  while (title.scrollWidth > title.clientWidth + 1 && fontSize > minimumFontSize && attempts < 32) {
    fontSize = Math.max(minimumFontSize, fontSize * 0.92);
    title.style.fontSize = `${fontSize}px`;
    attempts += 1;
  }
}

function scheduleHeroTitleFit(hero) {
  const title = findHeroTitle(hero);
  if (!title) return;
  const frame = typeof globalThis.requestAnimationFrame === "function"
    ? globalThis.requestAnimationFrame.bind(globalThis)
    : null;
  if (frame) frame(() => fitHeroTitle(title));
  else fitHeroTitle(title);
}

function itemReason(item) {
  const explicit = textValue(item?.personalized_reason)
    || textValue(item?.short_reason)
    || textValue(item?.reason);
  const genres = itemGenres(item);
  const mediaType = itemMediaType(item);
  const ratingLabel = publicRatingLabels(item)[0] || "";
  const rating = ratingLabel ? ` · ${ratingLabel}` : "";
  const genericScoreReason = /(?:豆瓣|评分|rating|高分|口碑)/i.test(explicit);
  const placeholderReason = !explicit || /^(?:资料完整|资料信息待补全|metadata complete)$/i.test(explicit);
  const genreCopy = genres.join(" / ");

  if (genres.length && (placeholderReason || genericScoreReason)) {
    const prefix = genericScoreReason && !placeholderReason ? "命中你的口味" : "类型";
    return `${prefix}：${genreCopy}${rating}`;
  }
  if (genres.length && explicit) return `${explicit} · 类型：${genreCopy}`;
  if (genres.length) return `类型：${genreCopy}${rating}`;
  if (placeholderReason) return `类型：${mediaType} · 资料信息待补全`;
  return `类型：${mediaType} · ${explicit}`;
}

export function displayItem(item = {}) {
  const genres = itemGenres(item);
  const ratings = publicRatingLabels(item);
  const metadata = [
    ...(ratings.length ? ratings : ["豆瓣评分待补全"]),
    itemMediaType(item),
    genres.length ? `类型：${genres.join(" / ")}` : "类型：作品",
    Number.isFinite(item.year) ? String(item.year) : "",
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

function restoringChannel(recommendation, channel) {
  return recommendation?.restoring === true && batchItems(channelState(recommendation, channel)).length === 0;
}

function prewarmChannelHeroes(recommendation) {
  if (typeof dependencies.preloadMedia !== "function") return;
  for (const channel of CHANNELS) {
    const item = batchItems(channelState(recommendation, channel))[0];
    if (!item) continue;
    const media = adaptRecommendationMedia(item);
    if (media.status !== "ready" || !media.localUrl || prewarmedHeroUrls.has(media.localUrl)) continue;
    prewarmedHeroUrls.add(media.localUrl);
    if (prewarmedHeroUrls.size > 120) prewarmedHeroUrls.delete(prewarmedHeroUrls.values().next().value);
    void Promise.resolve(dependencies.preloadMedia(media.localUrl)).catch(() => {});
  }
}

function personalizationCopy(recommendation) {
  const profile = recommendation?.personalization && typeof recommendation.personalization === "object"
    ? recommendation.personalization
    : {};
  const watched = numberValue(profile.watched_count);
  const wish = numberValue(profile.wish_count);
  const discovery = recommendation?.discovery && typeof recommendation.discovery === "object"
    ? recommendation.discovery
    : {};
  const sourceCounts = discovery.source_counts && typeof discovery.source_counts === "object"
    ? discovery.source_counts
    : {};
  const activeSources = Object.entries(sourceCounts)
    .filter(([, count]) => Number.isFinite(count) && count > 0)
    .map(([source]) => ({ tmdb: "TMDb", omdb: "IMDb", tvmaze: "TVMaze", anilist: "AniList", jikan: "MAL", apple_movies: "Apple TV" }[source] || source));
  const live = numberValue(discovery.live_size);
  const local = numberValue(discovery.local_index_size);
  const originCounts = discovery.recommendation_origin_counts && typeof discovery.recommendation_origin_counts === "object"
    ? discovery.recommendation_origin_counts
    : {};
  const originChannels = Array.isArray(discovery.recommendation_origin_channels)
    ? discovery.recommendation_origin_channels
    : [];
  const onlineDestinations = CHANNELS.map((channel) => ({
    channel: channel.backend,
    count: numberValue(
      originChannels.find((entry) => entry?.channel === channel.backend)?.online
      ?? originCounts[channel.backend]?.online,
    ),
  })).filter((entry) => entry.count > 0);
  const discoveryCopy = live || local
    ? `本次同时检索本地索引 ${local} 条、全网新增 ${live} 条${activeSources.length ? `（${activeSources.join(" / ")}）` : ""}。`
    : "";
  const destinationCopy = onlineDestinations.length
    ? `在线新增进入推荐：${onlineDestinations.map((entry) => `${entry.channel} ${entry.count}`).join(" · ")}。`
    : "";
  if (profile.source === "douban-sync" && (watched || wish)) {
    return `基于你的 ${watched} 部看过 · ${wish} 部想看，融合多源质量、语义口味与近期热度。${discoveryCopy}${destinationCopy}`;
  }
  if (profile.source === "local-library" && (watched || wish)) {
    return `基于本地片库的 ${watched} 部看过 · ${wish} 部想看，持续随反馈校准。${discoveryCopy}${destinationCopy}`;
  }
  return `描述片长、情绪或类型，CineScope 会建立可换批、可撤回的私人片单。${discoveryCopy}${destinationCopy}`;
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

function mediaUrlValue(value) {
  if (typeof value === "string") return textValue(value);
  if (!value || typeof value !== "object") return "";
  return textValue(value.localUrl) || textValue(value.url) || textValue(value.src);
}

function heroMediaForItem(item = {}) {
  const stills = Array.isArray(item?.stills) ? item.stills : [];
  const still = stills.map(mediaUrlValue).find(Boolean);
  if (still) return { localUrl: still, kind: "backdrop", status: "ready", title: displayTitle(item, "作品") };
  const backdrop = mediaUrlValue(item?.backdrop);
  if (backdrop) return { localUrl: backdrop, kind: "backdrop", status: "ready", title: displayTitle(item, "作品") };
  const poster = adaptRecommendationMedia(item);
  if (poster.status === "ready" && poster.localUrl) return { ...poster, kind: "poster" };
  return { kind: "backdrop", status: "missing", title: displayTitle(item, "作品") };
}

function readyHeroItems(state) {
  return batchItems(state).filter((item) => Boolean(heroMediaForItem(item).localUrl)).slice(0, 5);
}

function heroItemForChannel(state, channel) {
  const readyItems = readyHeroItems(state);
  const selectedKey = heroSelectionByChannel.get(channel.slug);
  const selected = readyItems.find((item) => itemIdentity(item) === selectedKey);
  return { item: selected || readyItems[0] || batchItems(state)[0], readyItems };
}

function renderHero(recommendation, channel) {
  const state = channelState(recommendation, channel);
  const { item, readyItems } = heroItemForChannel(state, channel);
  const slides = readyItems.length ? readyItems : (item ? [item] : []);
  const activeIndex = Math.max(0, slides.findIndex((candidate) => itemIdentity(candidate) === itemIdentity(item)));
  const carousel = renderCinemaCarousel({
    title: `${channel.label}焦点推荐`,
    ariaLabel: `${channel.label}焦点推荐轮播`,
    initialIndex: activeIndex,
    slides: slides.map((candidate) => ({
      ...candidate,
      id: itemIdentity(candidate),
      media: heroMediaForItem(candidate),
    })),
    renderContent: (candidate) => {
      const copy = element("div", "tonight-hero__copy cinema-carousel__copy");
      copy.append(element("p", "eyebrow", `TONIGHT / ${channel.label}`));
      const title = element("h1", "tonight-hero__title", displayTitle(candidate, "把今晚交给你的口味线索"));
      title.id = "tonight-hero-title";
      copy.append(title);
      copy.append(element(
        "p",
        "tonight-hero__reason",
        itemReason(candidate) || "从当前匹配池中选出的首席候选。",
      ));
      const metadata = displayItem(candidate || {}).metadata;
      if (metadata.length) copy.append(element("p", "tonight-hero__metadata", metadata.join(" · ")));
      const actions = element("div", "tonight-hero__actions");
      const detailRoute = titleRouteForItem(candidate || {});
      if (detailRoute) {
        const detail = element("a", "tonight-button tonight-button--detail", "查看详情");
        detail.setAttribute("href", detailRoute);
        detail.setAttribute("data-route", "");
        actions.append(detail);
      }
      const command = element("button", "tonight-button tonight-button--primary", "重新描述今晚");
      command.type = "button";
      command.addEventListener("click", () => dependencies.openCommandLens?.(""));
      actions.append(command);
      copy.append(actions);
      return copy;
    },
    onSelect: (selected) => {
      const key = itemIdentity(selected);
      if (key) heroSelectionByChannel.set(channel.slug, key);
      ensureHeroPeopleWarmup(recommendation, channel);
    },
  });
  carousel.className = `${carousel.className || ""} tonight-hero`.trim();
  carousel.setAttribute("aria-labelledby", "tonight-hero-title");
  return carousel;
}

function renderRestoreHero(channel) {
  const hero = element("section", "tonight-hero tonight-hero--restoring");
  hero.setAttribute("aria-labelledby", "tonight-hero-title");
  const atmosphere = element("div", "tonight-restore__atmosphere");
  atmosphere.setAttribute("aria-hidden", "true");
  const copy = element("div", "tonight-hero__copy tonight-restore__copy");
  copy.append(element("p", "eyebrow", `RESTORING / ${channel.label}`));
  const title = element("h1", "tonight-hero__title", "正在恢复你的私人片单");
  title.id = "tonight-hero-title";
  copy.append(
    title,
    element("p", "tonight-hero__reason", "正在读取上次会话、个性化排序与本地海报。内容就绪后会原位呈现，不会把等待误报成空片单。"),
  );
  const progress = element("div", "tonight-restore__progress");
  progress.setAttribute("role", "progressbar");
  progress.setAttribute("aria-label", "恢复私人片单");
  progress.append(element("span", "tonight-restore__progress-bar"));
  copy.append(progress);
  hero.append(atmosphere, copy);
  return hero;
}

function renderRestorePanel() {
  const panel = element("section", "tonight-restore");
  panel.setAttribute("aria-live", "polite");
  panel.append(
    element("strong", "tonight-restore__label", "私人推荐正在回到现场"),
    element("span", "tonight-restore__hint", "会话 · 排序 · 海报缓存"),
  );
  return panel;
}

function renderRestoreShelves() {
  const shelves = element("div", "tonight-shelves tonight-shelves--restoring");
  const rail = element("div", "tonight-restore-cards");
  for (let index = 0; index < 6; index += 1) {
    const card = element("div", "tonight-restore-card");
    card.setAttribute("aria-hidden", "true");
    card.append(
      element("span", "tonight-restore-card__poster"),
      element("span", "tonight-restore-card__line"),
      element("span", "tonight-restore-card__line tonight-restore-card__line--short"),
    );
    rail.append(card);
  }
  shelves.append(rail);
  return shelves;
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
    const items = batchItems(state).map(displayItem);
    shelves.append(renderShelf({
      title: channel.label,
      items,
      batchState: {
        poolSize: countValue(state, "pool_size"),
        matchedSize: countValue(state, "matched_size"),
        visibleSize: countValue(state, "visible_size"),
      },
      actionsForItem: recommendationActionsForItem,
      itemLimit: MAX_INITIAL_CARDS,
    }));
  }
  return shelves;
}


function discoveryItemId(item = {}) {
  return textValue(item.id) || textValue(item.item_key) || textValue(item.catalog_id);
}

function discoveryReferenceQuery(value = "") {
  const text = textValue(value);
  if (!text) return "";
  const quoted = text.match(/[《「『“\"]([^》」』”\"]{1,60})[》」』”\"]/);
  if (quoted?.[1]) return quoted[1].trim();
  const patterns = [
    /^喜欢\s*(.+?)\s*的还喜欢/u,
    /(?:想看|找|推荐)?\s*(?:和|与)\s*(.+?)\s*(?:类似|相似|差不多)/u,
    /(?:类似|像)\s*(?:于)?\s*(.+?)(?:[，。,.!?！？]|但|而|$)/u,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    const candidate = match?.[1]?.replace(/[“”\"《》「」『』]/g, "").trim();
    if (candidate && candidate.length <= 60) return candidate;
  }
  if (text.length <= 32 && !/[，。,.!?！？:：]/u.test(text) && !/(今晚|想看|推荐|更轻松|节奏|氛围|烧脑|情绪)/u.test(text)) {
    return text;
  }
  return "";
}

function discoveryBadge(item = {}) {
  const badge = item.media_badge && typeof item.media_badge === "object" ? item.media_badge : {};
  return {
    label: textValue(badge.label) || textValue(item.media_type, "作品"),
    tone: ["amber", "violet", "cyan", "slate"].includes(textValue(badge.tone)) ? badge.tone : "slate",
  };
}

function discoveryMeta(item = {}) {
  const parts = [];
  if (Number.isFinite(Number(item.year)) && Number(item.year) > 0) parts.push(String(Math.floor(Number(item.year))));
  const country = Array.isArray(item.countries) ? item.countries.map((value) => textValue(value)).find(Boolean) : "";
  if (country) parts.push(country);
  if (Number.isFinite(Number(item.douban_rating)) && Number(item.douban_rating) > 0) {
    parts.push(`豆瓣 ${Number(item.douban_rating).toFixed(1)}`);
  }
  return parts.join(" · ") || "年份与地区待补";
}

function setDiscoveryStatus(composer, message, tone = "neutral") {
  composer.status.dataset.tone = tone;
  composer.status.textContent = message;
}

function setDiscoveryCandidateStatus(composer, message = "") {
  composer.candidateStatus.textContent = message;
  composer.candidateStatus.hidden = !message;
}

function renderDiscoveryCandidates(composer) {
  composer.candidateList.replaceChildren();
  const candidates = Array.isArray(composer.candidates) ? composer.candidates.slice(0, 4) : [];
  composer.candidateTray.hidden = candidates.length === 0;
  if (!candidates.length) return;
  for (const item of candidates) {
    const id = discoveryItemId(item);
    if (!id) continue;
    const badge = discoveryBadge(item);
    const button = element("button", "tonight-discovery-candidate");
    button.type = "button";
    button.dataset.itemId = id;
    button.dataset.tone = badge.tone;
    button.setAttribute("aria-pressed", composer.selectedId === id ? "true" : "false");
    button.setAttribute("aria-label", `选择${badge.label}《${displayTitle(item)}》`);
    const poster = element("span", "tonight-discovery-candidate__poster");
    poster.append(renderMediaFrame(adaptCatalogMedia(item, "poster")));
    const copy = element("span", "tonight-discovery-candidate__copy");
    copy.append(
      element("strong", "tonight-discovery-candidate__title", displayTitle(item)),
      element("span", "tonight-discovery-candidate__meta", discoveryMeta(item)),
    );
    const badgeNode = element("span", "tonight-discovery-candidate__badge", badge.label);
    badgeNode.dataset.tone = badge.tone;
    button.append(poster, copy, badgeNode);
    button.addEventListener("pointerenter", () => {
      void Promise.resolve(dependencies.preloadMedia?.(adaptCatalogMedia(item, "poster")?.localUrl, button)).catch(() => {});
    });
    button.addEventListener("focus", () => {
      void Promise.resolve(dependencies.preloadMedia?.(adaptCatalogMedia(item, "poster")?.localUrl, button)).catch(() => {});
    });
    button.addEventListener("click", () => {
      composer.selectedId = id;
      renderDiscoveryCandidates(composer);
      setDiscoveryCandidateStatus(composer, `已选择${badge.label} · ${item.year || "年份待补"}《${displayTitle(item)}》`);
      if (composer.lastSubmittedText === textValue(composer.input.value)) {
        void submitDiscovery(composer, { preserveSelection: true });
      }
    });
    composer.candidateList.append(button);
  }
}

function discoveryExplanation(item = {}) {
  const explanation = item.explanation;
  if (typeof explanation === "string" && explanation.trim()) return explanation.trim();
  if (explanation && typeof explanation === "object") {
    return textValue(explanation.fusion) || textValue(explanation.from_left) || textValue(explanation.from_right);
  }
  return "这部作品在题材、口碑和你刚才描述的观看状态之间形成了更自然的交集。";
}

function renderDiscoveryResultCard(item = {}) {
  const id = discoveryItemId(item);
  const card = element("article", "tonight-discovery-result");
  const link = element("a", "tonight-discovery-result__link");
  if (id) {
    link.setAttribute("href", `/title/${encodeURIComponent(id)}`);
    link.setAttribute("data-route", "");
  }
  const poster = element("span", "tonight-discovery-result__poster");
  poster.append(renderMediaFrame(adaptCatalogMedia(item, "poster")));
  const body = element("span", "tonight-discovery-result__body");
  const badge = discoveryBadge(item);
  const kicker = element("span", "tonight-discovery-result__kicker");
  const badgeNode = element("span", "tonight-discovery-result__badge", badge.label);
  badgeNode.dataset.tone = badge.tone;
  kicker.append(badgeNode, element("span", "tonight-discovery-result__meta", discoveryMeta(item)));
  body.append(
    kicker,
    element("strong", "tonight-discovery-result__title", displayTitle(item)),
    element("span", "tonight-discovery-result__explanation", discoveryExplanation(item)),
  );
  link.append(poster, body);
  link.addEventListener("pointerenter", () => {
    void Promise.resolve(dependencies.preloadMedia?.(adaptCatalogMedia(item, "poster")?.localUrl, link)).catch(() => {});
  });
  link.addEventListener("focus", () => {
    void Promise.resolve(dependencies.preloadMedia?.(adaptCatalogMedia(item, "poster")?.localUrl, link)).catch(() => {});
  });
  card.append(link);
  return card;
}

function renderDiscoveryResponse(composer, response = {}) {
  const items = Array.isArray(response.items) ? response.items.slice(0, 12) : [];
  composer.resultsRail.replaceChildren();
  composer.intentChips.replaceChildren();
  const chips = Array.isArray(response.chips) ? response.chips : [];
  for (const chip of chips.slice(0, 8)) {
    const label = textValue(chip?.label);
    if (label) composer.intentChips.append(element("span", "tonight-discovery-chip", label));
  }
  composer.intentChips.hidden = composer.intentChips.children.length === 0;
  composer.results.hidden = false;
  composer.resultsTitle.textContent = response.matched_reference
    ? `喜欢《${displayTitle(response.matched_reference)}》的人，也可以从这里开始`
    : "按你此刻的描述，最值得先看的作品";
  if (!items.length) {
    composer.resultsRail.append(element("p", "tonight-discovery-empty", "暂时没有足够可靠的结果。换一种描述，或减少一个限制条件再试。"));
    return;
  }
  for (const item of items) composer.resultsRail.append(renderDiscoveryResultCard(item));
  for (const item of items.slice(0, 3)) {
    void Promise.resolve(dependencies.preloadMedia?.(adaptCatalogMedia(item, "poster")?.localUrl, composer.resultsRail)).catch(() => {});
  }
}

function mergedDiscoveryCandidates(response = {}, existing = []) {
  const merged = [response.matched_reference, ...(Array.isArray(response.alternatives) ? response.alternatives : []), ...existing]
    .filter((item) => item && discoveryItemId(item));
  const seen = new Set();
  return merged.filter((item) => {
    const id = discoveryItemId(item);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  }).slice(0, 4);
}

async function searchDiscoveryCandidates(composer, term, { silent = false } = {}) {
  const query = textValue(term);
  if (!query || composer.disposed || typeof dependencies.api?.getV2 !== "function") return [];
  composer.searchController?.abort();
  const controller = new AbortController();
  const sequence = ++discoveryRequestSequence;
  composer.searchController = controller;
  composer.lastSearchTerm = query;
  if (!silent) setDiscoveryCandidateStatus(composer, `正在辨认“${query}”的不同版本…`);
  try {
    const response = await dependencies.api.getV2(
      `/api/v2/titles/search?q=${encodeURIComponent(query)}&limit=4`,
      { signal: controller.signal },
    );
    if (composer.disposed || controller.signal.aborted || sequence !== discoveryRequestSequence) return composer.candidates;
    composer.candidates = Array.isArray(response?.items) ? response.items.slice(0, 4) : [];
    if (!composer.candidates.some((item) => discoveryItemId(item) === composer.selectedId)) composer.selectedId = "";
    renderDiscoveryCandidates(composer);
    if (!silent) {
      setDiscoveryCandidateStatus(
        composer,
        composer.candidates.length > 1
          ? `找到 ${composer.candidates.length} 个同名或相近作品，请用醒目的媒介角标确认版本。`
          : composer.candidates.length === 1
            ? "已识别到一个高可信作品版本。"
            : `没有找到“${query}”的明确版本，仍可按整句描述推荐。`,
      );
    }
    return composer.candidates;
  } catch (error) {
    if (error?.name === "AbortError" || composer.disposed || sequence !== discoveryRequestSequence) return composer.candidates;
    if (!silent) setDiscoveryCandidateStatus(composer, "作品版本辨认暂时不可用，仍可直接发送整句描述。 ");
    return composer.candidates;
  } finally {
    if (composer.searchController === controller) composer.searchController = null;
  }
}

function scheduleDiscoverySearch(composer) {
  if (composer.searchTimer !== null) dependencies.clearTimer?.(composer.searchTimer);
  composer.searchTimer = null;
  const query = discoveryReferenceQuery(composer.input.value);
  if (!query) {
    composer.searchController?.abort();
    composer.lastSearchTerm = "";
    composer.candidates = [];
    composer.selectedId = "";
    renderDiscoveryCandidates(composer);
    setDiscoveryCandidateStatus(composer, "");
    return;
  }
  composer.searchTimer = dependencies.setTimer?.(() => {
    composer.searchTimer = null;
    void searchDiscoveryCandidates(composer, query);
  }, DISCOVERY_DEBOUNCE_MS) ?? null;
}

async function submitDiscovery(composer, { preserveSelection = false } = {}) {
  const text = textValue(composer.input.value);
  if (!text || composer.disposed || typeof dependencies.api?.postV2 !== "function") {
    setDiscoveryStatus(composer, "先用一句话描述今晚想看的内容。", "error");
    composer.input.focus?.();
    return null;
  }
  if (composer.searchTimer !== null) dependencies.clearTimer?.(composer.searchTimer);
  composer.searchTimer = null;
  const reference = discoveryReferenceQuery(text);
  if (reference && composer.lastSearchTerm !== reference) await searchDiscoveryCandidates(composer, reference, { silent: true });
  if (composer.disposed) return null;

  let selected = composer.candidates.find((item) => discoveryItemId(item) === composer.selectedId) || null;
  let defaultNotice = "";
  if (!selected && composer.candidates.length) {
    selected = composer.candidates[0];
    composer.selectedId = discoveryItemId(selected);
    renderDiscoveryCandidates(composer);
    const badge = discoveryBadge(selected);
    defaultNotice = `已为你匹配热度最高的${badge.label}《${displayTitle(selected)}》，点击标签可切换其他版本`;
    setDiscoveryCandidateStatus(composer, defaultNotice);
  } else if (selected && preserveSelection) {
    const badge = discoveryBadge(selected);
    setDiscoveryCandidateStatus(composer, `正在切换到${badge.label} · ${selected.year || "年份待补"}《${displayTitle(selected)}》`);
  }

  composer.submitController?.abort();
  const controller = new AbortController();
  const sequence = ++discoveryRequestSequence;
  composer.submitController = controller;
  composer.submit.disabled = true;
  composer.panel.dataset.state = "loading";
  setDiscoveryStatus(composer, "正在把作品语义、情绪与口味证据组合成一组可解释结果…", "working");
  try {
    const response = await dependencies.api.postV2("/api/v2/discovery/query", {
      text,
      selection_id: selected ? discoveryItemId(selected) : "",
      limit: 12,
    }, { signal: controller.signal });
    if (composer.disposed || controller.signal.aborted || sequence !== discoveryRequestSequence) return null;
    composer.lastSubmittedText = text;
    composer.candidates = mergedDiscoveryCandidates(response, composer.candidates);
    composer.selectedId = discoveryItemId(response?.matched_reference) || composer.selectedId;
    renderDiscoveryCandidates(composer);
    renderDiscoveryResponse(composer, response);
    setDiscoveryStatus(
      composer,
      defaultNotice || textValue(response?.match_notice) || `已按“${text}”整理出 ${Array.isArray(response?.items) ? response.items.length : 0} 个结果。`,
      "success",
    );
    return response;
  } catch (error) {
    if (error?.name === "AbortError" || composer.disposed || sequence !== discoveryRequestSequence) return null;
    setDiscoveryStatus(composer, "这次探索没有完成。你的原始描述仍然保留，可以直接重试。", "error");
    return null;
  } finally {
    if (composer.submitController === controller) composer.submitController = null;
    if (!composer.disposed && sequence === discoveryRequestSequence) {
      composer.submit.disabled = false;
      composer.panel.dataset.state = "idle";
    }
  }
}

function createDiscoveryComposer() {
  const panel = element("section", "tonight-discovery");
  panel.dataset.state = "idle";
  const heading = element("div", "tonight-discovery__heading");
  const headingCopy = element("div", "tonight-discovery__heading-copy");
  headingCopy.append(
    element("p", "eyebrow", "NATURAL LANGUAGE / 说出今晚"),
    element("h2", "tonight-discovery__title", "不用先选分类，直接描述你想进入的世界。"),
    element("p", "tonight-discovery__copy", "例如：喜欢《星际穿越》的宏大感，但今晚想轻松一点；或直接输入“三体”确认具体版本。"),
  );
  const examples = element("div", "tonight-discovery__examples");
  for (const prompt of ["类似《降临》，但更温暖", "节奏紧凑、烧脑但不要恐怖", "喜欢三体的还喜欢什么"]) {
    const button = element("button", "tonight-discovery__example", prompt);
    button.type = "button";
    examples.append(button);
  }
  heading.append(headingCopy, examples);

  const form = element("form", "tonight-discovery__form");
  const inputWrap = element("div", "tonight-discovery__input-wrap");
  const input = document.createElement("textarea");
  input.className = "tonight-discovery__input";
  input.rows = 2;
  input.maxLength = 240;
  input.placeholder = "今晚我想看……";
  input.setAttribute("aria-label", "用自然语言描述今晚想看的作品");
  const submit = element("button", "tonight-discovery__submit", "开始探索");
  submit.type = "submit";
  inputWrap.append(input, submit);
  const helper = element("p", "tonight-discovery__helper", "输入停顿 420ms 后辨认同名作品 · Enter 发送 · Shift + Enter 换行");
  form.append(inputWrap, helper);

  const candidateTray = element("section", "tonight-discovery-candidates");
  candidateTray.hidden = true;
  const candidateHeading = element("div", "tonight-discovery-candidates__heading");
  candidateHeading.append(
    element("strong", "tonight-discovery-candidates__title", "你指的是哪一个？"),
    element("span", "tonight-discovery-candidates__hint", "媒介、年份和地区会直接影响推荐语境"),
  );
  const candidateStatus = element("p", "tonight-discovery-candidates__status");
  candidateStatus.setAttribute("aria-live", "polite");
  candidateStatus.hidden = true;
  const candidateList = element("div", "tonight-discovery-candidates__list");
  candidateTray.append(candidateHeading, candidateStatus, candidateList);

  const status = element("p", "tonight-discovery__status");
  status.setAttribute("aria-live", "polite");
  const results = element("section", "tonight-discovery-results");
  results.hidden = true;
  const resultsHeading = element("div", "tonight-discovery-results__heading");
  const resultsTitle = element("h3", "tonight-discovery-results__title", "按你此刻的描述，最值得先看的作品");
  const intentChips = element("div", "tonight-discovery-chips");
  intentChips.hidden = true;
  resultsHeading.append(resultsTitle, intentChips);
  const resultsRail = element("div", "tonight-discovery-results__rail");
  results.append(resultsHeading, resultsRail);
  panel.append(heading, form, candidateTray, status, results);

  const composer = {
    panel, form, input, submit, candidateTray, candidateStatus, candidateList,
    status, results, resultsTitle, intentChips, resultsRail,
    candidates: [], selectedId: "", lastSearchTerm: "", lastSubmittedText: "",
    searchTimer: null, searchController: null, submitController: null,
    composing: false, disposed: false,
    dispose() {
      if (composer.disposed) return;
      composer.disposed = true;
      if (composer.searchTimer !== null) dependencies.clearTimer?.(composer.searchTimer);
      composer.searchTimer = null;
      composer.searchController?.abort();
      composer.submitController?.abort();
    },
  };

  form.addEventListener("submit", (event) => {
    event?.preventDefault?.();
    void submitDiscovery(composer);
  });
  input.addEventListener("compositionstart", () => { composer.composing = true; });
  input.addEventListener("compositionend", () => {
    composer.composing = false;
    scheduleDiscoverySearch(composer);
  });
  input.addEventListener("input", () => {
    if (!composer.composing) scheduleDiscoverySearch(composer);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || composer.composing) return;
    event.preventDefault?.();
    void submitDiscovery(composer);
  });
  for (const button of examples.children || []) {
    button.addEventListener("click", () => {
      input.value = button.textContent;
      scheduleDiscoverySearch(composer);
      input.focus?.();
    });
  }
  return composer;
}

export function configureTonight(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    api: { ...dependencies.api, ...(options.api || {}) },
  };
  if (mountedTonight && options.root && mountedTonight.root !== options.root) {
    activeDiscoveryComposer?.dispose?.();
    activeDiscoveryComposer = null;
    mountedTonight = null;
  }
  if (!heroResizeHandler && typeof globalThis.addEventListener === "function") {
    heroResizeHandler = () => {
      if (mountedTonight?.hero) scheduleHeroTitleFit(mountedTonight.hero);
    };
    globalThis.addEventListener("resize", heroResizeHandler, { passive: true });
  }
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
  activeDiscoveryComposer?.dispose?.();
  const discovery = createDiscoveryComposer();
  activeDiscoveryComposer = discovery;
  const stage = element("div", "tonight-stage");
  const hero = element("section", "tonight-hero");
  hero.setAttribute("aria-labelledby", "tonight-hero-title");
  const toolbar = element("section", "tonight-batch-toolbar");
  const shelves = element("div", "tonight-shelves");
  stage.append(hero, toolbar, shelves);
  intro.append(introCopy, tabs);
  page.append(intro, discovery.panel, stage);
  return { page, deck, tabs, discovery, stage, hero, toolbar, shelves };
}

function replaceIntoStable(target, fresh) {
  target.className = fresh.className;
  for (const [key, value] of Object.entries(fresh.dataset || {})) target.dataset[key] = value;
  target.replaceChildren(...(fresh.children || []));
}

function updateStableHero(mount, recommendation, channel) {
  replaceIntoStable(mount.hero, renderHero(recommendation, channel));
  scheduleHeroTitleFit(mount.hero);
}

function updateStableToolbar(mount, recommendation, channel) {
  const state = channelState(recommendation, channel);
  const candidateCounts = state.candidate_counts && typeof state.candidate_counts === "object" ? state.candidate_counts : {};
  const toolbar = mount.toolbar;
  toolbar.className = "tonight-batch-toolbar";
  toolbar.setAttribute("aria-label", `${channel.label}批次工具栏`);
  let controls = toolbar._stableControls;
  if (!controls) {
    toolbar.replaceChildren();
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
    previous.addEventListener("click", () => {
      void restorePreviousBatch(toolbar._activeChannelSlug || "movie");
    });
    const next = element("button", "tonight-button tonight-button--signal", "按原因换一批");
    next.type = "button";
    next.addEventListener("click", () => {
      void requestNextBatch(toolbar._activeChannelSlug || "movie", reason.value);
    });
    controlsNode.append(reason, previous, next);
    const status = element("p", "tonight-batch-status");
    status.setAttribute("aria-live", "polite");
    toolbar.append(counts, controlsNode, status);
    controls = { counts, controlsNode, reason, previous, next, status };
    toolbar._stableControls = controls;
  }
  const previousChannelSlug = toolbar._activeChannelSlug;
  if (previousChannelSlug && previousChannelSlug !== channel.slug) {
    const previousOperation = batchOperation(previousChannelSlug);
    if (previousOperation.controls === controls) previousOperation.controls = null;
  }
  toolbar._activeChannelSlug = channel.slug;
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
    const items = batchItems(state).map(displayItem);
    mount.shelves.append(renderShelf({
      title: channel.label,
      items,
      batchState: {
        poolSize: countValue(state, "pool_size"),
        matchedSize: countValue(state, "matched_size"),
        visibleSize: countValue(state, "visible_size"),
      },
      actionsForItem: recommendationActionsForItem,
      itemLimit: MAX_INITIAL_CARDS,
      originFilter: sourceFilterByChannel.get(channel.slug) || "all",
      onOriginFilterChange: (filter) => {
        sourceFilterByChannel.set(channel.slug, filter);
        ensureVisibleMediaJobs(recommendation, channel, filter);
        ensureVisibleMetadataJobs(recommendation, channel, filter);
      },
    }));
  }
}

function updateStableRestore(mount, activeChannel) {
  replaceIntoStable(mount.hero, renderRestoreHero(activeChannel));
  mount.toolbar._stableControls = null;
  replaceIntoStable(mount.toolbar, renderRestorePanel());
  replaceIntoStable(mount.shelves, renderRestoreShelves());
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
  if (restoringChannel(recommendation, activeChannel)) {
    updateStableRestore(mount, activeChannel);
    mount.page.dataset.channel = activeChannel.slug;
    mount.page.dataset.state = "restoring";
    return mount.page;
  }
  prewarmChannelHeroes(recommendation);
  updateStableHero(mount, recommendation, activeChannel);
  updateStableToolbar(mount, recommendation, activeChannel);
  updateStableShelves(mount, recommendation, activeChannel);
  mount.page.dataset.channel = activeChannel.slug;
  mount.page.dataset.state = "ready";
  ensureVisibleMediaJobs(recommendation, activeChannel);
  ensureVisibleMetadataJobs(recommendation, activeChannel);
  ensureHeroPeopleWarmup(recommendation, activeChannel);
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
    if (root) scheduleHeroTitleFit(mount.hero);
    return mount.page;
  }
  return updateTonightPage(mountedTonight, recommendation);
}

function normalizeIdentityMediaType(value) {
  const normalized = textValue(value).normalize("NFKC").toLocaleLowerCase("zh-CN").replace(/[\s_-]+/g, "");
  if (["movie", "film", "电影"].includes(normalized)) return "电影";
  if (["tv", "series", "tvseries", "show", "电视剧", "剧集"].includes(normalized)) return "电视剧";
  if (["anime", "animation", "animatedseries", "动画", "动漫", "动画剧集"].includes(normalized)) return "动漫";
  return normalized;
}

function fallbackItemIdentity(item = {}) {
  const title = textValue(item.title || item.name)
    .normalize("NFKC")
    .toLocaleLowerCase("zh-CN")
    .replace(/[\s·:：\-—_（）()《》\[\]【】'"“”.,，。!?！？/\\|]+/g, "");
  if (!title) return "";
  const year = textValue(item.year || item.release_year || item.releaseYear);
  const mediaType = normalizeIdentityMediaType(item.media_type || item.mediaType || item.type);
  const basis = `${title}|${year}|${mediaType}`;
  let hash = 2166136261;
  for (let index = 0; index < basis.length; index += 1) {
    hash ^= basis.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `fallback:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function itemIdentity(item = {}) {
  return textValue(item.item_key) || textValue(item.itemKey) || textValue(item.id)
    || (textValue(item.douban_id) ? `douban:${textValue(item.douban_id)}` : "")
    || fallbackItemIdentity(item);
}

function feedbackFeatures(item = {}) {
  const list = (value, limit = 6) => (Array.isArray(value)
    ? value.map((entry) => textValue(entry)).filter(Boolean).slice(0, limit)
    : []);
  const mediaType = textValue(item.media_type);
  return {
    genre: list(item.genres),
    country: list(item.countries, 4),
    director: list(item.directors, 3),
    cast: list(item.casts, 4),
    media_type: mediaType ? [mediaType] : [],
  };
}

async function refreshSessionAfterFeedback(sessionId, source) {
  if (!sessionId || typeof dependencies.api?.getV2 !== "function") return null;
  const session = await dependencies.api.getV2(`/api/v2/recommend/sessions/${encodeURIComponent(sessionId)}`);
  dependencies.store?.dispatch?.({
    type: "recommendation/sessionReceived",
    session,
    source,
    expectedSessionId: sessionId,
    preserveOtherSessions: true,
  });
  return session;
}

function clearFeedbackToast() {
  if (feedbackToastTimer !== null) dependencies.clearTimer?.(feedbackToastTimer);
  feedbackToastTimer = null;
  feedbackToast?.remove?.();
  feedbackToast = null;
}

function showFeedbackToast(message, { eventId = "", sessionId = "", undo = false } = {}) {
  const host = dependencies.root || mountedTonight?.root;
  if (!host?.append) return;
  clearFeedbackToast();
  const toast = element("div", "tonight-feedback-toast");
  toast.setAttribute("role", "status");
  toast.append(element("span", "tonight-feedback-toast__copy", message));
  if (undo && eventId) {
    const button = element("button", "tonight-feedback-toast__undo", "撤销");
    button.type = "button";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await dependencies.api.postV2(`/api/v2/feedback/${encodeURIComponent(eventId)}/undo`, {});
        await refreshSessionAfterFeedback(sessionId, "feedback-undo");
        clearFeedbackToast();
      } catch {
        button.disabled = false;
        toast.querySelector?.(".tonight-feedback-toast__copy")?.replaceChildren?.("撤销失败，请稍后重试。");
      }
    });
    toast.append(button);
  }
  host.append(toast);
  feedbackToast = toast;
  feedbackToastTimer = dependencies.setTimer?.(clearFeedbackToast, 10000) ?? null;
}

export async function markItemNotInterested(item = {}) {
  const store = configuredStore();
  const itemKey = itemIdentity(item);
  if (!itemKey || typeof dependencies.api?.postV2 !== "function") return null;
  const current = feedbackOperations.get(itemKey);
  if (current?.promise) return current.promise;
  const recommendation = recommendationState(store.getState());
  const active = activeChannelFor(recommendation);
  const sessionId = textValue(channelState(recommendation, active).sessionId) || textValue(recommendation.sessionId);
  if (!sessionId) return null;
  store.dispatch({ type: "recommendation/itemSuppressed", itemKey });
  const promise = Promise.resolve(dependencies.api.postV2("/api/v2/feedback", {
    event_type: "permanent-avoid",
    scope: "permanent",
    session_id: sessionId,
    item_key: itemKey,
    payload: { features: feedbackFeatures(item) },
  })).then((result) => {
    const eventId = textValue(result?.id);
    feedbackOperations.set(itemKey, { eventId, promise: null });
    showFeedbackToast(`已将《${displayTitle(item, "这部作品")}》设为不感兴趣`, {
      eventId,
      sessionId,
      undo: Boolean(eventId),
    });
    return result;
  }).catch(async (error) => {
    feedbackOperations.delete(itemKey);
    try { await refreshSessionAfterFeedback(sessionId, "feedback-rollback"); } catch { /* keep the page usable */ }
    showFeedbackToast("保存不感兴趣失败，推荐已恢复。", {});
    throw error;
  });
  feedbackOperations.set(itemKey, { promise, eventId: "" });
  return promise;
}

export async function markItemWatched(item = {}) {
  const store = configuredStore();
  const itemKey = itemIdentity(item);
  if (!itemKey || typeof dependencies.api?.postV2 !== "function") return null;
  const current = feedbackOperations.get(itemKey);
  if (current?.promise) return current.promise;
  const recommendation = recommendationState(store.getState());
  const active = activeChannelFor(recommendation);
  const sessionId = textValue(channelState(recommendation, active).sessionId) || textValue(recommendation.sessionId);
  if (!sessionId) return null;
  store.dispatch({ type: "recommendation/itemSuppressed", itemKey });
  const promise = Promise.resolve(dependencies.api.postV2("/api/v2/feedback", {
    event_type: "watched",
    scope: "permanent",
    session_id: sessionId,
    item_key: itemKey,
    payload: { features: feedbackFeatures(item) },
  })).then(async (result) => {
    const eventId = textValue(result?.id);
    feedbackOperations.set(itemKey, { eventId, promise: null });
    try { await refreshSessionAfterFeedback(sessionId, "feedback-watched"); } catch { /* the durable feedback already succeeded */ }
    showFeedbackToast(`已把《${displayTitle(item, "这部作品")}》加入看过`, {
      eventId,
      sessionId,
      undo: Boolean(eventId),
    });
    return result;
  }).catch(async (error) => {
    feedbackOperations.delete(itemKey);
    try { await refreshSessionAfterFeedback(sessionId, "feedback-rollback"); } catch { /* keep the page usable */ }
    showFeedbackToast("保存看过状态失败，推荐已恢复。", {});
    throw error;
  });
  feedbackOperations.set(itemKey, { promise, eventId: "" });
  return promise;
}

export async function markItemWanted(item = {}) {
  const store = configuredStore();
  const itemKey = itemIdentity(item);
  if (!itemKey || typeof dependencies.api?.postV2 !== "function") return null;
  const current = feedbackOperations.get(itemKey);
  if (current?.promise) return current.promise;
  const recommendation = recommendationState(store.getState());
  const active = activeChannelFor(recommendation);
  const sessionId = textValue(channelState(recommendation, active).sessionId) || textValue(recommendation.sessionId);
  if (!sessionId) return null;
  store.dispatch({ type: "recommendation/itemSuppressed", itemKey });
  const promise = Promise.resolve(dependencies.api.postV2("/api/v2/feedback", {
    event_type: "want",
    scope: "permanent",
    session_id: sessionId,
    item_key: itemKey,
    payload: { features: feedbackFeatures(item) },
  })).then(async (result) => {
    const eventId = textValue(result?.id);
    feedbackOperations.set(itemKey, { eventId, promise: null });
    try { await refreshSessionAfterFeedback(sessionId, "feedback-want"); } catch { /* durable state already succeeded */ }
    showFeedbackToast(`已把《${displayTitle(item, "这部作品")}》加入想看`, {
      eventId,
      sessionId,
      undo: Boolean(eventId),
    });
    return result;
  }).catch(async (error) => {
    feedbackOperations.delete(itemKey);
    try { await refreshSessionAfterFeedback(sessionId, "feedback-rollback"); } catch { /* keep the page usable */ }
    showFeedbackToast("保存想看状态失败，推荐已恢复。", {});
    throw error;
  });
  feedbackOperations.set(itemKey, { promise, eventId: "" });
  return promise;
}

export function recommendationActionsForItem(item) {
  const itemKey = itemIdentity(item);
  const pending = Boolean(feedbackOperations.get(itemKey)?.promise);
  return [
    {
      label: pending ? "正在保存…" : "想看",
      ariaLabel: `将《${displayTitle(item, "这部作品")}》加入想看并停止重复推荐`,
      className: "title-card__action--want",
      disabled: pending,
      onClick: () => { void markItemWanted(item); },
    },
    {
      label: pending ? "正在保存…" : "已看过",
      ariaLabel: `将《${displayTitle(item, "这部作品")}》标记为已看过并停止推荐`,
      className: "title-card__action--watched",
      disabled: pending,
      onClick: () => { void markItemWatched(item); },
    },
    {
      label: pending ? "请稍候…" : "不感兴趣",
      ariaLabel: `不再推荐《${displayTitle(item, "这部作品")}》`,
      className: "title-card__action--negative",
      disabled: pending,
      onClick: () => { void markItemNotInterested(item); },
    },
  ];
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

function ensureVisibleMediaJobs(recommendation, channel, originFilter = sourceFilterByChannel.get(channel.slug) || "all") {
  const sessionId = textValue(channelState(recommendation, channel).sessionId) || textValue(recommendation.sessionId);
  if (!sessionId || typeof dependencies.api?.postV2 !== "function") return;
  const state = channelState(recommendation, channel);
  const seen = new Set();
  for (const item of visibleBatchItems(state, originFilter)) {
    const identity = itemIdentity(item);
    if (!identity || seen.has(identity)) continue;
    seen.add(identity);
    enqueueMediaJob(item, channel, sessionId);
  }
}

function enrichedTitlePatch(title = {}, fallback = {}) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const raw = item.raw && typeof item.raw === "object" ? item.raw : {};
  const patch = { item_key: itemIdentity(fallback) || textValue(title?.item_key) };
  const assignText = (field, ...values) => {
    const value = values.map((entry) => textValue(entry)).find(Boolean);
    if (value) patch[field] = value;
  };
  const assignList = (field, ...values) => {
    const value = values.find((entry) => Array.isArray(entry) && entry.length);
    if (value) patch[field] = value.map((entry) => textValue(entry)).filter(Boolean);
  };
  assignText("title", title?.title, item.title, fallback.title);
  assignText("media_type", title?.media_type, item.media_type, fallback.media_type);
  assignText("summary", item.summary, item.intro, fallback.summary);
  assignText("url", item.url, fallback.url);
  assignText("douban_id", item.douban_id, fallback.douban_id);
  if (Number.isFinite(title?.year ?? item.year)) patch.year = title?.year ?? item.year;
  if (Number.isFinite(item.douban_rating)) patch.douban_rating = item.douban_rating;
  if (Number.isFinite(item.vote_count)) patch.vote_count = item.vote_count;
  assignList("genres", item.genres, fallback.genres);
  assignList("countries", item.countries, fallback.countries);
  assignList("languages", item.languages, fallback.languages);
  assignList("directors", item.directors, fallback.directors);
  assignList("casts", item.casts, fallback.casts);
  const ratings = raw.ratings && typeof raw.ratings === "object" ? raw.ratings : null;
  if (ratings) patch.source_ratings = { ...(fallback.source_ratings || {}), ...ratings };
  for (const field of ["poster", "backdrop"]) {
    if (title?.[field] && typeof title[field] === "object") patch[field] = title[field];
  }
  if (Array.isArray(title?.stills) && title.stills.length) patch.stills = title.stills;
  if (Array.isArray(title?.people) && title.people.length) patch.people = title.people;
  return patch;
}

function pumpMetadataJobs() {
  if (typeof dependencies.api?.postV2 !== "function") return;
  while (activeMetadataJobs < MAX_VISIBLE_METADATA_JOBS && metadataJobQueue.length) {
    const task = metadataJobQueue.shift();
    const record = metadataJobsByIdentity.get(task.key);
    if (!record || record.state !== "queued") continue;
    activeMetadataJobs += 1;
    record.state = "running";
    record.attemptedAt = Date.now();
    Promise.resolve(dependencies.api.postV2(`/api/v2/titles/${encodeURIComponent(task.key)}/enrich`, {}))
      .then((title) => {
        const patch = enrichedTitlePatch(title, task.item);
        record.state = needsLocalizedSummary(patch.summary) ? "failed" : "ready";
        record.attemptedAt = Date.now();
        dependencies.store?.dispatch?.({
          type: "recommendation/itemHydrated",
          expectedSessionId: task.sessionId,
          itemKey: task.key,
          item: patch,
        });
      })
      .catch(() => {
        record.state = "failed";
        record.attemptedAt = Date.now();
      })
      .finally(() => {
        activeMetadataJobs = Math.max(0, activeMetadataJobs - 1);
        pumpMetadataJobs();
      });
  }
}

function enqueueMetadataEnrichment(item, sessionId) {
  const key = itemIdentity(item);
  if (!key || !needsLocalizedSummary(item?.summary)) return;
  const existing = metadataJobsByIdentity.get(key);
  if (existing?.state === "queued" || existing?.state === "running" || existing?.state === "ready") return;
  if (existing?.state === "failed" && Date.now() - Number(existing.attemptedAt || 0) < METADATA_RETRY_AFTER_MS) return;
  metadataJobsByIdentity.set(key, { state: "queued", attemptedAt: 0 });
  metadataJobQueue.push({ key, sessionId, item: { ...item } });
  if (metadataJobsByIdentity.size > 480) metadataJobsByIdentity.delete(metadataJobsByIdentity.keys().next().value);
  pumpMetadataJobs();
}

function ensureVisibleMetadataJobs(recommendation, channel, originFilter = sourceFilterByChannel.get(channel.slug) || "all") {
  const sessionId = textValue(channelState(recommendation, channel).sessionId) || textValue(recommendation.sessionId);
  if (!sessionId || typeof dependencies.api?.postV2 !== "function") return;
  const state = channelState(recommendation, channel);
  for (const item of visibleBatchItems(state, originFilter)) enqueueMetadataEnrichment(item, sessionId);
}

function portraitIsReady(person = {}) {
  const portrait = person?.portrait && typeof person.portrait === "object" ? person.portrait : {};
  return textValue(portrait.media_status).toLowerCase() === "ready"
    && textValue(portrait.url).startsWith("/media/");
}

function enqueueHeroPortraitWarmup(person, title) {
  const personId = textValue(person?.id);
  const personName = textValue(person?.name);
  if (!personId || !personName || portraitIsReady(person)) return Promise.resolve(null);
  const key = mediaJobKey("portrait", personId);
  const existing = portraitWarmupsByIdentity.get(key);
  if (existing?.promise) return existing.promise;
  if (["queued", "pending", "processing", "resolving", "downloading", "validating", "ready"].includes(existing?.state)) {
    return Promise.resolve(existing);
  }
  const record = { state: "queued", promise: null };
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const role = textValue(person?.role, "cast");
  const promise = Promise.resolve(dependencies.api.postV2("/api/v2/media/jobs", {
    kind: "portrait",
    identity_key: personId,
    person_name: personName,
    occupations: [role],
    work_context: [textValue(title?.title, textValue(item.title))].filter(Boolean),
    media_type: textValue(title?.media_type, textValue(item.media_type)),
    priority: role === "director" ? 12 : 8,
  })).then((job) => {
    record.promise = null;
    record.state = textValue(job?.state, "queued").toLowerCase();
    return job;
  }).catch(() => {
    portraitWarmupsByIdentity.delete(key);
    return null;
  });
  record.promise = promise;
  portraitWarmupsByIdentity.set(key, record);
  return promise;
}

function ensureHeroPeopleWarmup(recommendation, channel) {
  if (typeof dependencies.api?.getV2 !== "function" || typeof dependencies.api?.postV2 !== "function") return;
  const state = channelState(recommendation, channel);
  const hero = heroItemForChannel(state, channel).item;
  const identity = itemIdentity(hero || {});
  if (!identity || heroPeopleWarmups.has(identity)) return;
  const request = Promise.resolve(dependencies.api.getV2(`/api/v2/titles/${encodeURIComponent(identity)}`))
    .then((title) => Promise.all(
      (Array.isArray(title?.people) ? title.people : [])
        .slice(0, MAX_HERO_PEOPLE_PREFETCH)
        .map((person) => enqueueHeroPortraitWarmup(person, title)),
    ))
    .catch(() => {
      heroPeopleWarmups.delete(identity);
      return [];
    });
  heroPeopleWarmups.set(identity, request);
  if (heroPeopleWarmups.size > 80) heroPeopleWarmups.delete(heroPeopleWarmups.keys().next().value);
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
