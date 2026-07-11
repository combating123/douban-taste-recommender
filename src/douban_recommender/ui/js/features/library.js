import { renderMediaFrame } from "../components/media-frame.js";
import { getV2 } from "../core/api.js";
import { adaptCatalogMedia } from "../core/media.js";

const FILTERS = Object.freeze([
  ["all", "全部"],
  ["watched", "看过"],
  ["wish", "想看"],
  ["candidate", "候选"],
]);
const FILTER_KEYS = new Set(FILTERS.map(([key]) => key));
const PAGE_LIMIT = 24;
const ROW_HEIGHT = 420;
const OVERSCAN_ROWS = 2;

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function safeItemKey(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return /^[A-Za-z0-9:._~-]{1,256}$/.test(text) ? text : "";
}

function columnsFor(width) {
  if (width >= 1200) return 5;
  if (width >= 900) return 4;
  if (width >= 640) return 3;
  if (width >= 420) return 2;
  return 1;
}

function itemCard(item) {
  const card = element("article", "library-card");
  const key = safeItemKey(item?.item_key);
  const link = element("a", "library-card__link");
  link.setAttribute("href", key ? `/title/${encodeURIComponent(key)}` : "/library");
  if (key) link.setAttribute("data-route", "");
  link.append(renderMediaFrame(adaptCatalogMedia(item, "poster")));

  const body = element("div", "library-card__body");
  const title = element("h3", "library-card__title", typeof item?.title === "string" ? item.title : "未命名作品");
  const metadata = [item?.year, item?.media_type, item?.state].filter((value) => value !== null && value !== undefined && String(value).trim()).join(" · ");
  body.append(title, element("p", "library-card__meta", metadata || "本地片库条目"));
  link.append(body);
  card.append(link);
  return card;
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
  createObserver = defaultObserver,
  createResizeObserver = defaultResizeObserver,
  requestFrame = frameScheduler,
  cancelFrame = frameCanceller,
  onFilterChange = () => {},
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
  let observer = null;
  let resizeObserver = null;
  let usingWindowResize = false;
  let rafId = null;
  let pendingAnchorIndex = null;
  let currentColumns = 1;
  let anchorItemKey = "";
  const requestedCursors = new Set();
  const seenCursors = new Set();
  let renderedItemCount = 0;
  let topSpacerHeight = 0;
  let bottomSpacerHeight = 0;

  const section = element("section", "space space--library");
  section.dataset.space = "library";
  const header = element("header", "space-header");
  const headingWrap = element("div", "space-header__copy");
  headingWrap.append(element("p", "eyebrow", "LIBRARY / LOCAL CATALOG"), element("h1", "space-title", "片库"));
  const summary = element("p", "space-summary", "分段筛选本地条目；仅当前可见行进入页面。");
  header.append(headingWrap, summary);

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
  section.append(header, filters, viewport);
  root.replaceChildren(section);

  function updateFilterButtons() {
    for (const [key, button] of filterButtons) button.setAttribute("aria-pressed", String(key === state));
  }

  function renderWindow() {
    if (disposed) return;
    const columns = columnsFor(Number(viewport.clientWidth) || 0);
    if (pendingAnchorIndex !== null && columns !== currentColumns) {
      viewport.scrollTop = Math.floor(pendingAnchorIndex / columns) * ROW_HEIGHT;
    }
    pendingAnchorIndex = null;
    currentColumns = columns;
    const totalRows = Math.ceil(items.length / columns);
    const scrollTop = Math.max(0, Number(viewport.scrollTop) || 0);
    const viewportHeight = Math.max(1, Number(viewport.clientHeight) || 520);
    const firstRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN_ROWS);
    const lastRow = Math.min(totalRows, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN_ROWS);
    const anchorIndex = Math.min(items.length - 1, Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) * columns));
    anchorItemKey = items.length ? safeItemKey(items[anchorIndex]?.item_key) : "";
    topSpacerHeight = firstRow * ROW_HEIGHT;
    bottomSpacerHeight = Math.max(0, (totalRows - lastRow) * ROW_HEIGHT);
    topSpacer.style.height = `${topSpacerHeight}px`;
    bottomSpacer.style.height = `${bottomSpacerHeight}px`;
    rowsHost.replaceChildren();
    renderedItemCount = 0;
    for (let rowIndex = firstRow; rowIndex < lastRow; rowIndex += 1) {
      const row = element("div", "library-row");
      row.dataset.virtualRow = String(rowIndex);
      row.style.setProperty("--library-columns", String(columns));
      const start = rowIndex * columns;
      const rowItems = items.slice(start, start + columns);
      renderedItemCount += rowItems.length;
      row.append(...rowItems.map(itemCard));
      rowsHost.append(row);
    }
    summary.textContent = loading ? "正在读取本地片库…" : `已载入 ${items.length} 条；页面仅保留 ${renderedItemCount} 个可见卡片。`;
    sentinel.hidden = !nextCursor || loading;
  }

  function scheduleWindowRender() {
    if (rafId !== null || disposed) return;
    rafId = requestFrame(() => {
      rafId = null;
      renderWindow();
    });
  }

  function onResize() {
    if (disposed) return;
    const oldColumns = currentColumns || columnsFor(Number(viewport.clientWidth) || 0);
    pendingAnchorIndex = items.length
      ? Math.min(items.length - 1, Math.max(0, Math.floor((Number(viewport.scrollTop) || 0) / ROW_HEIGHT) * oldColumns))
      : 0;
    scheduleWindowRender();
  }

  viewport.addEventListener("scroll", scheduleWindowRender);

  async function loadPage({ reset = false } = {}) {
    if (disposed || loading || (!reset && !nextCursor)) return null;
    const requestGeneration = generation;
    const cursor = reset ? null : nextCursor;
    if (cursor && requestedCursors.has(cursor)) {
      nextCursor = null;
      renderWindow();
      return null;
    }
    if (cursor) requestedCursors.add(cursor);
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
      if (cursor) seenCursors.add(cursor);
      const candidateCursor = typeof payload?.next_cursor === "string" && payload.next_cursor ? payload.next_cursor : null;
      nextCursor = candidateCursor && !requestedCursors.has(candidateCursor) && !seenCursors.has(candidateCursor)
        ? candidateCursor
        : null;
      if (candidateCursor === cursor && addedCount === 0) nextCursor = null;
      return payload;
    } catch (error) {
      if (controller.signal.aborted || disposed || generation !== requestGeneration) return null;
      summary.textContent = "片库暂时无法读取，请稍后重试。";
      return null;
    } finally {
      if (activeFetch === controller) activeFetch = null;
      if (!disposed && generation === requestGeneration) {
        loading = false;
        renderWindow();
      }
    }
  }

  function reset(nextState) {
    generation += 1;
    activeFetch?.abort();
    activeFetch = null;
    loading = false;
    state = FILTER_KEYS.has(nextState) ? nextState : "all";
    items = [];
    nextCursor = null;
    requestedCursors.clear();
    seenCursors.clear();
    viewport.scrollTop = 0;
    updateFilterButtons();
    renderWindow();
  }

  function mount(initial = {}) {
    reset(initial.state);
    observer = createObserver((entries) => {
      if (entries.some((entry) => entry?.isIntersecting)) void loadPage();
    });
    observer?.observe?.(sentinel);
    resizeObserver = createResizeObserver?.(onResize) || null;
    if (resizeObserver) resizeObserver.observe?.(viewport);
    else if (windowTarget?.addEventListener) {
      windowTarget.addEventListener("resize", onResize);
      usingWindowResize = true;
    }
    return loadPage({ reset: true });
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
    disposed = true;
    generation += 1;
    activeFetch?.abort();
    activeFetch = null;
    observer?.disconnect?.();
    observer = null;
    resizeObserver?.disconnect?.();
    resizeObserver = null;
    if (usingWindowResize) windowTarget?.removeEventListener?.("resize", onResize);
    usingWindowResize = false;
    viewport.removeEventListener("scroll", scheduleWindowRender);
    if (rafId !== null) cancelFrame(rafId);
    rafId = null;
  }

  return {
    mount,
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
      disposed,
    }),
  };
}

let activeController = null;

export function renderLibrary(root, options = {}) {
  activeController?.dispose();
  const controller = createLibraryController({ root, ...options });
  activeController = controller;
  controller.ready = controller.mount(options.filters || {});
  return controller;
}

export function destroyLibrary() {
  activeController?.dispose();
  activeController = null;
}
