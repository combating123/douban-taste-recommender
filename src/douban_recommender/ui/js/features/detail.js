import { getV2, postV2 } from "../core/api.js";
import { adaptCatalogMedia, adaptPersonMedia, attachResilientImage } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";
import { renderMediaGallery } from "../components/media-gallery.js";
import { mediaBadgeLabel, renderTitleCard } from "../components/title-card.js";
import { openPersonSheet, setPersonContext } from "./people.js";

const RELATION_LIMIT = 9;
const SAFE_ROUTE_SEGMENT = /^[A-Za-z0-9:._~-]+$/;
const SAFE_DETAIL_RETURN_PATH = /^\/(?:tonight(?:\/(?:movie|series|anime-series))?|library|observatory|taste|universe|health)$/;
const RATING_LABELS = Object.freeze({ imdb: "IMDb", tmdb: "TMDb", tvmaze: "TVMaze", anilist: "AniList", jikan: "MAL" });
const LOCAL_STATE_LABELS = Object.freeze({
  candidate: "推荐候选",
  watched: "已看过",
  wish: "想看",
  wanted: "想看",
  collect: "想看",
  rated: "已评分",
  ready: "资料已就绪",
  online: "在线发现",
  hidden: "已隐藏",
  archived: "已归档",
});
const POLLABLE_MEDIA_STATES = new Set(["queued", "pending", "processing", "resolving", "downloading", "validating"]);
const portraitPrefetchInFlight = new Set();
const portraitPrefetched = new Set();
const portraitJobState = new Map();
const portraitJobTimers = new Map();
const personCardCache = new Map();
const relationPosterJobState = new Map();
const relationPosterJobTimers = new Map();
const titlePosterJobState = new Map();
const titlePosterJobTimers = new Map();
const titleBackdropJobState = new Map();
const titleBackdropJobTimers = new Map();
const metadataEnrichmentAttemptedAt = new Map();
const metadataEnrichmentInFlight = new Map();
let activeDetail = null;

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function titleDisplayName(record, fallback = "未命名作品") {
  return textValue(record?.display_title)
    || textValue(record?.item?.display_title)
    || textValue(record?.title)
    || textValue(record?.item?.title)
    || fallback;
}

function listValue(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()) : [];
}

function containsHan(value) {
  return /[\u3400-\u9fff]/u.test(textValue(value));
}

/**
 * Keep identity metadata in the API, but do not put an unverified foreign
 * title into the main Simplified-Chinese reading flow.  A localized display
 * title remains the hero heading; this helper only governs the optional fact
 * row for original/alternate names.
 */
export function displayableOriginalTitle(value) {
  const title = textValue(value);
  if (!title || !containsHan(title)) return "";
  return title;
}

export function localStateLabel(value) {
  const state = textValue(value);
  return LOCAL_STATE_LABELS[state.toLowerCase()] || state || "资料有限";
}

function isGeneratedSummary(value) {
  const summary = textValue(value);
  return !summary || [
    "正在补齐这部",
    "资料有限：本地片库暂未记录作品简介",
    "由 CineScope 精选扩展池补入的",
    "详情：点击卡片查看简介",
  ].some((prefix) => summary.startsWith(prefix));
}

function hasSpecificGenres(item = {}, mediaType = "") {
  const generic = new Set(["作品", "媒体", "电影", "电视剧", "动漫", textValue(mediaType)].filter(Boolean));
  return listValue(item?.genres).some((genre) => !generic.has(genre));
}

function apiRouteSegment(value) {
  const clean = textValue(value);
  return SAFE_ROUTE_SEGMENT.test(clean) ? clean : "";
}

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

async function requestJson(path, { signal } = {}) {
  const response = await fetch(path, { method: "GET", headers: { Accept: "application/json" }, signal });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

let dependencies = {
  root: null,
  fetchJson: requestJson,
  detailGet: getV2,
  api: { postV2, getV2 },
  openPersonSheet,
  setTimer: (callback, delay) => setTimeout(callback, delay),
  clearTimer: (id) => clearTimeout(id),
  mediaPollInterval: 1200,
  onExploreUniverse: () => {},
  getDetailReturnPath: () => "/tonight",
  onExitDetail: () => {},
};

export function configureDetail(options = {}) {
  const api = {
    ...dependencies.api,
    ...(options.api || {}),
    ...(options.getV2 ? { getV2: options.getV2 } : {}),
    ...(options.fetchJson && !options.api?.getV2 && !options.getV2 ? { getV2: options.fetchJson } : {}),
    ...(options.postV2 ? { postV2: options.postV2 } : {}),
  };
  const detailGet = options.detailGet
    || options.fetchJson
    || options.getV2
    || options.api?.getV2
    || dependencies.detailGet
    || getV2;
  dependencies = {
    ...dependencies,
    ...options,
    fetchJson: options.fetchJson || dependencies.fetchJson,
    detailGet,
    api,
    setTimer: options.setTimer || dependencies.setTimer,
    clearTimer: options.clearTimer || dependencies.clearTimer,
    mediaPollInterval: options.mediaPollInterval || dependencies.mediaPollInterval,
    openPersonSheet: options.openPersonSheet || dependencies.openPersonSheet,
    onExploreUniverse: options.onExploreUniverse || dependencies.onExploreUniverse,
    getDetailReturnPath: options.getDetailReturnPath || dependencies.getDetailReturnPath,
    onExitDetail: options.onExitDetail || dependencies.onExitDetail,
  };
}

function detailApiGet(path, options = {}) {
  const reader = dependencies.detailGet || dependencies.api?.getV2 || dependencies.fetchJson || getV2;
  return reader(path, options);
}

function auxiliaryApiGet(path, options = {}) {
  const reader = dependencies.api?.getV2 || dependencies.fetchJson || getV2;
  return reader(path, options);
}

export function safeDetailReturnPath(value) {
  const path = textValue(value);
  return SAFE_DETAIL_RETURN_PATH.test(path) ? path : "/tonight";
}

function detailReturnLabel(path) {
  if (path === "/library") return "返回片库";
  if (path === "/observatory") return "返回观影雷达";
  if (path === "/taste") return "返回口味";
  if (path === "/universe") return "返回探索实验室";
  if (path === "/health") return "返回设置";
  return "返回推荐";
}

function detailReturnPathFor(title = {}) {
  const historyFrom = textValue(globalThis.window?.history?.state?.from);
  const requestedPath = SAFE_DETAIL_RETURN_PATH.test(historyFrom)
    ? historyFrom
    : dependencies.getDetailReturnPath?.();
  let path = safeDetailReturnPath(requestedPath);
  if (title?.is_live && !SAFE_DETAIL_RETURN_PATH.test(historyFrom) && path === "/tonight") {
    path = "/observatory";
  }
  return path;
}

function renderDetailReturn(title = {}) {
  const path = detailReturnPathFor(title);
  const label = detailReturnLabel(path);
  const bar = element("div", "detail-return-bar");
  const button = element("button", "detail-return", `← ${label}`);
  button.type = "button";
  button.setAttribute("aria-label", `${label}并恢复之前的浏览位置`);
  button.addEventListener("click", () => dependencies.onExitDetail?.(path));
  bar.append(button, element("span", "detail-return-bar__context", "作品档案"));
  return bar;
}

function roleLabel(role) {
  if (role === "director") return "导演";
  if (role === "cast") return "演员";
  return textValue(role, "主创");
}

function fact(label, value) {
  const row = element("div", "detail-fact");
  row.append(element("dt", "detail-fact__label", label), element("dd", "detail-fact__value", value));
  return row;
}

function scoreCard(label, value, explanation) {
  const card = element("article", "detail-score-card");
  card.append(
    element("p", "detail-score-card__label", label),
    element("strong", "detail-score-card__value", value),
    element("p", "detail-score-card__explanation", explanation),
  );
  return card;
}

function numericText(value, suffix = "") {
  return Number.isFinite(value) ? `${value}${suffix}` : "资料有限";
}

function integerText(value) {
  return Number.isFinite(value) && value >= 0 ? new Intl.NumberFormat("zh-CN").format(Math.trunc(value)) : "";
}

function sourceRatingRows(item = {}) {
  const raw = item?.raw && typeof item.raw === "object" ? item.raw : {};
  const ratings = raw.ratings && typeof raw.ratings === "object" ? raw.ratings : {};
  const votes = raw.rating_votes && typeof raw.rating_votes === "object" ? raw.rating_votes : {};
  const rows = [];
  for (const [provider, value] of Object.entries(ratings)) {
    if (provider === "douban") continue;
    let score = Number(value);
    if (!Number.isFinite(score) || score <= 0) continue;
    if (score > 10 && score <= 100) score /= 10;
    if (score > 10) continue;
    const directVotes = Number(votes[provider]);
    const fallbackVotes = Number(votes[`${provider}_popularity`] ?? votes[`${provider}_weight`]);
    rows.push({
      provider,
      label: RATING_LABELS[provider] || provider,
      score: Math.round(score * 10) / 10,
      votes: Number.isFinite(directVotes) ? directVotes : Number.isFinite(fallbackVotes) ? fallbackVotes : null,
    });
  }
  return rows.slice(0, 4);
}

function scoreEvidenceCount(title = {}) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  return Number.isFinite(item.douban_rating)
    + sourceRatingRows(item).length
    + Number.isFinite(item.my_rating);
}

export function factRows(title = {}) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const raw = item.raw && typeof item.raw === "object" ? item.raw : {};
  const originalTitle = textValue(raw.original_title) || textValue(item.original_title);
  const visibleOriginalTitle = displayableOriginalTitle(originalTitle);
  const visibleAliases = listValue(raw.aliases)
    .map((value) => displayableOriginalTitle(value))
    .filter((value) => value && value !== visibleOriginalTitle)
    .slice(0, 6)
    .join(" / ");
  return [
    ["年份", Number.isFinite(title?.year) ? String(title.year) : ""],
    ["媒介类型", mediaBadgeLabel(title)],
    [title?.is_live ? "原始片名" : "原名", visibleOriginalTitle],
    ["又名", title?.is_live ? "" : visibleAliases],
    ["国家 / 地区", listValue(item.countries).join(" / ")],
    ["类型", listValue(item.genres).join(" / ")],
    ["导演", listValue(item.directors).join(" / ")],
    ["语言", listValue(item.languages).join(" / ")],
    ["上映日期", textValue(item.release_date) || textValue(raw.release_date)],
    ["片长", Number.isFinite(item.duration ?? raw.runtime) ? `${item.duration ?? raw.runtime} 分钟` : ""],
    ["单集时长", Number.isFinite(raw.episode_runtime) ? `${raw.episode_runtime} 分钟` : ""],
    ["集数", Number.isFinite(item.episode_count ?? raw.episodes) ? String(item.episode_count ?? raw.episodes) : ""],
  ].filter(([, value]) => value);
}

export function detailOverviewLayout(title = {}) {
  const scoreCount = scoreEvidenceCount(title);
  const factCount = factRows(title).length;
  const scoreDensity = scoreCount >= 3 ? "rich" : scoreCount >= 2 ? "regular" : "sparse";
  const factDensity = factCount >= 8 ? "rich" : factCount >= 5 ? "regular" : "sparse";
  return {
    mode: scoreCount >= 2 && factCount >= 6 ? "balanced" : "flow",
    scoreCount,
    factCount,
    scoreDensity,
    factDensity,
  };
}

function applyOverviewLayout(grid, title) {
  if (!grid) return detailOverviewLayout(title);
  const layout = detailOverviewLayout(title);
  grid.className = `detail-overview-grid detail-overview-grid--${layout.mode}`;
  grid.dataset.scoreDensity = layout.scoreDensity;
  grid.dataset.factDensity = layout.factDensity;
  return layout;
}

function trustedDetailVisualUrl(value) {
  const record = value && typeof value === "object" ? value : {};
  const candidate = typeof value === "string"
    ? value.trim()
    : textValue(record.localUrl) || textValue(record.url) || textValue(record.src);
  if (candidate.startsWith("/media/") || candidate.startsWith("/api/image-proxy?url=")) return candidate;
  if (/^https?:\/\//i.test(candidate)) return `/api/image-proxy?url=${encodeURIComponent(candidate)}`;
  return "";
}

function firstVerifiedStillUrl(title = {}) {
  const posterUrl = trustedDetailVisualUrl(title?.poster);
  for (const still of Array.isArray(title?.stills) ? title.stills : []) {
    if (textValue(still?.media_status, "ready") !== "ready") continue;
    const url = trustedDetailVisualUrl(still);
    if (url && url !== posterUrl) return url;
  }
  return "";
}

function renderVerifiedVisualEmpty(className = "detail-visual-empty") {
  const panel = element("div", className);
  panel.setAttribute("role", "status");
  panel.append(
    element("span", "detail-visual-empty__mark", "已核对剧照"),
    element("strong", "detail-visual-empty__copy", "暂未找到可核对的真实剧照"),
  );
  return panel;
}

function renderHeroQuickFacts(title, item) {
  const quickFacts = element("div", "detail-hero__quickfacts");
  if (title?.is_live) {
    const source = listValue(title?.source_labels)[0] || "在线来源";
    quickFacts.append(element("span", "detail-hero__quickfact detail-hero__quickfact--live", `实时 · ${source}`));
  }
  if (Number.isFinite(item?.douban_rating)) {
    quickFacts.append(element("span", "detail-hero__quickfact detail-hero__quickfact--primary", `豆瓣 ${item.douban_rating}`));
  }
  for (const rating of sourceRatingRows(item).slice(0, 2)) {
    quickFacts.append(element("span", "detail-hero__quickfact detail-hero__quickfact--rating", `${rating.label} ${rating.score}`));
  }
  const genres = listValue(item?.genres).slice(0, 4);
  for (const genre of genres) {
    quickFacts.append(element("span", "detail-hero__quickfact detail-hero__quickfact--genre", genre));
  }
  if (!quickFacts.children.length) {
    quickFacts.append(element("span", "detail-hero__quickfact detail-hero__quickfact--genre", mediaBadgeLabel(title, "作品")));
  }
  return quickFacts;
}

function renderExpandableSummary(value) {
  const summary = textValue(value, "资料有限：暂未记录作品简介。");
  const wrap = element("div", "detail-hero__summary-wrap");
  const copy = element("p", "detail-hero__summary", summary);
  const collapsible = [...summary].length > 150;
  if (collapsible) {
    copy.classList.add("is-collapsible");
    copy.dataset.expanded = "false";
    const toggle = element("button", "detail-hero__summary-toggle", "展开全文");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", () => {
      const expanded = copy.dataset.expanded === "true";
      copy.dataset.expanded = String(!expanded);
      toggle.setAttribute("aria-expanded", String(!expanded));
      toggle.textContent = expanded ? "展开全文" : "收起简介";
    });
    wrap.append(copy, toggle);
  } else {
    wrap.append(copy);
  }
  return wrap;
}

function renderHero(title) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const hero = element("section", "detail-hero");
  hero.id = "overview";
  const backdrop = element("div", "detail-backdrop");
  const posterMedia = titlePosterMedia(title);
  let backdropMedia = adaptCatalogMedia(title, "backdrop");
  const posterUrl = trustedDetailVisualUrl(title?.poster);
  const backdropUrl = trustedDetailVisualUrl(title?.backdrop);
  const backdropMatchesPoster = Boolean(
    (posterMedia.localUrl && backdropMedia.localUrl && posterMedia.localUrl === backdropMedia.localUrl)
    || (posterUrl && backdropUrl && posterUrl === backdropUrl),
  );
  if (backdropMatchesPoster) {
    backdropMedia = { ...backdropMedia, localUrl: "", status: "missing" };
  }
  const stillUrl = firstVerifiedStillUrl(title);
  if (stillUrl) {
    backdrop.classList.add("detail-backdrop--still");
    backdrop.dataset.mediaState = "loading";
    const image = document.createElement("img");
    image.className = "detail-backdrop__still";
    image.alt = `${titleDisplayName(title, "作品")} 剧照`;
    image.loading = "eager";
    image.decoding = "async";
    image.fetchPriority = "high";
    image.hidden = true;
    const loading = element("div", "detail-backdrop__loading");
    loading.setAttribute("aria-hidden", "true");
    loading.append(
      element("span", "detail-backdrop__loading-mark", "CS"),
      element("span", "detail-backdrop__loading-copy", "正在呈现高清剧照"),
    );
    const fallback = () => {
      backdrop.dataset.mediaState = "error";
      backdrop.classList.remove("detail-backdrop--still");
      if (backdropMedia.status === "ready") {
        backdrop.replaceChildren(renderMediaFrame(backdropMedia));
        return;
      }
      backdrop.replaceChildren(renderVerifiedVisualEmpty("detail-backdrop__empty"));
    };
    image.addEventListener?.("load", () => {
      const naturalWidth = Number(image.naturalWidth);
      if (Number.isFinite(naturalWidth) && naturalWidth <= 0) {
        fallback();
        return;
      }
      image.hidden = false;
      backdrop.dataset.mediaState = "ready";
      loading.remove?.();
    }, { once: true });
    backdrop.append(loading, image);
    attachResilientImage(image, stillUrl, {
      maxRetries: 2,
      onFailure: fallback,
    });
  } else if (backdropMedia.status === "ready") {
    backdrop.append(renderMediaFrame(backdropMedia));
  } else {
    if (hero.classList?.add) hero.classList.add("detail-hero--ambient");
    else hero.className = `${hero.className} detail-hero--ambient`.trim();
    if (backdrop.classList?.add) backdrop.classList.add("detail-backdrop--ambient");
    else backdrop.className = `${backdrop.className} detail-backdrop--ambient`.trim();
    backdrop.dataset.mediaState = "ambient";
    backdrop.setAttribute("aria-hidden", "true");
    backdrop.append(element("span", "detail-backdrop__ambient-mark", "CINESCOPE"));
  }

  const content = element("div", "detail-hero__content");
  const poster = element("div", "detail-poster");
  poster.append(renderMediaFrame(posterMedia));
  const copy = element("div", "detail-hero__copy");
  copy.append(element("p", "eyebrow", title?.is_live ? "在线作品档案" : "作品档案"));
  copy.append(element("h1", "detail-hero__title", titleDisplayName(title)));
  const metadata = [
    Number.isFinite(title?.year) ? String(title.year) : "",
    mediaBadgeLabel(title),
    title?.state ? localStateLabel(title.state) : "",
  ].filter(Boolean);
  if (metadata.length) copy.append(element("p", "detail-hero__metadata", metadata.join(" · ")));
  copy.append(renderHeroQuickFacts(title, item));
  const summary = textValue(item.summary) || textValue(item.intro) || "资料有限：本地片库暂未记录作品简介。";
  copy.append(renderExpandableSummary(summary));
  const source = element(
    "p",
    "detail-verified-note",
    isGeneratedSummary(summary)
      ? "资料补全中，仅采用通过作品身份校验的来源。"
      : title?.is_live
        ? "在线资料已按作品身份与来源核对。"
        : "来自本地记录或已核对的公共来源。",
  );
  copy.append(source);
  content.append(poster, copy);
  hero.append(backdrop, content);
  return hero;
}

function renderTabs(availableIds = null, title = {}) {
  const tabs = element("nav", "detail-tabs");
  tabs.setAttribute("aria-label", "作品详情分区");
  const returnPath = detailReturnPathFor(title);
  const returnButton = element("button", "detail-tabs__return", `← ${detailReturnLabel(returnPath)}`);
  returnButton.type = "button";
  returnButton.setAttribute("aria-label", `${detailReturnLabel(returnPath)}并恢复之前的浏览位置`);
  returnButton.addEventListener("click", () => dependencies.onExitDetail?.(returnPath));
  tabs.append(returnButton);
  for (const [href, label] of [["#overview", "概览"], ["#scores", "评分"], ["#facts", "资料"], ["#visuals", "剧照"], ["#people", "演职人员"], ["#similar", "相似推荐"], ["#relations", "关联"]]) {
    if (availableIds && !availableIds.has(href.slice(1))) continue;
    const link = element("a", "detail-tab", label);
    link.setAttribute("href", href);
    link.addEventListener("click", (event) => {
      const target = globalThis.document?.getElementById?.(href.slice(1));
      if (!target || typeof target.scrollIntoView !== "function") return;
      event?.preventDefault?.();
      const reduceMotion = globalThis.window?.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
      globalThis.history?.replaceState?.(globalThis.history.state, "", href);
    });
    tabs.append(link);
  }
  return tabs;
}

function renderScores(title) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const raw = item.raw && typeof item.raw === "object" ? item.raw : {};
  const section = element("section", "detail-section detail-scores");
  section.id = "scores";
  const density = detailOverviewLayout(title).scoreDensity;
  section.dataset.density = density;
  if (density === "sparse") section.classList?.add?.("detail-scores--compact");
  section.append(element("p", "eyebrow", "口碑证据"), element("h2", "detail-section__title", "评分与观影记录"));
  const grid = element("div", "detail-score-grid");
  const genreSignals = [...listValue(item.genres), ...listValue(item.directors).slice(0, 2)];
  const hasDoubanRating = Number.isFinite(item.douban_rating);
  const doubanVoteCount = hasDoubanRating ? integerText(item.vote_count) : "";
  const commentCount = Number(raw.comment_count) > 0 ? integerText(raw.comment_count) : "";
  const reviewCount = Number(raw.review_count) > 0 ? integerText(raw.review_count) : "";
  const sourceRatings = sourceRatingRows(item);
  if (hasDoubanRating) {
    grid.append(scoreCard("豆瓣评分", numericText(item.douban_rating), doubanVoteCount ? `${doubanVoteCount} 人参与豆瓣评分` : "来自本地目录中保存的豆瓣公开评分。"));
  }
  for (const rating of sourceRatings) {
    const ratingVotes = integerText(rating.votes);
    grid.append(scoreCard(
      `${rating.label} 评分`,
      numericText(rating.score),
      ratingVotes ? `${ratingVotes} 条公开评分或热度证据` : `来自 ${rating.label} 的已核对公开评分。`,
    ));
  }
  if (Number.isFinite(item.my_rating)) {
    grid.append(scoreCard("我的评分", numericText(item.my_rating), "来自你的本地观影记录。"));
  }
  if (!grid.children.length && !title?.is_live) {
    grid.append(scoreCard("公开评分", "补全中", "作品详情可以查看，评分数据会在来源返回后更新。"));
  }

  const signals = element("div", "detail-signal-strip");
  const sourceLabels = listValue(title?.source_labels);
  const signalValues = [
    title?.is_live ? (sourceLabels[0] || "在线发现") : localStateLabel(title?.state),
    ...genreSignals.slice(0, 4),
  ].filter(Boolean);
  for (const value of [...new Set(signalValues)]) signals.append(element("span", "detail-signal-strip__item", value));

  const evidence = element("div", "detail-evidence");
  const publicPanel = element("article", "detail-evidence__panel");
  const publicScores = [
    ...(Number.isFinite(item.douban_rating) ? [`豆瓣 ${item.douban_rating}`] : []),
    ...sourceRatings.map((rating) => `${rating.label} ${rating.score}`),
  ];
  publicPanel.append(
    element("p", "detail-evidence__label", "公开样本"),
    element("strong", "detail-evidence__headline", [
      doubanVoteCount ? `${doubanVoteCount} 人参与豆瓣评分` : "",
      commentCount ? `${commentCount} 条短评` : "",
      reviewCount ? `${reviewCount} 篇影评` : "",
    ].filter(Boolean).join(" · ") || (publicScores.length ? publicScores.join(" · ") : "样本补全中")),
    element(
      "p",
      "detail-evidence__copy",
      [
        doubanVoteCount
          ? `${doubanVoteCount} 人参与豆瓣评分。`
          : hasDoubanRating
            ? "豆瓣评分人数尚未同步。"
            : "未发现可核对的豆瓣评分记录。",
        publicScores.length ? "各平台评分独立展示，不混算。" : "评分返回后会自动更新。",
      ].join(" "),
    ),
  );
  evidence.append(publicPanel);
  if (title?.is_live) {
    const sourcePanel = element("article", "detail-evidence__panel detail-evidence__panel--source");
    sourcePanel.append(
      element("p", "detail-evidence__label", "在线来源"),
      element("strong", "detail-evidence__headline", sourceLabels.join(" · ") || "可信公共来源"),
      element("p", "detail-evidence__copy", textValue(item.release_date) ? `上映日期 ${item.release_date} · 在线资料独立缓存。` : "在线资料独立缓存，不改写本地片库。"),
    );
    evidence.append(sourcePanel);
  } else {
    const comment = textValue(raw.comment) || textValue(raw.short_comment) || textValue(raw.review);
    const personalPanel = element("article", "detail-evidence__panel detail-evidence__panel--personal");
    personalPanel.append(
      element("p", "detail-evidence__label", "我的记录"),
      element("strong", "detail-evidence__headline", Number.isFinite(item.my_rating) ? `我的评分 ${item.my_rating}` : localStateLabel(title?.state)),
      element("p", "detail-evidence__copy", comment || "暂无个人短评。"),
    );
    evidence.append(personalPanel);
  }
  if (grid.children.length) section.append(grid);
  if (signals.children.length) section.append(signals);
  section.append(evidence);
  return section;
}

function renderFacts(title) {
  const section = element("section", "detail-section detail-facts");
  section.id = "facts";
  const layout = detailOverviewLayout(title);
  section.dataset.density = layout.factDensity;
  if (layout.factDensity === "sparse") section.classList?.add?.("detail-facts--compact");
  section.append(element("p", "eyebrow", "已核资料"), element("h2", "detail-section__title", "作品资料"));
  const values = factRows(title);
  if (!values.length) {
    section.append(element("p", "detail-limited", "资料有限：本地片库尚未记录可核对的事实字段。"));
    return section;
  }
  const facts = element("dl", "detail-facts__grid");
  for (const [label, value] of values) facts.append(fact(label, value));
  section.append(facts);
  return section;
}


function visualAssets(title) {
  const assets = [];
  const seen = new Set();
  const posterUrl = trustedDetailVisualUrl(title?.poster);
  const add = (asset, label) => {
    const record = asset && typeof asset === "object" ? asset : {};
    const url = trustedDetailVisualUrl(asset);
    if (!url || url === posterUrl || seen.has(url)) return;
    seen.add(url);
    assets.push({
      id: `detail-visual-${assets.length + 1}`,
      url,
      label,
      status: textValue(record.media_status) || textValue(record.status, "ready"),
      source: textValue(record.source, "verified-detail-gallery"),
    });
  };
  for (const still of Array.isArray(title?.stills) ? title.stills : []) add(still, "剧照");
  add(title?.backdrop, "主视觉");
  return assets.slice(0, 12);
}

function renderVisuals(title) {
  const section = element("section", "detail-section detail-visuals");
  section.id = "visuals";
  section.append(
    element("p", "eyebrow", "视觉资料"),
    element("h2", "detail-section__title", "剧照与视觉资料"),
    element("p", "detail-section__deck", "仅展示通过作品身份与画面类型校验的素材。"),
  );
  const assets = visualAssets(title);
  if (!assets.length) {
    const state = titleBackdropJobState.get(titleIdentity(title));
    const panel = element("div", "detail-visuals__empty");
    panel.append(
      element("strong", "detail-visuals__empty-title", "暂未找到可核对的真实剧照"),
      element(
        "p",
        "detail-visuals__empty-copy",
        state === "in-progress"
          ? "正在从可核对的公开来源继续匹配；通过身份与画面类型校验后会原位出现。"
          : "系统只展示通过作品身份与画面类型校验的真实剧照，不以海报或错配素材填充。",
      ),
    );
    section.append(panel);
    return section;
  }
  section.append(renderMediaGallery({
    assets,
    title: titleDisplayName(title, "作品"),
    ariaLabel: `${titleDisplayName(title, "作品")}剧照与视觉资料`,
  }));
  return section;
}

function visiblePeopleForTitle(title) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const people = Array.isArray(title?.people) ? title.people : [];
  const directors = listValue(item.directors);
  const casts = listValue(item.casts);
  const requestedNames = [...directors.slice(0, 2), ...casts.slice(0, 8)];
  if (!requestedNames.length) return people.slice(0, 9);
  const visible = [];
  const seen = new Set();
  for (const name of requestedNames) {
    const person = people.find((candidate) => textValue(candidate?.name) === name);
    const personId = textValue(person?.id);
    if (!person || !personId || seen.has(personId)) continue;
    seen.add(personId);
    visible.push(person);
  }
  return visible;
}

function portraitJobPriority(person, item = {}) {
  const name = textValue(person?.name);
  const directors = listValue(item.directors);
  if (textValue(person?.role) === "director" || directors.includes(name)) return 120;
  const castIndex = listValue(item.casts).indexOf(name);
  return castIndex >= 0 && castIndex < 6 ? 80 : 40;
}

function portraitWorkContext(title = {}, person = {}) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const raw = item?.raw && typeof item.raw === "object" ? item.raw : {};
  const metadata = person?.metadata && typeof person.metadata === "object" ? person.metadata : {};
  const candidates = [
    title?.title,
    item?.title,
    raw?.original_title,
    ...listValue(raw?.aliases),
    ...listValue(person?.known_works),
    ...listValue(metadata?.known_works),
  ];
  const context = [];
  const seen = new Set();
  for (const value of candidates) {
    const clean = textValue(value);
    const key = clean.toLocaleLowerCase();
    if (!clean || seen.has(key)) continue;
    seen.add(key);
    context.push(clean);
    if (context.length >= 8) break;
  }
  return context;
}

function personMonogram(value) {
  const name = textValue(value, "?");
  const words = name.split(/[\s\-_.·]+/u).map((part) => part.trim()).filter(Boolean);
  if (words.length > 1) {
    const first = Array.from(words[0])[0] || "";
    const last = Array.from(words[words.length - 1])[0] || "";
    return `${first}${last}`.toLocaleUpperCase();
  }
  const glyphs = Array.from(name.replace(/\s+/gu, ""));
  return (glyphs.slice(0, 2).join("") || "?").toLocaleUpperCase();
}

function personCardSignature(person) {
  const portrait = adaptPersonMedia(person);
  return JSON.stringify({
    id: textValue(person?.id),
    name: textValue(person?.name),
    role: textValue(person?.role),
    localUrl: portrait.localUrl,
    status: portrait.status,
    source: portrait.source,
    jobState: portraitJobState.get(textValue(person?.id)) || "",
  });
}

function renderPersonCard(person) {
  const personId = textValue(person?.id);
  const signature = personCardSignature(person);
  const cached = personCardCache.get(personId);
  if (cached?.signature === signature) return cached.node;

  const button = element("button", "person-card");
  button.type = "button";
  const personName = textValue(person?.name, "未命名人物");
  button.setAttribute("aria-label", `打开${personName}人物聚光灯`);
  const portraitMedia = adaptPersonMedia(person);
  const portrait = element("div", "person-card__portrait");
  if (portraitMedia.status === "ready") {
    portrait.append(renderMediaFrame(portraitMedia));
  } else {
    portrait.classList.add("person-card__portrait--fallback");
    portrait.append(
      element("strong", "person-card__monogram", personMonogram(personName)),
      element("span", "person-card__fallback-note", "姓名身份已保留"),
    );
  }
  const copy = element("div", "person-card__copy");
  const jobState = portraitJobState.get(personId);
  copy.append(
    element("span", "person-card__role", roleLabel(person?.role)),
    element("strong", "person-card__name", personName),
    element("span", "person-card__status", portraitMedia.status === "ready" ? "本地肖像已就绪" : "身份卡 · 肖像待补"),
  );
  if (jobState) {
    const labels = {
      "in-progress": "正在匹配真实肖像",
      success: "真实肖像已补齐",
      failed: "暂未找到可核对的肖像",
    };
    const job = element("span", "person-card__job", labels[jobState] || jobState);
    job.dataset.state = jobState;
    copy.append(job);
  }
  button.append(portrait, copy);
  button.addEventListener("click", () => {
    const rect = typeof button.getBoundingClientRect === "function" ? button.getBoundingClientRect() : null;
    void dependencies.openPersonSheet(personId, rect);
  });
  personCardCache.set(personId, { signature, node: button });
  return button;
}

function renderPeople(title) {
  const section = element("section", "detail-section detail-people");
  section.id = "people";
  section.append(element("p", "eyebrow", "主创阵容"));
  const allPeople = Array.isArray(title?.people) ? title.people : [];
  const people = visiblePeopleForTitle(title);
  const heading = element("div", "detail-people__heading");
  heading.append(element("h2", "detail-section__title", "演职人员"));
  const unresolved = people.filter((person) => adaptPersonMedia(person).status !== "ready");
  if (unresolved.length) {
    const retry = element("button", "detail-people__retry", `重试未命中肖像 · ${unresolved.length}`);
    retry.type = "button";
    retry.addEventListener("click", async () => {
      retry.disabled = true;
      retry.textContent = "正在重新匹配人物图片…";
      await retryMissingPortraits(title);
    });
    heading.append(retry);
  }
  section.append(heading);
  if (!allPeople.length) {
    section.append(element("p", "detail-limited", "资料有限：本地片库尚未记录演职人员身份。"));
    return section;
  }
  if (unresolved.length) {
    const hydration = element("div", "detail-people-hydration");
    const failedCount = unresolved.filter((person) => portraitJobState.get(textValue(person?.id)) === "failed").length;
    hydration.dataset.state = failedCount === unresolved.length ? "degraded" : "loading";
    hydration.append(
      element(
        "strong",
        "detail-people-hydration__title",
        failedCount === unresolved.length
          ? `${unresolved.length} 位演职人员肖像暂未命中`
          : `正在匹配 ${unresolved.length} 位演职人员肖像`,
      ),
      element(
        "p",
        "detail-people-hydration__copy",
        failedCount === unresolved.length
          ? "姓名与职务仍然保留；只有通过人物身份校验的真实照片才会进入肖像栏。"
          : "正在按姓名、职务与当前作品交叉核验，避免把同名人物或错误照片放进详情页。",
      ),
    );
    const queue = element("div", "detail-people-hydration__queue");
    for (const person of unresolved.slice(0, 8)) {
      queue.append(element("span", "detail-people-hydration__chip", `${roleLabel(person?.role)} · ${textValue(person?.name, "待补人物")}`));
    }
    hydration.append(queue);
    section.append(hydration);
  }
  const rail = element("div", "detail-people-rail");
  rail.setAttribute("role", "list");
  for (const person of people) {
    const entry = element("div", "detail-people-rail__item");
    entry.setAttribute("role", "listitem");
    entry.append(renderPersonCard(person));
    rail.append(entry);
  }
  if (people.length) section.append(rail);
  if (allPeople.length > people.length) {
    section.append(element("p", "detail-people__remainder", `另有 ${allPeople.length - people.length} 位演职人员保留在本地资料档案中。`));
  }
  return section;
}

function titleIdentity(title) {
  return textValue(title?.item_key) || textValue(title?.id);
}

function titlePosterMedia(title) {
  const media = adaptCatalogMedia(title, "poster");
  const state = titlePosterJobState.get(titleIdentity(title));
  return media.status !== "ready" && state === "in-progress" ? { ...media, status: "pending" } : media;
}

function relatedNodes(title, universe) {
  const focus = textValue(universe?.focus_id, textValue(title?.item_key));
  return (Array.isArray(universe?.nodes) ? universe.nodes : [])
    .filter((node) => {
      const key = textValue(node?.item_key) || textValue(node?.id);
      return key && key !== focus;
    })
    .slice(0, 8);
}

function relationNodeKey(node) {
  return textValue(node?.item_key) || textValue(node?.id);
}

function edgeFor(universe, itemKey) {
  return (Array.isArray(universe?.edges) ? universe.edges : []).find((edge) => textValue(edge?.target) === itemKey) || null;
}

function relationReason(edge, fallback = "共享本地目录字段") {
  const raw = textValue(edge?.reason);
  if (!raw) return fallback;
  const labels = {
    "shared director": "共同导演",
    "shared cast": "共同演员",
    "shared genre": "共同类型",
    "shared country": "共同地区",
    "same media type": "相同媒介类型",
    "same decade": "相同年代",
  };
  const separator = raw.indexOf(":");
  const key = (separator >= 0 ? raw.slice(0, separator) : raw).trim().toLowerCase();
  const label = labels[key];
  if (!label) return raw;
  const value = separator >= 0 ? raw.slice(separator + 1).trim() : "";
  return value ? `${label}：${value}` : label;
}

function renderRelations(title, universe) {
  const section = element("section", "detail-section detail-relations");
  section.id = "relations";
  section.append(
    element("p", "eyebrow", "关系证据"),
    element("h2", "detail-section__title", "本地关联路径"),
    element("p", "detail-section__deck", "依据本地片库中的共同类型、主创与地区连接。"),
  );
  const universeAction = element("button", "detail-universe-action route-recovery__action", "在探索实验室展开");
  universeAction.type = "button";
  universeAction.addEventListener("click", () => dependencies.onExploreUniverse(textValue(title?.item_key)));
  section.append(universeAction);
  const nodes = relatedNodes(title, universe);
  if (!nodes.length) {
    section.append(element("p", "detail-limited", "资料有限：本地片库暂未形成可展示的关联路径。"));
    return section;
  }

  const preview = element("div", "detail-relation-preview");
  for (const node of nodes.slice(0, 3)) {
    const edge = edgeFor(universe, relationNodeKey(node));
    const item = element("article", "detail-relation-preview__item");
    item.append(
      element("strong", "detail-relation-preview__title", textValue(node.title, "未命名作品")),
      element("p", "detail-relation-preview__reason", relationReason(edge)),
    );
    preview.append(item);
  }

  const readyNodes = nodes.filter((node) => adaptCatalogMedia(node, "poster").status === "ready");
  const unresolvedNodes = nodes.filter((node) => adaptCatalogMedia(node, "poster").status !== "ready");
  if (unresolvedNodes.length) {
    const hydration = element("div", "detail-related-hydration");
    const failedCount = unresolvedNodes.filter((node) => relationPosterJobState.get(relationNodeKey(node)) === "failed").length;
    hydration.dataset.state = failedCount === unresolvedNodes.length ? "degraded" : "loading";
    hydration.append(
      element(
        "strong",
        "detail-related-hydration__title",
        failedCount === unresolvedNodes.length
          ? `${unresolvedNodes.length} 张关联海报暂未命中`
          : `正在补齐 ${unresolvedNodes.length} 张关联海报`,
      ),
      element(
        "p",
        "detail-related-hydration__copy",
        failedCount === unresolvedNodes.length
          ? "已保留可靠的文字关系，不展示空白或错配图片；重新进入详情时会再次尝试。"
          : "只在本地媒体校验完成后加入作品卡，避免先出现空白或错图。",
      ),
    );
    const queue = element("div", "detail-related-hydration__queue");
    for (const node of unresolvedNodes.slice(0, 6)) {
      queue.append(element("span", "detail-related-hydration__chip", textValue(node?.title, "待补作品")));
    }
    hydration.append(queue);
    section.append(hydration);
  }

  const worksHeading = element("h3", "detail-related-works__title", "关联作品区");
  const works = element("div", "detail-related-works");
  works.setAttribute("role", "list");
  for (const node of readyNodes) {
    const itemKey = relationNodeKey(node);
    const edge = edgeFor(universe, itemKey);
    const item = element("div", "detail-related-works__item");
    item.setAttribute("role", "listitem");
    item.append(renderTitleCard({
      ...node,
      item_key: itemKey,
      metadata: mediaBadgeLabel(node),
      reason: relationReason(edge, "本地关联"),
    }));
    works.append(item);
  }
  section.append(preview);
  if (readyNodes.length) section.append(worksHeading, works);
  return section;
}

function renderRelationsSkeleton(title) {
  const section = element("section", "detail-section detail-relations detail-relations--loading");
  section.id = "relations";
  section.setAttribute("aria-busy", "true");
  section.append(
    element("p", "eyebrow", "关系证据"),
    element("h2", "detail-section__title", "本地关联路径"),
    element("p", "detail-section__deck", "关系证据正在后台加载。"),
  );
  const universeAction = element("button", "detail-universe-action route-recovery__action", "在探索实验室展开");
  universeAction.type = "button";
  universeAction.addEventListener("click", () => dependencies.onExploreUniverse(textValue(title?.item_key)));
  const skeleton = element("div", "detail-discovery-skeleton");
  for (let index = 0; index < 3; index += 1) skeleton.append(element("span", "detail-discovery-skeleton__line"));
  section.append(universeAction, skeleton);
  return section;
}

function hasRenderableTitlePoster(item = {}) {
  const media = adaptCatalogMedia(item, "poster");
  return media.status === "ready" && Boolean(media.localUrl);
}

export function visibleSimilarItems(payload, limit = 8) {
  return (Array.isArray(payload?.items) ? payload.items : [])
    .filter((item) => item && typeof item === "object" && relationNodeKey(item))
    .filter(hasRenderableTitlePoster)
    .slice(0, Math.max(1, Math.min(12, Number(limit) || 8)));
}

function renderSimilarRecommendations(title, payload = {}, { loading = false, failed = false } = {}) {
  const section = element("section", "detail-section detail-similar");
  section.id = "similar";
  section.setAttribute("aria-busy", loading ? "true" : "false");
  section.append(
    element("p", "eyebrow", "可解释推荐"),
    element("h2", "detail-section__title", `喜欢《${titleDisplayName(title, "这部作品")}》的还喜欢`),
    element("p", "detail-section__deck", "推荐理由来自类型、主创、地区与叙事线索；仅展示海报已就绪的完整候选。"),
  );
  if (loading) {
    const skeleton = element("div", "detail-similar__grid detail-similar__grid--loading");
    for (let index = 0; index < 4; index += 1) skeleton.append(element("article", "detail-similar__skeleton"));
    section.append(skeleton);
    return section;
  }
  const items = visibleSimilarItems(payload);
  if (!items.length) {
    section.append(element(
      "p",
      "detail-limited",
      failed ? "相似推荐暂时没有返回；作品详情与本地关联仍可正常使用。" : "当前没有足够可靠的相似候选，系统不会用低质量结果填满版面。",
    ));
    return section;
  }
  const grid = element("div", "detail-similar__grid");
  grid.setAttribute("role", "list");
  for (const candidate of items) {
    const wrapper = element("div", "detail-similar__item");
    wrapper.setAttribute("role", "listitem");
    wrapper.append(renderTitleCard({
      ...candidate,
      item_key: relationNodeKey(candidate),
      metadata: mediaBadgeLabel(candidate),
      reason: textValue(candidate.primary_reason) || textValue(candidate.explanation, "与当前作品共享可靠的内容线索"),
    }));
    grid.append(wrapper);
  }
  section.append(grid);
  return section;
}

function renderDetailPage(title) {
  const page = element("article", "detail-page route-view--enter");
  if (title?.is_live) page.classList.add("detail-page--live");
  const overviewSections = [renderScores(title), renderFacts(title)];
  const overviewGrid = element("div", "detail-overview-grid");
  applyOverviewLayout(overviewGrid, title);
  overviewGrid.append(...overviewSections);
  const sections = [];
  if (!title?.is_live || visualAssets(title).length) sections.push(renderVisuals(title));
  if (!title?.is_live || (Array.isArray(title?.people) && title.people.length)) sections.push(renderPeople(title));
  sections.push(
    renderSimilarRecommendations(title, {}, { loading: true }),
    renderRelationsSkeleton(title),
  );
  const availableIds = new Set([
    "overview",
    ...overviewSections.map((section) => textValue(section?.id)).filter(Boolean),
    ...sections.map((section) => textValue(section?.id)).filter(Boolean),
  ]);
  page.append(
    renderDetailReturn(title),
    renderHero(title),
    renderTabs(availableIds, title),
    overviewGrid,
    ...sections,
  );
  return page;
}

function recoveryPanel(titleId, retry) {
  const panel = element("section", "route-recovery detail-recovery");
  panel.append(
    element("p", "eyebrow", "详情恢复"),
    element("h1", "route-recovery__title", "作品详情暂时无法打开"),
    element("p", "route-recovery__copy", "可能是记录不存在或本地服务暂时不可用。旧视图会保留到此恢复面板准备完成。"),
  );
  const button = element("button", "route-recovery__action", "重试详情");
  button.type = "button";
  button.addEventListener("click", retry);
  panel.append(button);
  panel.dataset.titleId = titleId;
  return panel;
}

async function swapPreparedView(root, view, isCurrent = () => true) {
  if (!root || !view || !isCurrent()) return false;
  let committed = false;
  const update = () => {
    if (committed || !isCurrent()) return false;
    root.replaceChildren(view);
    committed = true;
    return true;
  };
  const reduceMotion = globalThis.window?.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (reduceMotion || typeof document.startViewTransition !== "function") return update();
  let transition;
  try {
    transition = document.startViewTransition(update);
  } catch {
    return committed || update();
  }
  if (transition?.ready) void Promise.resolve(transition.ready).catch(() => {});
  const updateDone = transition?.updateCallbackDone || transition?.finished;
  if (transition?.finished && transition.finished !== updateDone) void Promise.resolve(transition.finished).catch(() => {});
  if (!updateDone || typeof updateDone.then !== "function") return committed || update();
  try {
    await updateDone;
  } catch {
    if (!committed && isCurrent()) return update();
    return committed;
  }
  return committed;
}

async function commitView(view, meta, options = {}) {
  if (options.signal?.aborted || (typeof options.isCurrent === "function" && !options.isCurrent())) return false;
  if (typeof options.commit === "function") return Boolean(await options.commit(view, meta));
  const isCurrent = typeof options.isCurrent === "function" ? options.isCurrent : () => !options.signal?.aborted;
  return swapPreparedView(options.root || dependencies.root, view, isCurrent);
}

async function requestUniverseDiscovery(titleId, signal) {
  try {
    const value = await auxiliaryApiGet(
      `/api/v2/universe?focus=${encodeURIComponent(titleId)}&limit=${RELATION_LIMIT}`,
      { signal },
    );
    return { ok: true, value };
  } catch (error) {
    return { ok: false, error };
  }
}

async function requestSimilarDiscovery(titleId, signal) {
  try {
    const value = await auxiliaryApiGet(
      `/api/v2/discovery/similar?focus=${encodeURIComponent(titleId)}&mode=balanced&limit=24&complete_media=1`,
      { signal },
    );
    return { ok: true, value };
  } catch (error) {
    return { ok: false, error };
  }
}

function findDetailSection(page, sectionId) {
  if (!page) return null;
  const stack = [page];
  while (stack.length) {
    const node = stack.shift();
    if (node?.id === sectionId) return node;
    stack.unshift(...(node?.children || []));
  }
  return null;
}

function findPeopleSection(page) {
  return findDetailSection(page, "people");
}

function findRelationsSection(page) {
  return findDetailSection(page, "relations");
}

function findSimilarSection(page) {
  return findDetailSection(page, "similar");
}

function replaceDetailNode(current, next) {
  if (!current || !next) return false;
  if (typeof current.replaceWith === "function") {
    current.replaceWith(next);
    return true;
  }
  const parent = current.parentNode;
  if (typeof parent?.replaceChild === "function") {
    parent.replaceChild(next, current);
    return true;
  }
  if (Array.isArray(parent?.children)) {
    const index = parent.children.indexOf(current);
    if (index < 0) return false;
    parent.children.splice(index, 1, next);
    next.parentNode = parent;
    current.parentNode = null;
    return true;
  }
  return false;
}

function patchPeopleSection(title) {
  const page = activeDetail?.page;
  const current = findPeopleSection(page);
  if (!page || !current) return;
  const next = renderPeople(title);
  replaceDetailNode(current, next);
}

function patchRelationsSection(title = activeDetail?.title || {}, universe = activeDetail?.universe || {}, { failed = false } = {}) {
  const page = activeDetail?.page;
  const current = findRelationsSection(page);
  if (!page || !current) return;
  if (failed) {
    const fallback = renderRelations(title, {});
    fallback.dataset.state = "degraded";
    replaceDetailNode(current, fallback);
    return;
  }
  replaceDetailNode(current, renderRelations(title, universe));
}

function patchSimilarSection(title = activeDetail?.title || {}, payload = activeDetail?.similar || {}, state = {}) {
  const page = activeDetail?.page;
  const current = findSimilarSection(page);
  if (!page || !current) return;
  replaceDetailNode(current, renderSimilarRecommendations(title, payload, state));
}

export async function hydrateDetailDiscovery(titleId, title, { universePromise, similarPromise, signal, isCurrent } = {}) {
  const stillCurrent = () => (
    !signal?.aborted
    && (typeof isCurrent !== "function" || isCurrent())
    && activeDetail?.titleId === titleId
  );
  const universeTask = Promise.resolve(universePromise).then((result) => {
    if (!stillCurrent()) return null;
    if (!result?.ok) {
      patchRelationsSection(title, {}, { failed: true });
      return null;
    }
    const universe = result.value && typeof result.value === "object" ? result.value : {};
    activeDetail.universe = universe;
    patchRelationsSection(activeDetail.title, universe);
    void prefetchVisibleRelations(activeDetail.title, universe, { titleId });
    return universe;
  });
  const similarTask = Promise.resolve(similarPromise).then((result) => {
    if (!stillCurrent()) return null;
    if (!result?.ok) {
      patchSimilarSection(title, {}, { failed: true });
      return null;
    }
    const payload = result.value && typeof result.value === "object" ? result.value : {};
    activeDetail.similar = payload;
    patchSimilarSection(activeDetail.title, payload);
    return payload;
  });
  return Promise.allSettled([universeTask, similarTask]);
}

function patchMetadataSections(title) {
  const page = activeDetail?.page;
  if (!page) return;
  const replacements = [
    ["overview", renderHero],
    ["scores", renderScores],
    ["facts", renderFacts],
    ["visuals", renderVisuals],
    ["people", renderPeople],
  ];
  for (const [sectionId, renderer] of replacements) {
    const current = findDetailSection(page, sectionId);
    if (current) replaceDetailNode(current, renderer(title));
  }
  applyOverviewLayout(page.querySelector?.(".detail-overview-grid"), title);
}

function needsMetadataEnrichment(title, titleId) {
  if (title?.is_live) return false;
  if (!/^(?:douban|item|external):/.test(textValue(titleId))) return false;
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const summary = textValue(item.summary) || textValue(item.intro);
  const mediaType = textValue(title?.media_type) || textValue(item.media_type);
  return isGeneratedSummary(summary) || !hasSpecificGenres(item, mediaType) || !listValue(item.directors).length;
}

export function enrichThinTitleMetadata(title = {}, { titleId = textValue(title?.item_key) } = {}) {
  if (!needsMetadataEnrichment(title, titleId) || typeof dependencies.api?.postV2 !== "function") return Promise.resolve(null);
  const existing = metadataEnrichmentInFlight.get(titleId);
  if (existing) return existing;
  const attemptedAt = Number(metadataEnrichmentAttemptedAt.get(titleId) || 0);
  if (attemptedAt && Date.now() - attemptedAt < 120_000) return Promise.resolve(null);
  metadataEnrichmentAttemptedAt.set(titleId, Date.now());
  const request = Promise.resolve(dependencies.api.postV2(`/api/v2/titles/${titleId}/enrich`, {}))
    .then((refreshed) => {
      if (!refreshed || typeof refreshed !== "object" || activeDetail?.titleId !== titleId) return refreshed || null;
      activeDetail.title = refreshed;
      setPersonContext(refreshed);
      patchMetadataSections(refreshed);
      void prefetchVisiblePeople(refreshed, { titleId });
      return refreshed;
    })
    .catch(() => {
      metadataEnrichmentAttemptedAt.delete(titleId);
      return null;
    })
    .finally(() => metadataEnrichmentInFlight.delete(titleId));
  metadataEnrichmentInFlight.set(titleId, request);
  return request;
}

async function refreshTitlePeople(titleId) {
  if (!activeDetail || activeDetail.titleId !== titleId) return null;
  const refreshed = await dependencies.fetchJson(`/api/v2/titles/${titleId}`);
  if (!activeDetail || activeDetail.titleId !== titleId) return null;
  activeDetail.title = refreshed;
  setPersonContext(refreshed);
  patchPeopleSection(refreshed);
  return refreshed;
}

async function refreshTitleRelations(titleId) {
  if (!activeDetail || activeDetail.titleId !== titleId) return null;
  const universe = await dependencies.fetchJson(
    `/api/v2/universe?focus=${encodeURIComponent(titleId)}&limit=${RELATION_LIMIT}`,
  );
  if (!activeDetail || activeDetail.titleId !== titleId) return null;
  activeDetail.universe = universe;
  patchRelationsSection(activeDetail.title, universe);
  return universe;
}

async function refreshTitleMetadata(titleId) {
  if (!activeDetail || activeDetail.titleId !== titleId) return null;
  const refreshed = await dependencies.fetchJson(`/api/v2/titles/${titleId}`);
  if (!activeDetail || activeDetail.titleId !== titleId) return null;
  activeDetail.title = refreshed;
  setPersonContext(refreshed);
  patchMetadataSections(refreshed);
  void prefetchVisiblePeople(refreshed, { titleId });
  return refreshed;
}

function scheduleTitlePosterPoll(titleId, jobId) {
  if (!jobId || titlePosterJobTimers.has(titleId)) return;
  const timer = dependencies.setTimer(async () => {
    titlePosterJobTimers.delete(titleId);
    try {
      const job = await auxiliaryApiGet(`/api/v2/media/jobs/${encodeURIComponent(jobId)}`);
      const state = textValue(job?.state).toLowerCase();
      if (state === "ready") {
        titlePosterJobState.set(titleId, "success");
        await refreshTitleMetadata(titleId);
        return;
      }
      if (POLLABLE_MEDIA_STATES.has(state)) {
        scheduleTitlePosterPoll(titleId, jobId);
        return;
      }
      titlePosterJobState.set(titleId, "failed");
      if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    } catch {
      titlePosterJobState.set(titleId, "failed");
      if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    }
  }, dependencies.mediaPollInterval);
  titlePosterJobTimers.set(titleId, timer);
}

export function prefetchTitlePoster(title = {}, { titleId = titleIdentity(title) } = {}) {
  const media = adaptCatalogMedia(title, "poster");
  const existing = titlePosterJobState.get(titleId);
  if (!titleId || media.status === "ready" || existing === "in-progress" || existing === "success" || typeof dependencies.api?.postV2 !== "function") {
    return Promise.resolve(null);
  }
  titlePosterJobState.set(titleId, "in-progress");
  if (activeDetail?.titleId === titleId) patchMetadataSections(title);
  return Promise.resolve(dependencies.api.postV2("/api/v2/media/jobs", {
    kind: "poster",
    identity_key: titleId,
    title: textValue(title?.title) || textValue(title?.item?.title),
    year: Number.isFinite(title?.year) ? title.year : Number.isFinite(title?.item?.year) ? title.item.year : undefined,
    media_type: textValue(title?.media_type) || textValue(title?.item?.media_type),
    priority: 0,
  })).then((job) => {
    const jobId = textValue(job?.job_id) || textValue(job?.id);
    const state = textValue(job?.state, "queued").toLowerCase();
    if (state === "ready") {
      titlePosterJobState.set(titleId, "success");
      void refreshTitleMetadata(titleId);
    } else if (jobId && POLLABLE_MEDIA_STATES.has(state)) {
      scheduleTitlePosterPoll(titleId, jobId);
    } else {
      titlePosterJobState.set(titleId, "failed");
      if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    }
    return job;
  }).catch(() => {
    titlePosterJobState.set(titleId, "failed");
    if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    return null;
  });
}

function scheduleTitleBackdropPoll(titleId, jobId) {
  if (!jobId || titleBackdropJobTimers.has(titleId)) return;
  const timer = dependencies.setTimer(async () => {
    titleBackdropJobTimers.delete(titleId);
    try {
      const job = await auxiliaryApiGet(`/api/v2/media/jobs/${encodeURIComponent(jobId)}`);
      const state = textValue(job?.state).toLowerCase();
      if (state === "ready") {
        titleBackdropJobState.set(titleId, "success");
        await refreshTitleMetadata(titleId);
        return;
      }
      if (POLLABLE_MEDIA_STATES.has(state)) {
        scheduleTitleBackdropPoll(titleId, jobId);
        return;
      }
      titleBackdropJobState.set(titleId, "failed");
      if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    } catch {
      titleBackdropJobState.set(titleId, "failed");
      if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    }
  }, dependencies.mediaPollInterval);
  titleBackdropJobTimers.set(titleId, timer);
}

export function prefetchTitleBackdrop(title = {}, { titleId = titleIdentity(title) } = {}) {
  if (title?.is_live) return Promise.resolve(null);
  const existing = titleBackdropJobState.get(titleId);
  const backdrop = title?.backdrop && typeof title.backdrop === "object" ? title.backdrop : {};
  const backdropUrl = trustedDetailVisualUrl(backdrop);
  const posterUrl = trustedDetailVisualUrl(title?.poster);
  const hasIndependentBackdrop = Boolean(backdropUrl && backdropUrl !== posterUrl);
  if (!titleId || hasIndependentBackdrop || firstVerifiedStillUrl(title) || existing === "in-progress" || existing === "success" || typeof dependencies.api?.postV2 !== "function") {
    return Promise.resolve(null);
  }
  titleBackdropJobState.set(titleId, "in-progress");
  if (activeDetail?.titleId === titleId) patchMetadataSections(title);
  return Promise.resolve(dependencies.api.postV2("/api/v2/media/jobs", {
    kind: "backdrop",
    identity_key: titleId,
    title: textValue(title?.title) || textValue(title?.item?.title),
    year: Number.isFinite(title?.year) ? title.year : Number.isFinite(title?.item?.year) ? title.item.year : undefined,
    media_type: textValue(title?.media_type) || textValue(title?.item?.media_type),
    priority: 0,
  })).then((job) => {
    const jobId = textValue(job?.job_id) || textValue(job?.id);
    const state = textValue(job?.state, "queued").toLowerCase();
    if (state === "ready") {
      titleBackdropJobState.set(titleId, "success");
      void refreshTitleMetadata(titleId);
    } else if (jobId && POLLABLE_MEDIA_STATES.has(state)) {
      scheduleTitleBackdropPoll(titleId, jobId);
    } else {
      titleBackdropJobState.set(titleId, "failed");
      if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    }
    return job;
  }).catch(() => {
    titleBackdropJobState.set(titleId, "failed");
    if (activeDetail?.titleId === titleId) patchMetadataSections(activeDetail.title);
    return null;
  });
}

function scheduleRelationPosterPoll(itemKey, jobId, titleId) {
  if (!jobId || relationPosterJobTimers.has(itemKey)) return;
  const timer = dependencies.setTimer(async () => {
    relationPosterJobTimers.delete(itemKey);
    try {
      const job = await auxiliaryApiGet(`/api/v2/media/jobs/${encodeURIComponent(jobId)}`);
      const state = textValue(job?.state).toLowerCase();
      if (state === "ready") {
        relationPosterJobState.set(itemKey, "success");
        await refreshTitleRelations(titleId);
        return;
      }
      if (POLLABLE_MEDIA_STATES.has(state)) {
        scheduleRelationPosterPoll(itemKey, jobId, titleId);
        return;
      }
      relationPosterJobState.set(itemKey, "failed");
      patchRelationsSection();
    } catch {
      relationPosterJobState.set(itemKey, "failed");
      patchRelationsSection();
    }
  }, dependencies.mediaPollInterval);
  relationPosterJobTimers.set(itemKey, timer);
}

export function prefetchVisibleRelations(title = {}, universe = {}, { titleId = textValue(title?.item_key) } = {}) {
  if (typeof dependencies.api?.postV2 !== "function") return Promise.resolve([]);
  const pending = relatedNodes(title, universe)
    .filter((node) => adaptCatalogMedia(node, "poster").status !== "ready")
    .filter((node) => {
      const state = relationPosterJobState.get(relationNodeKey(node));
      return state !== "in-progress" && state !== "success";
    })
    .slice(0, 8);
  const jobs = pending.map(async (node) => {
    const itemKey = relationNodeKey(node);
    relationPosterJobState.set(itemKey, "in-progress");
    patchRelationsSection(title, universe);
    try {
      const job = await dependencies.api.postV2("/api/v2/media/jobs", {
        kind: "poster",
        identity_key: itemKey,
        title: textValue(node?.title),
        year: Number.isFinite(node?.year) ? node.year : undefined,
        media_type: textValue(node?.media_type),
        priority: 1,
      });
      const jobId = textValue(job?.job_id) || textValue(job?.id);
      const state = textValue(job?.state, "queued").toLowerCase();
      if (state === "ready") {
        relationPosterJobState.set(itemKey, "success");
        void refreshTitleRelations(titleId);
      } else if (jobId && POLLABLE_MEDIA_STATES.has(state)) {
        scheduleRelationPosterPoll(itemKey, jobId, titleId);
      } else {
        relationPosterJobState.set(itemKey, "failed");
        patchRelationsSection(title, universe);
      }
      return job;
    } catch {
      relationPosterJobState.set(itemKey, "failed");
      patchRelationsSection(title, universe);
      return null;
    }
  });
  return Promise.all(jobs);
}

function schedulePortraitPoll(personId, jobId, titleId) {
  if (!jobId || portraitJobTimers.has(personId)) return;
  const timer = dependencies.setTimer(async () => {
    portraitJobTimers.delete(personId);
    try {
      const job = await auxiliaryApiGet(`/api/v2/media/jobs/${encodeURIComponent(jobId)}`);
      const state = textValue(job?.state).toLowerCase();
      if (state === "ready" || state === "degraded") {
        portraitJobState.set(personId, state === "ready" ? "success" : "failed");
        if (state === "ready") portraitPrefetched.add(personId);
        else portraitPrefetched.delete(personId);
        await refreshTitlePeople(titleId);
        return;
      }
      if (["queued", "pending", "processing", "resolving", "downloading", "validating"].includes(state)) {
        schedulePortraitPoll(personId, jobId, titleId);
      } else {
        portraitJobState.set(personId, "failed");
        portraitPrefetched.delete(personId);
        patchPeopleSection(activeDetail?.title || {});
      }
    } catch {
      portraitJobState.set(personId, "failed");
      portraitPrefetched.delete(personId);
      patchPeopleSection(activeDetail?.title || {});
    }
  }, dependencies.mediaPollInterval);
  portraitJobTimers.set(personId, timer);
}

/**
 * Enqueues only directors and the first eight cast portraits. Name matching is
 * exact against title.people, while every job uses the backend-provided person id.
 */
export function prefetchVisiblePeople(title = {}, { titleId = textValue(title?.item_key) } = {}) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const people = visiblePeopleForTitle(title);
  const uniquePeople = [];
  const seen = new Set();
  for (const person of people) {
    const personId = textValue(person?.id);
    if (!personId || seen.has(personId)) continue;
    seen.add(personId);
    if (adaptPersonMedia(person).status === "ready" || portraitPrefetchInFlight.has(personId) || portraitPrefetched.has(personId)) continue;
    uniquePeople.push(person);
  }

  uniquePeople.sort((left, right) => portraitJobPriority(right, item) - portraitJobPriority(left, item));

  for (const person of uniquePeople) {
    const personId = textValue(person.id);
    portraitPrefetchInFlight.add(personId);
    portraitJobState.set(personId, "in-progress");
  }
  if (uniquePeople.length) patchPeopleSection(title);

  const jobs = uniquePeople.map(async (person) => {
    const personId = textValue(person.id);
    try {
      const job = await dependencies.api.postV2("/api/v2/media/jobs", {
        kind: "portrait",
        identity_key: personId,
        person_name: textValue(person.name),
        occupations: [textValue(person.role, "cast")],
        work_context: portraitWorkContext(title, person),
        priority: portraitJobPriority(person, item),
      });
      if (job && typeof job === "object") {
        portraitPrefetched.add(personId);
        const jobId = textValue(job.job_id) || textValue(job.id);
        const state = textValue(job.state).toLowerCase();
        if (state === "ready" || state === "degraded") {
          portraitJobState.set(personId, state === "ready" ? "success" : "failed");
          if (state === "ready") portraitPrefetched.add(personId);
          else portraitPrefetched.delete(personId);
          void refreshTitlePeople(titleId);
        } else {
          schedulePortraitPoll(personId, jobId, titleId);
        }
      }
      return job;
    } catch {
      portraitJobState.set(personId, "failed");
      portraitPrefetched.delete(personId);
      patchPeopleSection(title);
      return null;
    } finally {
      portraitPrefetchInFlight.delete(personId);
    }
  });
  return Promise.all(jobs);
}

export function retryMissingPortraits(title = activeDetail?.title || {}) {
  const people = Array.isArray(title?.people) ? title.people : [];
  for (const person of people) {
    if (adaptPersonMedia(person).status === "ready") continue;
    const personId = textValue(person?.id);
    if (!personId || portraitPrefetchInFlight.has(personId)) continue;
    portraitPrefetched.delete(personId);
    portraitJobState.delete(personId);
    const timer = portraitJobTimers.get(personId);
    if (timer !== undefined) dependencies.clearTimer(timer);
    portraitJobTimers.delete(personId);
  }
  patchPeopleSection(title);
  return prefetchVisiblePeople(title, { titleId: textValue(title?.item_key, activeDetail?.titleId) });
}

export async function renderTitleDetail(titleId, options = {}) {
  const cleanId = apiRouteSegment(titleId);
  if (!cleanId) return null;
  const universePromise = requestUniverseDiscovery(cleanId, options.signal);
  const similarPromise = requestSimilarDiscovery(cleanId, options.signal);
  try {
    const title = await detailApiGet(`/api/v2/titles/${cleanId}`, { signal: options.signal });
    if (options.signal?.aborted || (typeof options.isCurrent === "function" && !options.isCurrent())) return null;
    if (activeDetail?.titleId !== cleanId) personCardCache.clear();
    const page = renderDetailPage(title);
    const committed = await commitView(page, { heading: titleDisplayName(title, "作品详情") }, options);
    if (!committed) return null;
    setPersonContext(title);
    activeDetail = { titleId: cleanId, page, title, universe: {}, similar: {} };
    void prefetchVisiblePeople(title, { titleId: cleanId });
    void prefetchTitlePoster(title, { titleId: cleanId });
    void prefetchTitleBackdrop(title, { titleId: cleanId });
    void enrichThinTitleMetadata(title, { titleId: cleanId });
    void hydrateDetailDiscovery(cleanId, title, {
      universePromise,
      similarPromise,
      signal: options.signal,
      isCurrent: options.isCurrent,
    });
    return page;
  } catch (error) {
    if (options.signal?.aborted || error?.name === "AbortError") return null;
    globalThis.console?.error?.("CineScope detail render failed", error);
    const recovery = recoveryPanel(cleanId, () => { void renderTitleDetail(cleanId, options); });
    return await commitView(recovery, { heading: "作品详情恢复" }, options) ? recovery : null;
  }
}
