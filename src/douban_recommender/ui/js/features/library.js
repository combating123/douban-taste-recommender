import { disposeMediaFrame, renderMediaFrame } from "../components/media-frame.js";
import { openMediaLightbox } from "../components/media-lightbox.js";
import { decisionSummary, mediaBadgeLabel } from "../components/title-card.js";
import { getV2, postV2 } from "../core/api.js";
import { adaptCatalogMedia, attachResilientImage, MEDIA_LOAD_PRIORITY } from "../core/media.js";

const FILTERS = Object.freeze([
  ["all", "全部"],
  ["watched", "看过"],
  ["wish", "想看"],
  ["candidate", "候选"],
]);
const FILTER_KEYS = new Set(FILTERS.map(([key]) => key));
const PAGE_LIMIT = 24;
const ROW_HEIGHT = 400;
const OVERSCAN_ROWS = 4;
const MEDIA_OVERSCAN_ROWS = 9;
const MAX_VISIBLE_MEDIA_JOBS = 8;
const DETAIL_WARM_CONCURRENCY = 2;

const STATE_LABELS = Object.freeze({
  all: "全部",
  watched: "看过",
  wish: "想看",
  wanted: "想看",
  candidate: "推荐候选",
  rated: "已评分",
  collect: "看过",
});

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

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

function visualLoadingSurface() {
  const loading = element("span", "library-card__visual-loading");
  loading.setAttribute("aria-hidden", "true");
  loading.append(
    element("span", "library-card__visual-loading-glow"),
    element("span", "library-card__visual-loading-line"),
  );
  return loading;
}

function visualFallbackSurface(message = "视觉资料暂缺") {
  const fallback = element("span", "library-card__visual-fallback");
  const mark = element("span", "library-card__visual-fallback-mark");
  mark.setAttribute("aria-hidden", "true");
  fallback.append(mark, element("span", "library-card__visual-fallback-copy", message));
  return fallback;
}

function safeItemKey(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return /^[A-Za-z0-9:._~-]{1,256}$/.test(text) ? text : "";
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function listValue(value) {
  return Array.isArray(value) ? value.filter((entry) => typeof entry === "string" && entry.trim()) : [];
}

function visualUrlValue(value) {
  if (typeof value === "string") return value.trim();
  if (!value || typeof value !== "object") return "";
  return String(value.localUrl || value.url || value.src || "").trim();
}

function verifiedVisualUrl(value) {
  const url = visualUrlValue(value);
  if (url.startsWith("/api/image-proxy?url=") || url.startsWith("/media/")) return url;
  if (/^https?:\/\//i.test(url)) return `/api/image-proxy?url=${encodeURIComponent(url)}`;
  return "";
}

function visualCandidates(item) {
  const candidates = [];
  const seen = new Set();
  const poster = adaptCatalogMedia(item, "poster");
  const posterUrl = poster.status === "ready" ? verifiedVisualUrl(poster.localUrl) : "";
  const add = (value, label, kind) => {
    const url = verifiedVisualUrl(value);
    if (!url || url === posterUrl || seen.has(url)) return;
    seen.add(url);
    candidates.push({ url, label, kind });
  };
  for (const still of Array.isArray(item?.stills) ? item.stills : []) add(still, "剧照", "still");
  add(item?.backdrop, "主视觉", "backdrop");
  return candidates;
}

function clampRailScroll(rail, nextLeft) {
  const maximum = Math.max(0, Number(rail.scrollWidth || 0) - Number(rail.clientWidth || 0));
  rail.scrollLeft = Math.min(maximum, Math.max(0, nextLeft));
}

function installHorizontalRailInteractions(rail, onInteraction = null) {
  let pointerId = null;
  let startX = 0;
  let startScrollLeft = 0;
  let dragged = false;
  let suppressNextClick = false;
  const warmForInteraction = (direction = 1) => {
    if (typeof onInteraction === "function") onInteraction(direction < 0 ? -1 : 1);
  };

  const scrollStep = () => Math.max(180, Math.round((Number(rail.clientWidth) || 320) * 0.45));
  const finishDrag = (event) => {
    if (pointerId === null) return;
    if (event?.pointerId !== undefined && event.pointerId !== pointerId) return;
    if (dragged) rail.releasePointerCapture?.(pointerId);
    pointerId = null;
    rail.classList.remove("is-dragging");
    suppressNextClick = dragged;
  };

  rail.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault?.();
      event.stopPropagation?.();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      clampRailScroll(rail, rail.scrollLeft + direction * scrollStep());
      warmForInteraction(direction);
    } else if (event.key === "Home") {
      event.preventDefault?.();
      event.stopPropagation?.();
      clampRailScroll(rail, 0);
      warmForInteraction(1);
    } else if (event.key === "End") {
      event.preventDefault?.();
      event.stopPropagation?.();
      clampRailScroll(rail, Number(rail.scrollWidth || 0));
      warmForInteraction(-1);
    }
  });

  rail.addEventListener("wheel", (event) => {
    const deltaX = Number(event.deltaX) || 0;
    const deltaY = Number(event.deltaY) || 0;
    const intendedDelta = event.shiftKey && !deltaX ? deltaY : deltaX;
    if (!intendedDelta || (Math.abs(deltaX) < Math.abs(deltaY) && !event.shiftKey)) return;
    const before = rail.scrollLeft;
    clampRailScroll(rail, before + intendedDelta);
    warmForInteraction(intendedDelta < 0 ? -1 : 1);
    if (rail.scrollLeft !== before) event.preventDefault?.();
  }, { passive: false });

  rail.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    pointerId = event.pointerId ?? 1;
    startX = Number(event.clientX) || 0;
    startScrollLeft = Number(rail.scrollLeft) || 0;
    dragged = false;
    warmForInteraction(1);
  });
  rail.addEventListener("pointermove", (event) => {
    if (pointerId === null || (event.pointerId !== undefined && event.pointerId !== pointerId)) return;
    const distance = (Number(event.clientX) || 0) - startX;
    if (!dragged && Math.abs(distance) > 5) {
      dragged = true;
      rail.setPointerCapture?.(pointerId);
      rail.classList.add("is-dragging");
      warmForInteraction(distance < 0 ? 1 : -1);
    }
    if (dragged) {
      event.preventDefault?.();
      clampRailScroll(rail, startScrollLeft - distance * 0.65);
    }
  });
  rail.addEventListener("pointerup", finishDrag);
  rail.addEventListener("pointercancel", finishDrag);
  rail.addEventListener("dragstart", (event) => event.preventDefault?.());
  rail.addEventListener("click", (event) => {
    if (!suppressNextClick) return;
    suppressNextClick = false;
    event.preventDefault?.();
    event.stopPropagation?.();
  }, true);
}

function renderStillPreview(item, detailHref, options = {}) {
  const visuals = visualCandidates(item);
  const stillCount = visuals.filter((visual) => visual.kind === "still").length;
  const preview = element("div", "library-card__visuals");
  const label = stillCount
    ? "剧照 · " + stillCount
    : visuals.length
      ? "主视觉"
      : "剧照 · 0";
  const accessibleLabel = stillCount
    ? "共 " + stillCount + " 张剧照"
    : visuals.length
      ? "作品主视觉"
      : "暂无真实剧照";
  preview.setAttribute("aria-label", accessibleLabel);
  preview.append(element("span", "library-card__visuals-label", label));
  const rail = element("div", "library-card__visuals-rail");
  rail.setAttribute("role", "group");
  rail.setAttribute("aria-label", accessibleLabel + "，横向视觉轨道");
  rail.setAttribute("tabindex", "0");
  rail.dataset.horizontalRail = "true";
  let warmRailInteraction = () => {};
  installHorizontalRailInteractions(rail, (direction) => warmRailInteraction(direction));
  if (!visuals.length) {
    rail.dataset.state = "empty";
    rail.append(visualFallbackSurface("暂未找到可核对的真实剧照"));
    preview.append(rail);
    return preview;
  }

  const mounts = [];
  const itemKey = safeItemKey(options.itemKey);
  const onScrollLeftChange = typeof options.onScrollLeftChange === "function" ? options.onScrollLeftChange : () => {};
  let lastKnownScrollLeft = Math.max(0, Number(options.initialScrollLeft) || 0);
  let disposed = false;
  let stillObserver = null;
  const loadVisual = (index, priority = MEDIA_LOAD_PRIORITY.visible) => {
    const mount = mounts[index];
    if (!mount || disposed) return;
    if (mount.started) {
      mount.handle?.promote?.(priority);
      return;
    }
    mount.started = true;
    mount.image.loading = "eager";
    mount.image.dataset.mediaState = "loading";
    mount.frame.dataset.mediaState = "loading";
    mount.handle = attachResilientImage(mount.image, mount.visual.url, {
      maxRetries: 0,
      priority,
      backgroundOnly: true,
      onFailure: () => {
        if (disposed) return;
        mount.image.hidden = true;
        mount.image.dataset.mediaState = "failed";
        mount.frame.dataset.mediaState = "failed";
        mount.frame.replaceChildren(visualFallbackSurface());
      },
    });
  };
  const loadVisualAndNeighbours = (index, priority = MEDIA_LOAD_PRIORITY.visible) => {
    loadVisual(index, priority);
    loadVisual(index - 1, MEDIA_LOAD_PRIORITY.standard);
    loadVisual(index + 1, MEDIA_LOAD_PRIORITY.standard);
  };
  const loadStillsNearViewport = () => {
    if (disposed || !mounts.length) return;
    const left = Math.max(0, Number(rail.scrollLeft) || 0);
    const width = Math.max(1, Number(rail.clientWidth) || 1);
    const right = left + width;
    const margin = width * 0.75;
    let matched = false;
    for (const [index, mount] of mounts.entries()) {
      const frameLeft = Number(mount.frame.offsetLeft);
      const frameWidth = Number(mount.frame.offsetWidth);
      if (!Number.isFinite(frameLeft) || !Number.isFinite(frameWidth) || frameWidth <= 0) continue;
      if (frameLeft <= right + margin && frameLeft + frameWidth >= left - margin) {
        matched = true;
        loadVisualAndNeighbours(index);
      }
    }
    if (matched) return;
    const maximum = Math.max(0, Number(rail.scrollWidth || 0) - width);
    const progress = maximum > 0 ? Math.min(1, left / maximum) : 0;
    loadVisualAndNeighbours(Math.round(progress * Math.max(0, mounts.length - 1)));
  };
  const visualIndexAtRailPosition = () => {
    const left = Math.max(0, Number(rail.scrollLeft) || 0);
    const width = Math.max(1, Number(rail.clientWidth) || 1);
    const center = left + width / 2;
    let nearestIndex = -1;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (const [index, mount] of mounts.entries()) {
      const frameLeft = Number(mount.frame.offsetLeft);
      const frameWidth = Number(mount.frame.offsetWidth);
      if (!Number.isFinite(frameLeft) || !Number.isFinite(frameWidth) || frameWidth <= 0) continue;
      const distance = Math.abs(frameLeft + frameWidth / 2 - center);
      if (distance < nearestDistance) {
        nearestIndex = index;
        nearestDistance = distance;
      }
    }
    if (nearestIndex >= 0) return nearestIndex;
    const maximum = Math.max(0, Number(rail.scrollWidth || 0) - width);
    const progress = maximum > 0 ? Math.min(1, left / maximum) : 0;
    return Math.round(progress * Math.max(0, mounts.length - 1));
  };
  warmRailInteraction = (direction = 1) => {
    if (disposed || !mounts.length) return;
    const step = direction < 0 ? -1 : 1;
    const anchor = visualIndexAtRailPosition();
    loadVisual(anchor + step, MEDIA_LOAD_PRIORITY.interaction);
    loadVisual(anchor + step * 2, MEDIA_LOAD_PRIORITY.standard);
  };
  const reportRailScroll = () => {
    if (itemKey) onScrollLeftChange(itemKey, lastKnownScrollLeft);
  };
  const handleRailScroll = () => {
    lastKnownScrollLeft = Math.max(0, Number(rail.scrollLeft) || 0);
    reportRailScroll();
    loadStillsNearViewport();
  };
  rail.addEventListener("scroll", handleRailScroll, { passive: true });

  for (const [index, visual] of visuals.entries()) {
    const frame = element("button", "library-card__still-frame");
    frame.type = "button";
    frame.dataset.visualKind = visual.kind;
    frame.dataset.stillIndex = String(index);
    frame.setAttribute("aria-label", "放大查看" + visual.label + " " + (index + 1) + " / " + visuals.length);
    const loading = visualLoadingSurface();
    const image = document.createElement("img");
    image.className = "library-card__still";
    image.alt = visual.label + " " + (index + 1);
    image.loading = index < 3 ? "eager" : "lazy";
    image.decoding = "async";
    image.fetchPriority = index === 0 ? "high" : "auto";
    image.hidden = true;
    image.dataset.mediaState = index < 3 ? "loading" : "deferred";
    frame.dataset.mediaState = image.dataset.mediaState;
    const handleVisualLoad = () => {
      if (disposed || image.dataset.mediaState === "failed") return;
      const width = Math.round(Number(image.naturalWidth) || 0);
      const height = Math.round(Number(image.naturalHeight) || 0);
      if (width > 0 && height > 0) frame.style.setProperty("--still-aspect", width + " / " + height);
      image.hidden = false;
      image.dataset.mediaState = "ready";
      frame.dataset.mediaState = "ready";
      frame.replaceChildren(image);
      image.removeEventListener?.("load", handleVisualLoad);
    };
    image.addEventListener("load", handleVisualLoad);
    const mount = { frame, image, visual, started: false, handle: null, handleVisualLoad };
    mounts.push(mount);
    const preload = (priority = MEDIA_LOAD_PRIORITY.interaction) => {
      loadVisualAndNeighbours(index, priority);
    };
    frame.addEventListener("pointerenter", () => preload(), { once: true });
    frame.addEventListener("focus", () => preload(), { once: true });
    frame.addEventListener("click", (event) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      preload(MEDIA_LOAD_PRIORITY.interaction);
      openMediaLightbox({
        items: visuals,
        index,
        title: titleDisplayName(item, "作品剧照"),
        detailHref,
        trigger: frame,
      });
    });
    frame.append(loading, image);
    rail.append(frame);
  }

  const createStillObserver = typeof options.createStillObserver === "function"
    ? options.createStillObserver
    : defaultStillObserver;
  stillObserver = createStillObserver?.((entries) => {
    for (const entry of entries || []) {
      if (!entry?.isIntersecting) continue;
      const index = Number(entry.target?.dataset?.stillIndex);
      if (Number.isInteger(index)) loadVisualAndNeighbours(index);
    }
  }, {
    root: rail,
    rootMargin: "0px 75% 0px 75%",
    threshold: 0.01,
  }) || null;
  for (const mount of mounts) stillObserver?.observe?.(mount.frame);
  loadVisual(0, MEDIA_LOAD_PRIORITY.visible);
  loadVisual(1, MEDIA_LOAD_PRIORITY.standard);
  loadVisual(2, MEDIA_LOAD_PRIORITY.background);

  preview.restoreStillPreview = () => {
    if (disposed) return;
    rail.scrollLeft = lastKnownScrollLeft;
    loadStillsNearViewport();
  };
  rail.scrollLeft = lastKnownScrollLeft;
  preview.disposeStillPreview = () => {
    if (disposed) return;
    reportRailScroll();
    disposed = true;
    rail.removeEventListener?.("scroll", handleRailScroll);
    stillObserver?.disconnect?.();
    stillObserver = null;
    for (const mount of [...mounts].reverse()) {
      mount.image.removeEventListener?.("load", mount.handleVisualLoad);
      mount.handle?.cancel?.();
    }
  };
  preview.append(rail);
  return preview;
}

function scoreValue(item) {
  const score = objectValue(item?.item).douban_rating;
  return typeof score === "number" && Number.isFinite(score) ? score : null;
}

function ratingRows(item) {
  const payload = objectValue(item?.item);
  const raw = objectValue(payload.raw);
  const source = objectValue(raw.ratings);
  const labels = { imdb: "IMDb", tmdb: "TMDb", tvmaze: "TVMaze", anilist: "AniList", jikan: "MAL" };
  const rows = [];
  const douban = scoreValue(item);
  if (douban !== null) rows.push(["douban", "豆瓣", douban]);
  for (const [provider, value] of Object.entries(source)) {
    const score = Number(value);
    if (!Number.isFinite(score) || score <= 0 || provider === "douban") continue;
    rows.push([provider, labels[provider] || provider, Math.round(score * 10) / 10]);
  }
  return rows.slice(0, 3);
}

function itemCardSignature(item) {
  const payload = objectValue(item?.item);
  const poster = adaptCatalogMedia(item, "poster");
  return JSON.stringify({
    key: safeItemKey(item?.item_key),
    title: typeof item?.title === "string" ? item.title : "",
    displayTitle: titleDisplayName(item, ""),
    state: typeof item?.state === "string" ? item.state : "",
    year: item?.year ?? null,
    mediaType: typeof item?.media_type === "string" ? item.media_type : "",
    score: scoreValue(item),
    ratings: objectValue(objectValue(payload.raw).ratings),
    genres: listValue(payload.genres).slice(0, 3),
    summary: typeof payload.summary === "string" ? payload.summary.trim() : "",
    directors: listValue(payload.directors).slice(0, 2),
    casts: listValue(payload.casts).slice(0, 3),
    visuals: visualCandidates(item),
    poster: {
      localUrl: poster.localUrl,
      status: poster.status,
      source: poster.source,
    },
  });
}

function countText(value) {
  return Number.isInteger(value) && value >= 0 ? String(value) : "—";
}

function columnsFor(width) {
  if (width >= 1880) return 3;
  if (width >= 880) return 2;
  return 1;
}

function itemCard(item, options = {}) {
  const card = element("article", "library-card");
  const key = safeItemKey(item?.item_key);
  const detailHref = key ? `/title/${encodeURIComponent(key)}` : "/library";
  const link = element("a", "library-card__link");
  link.setAttribute("href", detailHref);
  if (key) link.setAttribute("data-route", "");
  const warmDetail = () => options.onWarmDetail?.(key);
  if (key) {
    link.addEventListener("pointerenter", warmDetail);
    link.addEventListener("focus", warmDetail);
    link.addEventListener("pointerdown", warmDetail);
  }
  const posterFrame = renderMediaFrame(adaptCatalogMedia(item, "poster"), {
    priority: MEDIA_LOAD_PRIORITY.visible,
    backgroundOnly: true,
  });
  const posterShell = element("div", "library-card__poster-shell");
  posterShell.append(posterFrame);
  link.append(posterShell);

  const payload = objectValue(item?.item);
  const body = element("div", "library-card__body");
  const copy = element("div", "library-card__copy");
  const badges = element("div", "library-card__badges");
  const ratings = ratingRows(item);
  if (ratings.length) {
    for (const [provider, label, score] of ratings) {
      badges.append(element("span", `library-card__score library-card__score--${provider}`, `${label} ${score}`));
    }
  } else {
    badges.append(element("span", "library-card__score library-card__score--pending", "评分样本不足"));
  }
  badges.append(element("span", "library-card__state", STATE_LABELS[item?.state] || "片库记录"));
  const title = element("h3", "library-card__title", titleDisplayName(item));
  const mediaType = mediaBadgeLabel(item, "媒体类型待补全");
  const year = Number.isInteger(item?.year) ? String(item.year) : "年份待补全";
  const metadata = [mediaType, year].filter((value) => value !== null && value !== undefined && String(value).trim()).join(" · ");
  const genres = listValue(payload.genres).slice(0, 3);
  const visibleGenres = genres.length ? genres : [mediaType];
  const summary = decisionSummary(payload, genres, mediaType);
  const directors = listValue(payload.directors).slice(0, 2);
  const casts = listValue(payload.casts).slice(0, 3);
  const people = [
    directors.length ? `导演：${directors.join(" / ")}` : "",
    casts.length ? `主演：${casts.join(" / ")}` : "",
  ].filter(Boolean).join(" · ");
  copy.append(
    badges,
    title,
    element("p", "library-card__meta", metadata || "本地片库条目"),
    element("p", "library-card__genres", `类型：${visibleGenres.join(" / ")}`),
    element("p", "library-card__summary", summary),
  );
  if (people) copy.append(element("p", "library-card__people", people));
  body.append(copy);
  link.append(body);
  const stillPreview = renderStillPreview(item, detailHref, options);
  if (stillPreview) body.classList.add("library-card__body--with-visuals");
  else body.classList.add("library-card__body--without-visuals");
  card.append(link);
  if (stillPreview) card.append(stillPreview);
  card.restoreLibraryCard = () => stillPreview?.restoreStillPreview?.();
  card.disposeLibraryCard = () => {
    stillPreview?.disposeStillPreview?.();
    if (key) {
      link.removeEventListener("pointerenter", warmDetail);
      link.removeEventListener("focus", warmDetail);
      link.removeEventListener("pointerdown", warmDetail);
    }
    disposeMediaFrame(posterFrame);
  };
  return card;
}

function defaultStillObserver(callback, options = {}) {
  if (typeof globalThis.IntersectionObserver !== "function") return null;
  return new IntersectionObserver(callback, options);
}

function defaultObserver(callback) {
  if (typeof globalThis.IntersectionObserver !== "function") return { observe() {}, disconnect() {} };
  return new IntersectionObserver(callback, { rootMargin: "600px 0px" });
}

function defaultResizeObserver(callback) {
  if (typeof globalThis.ResizeObserver !== "function") return null;
  return new ResizeObserver(callback);
}

function frameScheduler(callback) {
  const request = globalThis.requestAnimationFrame || ((next) => setTimeout(next, 0));
  return request(callback);
}

function frameCanceller(id) {
  const cancel = globalThis.cancelAnimationFrame || clearTimeout;
  cancel(id);
}

export function createLibraryController({
  root,
  fetchJson = getV2,
  postJson = null,
  setTimer = null,
  clearTimer = null,
  mediaPollInterval = 900,
  createObserver = defaultObserver,
  createStillObserver = defaultStillObserver,
  createResizeObserver = defaultResizeObserver,
  requestFrame = frameScheduler,
  cancelFrame = frameCanceller,
  onFilterChange = () => {},
  onScrollChange = () => {},
  windowTarget = globalThis.window,
} = {}) {
  if (!root) throw new TypeError("Library requires a root element");

  let state = "all";
  let items = [];
  let nextCursor = null;
  let generation = 0;
  let activeFetch = null;
  let loading = false;
  let disposed = false;
  let suspended = false;
  let observer = null;
  let resizeObserver = null;
  let usingWindowResize = false;
  let rafId = null;
  let pendingAnchorIndex = null;
  let currentColumns = 1;
  let anchorItemKey = "";
  const inFlightCursors = new Set();
  const seenCursors = new Set();
  let renderedItemCount = 0;
  let topSpacerHeight = 0;
  let bottomSpacerHeight = 0;
  let itemsVersion = 0;
  let renderedWindowKey = "";
  let counts = {};
  const cardCache = new Map();
  const stillRailPositions = new Map();
  const detailWarmKeys = new Set();
  const detailWarmQueue = [];
  const activeDetailWarmKeys = new Set();
  const attemptedPosterKeys = new Set();
  const activePosterKeys = new Set();
  const posterPollTimers = new Map();
  const posterPollJobs = new Map();
  const pendingMediaRefreshKeys = new Set();
  const mediaRefreshControllers = new Set();
  let visiblePosterItems = [];
  let mediaRefreshTimer = null;
  let scrollReportTimer = null;
  let lastReportedScrollTop = 0;

  const section = element("section", "space space--library");
  section.dataset.space = "library";
  const header = element("header", "space-header");
  const headingWrap = element("div", "space-header__copy");
  headingWrap.append(element("p", "eyebrow", "本地作品目录"), element("h1", "space-title", "片库"));
  const summary = element("p", "space-summary", "分段筛选本地条目；仅当前可见行进入页面。");
  const headerTools = element("div", "library-header__tools");
  const observatoryEntry = element("a", "library-observatory-entry");
  observatoryEntry.href = "/observatory";
  observatoryEntry.dataset.route = "";
  observatoryEntry.setAttribute("aria-label", "打开观影雷达、最近观看与在线发现");
  const entrySignal = element("span", "library-observatory-entry__signal");
  entrySignal.setAttribute("aria-hidden", "true");
  const entryCopy = element("span", "library-observatory-entry__copy");
  entryCopy.append(
    element("strong", "library-observatory-entry__title", "观影雷达"),
    element("small", "library-observatory-entry__meta", "最近观看 · 神经漫游 · 在线新片"),
  );
  observatoryEntry.append(entrySignal, entryCopy, element("span", "library-observatory-entry__arrow", "↗"));
  headerTools.append(summary, observatoryEntry);
  header.append(headingWrap, headerTools);

  const overview = element("section", "library-overview");
  overview.setAttribute("aria-label", "片库统计");
  const countNodes = new Map();
  for (const [key, label] of [["watched", "看过"], ["wish", "想看"], ["all", "全部档案"], ["candidate", "推荐候选"]]) {
    const metric = element("article", "library-overview__metric");
    const value = element("strong", "library-overview__value", "—");
    countNodes.set(key, value);
    metric.append(element("span", "library-overview__label", label), value);
    overview.append(metric);
  }

  const filters = element("div", "segmented-filter");
  filters.setAttribute("aria-label", "片库状态筛选");
  const filterButtons = new Map();
  for (const [key, label] of FILTERS) {
    const button = element("button", "segmented-filter__button", label);
    button.type = "button";
    button.dataset.libraryState = key;
    button.addEventListener("click", () => { void setFilter(key); });
    filterButtons.set(key, button);
    filters.append(button);
  }

  const viewport = element("div", "library-window");
  viewport.dataset.role = "library-window";
  const topSpacer = element("div", "library-spacer");
  topSpacer.dataset.role = "top-spacer";
  const rowsHost = element("div", "library-rows");
  rowsHost.dataset.role = "visible-rows";
  const bottomSpacer = element("div", "library-spacer");
  bottomSpacer.dataset.role = "bottom-spacer";
  const sentinel = element("div", "library-sentinel", "继续载入");
  sentinel.dataset.role = "library-sentinel";
  viewport.append(topSpacer, rowsHost, bottomSpacer, sentinel);
  section.append(header, overview, filters, viewport);
  root.replaceChildren(section);

  const usesPageScroll = Boolean(
    windowTarget?.document?.documentElement
    && typeof viewport.getBoundingClientRect === "function"
    && Number.isFinite(Number(windowTarget.scrollY)),
  );

  function viewportScrollTop() {
    if (!usesPageScroll) return Math.max(0, Number(viewport.scrollTop) || 0);
    const rect = viewport.getBoundingClientRect();
    return Math.max(0, -(Number(rect?.top) || 0));
  }

  function viewportVisibleHeight() {
    if (!usesPageScroll) return Math.max(1, Number(viewport.clientHeight) || 520);
    return Math.max(1, Number(windowTarget.innerHeight) || Number(windowTarget.document?.documentElement?.clientHeight) || 720);
  }

  function setViewportScrollTop(value) {
    const scrollTop = Math.max(0, Number(value) || 0);
    if (!usesPageScroll) {
      viewport.scrollTop = scrollTop;
      return;
    }
    const rect = viewport.getBoundingClientRect();
    const pageTop = (Number(windowTarget.scrollY) || 0) + (Number(rect?.top) || 0);
    windowTarget.scrollTo?.({ top: pageTop + scrollTop, behavior: "auto" });
  }

  function updateCounts(nextCounts) {
    counts = nextCounts && typeof nextCounts === "object" ? { ...nextCounts } : counts;
    for (const [key, node] of countNodes) node.textContent = countText(counts[key]);
    for (const [key, button] of filterButtons) {
      const value = countText(counts[key]);
      button.setAttribute("aria-label", `${button.textContent} ${value}`);
      button.dataset.count = value;
    }
  }

  function queuePoster(item) {
    if (typeof postJson !== "function" || activePosterKeys.size >= MAX_VISIBLE_MEDIA_JOBS) return;
    const key = safeItemKey(item?.item_key);
    const media = adaptCatalogMedia(item, "poster");
    if (!key || media.status === "ready" || media.status === "pending" || attemptedPosterKeys.has(key)) return;
    attemptedPosterKeys.add(key);
    activePosterKeys.add(key);
    void Promise.resolve(postJson("/api/v2/media/jobs", {
      kind: "poster",
      identity_key: key,
      title: typeof item?.title === "string" ? item.title : "",
      year: Number.isInteger(item?.year) ? item.year : undefined,
      media_type: typeof item?.media_type === "string" ? item.media_type : "",
      priority: 1,
    })).then((job) => {
      const jobId = typeof job?.job_id === "string" && job.job_id ? job.job_id : typeof job?.id === "string" ? job.id : "";
      const jobState = typeof job?.state === "string" ? job.state.toLowerCase() : "queued";
      if (jobState === "ready") {
        activePosterKeys.delete(key);
        scheduleMediaRefresh(key);
        pumpVisiblePosters();
      } else if (jobId && ["queued", "pending", "processing", "resolving", "downloading", "validating"].includes(jobState)) {
        schedulePosterPoll(key, jobId);
      } else {
        activePosterKeys.delete(key);
        pumpVisiblePosters();
      }
    }).catch(() => {
      activePosterKeys.delete(key);
      pumpVisiblePosters();
    });
  }

  function pumpVisiblePosters() {
    if (disposed || typeof postJson !== "function") return;
    for (const item of visiblePosterItems) {
      if (activePosterKeys.size >= MAX_VISIBLE_MEDIA_JOBS) break;
      queuePoster(item);
    }
  }

  async function refreshMediaItems(keys) {
    const requestGeneration = generation;
    const refreshed = await Promise.all(keys.map(async (key) => {
      const controller = new AbortController();
      mediaRefreshControllers.add(controller);
      try {
        const payload = await fetchJson(`/api/v2/titles/${encodeURIComponent(key)}`, { signal: controller.signal });
        if (disposed || controller.signal.aborted || generation !== requestGeneration) return null;
        return safeItemKey(payload?.item_key) === key ? payload : null;
      } catch {
        return null;
      } finally {
        mediaRefreshControllers.delete(controller);
      }
    }));
    if (disposed || generation !== requestGeneration) return;
    applyRefreshedItems(refreshed);
  }

  function applyRefreshedItems(refreshed) {
    const replacements = new Map((Array.isArray(refreshed) ? refreshed : []).filter(Boolean).map((item) => [safeItemKey(item?.item_key), item]));
    if (!replacements.size) return;
    let changed = false;
    items = items.map((item) => {
      const replacement = replacements.get(safeItemKey(item?.item_key));
      if (!replacement) return item;
      const currentPayload = objectValue(item?.item);
      const replacementPayload = objectValue(replacement?.item);
      const merged = {
        ...item,
        ...replacement,
        poster: replacement?.poster || item?.poster,
        backdrop: replacement?.backdrop || item?.backdrop,
        stills: Array.isArray(replacement?.stills) ? replacement.stills : item?.stills,
        people: Array.isArray(replacement?.people) ? replacement.people : item?.people,
        item: {
          ...currentPayload,
          ...replacementPayload,
          raw: { ...objectValue(currentPayload.raw), ...objectValue(replacementPayload.raw) },
        },
      };
      if (itemCardSignature(item) === itemCardSignature(merged)) return item;
      changed = true;
      return merged;
    });
    if (!changed) return;
    itemsVersion += 1;
    pruneCardCache();
    renderWindow();
  }

  function scheduleMediaRefresh(key) {
    const safeKey = safeItemKey(key);
    if (disposed || !safeKey || typeof setTimer !== "function") return;
    pendingMediaRefreshKeys.add(safeKey);
    if (mediaRefreshTimer !== null) return;
    mediaRefreshTimer = setTimer(async () => {
      mediaRefreshTimer = null;
      const keys = [...pendingMediaRefreshKeys];
      pendingMediaRefreshKeys.clear();
      if (!disposed) await refreshMediaItems(keys);
    }, 180);
  }

  function schedulePosterPoll(key, jobId) {
    if (disposed || !key || !jobId) return;
    posterPollJobs.set(key, jobId);
    if (suspended || typeof setTimer !== "function" || posterPollTimers.has(key)) return;
    const timer = setTimer(async () => {
      posterPollTimers.delete(key);
      if (disposed || suspended) return;
      try {
        const job = await fetchJson(`/api/v2/media/jobs/${encodeURIComponent(jobId)}`);
        const state = typeof job?.state === "string" ? job.state.toLowerCase() : "";
        if (state === "ready") {
          posterPollJobs.delete(key);
          activePosterKeys.delete(key);
          scheduleMediaRefresh(key);
          pumpVisiblePosters();
        } else if (["queued", "pending", "processing", "resolving", "downloading", "validating"].includes(state)) {
          schedulePosterPoll(key, jobId);
        } else {
          posterPollJobs.delete(key);
          activePosterKeys.delete(key);
          pumpVisiblePosters();
        }
      } catch {
        posterPollJobs.delete(key);
        activePosterKeys.delete(key);
        pumpVisiblePosters();
      }
    }, mediaPollInterval);
    posterPollTimers.set(key, timer);
  }

  function clearQueuedDetailWarm() {
    for (const key of detailWarmQueue) detailWarmKeys.delete(key);
    detailWarmQueue.length = 0;
  }

  function pumpDetailWarmQueue() {
    if (disposed) {
      clearQueuedDetailWarm();
      return;
    }
    while (activeDetailWarmKeys.size < DETAIL_WARM_CONCURRENCY && detailWarmQueue.length) {
      const key = detailWarmQueue.shift();
      if (!key || activeDetailWarmKeys.has(key)) continue;
      activeDetailWarmKeys.add(key);
      void Promise.resolve()
        .then(() => fetchJson(`/api/v2/titles/${key}`))
        .catch(() => null)
        .finally(() => {
          activeDetailWarmKeys.delete(key);
          if (!disposed) pumpDetailWarmQueue();
        });
    }
  }

  function queueDetailWarm(value) {
    const key = safeItemKey(value);
    if (disposed || !key || detailWarmKeys.has(key)) return false;
    detailWarmKeys.add(key);
    detailWarmQueue.push(key);
    pumpDetailWarmQueue();
    return true;
  }

  function updateFilterButtons() {
    for (const [key, button] of filterButtons) button.setAttribute("aria-pressed", String(key === state));
  }

  function rememberStillRailPosition(itemKey, scrollLeft) {
    const key = safeItemKey(itemKey);
    if (!key) return;
    stillRailPositions.set(key, Math.max(0, Number(scrollLeft) || 0));
  }

  function disposeCardCacheEntry(entry) {
    entry?.node?.disposeLibraryCard?.();
  }

  function cachedItemCard(item) {
    const key = safeItemKey(item?.item_key);
    const signature = itemCardSignature(item);
    const cached = cardCache.get(key);
    if (cached?.signature === signature) return cached.node;
    disposeCardCacheEntry(cached);
    const node = itemCard(item, {
      createStillObserver,
      itemKey: key,
      initialScrollLeft: stillRailPositions.get(key) || 0,
      onScrollLeftChange: rememberStillRailPosition,
      onWarmDetail: queueDetailWarm,
    });
    cardCache.set(key, { signature, node });
    return node;
  }

  function pruneCardCache() {
    const activeKeys = new Set(items.map((item) => safeItemKey(item?.item_key)).filter(Boolean));
    for (const [key, cached] of cardCache.entries()) {
      if (activeKeys.has(key)) continue;
      disposeCardCacheEntry(cached);
      cardCache.delete(key);
    }
  }

  function renderWindow() {
    if (disposed) return;
    const columns = columnsFor(Number(viewport.clientWidth) || 0);
    if (pendingAnchorIndex !== null && columns !== currentColumns) {
      setViewportScrollTop(Math.floor(pendingAnchorIndex / columns) * ROW_HEIGHT);
    }
    pendingAnchorIndex = null;
    currentColumns = columns;
    const totalRows = Math.ceil(items.length / columns);
    const scrollTop = viewportScrollTop();
    const viewportHeight = viewportVisibleHeight();
    const firstRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN_ROWS);
    const lastRow = Math.min(totalRows, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN_ROWS);
    const anchorIndex = Math.min(items.length - 1, Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) * columns));
    anchorItemKey = items.length ? safeItemKey(items[anchorIndex]?.item_key) : "";
    topSpacerHeight = firstRow * ROW_HEIGHT;
    bottomSpacerHeight = Math.max(0, (totalRows - lastRow) * ROW_HEIGHT);
    topSpacer.style.height = `${topSpacerHeight}px`;
    bottomSpacer.style.height = `${bottomSpacerHeight}px`;
    const windowKey = `${columns}:${firstRow}:${lastRow}:${itemsVersion}`;
    if (windowKey !== renderedWindowKey) {
      const rows = [];
      const mediaFirstRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - MEDIA_OVERSCAN_ROWS);
      const mediaLastRow = Math.min(totalRows, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + MEDIA_OVERSCAN_ROWS);
      visiblePosterItems = items.slice(mediaFirstRow * columns, mediaLastRow * columns);
      renderedItemCount = 0;
      for (let rowIndex = firstRow; rowIndex < lastRow; rowIndex += 1) {
        const row = element("div", "library-row");
        row.dataset.virtualRow = String(rowIndex);
        row.style.setProperty("--library-columns", String(columns));
        const start = rowIndex * columns;
        const rowItems = items.slice(start, start + columns);
        renderedItemCount += rowItems.length;
        row.append(...rowItems.map(cachedItemCard));
        rows.push(row);
      }
      rowsHost.replaceChildren(...rows);
      for (const row of rows) {
        for (const card of row.children || []) card.restoreLibraryCard?.();
      }
      renderedWindowKey = windowKey;
      pumpVisiblePosters();
    }
    summary.textContent = loading ? "正在读取本地片库…" : `已载入 ${items.length} 条；页面仅保留 ${renderedItemCount} 个可见卡片。`;
    sentinel.hidden = !nextCursor || loading;
  }

  function scheduleWindowRender() {
    if (rafId !== null || disposed || suspended) return;
    rafId = requestFrame(() => {
      rafId = null;
      renderWindow();
    });
  }

  function reportScrollPosition() {
    const scrollTop = Math.max(0, Math.floor(viewportScrollTop()));
    if (scrollTop === lastReportedScrollTop) return;
    lastReportedScrollTop = scrollTop;
    onScrollChange(scrollTop);
  }

  function scheduleScrollReport() {
    if (typeof setTimer !== "function") {
      reportScrollPosition();
      return;
    }
    if (scrollReportTimer !== null && typeof clearTimer === "function") clearTimer(scrollReportTimer);
    scrollReportTimer = setTimer(() => {
      scrollReportTimer = null;
      if (!disposed) reportScrollPosition();
    }, 120);
  }

  function onViewportScroll() {
    if (suspended) return;
    scheduleWindowRender();
    scheduleScrollReport();
  }

  function onResize() {
    if (disposed || suspended) return;
    const oldColumns = currentColumns || columnsFor(Number(viewport.clientWidth) || 0);
    pendingAnchorIndex = items.length
      ? Math.min(items.length - 1, Math.max(0, Math.floor(viewportScrollTop() / ROW_HEIGHT) * oldColumns))
      : 0;
    scheduleWindowRender();
  }

  if (usesPageScroll) windowTarget.addEventListener?.("scroll", onViewportScroll, { passive: true });
  else viewport.addEventListener("scroll", onViewportScroll);

  function disconnectViewportObservers() {
    observer?.disconnect?.();
    observer = null;
    resizeObserver?.disconnect?.();
    resizeObserver = null;
    if (usingWindowResize) windowTarget?.removeEventListener?.("resize", onResize);
    usingWindowResize = false;
  }

  function connectViewportObservers() {
    if (disposed || suspended) return;
    resizeObserver = createResizeObserver?.(onResize) || null;
    if (resizeObserver) resizeObserver.observe?.(viewport);
    else if (windowTarget?.addEventListener) {
      windowTarget.addEventListener("resize", onResize);
      usingWindowResize = true;
    }
    observer = createObserver((entries) => {
      if (!suspended && entries.some((entry) => entry?.isIntersecting)) void loadPage();
    });
    observer?.observe?.(sentinel);
  }

  async function loadPage({ reset = false } = {}) {
    if (disposed || suspended || loading || (!reset && !nextCursor)) return null;
    const requestGeneration = generation;
    const cursor = reset ? null : nextCursor;
    if (cursor && (inFlightCursors.has(cursor) || seenCursors.has(cursor))) {
      nextCursor = null;
      renderWindow();
      return null;
    }
    if (cursor) inFlightCursors.add(cursor);
    const controller = new AbortController();
    activeFetch?.abort();
    activeFetch = controller;
    loading = true;
    renderWindow();
    const query = new URLSearchParams({ state, limit: String(PAGE_LIMIT) });
    if (cursor) query.set("cursor", cursor);
    try {
      const payload = await fetchJson(`/api/v2/library?${query.toString()}`, { signal: controller.signal });
      if (disposed || controller.signal.aborted || generation !== requestGeneration) return null;
      const incoming = Array.isArray(payload?.items) ? payload.items : [];
      updateCounts(payload?.counts);
      const merged = reset ? [] : [...items];
      const seen = new Set(merged.map((item) => safeItemKey(item?.item_key)).filter(Boolean));
      let addedCount = 0;
      for (const item of incoming) {
        const key = safeItemKey(item?.item_key);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        merged.push(item);
        addedCount += 1;
      }
      items = merged;
      itemsVersion += 1;
      pruneCardCache();
      if (cursor) seenCursors.add(cursor);
      const candidateCursor = typeof payload?.next_cursor === "string" && payload.next_cursor ? payload.next_cursor : null;
      nextCursor = candidateCursor && !seenCursors.has(candidateCursor)
        ? candidateCursor
        : null;
      if (candidateCursor === cursor && addedCount === 0) nextCursor = null;
      return payload;
    } catch (error) {
      if (cursor && generation === requestGeneration && !disposed) inFlightCursors.delete(cursor);
      if (controller.signal.aborted || disposed || generation !== requestGeneration) return null;
      summary.textContent = "片库暂时无法读取，请稍后重试。";
      return null;
    } finally {
      if (cursor) inFlightCursors.delete(cursor);
      if (activeFetch === controller) activeFetch = null;
      if (!disposed && generation === requestGeneration) {
        loading = false;
        renderWindow();
      }
    }
  }

  function reset(nextState, { reportScroll = true } = {}) {
    generation += 1;
    activeFetch?.abort();
    activeFetch = null;
    loading = false;
    state = FILTER_KEYS.has(nextState) ? nextState : "all";
    items = [];
    itemsVersion += 1;
    renderedWindowKey = "";
    for (const cached of cardCache.values()) disposeCardCacheEntry(cached);
    cardCache.clear();
    nextCursor = null;
    inFlightCursors.clear();
    seenCursors.clear();
    clearQueuedDetailWarm();
    setViewportScrollTop(0);
    lastReportedScrollTop = 0;
    if (reportScroll) onScrollChange(0);
    updateFilterButtons();
    renderWindow();
  }

  async function mount(initial = {}) {
    reset(initial.state, { reportScroll: false });
    const payload = await loadPage({ reset: true });
    const restoredScrollTop = Number.isFinite(initial.scrollTop) && initial.scrollTop >= 0 ? Math.floor(initial.scrollTop) : 0;
    const viewportHeight = viewportVisibleHeight();
    const requiredVirtualHeight = restoredScrollTop + viewportHeight;
    while (!disposed && restoredScrollTop > 0 && nextCursor) {
      const columns = columnsFor(Number(viewport.clientWidth) || 0);
      const virtualHeight = Math.ceil(items.length / columns) * ROW_HEIGHT;
      if (virtualHeight >= requiredVirtualHeight) break;
      const previousCount = items.length;
      const previousCursor = nextCursor;
      await loadPage();
      if (items.length <= previousCount || nextCursor === previousCursor) break;
    }
    if (!disposed && restoredScrollTop > 0) {
      setViewportScrollTop(restoredScrollTop);
      renderWindow();
    }
    lastReportedScrollTop = Math.max(0, Math.floor(viewportScrollTop()));
    connectViewportObservers();
    return payload;
  }

  function suspend() {
    if (disposed || suspended) return false;
    reportScrollPosition();
    suspended = true;
    if (typeof clearTimer === "function") {
      for (const timer of posterPollTimers.values()) clearTimer(timer);
    }
    posterPollTimers.clear();
    generation += 1;
    activeFetch?.abort();
    activeFetch = null;
    loading = false;
    inFlightCursors.clear();
    disconnectViewportObservers();
    if (rafId !== null) cancelFrame(rafId);
    rafId = null;
    pendingAnchorIndex = null;
    renderWindow();
    return true;
  }

  function resume({ scrollTop = lastReportedScrollTop } = {}) {
    if (disposed) return false;
    const restoredScrollTop = Number.isFinite(scrollTop) && scrollTop >= 0 ? Math.floor(scrollTop) : 0;
    suspended = false;
    for (const [key, jobId] of posterPollJobs) schedulePosterPoll(key, jobId);
    pendingAnchorIndex = null;
    currentColumns = columnsFor(Number(viewport.clientWidth) || 0);
    setViewportScrollTop(restoredScrollTop);
    lastReportedScrollTop = Math.max(0, Math.floor(viewportScrollTop()));
    renderedWindowKey = "";
    renderWindow();
    if (rafId !== null) cancelFrame(rafId);
    rafId = requestFrame(() => {
      rafId = null;
      if (disposed || suspended) return;
      pendingAnchorIndex = null;
      currentColumns = columnsFor(Number(viewport.clientWidth) || 0);
      setViewportScrollTop(restoredScrollTop);
      lastReportedScrollTop = Math.max(0, Math.floor(viewportScrollTop()));
      renderedWindowKey = "";
      renderWindow();
    });
    connectViewportObservers();
    return true;
  }

  function setFilter(nextState) {
    const normalized = FILTER_KEYS.has(nextState) ? nextState : "all";
    if (normalized === state && items.length) return Promise.resolve(null);
    reset(normalized);
    onFilterChange(normalized);
    return loadPage({ reset: true });
  }

  function dispose() {
    if (disposed) return;
    if (scrollReportTimer !== null && typeof clearTimer === "function") clearTimer(scrollReportTimer);
    scrollReportTimer = null;
    reportScrollPosition();
    disposed = true;
    generation += 1;
    activeFetch?.abort();
    activeFetch = null;
    disconnectViewportObservers();
    if (usesPageScroll) windowTarget?.removeEventListener?.("scroll", onViewportScroll);
    else viewport.removeEventListener("scroll", onViewportScroll);
    if (rafId !== null) cancelFrame(rafId);
    rafId = null;
    if (mediaRefreshTimer !== null && typeof clearTimer === "function") clearTimer(mediaRefreshTimer);
    mediaRefreshTimer = null;
    pendingMediaRefreshKeys.clear();
    visiblePosterItems = [];
    for (const controller of mediaRefreshControllers) controller.abort();
    mediaRefreshControllers.clear();
    if (typeof clearTimer === "function") {
      for (const timer of posterPollTimers.values()) clearTimer(timer);
    }
    posterPollTimers.clear();
    posterPollJobs.clear();
    clearQueuedDetailWarm();
    for (const cached of cardCache.values()) disposeCardCacheEntry(cached);
    cardCache.clear();
    renderedWindowKey = "";
  }

  return {
    mount,
    suspend,
    resume,
    setFilter,
    loadNext: () => loadPage(),
    dispose,
    snapshot: () => ({
      state,
      itemCount: items.length,
      itemKeys: items.map((item) => safeItemKey(item?.item_key)).filter(Boolean),
      nextCursor,
      renderedItemCount,
      columns: currentColumns,
      anchorItemKey,
      topSpacer: topSpacerHeight,
      bottomSpacer: bottomSpacerHeight,
      counts: { ...counts },
      activePosterJobs: activePosterKeys.size,
      activeMetadataJobs: 0,
      activeDetailWarms: activeDetailWarmKeys.size,
      queuedDetailWarms: detailWarmQueue.length,
      cachedCardCount: cardCache.size,
      stillRailPositions: Object.fromEntries(stillRailPositions),
      scrollTop: Math.max(0, Math.floor(viewportScrollTop())),
      suspended,
      disposed,
    }),
  };
}

let activeController = null;

export function renderLibrary(root, options = {}) {
  activeController?.dispose();
  const controller = createLibraryController({
    root,
    ...options,
    postJson: options.postJson || postV2,
    setTimer: options.setTimer || ((callback, delay) => setTimeout(callback, delay)),
    clearTimer: options.clearTimer || ((id) => clearTimeout(id)),
  });
  activeController = controller;
  controller.ready = controller.mount(options.filters || {});
  return controller;
}

export function destroyLibrary() {
  activeController?.dispose();
  activeController = null;
}
