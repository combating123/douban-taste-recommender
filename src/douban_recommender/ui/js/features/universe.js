import { getV2, postV2 } from "../core/api.js";
import { adaptCatalogMedia, preloadLocalMedia } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";
import { displayTitle } from "../components/title-card.js";

const INITIAL_LIMIT = 9;
const MAX_NODES = 36;
const FOCUS_TWEEN_MS = 260;
const SAFE_NODE_ID = /^[A-Za-z0-9:._~-]{1,256}$/;
export const LAB_SEARCH_DEBOUNCE_MS = 420;
const LAB_SEARCH_LIMIT = 4;
const BLEND_LIMIT = 12;
const DEFAULT_LEFT_WEIGHT = 0.5;
const MOOD_AXIS_DEFINITIONS = Object.freeze([
  { key: "pace_axis", label: "节奏", low: "缓慢", high: "紧凑" },
  { key: "atmosphere_axis", label: "氛围", low: "明快", high: "阴郁" },
  { key: "cognitive_load_axis", label: "脑力消耗", low: "放松", high: "极度烧脑" },
  { key: "emotional_intensity_axis", label: "情绪强度", low: "克制", high: "强烈" },
]);

let labSearchSequence = 0;
let blendRequestSequence = 0;

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function listValue(value) {
  return Array.isArray(value) ? value.filter((entry) => typeof entry === "string" && entry.trim()) : [];
}

function finiteScore(value) {
  const score = Number(value);
  return Number.isFinite(score) ? Math.max(0, score) : 0;
}

function visualScore(value) {
  const score = finiteScore(value);
  return Math.max(0, Math.min(1, score <= 1 ? score : score / 10));
}

function nodeId(value) {
  const clean = textValue(value);
  return SAFE_NODE_ID.test(clean) ? clean : "";
}

function clampedNumber(value, minimum, maximum, fallback = 0) {
  const parsed = Number(value);
  const finite = Number.isFinite(parsed) ? parsed : fallback;
  return Math.max(minimum, Math.min(maximum, finite));
}

export function buildBlendPayload({ leftId, rightId, leftWeight = DEFAULT_LEFT_WEIGHT, axes = {}, limit = BLEND_LIMIT } = {}) {
  const left = nodeId(leftId);
  const right = nodeId(rightId);
  if (!left || !right) throw new TypeError("Blend sources require two stable work IDs");
  if (left === right) throw new RangeError("Blend sources must be different works");
  const intent = {};
  for (const axis of MOOD_AXIS_DEFINITIONS) {
    intent[axis.key] = Number(clampedNumber(axes?.[axis.key], -1, 1, 0).toFixed(2));
  }
  return {
    left,
    right,
    left_weight: Number(clampedNumber(leftWeight, 0.05, 0.95, DEFAULT_LEFT_WEIGHT).toFixed(2)),
    intent,
    limit: Math.round(clampedNumber(limit, 1, 30, BLEND_LIMIT)),
  };
}

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function toggleClass(node, className, enabled) {
  if (!node) return;
  const names = new Set(String(node.className || "").split(/\s+/).filter(Boolean));
  if (enabled) names.add(className);
  else names.delete(className);
  node.className = [...names].join(" ");
}

function edgeKey(source, target) {
  return [source, target].sort().join("\u0000");
}

function normalizeNode(raw) {
  const id = nodeId(raw?.id);
  if (!id) return null;
  return {
    ...raw,
    id,
    title: textValue(raw?.title, "未命名作品"),
    media_type: textValue(raw?.media_type, "作品"),
    year: Number.isFinite(Number(raw?.year)) ? Number(raw.year) : null,
  };
}

function normalizeEdge(raw) {
  const source = nodeId(raw?.source);
  const target = nodeId(raw?.target);
  if (!source || !target || source === target) return null;
  const listedReasons = listValue(raw?.reasons);
  const reason = textValue(raw?.reason);
  const reasons = [...new Set([reason, ...listedReasons].filter(Boolean))];
  return {
    source,
    target,
    score: finiteScore(raw?.score),
    reason,
    reasons: reasons.length ? reasons : ["本地目录关联"],
  };
}

function requestJson(path, options = {}) {
  return getV2(path, options);
}

let dependencies = {
  api: { getV2, postV2 },
  fetchJson: requestJson,
  preloadMedia: preloadLocalMedia,
  setTimer: (callback, delay) => globalThis.setTimeout?.(callback, delay),
  clearTimer: (timer) => globalThis.clearTimeout?.(timer),
  onContextChange: () => {},
  onRecommendNode: () => {},
};
let activeUniverse = null;
let activeExplorationLab = null;
let lifecycleGeneration = 0;
let universeContainer = null;

export function configureUniverse(options = {}) {
  const api = { ...dependencies.api, ...(options.api || {}) };
  dependencies = {
    ...dependencies,
    ...options,
    api,
    fetchJson: options.fetchJson || options.api?.getV2 || dependencies.fetchJson,
    preloadMedia: options.preloadMedia || dependencies.preloadMedia,
    setTimer: options.setTimer || dependencies.setTimer,
    clearTimer: options.clearTimer || dependencies.clearTimer,
    onContextChange: options.onContextChange || dependencies.onContextChange,
    onRecommendNode: options.onRecommendNode || dependencies.onRecommendNode,
  };
}

function nodeScore(state, id) {
  let score = 0;
  for (const edge of state.edgesByKey.values()) {
    if (edge.source === id || edge.target === id) score = Math.max(score, edge.score);
  }
  return score;
}

function enforceCap(state, preferredFocus) {
  if (state.nodesById.size <= MAX_NODES) return false;
  const keep = [...state.nodesById.keys()].sort((left, right) => {
    if (left === preferredFocus) return -1;
    if (right === preferredFocus) return 1;
    if (left === state.focusedId) return -1;
    if (right === state.focusedId) return 1;
    const scoreDifference = nodeScore(state, right) - nodeScore(state, left);
    return scoreDifference || left.localeCompare(right);
  }).slice(0, MAX_NODES);
  const keepIds = new Set(keep);
  for (const id of [...state.nodesById.keys()]) {
    if (!keepIds.has(id)) state.nodesById.delete(id);
  }
  for (const [key, edge] of [...state.edgesByKey.entries()]) {
    if (!keepIds.has(edge.source) || !keepIds.has(edge.target)) state.edgesByKey.delete(key);
  }
  state.limitMessage = `口味宇宙最多保留 ${MAX_NODES} 个作品；已优先保留当前焦点与高分邻居。`;
  return true;
}

function mergeGraph(state, graph, { initial = false } = {}) {
  const focus = nodeId(graph?.focus_id) || state.focusedId;
  const incomingNodes = (Array.isArray(graph?.nodes) ? graph.nodes : []).map(normalizeNode).filter(Boolean);
  const boundedNodes = initial
    ? [incomingNodes.find((node) => node.id === focus), ...incomingNodes.filter((node) => node.id !== focus)].filter(Boolean).slice(0, INITIAL_LIMIT)
    : incomingNodes;
  for (const node of boundedNodes) state.nodesById.set(node.id, node);
  hydrateExplorationSeed(state, boundedNodes);

  for (const rawEdge of Array.isArray(graph?.edges) ? graph.edges : []) {
    const edge = normalizeEdge(rawEdge);
    if (!edge || !state.nodesById.has(edge.source) || !state.nodesById.has(edge.target)) continue;
    const key = edgeKey(edge.source, edge.target);
    const existing = state.edgesByKey.get(key);
    if (!existing || edge.score >= existing.score) state.edgesByKey.set(key, edge);
  }
  enforceCap(state, focus);
  if (focus && state.nodesById.has(focus)) state.focusedId = focus;
}

function stableAngle(id) {
  let hash = 0;
  for (const character of id) hash = ((hash * 31) + character.charCodeAt(0)) >>> 0;
  return (hash % 360) * Math.PI / 180;
}

function updateLayout(state) {
  const ids = [...state.nodesById.keys()];
  const focus = state.focusedId;
  state.positions.clear();
  if (focus && state.nodesById.has(focus)) state.positions.set(focus, { x: 0, y: 0 });
  const others = ids.filter((id) => id !== focus);
  others.forEach((id, index) => {
    const ring = 1 + Math.floor(index / 8);
    const ringIndex = index % 8;
    const angle = (ringIndex / Math.min(8, others.length || 1)) * Math.PI * 2 + stableAngle(id) * 0.18;
    const radius = 128 + ring * 82;
    state.positions.set(id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  });
}

function scoreLabel(score) {
  const value = finiteScore(score);
  if (value <= 1) return `${Math.round(value * 100)}%`;
  return value.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
}

function nodeTitle(state, id) {
  return state.nodesById.get(id)?.title || id;
}

function titleRoute(id) {
  const stableId = nodeId(id);
  return stableId ? `/title/${encodeURIComponent(stableId)}` : "";
}

function detailAction(id, className) {
  const link = element("a", className, "查看详情");
  link.setAttribute("href", titleRoute(id));
  link.setAttribute("data-route", "");
  return link;
}

function recommendAction(state, id, className) {
  const button = element("button", className, "带入今晚推荐");
  button.type = "button";
  button.addEventListener("click", () => {
    const node = state.nodesById.get(id);
    if (!node) return;
    try {
      void Promise.resolve(dependencies.onRecommendNode({ id: node.id, title: node.title })).catch(() => {});
    } catch {
      // Injected UI callbacks are isolated from the event loop.
    }
  });
  return button;
}

function expandNodeFromUi(id) {
  void expandNode(id).catch(() => {});
}

function discoveryItemId(item = {}) {
  return nodeId(item?.id) || nodeId(item?.item_key) || nodeId(item?.catalog_id);
}

function normalizeDiscoveryItem(item = {}) {
  const id = discoveryItemId(item);
  if (!id) return null;
  return {
    ...item,
    id,
    item_key: nodeId(item?.item_key) || id,
    title: textValue(item?.title, "未命名作品"),
    media_type: textValue(item?.media_type) || textValue(item?.format) || "作品",
    year: Number.isFinite(Number(item?.year)) && Number(item.year) > 0 ? Math.floor(Number(item.year)) : null,
  };
}

function discoveryBadge(item = {}) {
  const provided = item?.media_badge && typeof item.media_badge === "object" ? item.media_badge : {};
  const rawType = `${textValue(item?.media_type)} ${textValue(item?.format)}`.toLowerCase();
  if (textValue(provided.label)) {
    return {
      label: textValue(provided.label),
      tone: ["amber", "violet", "cyan", "slate"].includes(textValue(provided.tone)) ? textValue(provided.tone) : "slate",
    };
  }
  if (/(动画|动漫|anime)/u.test(rawType)) return { label: "动画", tone: "cyan" };
  if (/(电视剧|剧集|series|tv)/u.test(rawType)) return { label: "剧集", tone: "violet" };
  if (/(电影|movie|film)/u.test(rawType)) return { label: "电影", tone: "amber" };
  return { label: textValue(item?.media_type, "作品"), tone: "slate" };
}

function discoveryMeta(item = {}) {
  const parts = [];
  if (item.year) parts.push(String(item.year));
  const country = Array.isArray(item?.countries) ? item.countries.map((value) => textValue(value)).find(Boolean) : "";
  if (country) parts.push(country);
  const rating = Number(item?.douban_rating);
  if (Number.isFinite(rating) && rating > 0) parts.push(`豆瓣 ${rating.toFixed(1)}`);
  return parts.join(" · ") || "年份与地区待补";
}

function setLabStatus(state, message, tone = "neutral") {
  if (!state?.status) return;
  state.status.dataset.tone = tone;
  state.status.textContent = message;
}

function setSlotStatus(slot, message = "", tone = "neutral") {
  slot.status.dataset.tone = tone;
  slot.status.textContent = message;
  slot.status.hidden = !message;
}

function warmPoster(item, owner) {
  const media = adaptCatalogMedia(item, "poster");
  if (!media.localUrl || typeof dependencies.preloadMedia !== "function") return;
  void Promise.resolve(dependencies.preloadMedia(media.localUrl, owner)).catch(() => {});
}

function axisDescription(definition, value) {
  const amount = clampedNumber(value, -1, 1, 0);
  if (Math.abs(amount) < 0.05) return "平衡";
  const label = amount < 0 ? definition.low : definition.high;
  return `${label} ${Math.round(Math.abs(amount) * 100)}%`;
}

function currentAxes(state) {
  const values = {};
  for (const definition of MOOD_AXIS_DEFINITIONS) {
    const control = state.axes.get(definition.key);
    values[definition.key] = Number((clampedNumber(control?.input?.value, -100, 100, 0) / 100).toFixed(2));
  }
  return values;
}

function clearBlendResults(state) {
  state.results.hidden = true;
  state.resultsRail.replaceChildren();
  state.resultsTitle.textContent = "融合结果";
}

function cancelBlendRequest(state) {
  state.blendController?.abort();
  state.blendController = null;
  state.loading = false;
}

function syncBlendAvailability(state) {
  const ready = Boolean(state.slots.left?.selected && state.slots.right?.selected);
  state.submit.disabled = !ready || state.loading;
  state.submit.setAttribute("aria-disabled", state.submit.disabled ? "true" : "false");
  toggleClass(state.stage, "is-ready", ready);
  if (!ready && !state.loading) {
    const missing = !state.slots.left?.selected && !state.slots.right?.selected
      ? "先为 A 与 B 各选择一部作品，再让两个世界发生碰撞。"
      : `还需要选择作品 ${state.slots.left?.selected ? "B" : "A"}。`;
    setLabStatus(state, missing);
  }
}

function renderBlendSelection(state, slot) {
  slot.selection.replaceChildren();
  const item = slot.selected;
  if (!item) {
    const empty = element("div", "blend-source__empty");
    empty.append(
      element("span", "blend-source__empty-glyph", slot.label),
      element("strong", "blend-source__empty-title", `等待作品 ${slot.label}`),
      element("span", "blend-source__empty-copy", "输入片名，点击或拖入候选作品"),
    );
    slot.selection.append(empty);
    toggleClass(slot.root, "has-selection", false);
    return;
  }

  toggleClass(slot.root, "has-selection", true);
  const card = element("article", "blend-source-card");
  card.draggable = true;
  card.dataset.itemId = item.id;
  card.dataset.side = slot.side;
  const poster = element("div", "blend-source-card__poster");
  poster.append(renderMediaFrame(adaptCatalogMedia(item, "poster")));
  const copy = element("div", "blend-source-card__copy");
  const badge = discoveryBadge(item);
  const badgeNode = element("span", "blend-media-badge", badge.label);
  badgeNode.dataset.tone = badge.tone;
  copy.append(
    badgeNode,
    element("strong", "blend-source-card__title", displayTitle(item)),
    element("span", "blend-source-card__meta", discoveryMeta(item)),
  );
  const clear = element("button", "blend-source-card__clear", "更换");
  clear.type = "button";
  clear.setAttribute("aria-label", `更换作品 ${slot.label}《${displayTitle(item)}》`);
  clear.addEventListener("click", () => {
    slot.selected = null;
    slot.input.value = "";
    cancelBlendRequest(state);
    clearBlendResults(state);
    renderBlendSelection(state, slot);
    syncBlendAvailability(state);
    slot.input.focus?.();
  });
  card.addEventListener("pointerenter", () => warmPoster(item, card));
  card.addEventListener("focusin", () => warmPoster(item, card));
  card.addEventListener("dragstart", (event) => {
    state.draggedItem = item;
    state.draggedFrom = slot.side;
    event?.dataTransfer?.setData?.("text/plain", item.id);
    if (event?.dataTransfer) event.dataTransfer.effectAllowed = "copyMove";
    toggleClass(state.stage, "is-dragging", true);
  });
  card.addEventListener("dragend", () => {
    state.draggedItem = null;
    state.draggedFrom = "";
    toggleClass(state.stage, "is-dragging", false);
  });
  card.append(poster, copy, clear);
  slot.selection.append(card);
}

function selectBlendSource(state, slot, rawItem, { autoBlend = true } = {}) {
  const item = normalizeDiscoveryItem(rawItem);
  if (!item) return false;
  const other = state.slots[slot.side === "left" ? "right" : "left"];
  if (other?.selected?.id === item.id) {
    setSlotStatus(slot, `《${displayTitle(item)}》已经在作品 ${other.label} 中，请选择另一部作品。`, "error");
    setLabStatus(state, "碰撞需要两个不同的作品世界。", "error");
    return false;
  }
  cancelBlendRequest(state);
  slot.selected = item;
  slot.input.value = displayTitle(item);
  slot.candidates = [];
  slot.lastQuery = displayTitle(item);
  renderBlendCandidates(state, slot);
  renderBlendSelection(state, slot);
  setSlotStatus(slot, `已选择${discoveryBadge(item).label}《${displayTitle(item)}》`, "success");
  clearBlendResults(state);
  syncBlendAvailability(state);
  warmPoster(item, slot.selection);
  if (autoBlend && state.slots.left?.selected && state.slots.right?.selected) void requestBlend(state);
  return true;
}

function attachCandidateDrag(state, slot, card, item) {
  card.draggable = true;
  card.addEventListener("dragstart", (event) => {
    state.draggedItem = item;
    state.draggedFrom = slot.side;
    event?.dataTransfer?.setData?.("text/plain", item.id);
    if (event?.dataTransfer) event.dataTransfer.effectAllowed = "copy";
    toggleClass(state.stage, "is-dragging", true);
  });
  card.addEventListener("dragend", () => {
    state.draggedItem = null;
    state.draggedFrom = "";
    toggleClass(state.stage, "is-dragging", false);
  });
}

function renderBlendCandidates(state, slot) {
  slot.candidateList.replaceChildren();
  const candidates = Array.isArray(slot.candidates) ? slot.candidates.slice(0, LAB_SEARCH_LIMIT) : [];
  slot.candidateTray.hidden = candidates.length === 0;
  if (!candidates.length) return;
  const other = state.slots[slot.side === "left" ? "right" : "left"];
  for (const item of candidates) {
    const badge = discoveryBadge(item);
    const duplicate = other?.selected?.id === item.id;
    const card = element("button", "blend-candidate");
    card.type = "button";
    card.dataset.itemId = item.id;
    card.dataset.tone = badge.tone;
    card.disabled = duplicate;
    card.setAttribute("aria-disabled", duplicate ? "true" : "false");
    card.setAttribute("aria-label", duplicate
      ? `《${displayTitle(item)}》已用于作品 ${other.label}`
      : `选为作品 ${slot.label}：${badge.label}《${displayTitle(item)}》`);
    const poster = element("span", "blend-candidate__poster");
    poster.append(renderMediaFrame(adaptCatalogMedia(item, "poster")));
    const copy = element("span", "blend-candidate__copy");
    copy.append(
      element("strong", "blend-candidate__title", displayTitle(item)),
      element("span", "blend-candidate__meta", discoveryMeta(item)),
    );
    const badgeNode = element("span", "blend-media-badge", badge.label);
    badgeNode.dataset.tone = badge.tone;
    card.append(poster, copy, badgeNode);
    card.addEventListener("pointerenter", () => warmPoster(item, card));
    card.addEventListener("focus", () => warmPoster(item, card));
    card.addEventListener("click", () => selectBlendSource(state, slot, item));
    attachCandidateDrag(state, slot, card, item);
    slot.candidateList.append(card);
  }
}

async function searchBlendSlot(state, slot) {
  const query = textValue(slot.input.value);
  if (!query || state.disposed || typeof dependencies.api?.getV2 !== "function") {
    slot.candidates = [];
    renderBlendCandidates(state, slot);
    setSlotStatus(slot, "");
    return [];
  }
  slot.searchController?.abort();
  const controller = new AbortController();
  const sequence = ++labSearchSequence;
  slot.searchController = controller;
  slot.searchSequence = sequence;
  slot.lastQuery = query;
  setSlotStatus(slot, `正在辨认“${query}”的媒介与版本…`, "busy");
  try {
    const response = await dependencies.api.getV2(
      `/api/v2/titles/search?q=${encodeURIComponent(query)}&limit=${LAB_SEARCH_LIMIT}`,
      { signal: controller.signal },
    );
    if (state.disposed || controller.signal.aborted || slot.searchSequence !== sequence) return slot.candidates;
    slot.candidates = (Array.isArray(response?.items) ? response.items : []).map(normalizeDiscoveryItem).filter(Boolean).slice(0, LAB_SEARCH_LIMIT);
    renderBlendCandidates(state, slot);
    if (slot.candidates.length > 1) setSlotStatus(slot, `找到 ${slot.candidates.length} 个候选，用媒介角标与年份确认版本。`);
    else if (slot.candidates.length === 1) setSlotStatus(slot, "找到 1 个可用作品，回车或点击即可选中。", "success");
    else setSlotStatus(slot, "没有找到可碰撞的本地作品，请尝试更完整的片名。", "error");
    return slot.candidates;
  } catch (error) {
    if (error?.name === "AbortError" || state.disposed || slot.searchSequence !== sequence) return slot.candidates;
    slot.candidates = [];
    renderBlendCandidates(state, slot);
    setSlotStatus(slot, "作品检索暂时不可用；当前已选作品不会丢失。", "error");
    return [];
  } finally {
    if (slot.searchController === controller) slot.searchController = null;
  }
}

function scheduleBlendSlotSearch(state, slot) {
  if (slot.searchTimer !== null) dependencies.clearTimer?.(slot.searchTimer);
  slot.searchTimer = null;
  if (slot.composing) return;
  const query = textValue(slot.input.value);
  if (!query) {
    slot.candidates = [];
    slot.lastQuery = "";
    renderBlendCandidates(state, slot);
    setSlotStatus(slot, "");
    return;
  }
  slot.searchTimer = dependencies.setTimer?.(() => {
    slot.searchTimer = null;
    void searchBlendSlot(state, slot);
  }, LAB_SEARCH_DEBOUNCE_MS) ?? null;
}

function createBlendSlot(state, side, label) {
  const root = element("section", `blend-source blend-source--${side}`);
  root.dataset.side = side;
  const heading = element("div", "blend-source__heading");
  heading.append(
    element("span", "blend-source__index", label),
    element("div", "blend-source__heading-copy"),
  );
  heading.children?.[1]?.append?.(
    element("strong", "blend-source__title", `作品 ${label}`),
    element("span", "blend-source__hint", side === "left" ? "世界观、题材与叙事骨架" : "情绪、关系与审美质感"),
  );
  const search = element("div", "blend-source__search");
  const input = document.createElement("input");
  input.className = "blend-source__input";
  input.type = "search";
  input.autocomplete = "off";
  input.maxLength = 80;
  input.placeholder = side === "left" ? "搜索第一部作品" : "搜索第二部作品";
  input.setAttribute("aria-label", `搜索作品 ${label}`);
  const searchHint = element("span", "blend-source__search-hint", "停顿 420ms 自动辨认");
  search.append(input, searchHint);
  const status = element("p", "blend-source__status");
  status.setAttribute("aria-live", "polite");
  status.hidden = true;
  const selection = element("div", "blend-source__selection");
  const candidateTray = element("div", "blend-source__candidates");
  candidateTray.hidden = true;
  const candidateList = element("div", "blend-source__candidate-list");
  candidateTray.append(candidateList);
  root.append(heading, search, status, selection, candidateTray);

  const slot = {
    side, label, root, input, status, selection, candidateTray, candidateList,
    selected: null, candidates: [], lastQuery: "", composing: false,
    searchTimer: null, searchController: null, searchSequence: 0,
  };
  renderBlendSelection(state, slot);
  input.addEventListener("compositionstart", () => { slot.composing = true; });
  input.addEventListener("compositionend", () => {
    slot.composing = false;
    scheduleBlendSlotSearch(state, slot);
  });
  input.addEventListener("input", () => {
    if (slot.selected && textValue(input.value) !== displayTitle(slot.selected)) {
      cancelBlendRequest(state);
      slot.selected = null;
      clearBlendResults(state);
      renderBlendSelection(state, slot);
      syncBlendAvailability(state);
    }
    if (!slot.composing) scheduleBlendSlotSearch(state, slot);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing || slot.composing) return;
    event.preventDefault?.();
    if (slot.candidates[0]) {
      selectBlendSource(state, slot, slot.candidates[0]);
      return;
    }
    void searchBlendSlot(state, slot).then((items) => {
      if (items?.[0]) selectBlendSource(state, slot, items[0]);
    });
  });
  root.addEventListener("dragover", (event) => {
    if (!state.draggedItem) return;
    event.preventDefault?.();
    if (event?.dataTransfer) event.dataTransfer.dropEffect = "copy";
    toggleClass(root, "is-drop-target", true);
  });
  root.addEventListener("dragleave", () => toggleClass(root, "is-drop-target", false));
  root.addEventListener("drop", (event) => {
    event.preventDefault?.();
    toggleClass(root, "is-drop-target", false);
    if (state.draggedItem) selectBlendSource(state, slot, state.draggedItem);
  });
  return slot;
}

function createMoodAxis(state, definition) {
  const wrapper = element("label", "mood-axis");
  const heading = element("span", "mood-axis__heading");
  const name = element("strong", "mood-axis__name", definition.label);
  const output = element("span", "mood-axis__value", "平衡");
  heading.append(name, output);
  const input = document.createElement("input");
  input.className = "mood-axis__input";
  input.type = "range";
  input.min = "-100";
  input.max = "100";
  input.step = "5";
  input.value = "0";
  input.setAttribute("aria-label", `${definition.label}：${definition.low}到${definition.high}`);
  const scale = element("span", "mood-axis__scale");
  scale.append(element("span", "mood-axis__low", definition.low), element("span", "mood-axis__high", definition.high));
  wrapper.append(heading, input, scale);
  input.addEventListener("input", () => {
    output.textContent = axisDescription(definition, Number(input.value) / 100);
    scheduleBlend(state);
  });
  return { wrapper, input, output, definition };
}

function renderBlendLoading(state) {
  state.results.hidden = false;
  state.resultsTitle.textContent = "正在计算两个世界的交集";
  state.resultsRail.replaceChildren();
  for (let index = 0; index < 4; index += 1) {
    const skeleton = element("article", "blend-result-card blend-result-card--loading");
    skeleton.setAttribute("aria-hidden", "true");
    skeleton.append(element("span", "blend-result-card__skeleton-poster"), element("span", "blend-result-card__skeleton-copy"));
    state.resultsRail.append(skeleton);
  }
}

function explanationLine(label, value, fallback) {
  const row = element("p", "blend-result-card__reason");
  row.append(
    element("strong", "blend-result-card__reason-label", label),
    element("span", "blend-result-card__reason-copy", textValue(value, fallback)),
  );
  return row;
}

function renderBlendResults(state, response = {}) {
  const items = (Array.isArray(response?.items) ? response.items : []).map(normalizeDiscoveryItem).filter(Boolean);
  state.results.hidden = false;
  state.resultsRail.replaceChildren();
  const left = state.slots.left.selected;
  const right = state.slots.right.selected;
  const leftWeight = clampedNumber(response?.left_weight, 0.05, 0.95, Number(state.weight.value) / 100);
  const rightWeight = clampedNumber(response?.right_weight, 0.05, 0.95, 1 - leftWeight);
  state.resultsTitle.textContent = items.length
    ? `融合结果 · ${displayTitle(left || {}, "A")} ${Math.round(leftWeight * 100)} / ${displayTitle(right || {}, "B")} ${Math.round(rightWeight * 100)}`
    : "融合结果 · 暂无可用桥梁作品";
  if (!items.length) {
    const empty = element("div", "blend-results__empty");
    empty.append(
      element("strong", "blend-results__empty-title", "这组碰撞暂时没有足够稳定的结果"),
      element("p", "blend-results__empty-copy", "可以减弱某个情绪维度、调整 A/B 比重，或更换其中一部作品。"),
    );
    state.resultsRail.append(empty);
    return;
  }

  for (const item of items) {
    const card = element("article", "blend-result-card");
    const poster = element("a", "blend-result-card__poster");
    poster.setAttribute("href", titleRoute(item.id));
    poster.setAttribute("data-route", "");
    poster.setAttribute("aria-label", `查看《${displayTitle(item)}》详情`);
    poster.append(renderMediaFrame(adaptCatalogMedia(item, "poster")));
    const body = element("div", "blend-result-card__body");
    const kicker = element("div", "blend-result-card__kicker");
    const badge = discoveryBadge(item);
    const badgeNode = element("span", "blend-media-badge", badge.label);
    badgeNode.dataset.tone = badge.tone;
    kicker.append(badgeNode, element("span", "blend-result-card__meta", discoveryMeta(item)));
    const title = element("a", "blend-result-card__title", displayTitle(item));
    title.setAttribute("href", titleRoute(item.id));
    title.setAttribute("data-route", "");
    const explanation = item?.explanation && typeof item.explanation === "object" ? item.explanation : {};
    const reasons = element("div", "blend-result-card__reasons");
    reasons.append(
      explanationLine("来自 A", explanation.from_left, `延续《${displayTitle(left || {}, "作品 A")}》的核心气质`),
      explanationLine("来自 B", explanation.from_right, `保留《${displayTitle(right || {}, "作品 B")}》的观看质感`),
      explanationLine("融合结果", explanation.fusion, `把两个来源的叙事与情绪线索融合到《${displayTitle(item)}》中`),
    );
    body.append(kicker, title, reasons);
    card.append(poster, body);
    card.addEventListener("pointerenter", () => {
      state.root.dataset.activeTone = badge.tone;
      warmPoster(item, card);
    });
    card.addEventListener("focusin", () => {
      state.root.dataset.activeTone = badge.tone;
      warmPoster(item, card);
    });
    state.resultsRail.append(card);
  }
}

async function requestBlend(state) {
  if (state.disposed || !state.slots.left?.selected || !state.slots.right?.selected || typeof dependencies.api?.postV2 !== "function") {
    syncBlendAvailability(state);
    return null;
  }
  state.blendController?.abort();
  const controller = new AbortController();
  const sequence = ++blendRequestSequence;
  state.blendController = controller;
  state.blendSequence = sequence;
  state.loading = true;
  syncBlendAvailability(state);
  renderBlendLoading(state);
  setLabStatus(state, "正在计算语义中点、共同证据与情绪偏移…", "busy");
  try {
    const payload = buildBlendPayload({
      leftId: state.slots.left.selected.id,
      rightId: state.slots.right.selected.id,
      leftWeight: Number(state.weight.value) / 100,
      axes: currentAxes(state),
      limit: BLEND_LIMIT,
    });
    const response = await dependencies.api.postV2("/api/v2/discovery/blend", payload, { signal: controller.signal });
    if (state.disposed || controller.signal.aborted || state.blendSequence !== sequence) return null;
    renderBlendResults(state, response);
    setLabStatus(state, `已找到 ${Array.isArray(response?.items) ? response.items.length : 0} 部桥梁作品；每张卡片都说明 A、B 与融合依据。`, "success");
    return response;
  } catch (error) {
    if (error?.name === "AbortError" || controller.signal.aborted || state.disposed || state.blendSequence !== sequence) return null;
    clearBlendResults(state);
    setLabStatus(state, error?.status === 400
      ? "这两个来源无法直接碰撞，请确认它们不是同一作品。"
      : "融合请求暂时失败；已选作品与调色盘参数均已保留。", "error");
    return null;
  } finally {
    if (state.blendSequence === sequence) {
      state.loading = false;
      if (state.blendController === controller) state.blendController = null;
      syncBlendAvailability(state);
    }
  }
}

function scheduleBlend(state, delay = 220) {
  if (state.blendTimer !== null) dependencies.clearTimer?.(state.blendTimer);
  state.blendTimer = null;
  cancelBlendRequest(state);
  if (!state.slots.left?.selected || !state.slots.right?.selected) {
    syncBlendAvailability(state);
    return;
  }
  state.blendTimer = dependencies.setTimer?.(() => {
    state.blendTimer = null;
    void requestBlend(state);
  }, delay) ?? null;
}

function createExplorationLab(container, generation, seed = null) {
  const root = element("section", "exploration-lab");
  const header = element("header", "exploration-lab__header");
  const headerCopy = element("div", "exploration-lab__header-copy");
  headerCopy.append(
    element("p", "eyebrow", "向量碰撞实验室"),
    element("h1", "exploration-lab__title", "探索实验室"),
    element("p", "exploration-lab__copy", "把两部作品的世界观、叙事和情绪放上碰撞台，再用调色盘决定今晚想靠近哪一边。"),
  );
  const features = element("div", "exploration-lab__features");
  for (const label of ["双片碰撞", "动态情绪", "三段理由"]) features.append(element("span", "exploration-lab__feature", label));
  header.append(headerCopy, features);

  const stage = element("div", "blend-stage");
  const state = {
    generation, container, root, stage, slots: {}, axes: new Map(), status: null, submit: null,
    results: null, resultsTitle: null, resultsRail: null, weight: null, weightOutput: null,
    blendTimer: null, blendController: null, blendSequence: 0, loading: false,
    draggedItem: null, draggedFrom: "", disposed: false,
  };
  const leftSlot = createBlendSlot(state, "left", "A");
  const rightSlot = createBlendSlot(state, "right", "B");
  state.slots = { left: leftSlot, right: rightSlot };

  const core = element("div", "blend-core");
  core.setAttribute("aria-label", "双片碰撞核心");
  const orb = element("div", "blend-core__orb");
  orb.append(element("span", "blend-core__symbol", "A × B"), element("span", "blend-core__caption", "VECTOR COLLISION"));
  const submit = element("button", "blend-core__submit", "碰撞生成");
  submit.type = "button";
  submit.addEventListener("click", () => void requestBlend(state));
  core.append(orb, submit);
  core.addEventListener("dragover", (event) => {
    if (!state.draggedItem) return;
    event.preventDefault?.();
    toggleClass(core, "is-drop-target", true);
  });
  core.addEventListener("dragleave", () => toggleClass(core, "is-drop-target", false));
  core.addEventListener("drop", (event) => {
    event.preventDefault?.();
    toggleClass(core, "is-drop-target", false);
    if (!state.draggedItem) return;
    const target = !state.slots.left.selected
      ? state.slots.left
      : !state.slots.right.selected
        ? state.slots.right
        : state.slots[state.draggedFrom === "left" ? "right" : "left"];
    selectBlendSource(state, target, state.draggedItem);
  });
  state.submit = submit;
  stage.append(leftSlot.root, core, rightSlot.root);

  const controls = element("section", "blend-controls");
  const weightPanel = element("div", "blend-weight");
  const weightHeading = element("div", "blend-weight__heading");
  weightHeading.append(
    element("strong", "blend-weight__title", "来源配比"),
    element("span", "blend-weight__value", "A 50 · 50 B"),
  );
  const weight = document.createElement("input");
  weight.className = "blend-weight__input";
  weight.type = "range";
  weight.min = "5";
  weight.max = "95";
  weight.step = "5";
  weight.value = "50";
  weight.setAttribute("aria-label", "作品 A 与作品 B 的融合配比");
  const weightScale = element("div", "blend-weight__scale");
  weightScale.append(element("span", "blend-weight__left", "更接近 A"), element("span", "blend-weight__right", "更接近 B"));
  weightPanel.append(weightHeading, weight, weightScale);
  state.weight = weight;
  state.weightOutput = weightHeading.children?.[1];
  weight.addEventListener("input", () => {
    const left = Math.round(clampedNumber(weight.value, 5, 95, 50));
    state.weightOutput.textContent = `A ${left} · ${100 - left} B`;
    scheduleBlend(state);
  });

  const mood = element("div", "mood-equalizer");
  const moodHeading = element("div", "mood-equalizer__heading");
  const moodCopy = element("div", "mood-equalizer__copy");
  moodCopy.append(
    element("strong", "mood-equalizer__title", "动态情绪调色盘"),
    element("span", "mood-equalizer__hint", "拖动时只更新当前探索，不会永久改变你的口味档案"),
  );
  const reset = element("button", "mood-equalizer__reset", "恢复默认");
  reset.type = "button";
  moodHeading.append(moodCopy, reset);
  const axisGrid = element("div", "mood-equalizer__grid");
  for (const definition of MOOD_AXIS_DEFINITIONS) {
    const axis = createMoodAxis(state, definition);
    state.axes.set(definition.key, axis);
    axisGrid.append(axis.wrapper);
  }
  reset.addEventListener("click", () => {
    weight.value = "50";
    state.weightOutput.textContent = "A 50 · 50 B";
    for (const axis of state.axes.values()) {
      axis.input.value = "0";
      axis.output.textContent = "平衡";
    }
    scheduleBlend(state, 0);
  });
  mood.append(moodHeading, axisGrid);
  controls.append(weightPanel, mood);

  const status = element("p", "exploration-lab__status", "先为 A 与 B 各选择一部作品，再让两个世界发生碰撞。");
  status.setAttribute("aria-live", "polite");
  state.status = status;
  const results = element("section", "blend-results");
  results.hidden = true;
  const resultsHeader = element("div", "blend-results__header");
  const resultsTitle = element("h2", "blend-results__title", "融合结果");
  const resultsHint = element("p", "blend-results__hint", "横向浏览桥梁作品；解释会分别标明来自 A、来自 B 与最终融合。" );
  resultsHeader.append(resultsTitle, resultsHint);
  const resultsRail = element("div", "blend-results__rail");
  results.setAttribute("aria-live", "polite");
  results.append(resultsHeader, resultsRail);
  state.results = results;
  state.resultsTitle = resultsTitle;
  state.resultsRail = resultsRail;

  root.append(header, stage, controls, status, results);
  activeExplorationLab = state;
  if (seed) selectBlendSource(state, leftSlot, seed, { autoBlend: false });
  syncBlendAvailability(state);
  return root;
}

function explorationSeed(graph) {
  const focusId = nodeId(graph?.focus_id);
  if (!focusId) return null;
  const candidate = (Array.isArray(graph?.nodes) ? graph.nodes : []).map(normalizeDiscoveryItem).find((item) => item?.id === focusId);
  return candidate || { id: focusId, item_key: focusId, title: "当前关系焦点", media_type: "作品", _labSeed: true };
}

function hydrateExplorationSeed(graphState, incomingNodes) {
  const lab = activeExplorationLab;
  const selected = lab?.slots?.left?.selected;
  if (!lab || lab.disposed || lab.generation !== graphState.generation || !selected?._labSeed) return;
  const replacement = incomingNodes.find((item) => item.id === selected.id);
  if (replacement) selectBlendSource(lab, lab.slots.left, replacement, { autoBlend: false });
}

function renderEmpty(container, generation) {
  const empty = element("section", "universe-empty route-view--enter");
  empty.append(createExplorationLab(container, generation));
  const guide = element("aside", "universe-empty__guide");
  guide.append(
    element("p", "eyebrow", "可选关系图谱"),
    element("h2", "universe-empty__title", "想继续空间漫游，再从任一详情页带入关系焦点"),
    element("p", "universe-empty__copy", "双片碰撞无需预先选择焦点即可使用；关系星图则坚持使用稳定作品 ID，避免凭空制造关联。"),
  );
  const action = element("a", "universe-empty__action", "前往片库选择关系焦点");
  action.setAttribute("href", "/library");
  action.setAttribute("data-route", "");
  guide.append(action);
  empty.append(guide);
  container.replaceChildren(empty);
  universeContainer = container;
  return empty;
}

function relationRow(state, edge) {
  const item = element("li", "relationship-list__item");
  const media = element("div", "relationship-list__media");
  media.append(renderMediaFrame(adaptCatalogMedia(state.nodesById.get(edge.target), "poster")));
  const copy = element("div", "relationship-list__copy");
  const route = element("p", "relationship-list__route", `${nodeTitle(state, edge.source)} → ${nodeTitle(state, edge.target)}`);
  const reason = element("p", "relationship-list__reason", edge.reasons.join(" · "));
  const score = element("p", "relationship-list__score", `关系强度 ${scoreLabel(edge.score)}`);
  const controls = element("div", "relationship-list__controls");
  for (const id of [edge.source, edge.target]) {
    const button = element("button", "relationship-list__focus", id === edge.source ? "聚焦来源" : "聚焦目标");
    button.type = "button";
    button.addEventListener("click", () => focusNode(id));
    controls.append(button);
  }
  const expand = element("button", "relationship-list__expand", "展开目标节点");
  expand.type = "button";
  expand.addEventListener("click", () => expandNodeFromUi(edge.target));
  controls.append(
    expand,
    detailAction(edge.target, "relationship-list__detail"),
    recommendAction(state, edge.target, "relationship-list__recommend"),
  );
  copy.append(route, reason, score, controls);
  item.append(media, copy);
  return item;
}

function rebuildSemanticView(state) {
  if (!state.view) return;
  updateLayout(state);
  state.nodeButtons.clear();
  state.nodeRoster.replaceChildren();
  for (const node of state.nodesById.values()) {
    const entry = element("div", "universe-node-entry");
    const button = element("button", "universe-node-button", node.title);
    button.type = "button";
    button.dataset.nodeId = node.id;
    button.setAttribute("aria-label", `聚焦并展开 ${node.title}`);
    button.addEventListener("mouseenter", () => {
      state.hoveredId = node.id;
      scheduleDraw(state);
    });
    button.addEventListener("mouseleave", () => {
      state.hoveredId = null;
      scheduleDraw(state);
    });
    button.addEventListener("focus", () => focusNode(node.id));
    button.addEventListener("click", () => { focusNode(node.id); expandNodeFromUi(node.id); });
    state.nodeButtons.set(node.id, button);
    const actions = element("div", "universe-node-actions");
    actions.append(
      detailAction(node.id, "universe-node-detail"),
      recommendAction(state, node.id, "universe-node-recommend"),
    );
    entry.append(button, actions);
    state.nodeRoster.append(entry);
  }

  state.relationList.replaceChildren();
  const edges = [...state.edgesByKey.values()].sort((left, right) => right.score - left.score || edgeKey(left.source, left.target).localeCompare(edgeKey(right.source, right.target)));
  if (!edges.length) {
    const empty = element("li", "relationship-list__empty", "当前作品尚无可展示的本地关系；仍可从节点列表继续尝试展开。" );
    state.relationList.append(empty);
  } else {
    for (const edge of edges) state.relationList.append(relationRow(state, edge));
  }
  state.limitNote.textContent = state.limitMessage;
  state.limitNote.hidden = !state.limitMessage;
  syncFocusState(state);
  scheduleDraw(state);
}

function syncFocusState(state) {
  for (const [id, button] of state.nodeButtons) {
    const focused = id === state.focusedId;
    toggleClass(button, "is-focused", focused);
    if (focused) button.setAttribute("aria-current", "true");
    else button.removeAttribute("aria-current");
  }
  const focused = state.nodesById.get(state.focusedId);
  state.focusLabel.textContent = focused ? `当前焦点：${focused.title}` : "尚未聚焦作品";
}

function canvasPoint(state, event) {
  const rect = state.canvas.getBoundingClientRect();
  return { x: Number(event.clientX || 0) - rect.left, y: Number(event.clientY || 0) - rect.top };
}

function screenPosition(state, position, width, height) {
  return {
    x: width / 2 + state.pan.x + position.x * state.zoom,
    y: height / 2 + state.pan.y + position.y * state.zoom,
  };
}

function nearestNode(state, point) {
  const rect = state.canvas.getBoundingClientRect();
  let nearest = null;
  let distance = 42;
  for (const [id, position] of state.positions) {
    const screen = screenPosition(state, position, rect.width, rect.height);
    const nextDistance = Math.hypot(screen.x - point.x, screen.y - point.y);
    if (nextDistance < distance) {
      distance = nextDistance;
      nearest = id;
    }
  }
  return nearest;
}

function drawCanvas(state, timestamp = 0) {
  if (!state.canvasVisible || state.destroyed) return false;
  const rect = state.canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  const ratio = Math.max(1, Math.min(2, Number(globalThis.window?.devicePixelRatio) || 1));
  const pixelWidth = Math.max(1, Math.round(width * ratio));
  const pixelHeight = Math.max(1, Math.round(height * ratio));
  if (state.canvas.width !== pixelWidth || state.canvas.height !== pixelHeight) {
    state.canvas.width = pixelWidth;
    state.canvas.height = pixelHeight;
  }
  const context = state.context;
  if (!context) return false;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);

  if (state.tween) {
    const elapsed = Math.max(0, timestamp - state.tween.startedAt);
    const progress = Math.min(1, elapsed / FOCUS_TWEEN_MS);
    const eased = 1 - ((1 - progress) ** 3);
    state.pan.x = state.tween.from.x + (state.tween.to.x - state.tween.from.x) * eased;
    state.pan.y = state.tween.from.y + (state.tween.to.y - state.tween.from.y) * eased;
    if (progress >= 1) state.tween = null;
  }

  context.lineWidth = 1;
  for (const edge of state.edgesByKey.values()) {
    const source = state.positions.get(edge.source);
    const target = state.positions.get(edge.target);
    if (!source || !target) continue;
    const from = screenPosition(state, source, width, height);
    const to = screenPosition(state, target, width, height);
    context.beginPath();
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.strokeStyle = `rgba(200, 168, 107, ${0.16 + visualScore(edge.score) * 0.52})`;
    context.stroke();
  }

  for (const [id, node] of state.nodesById) {
    const position = state.positions.get(id);
    if (!position) continue;
    const screen = screenPosition(state, position, width, height);
    const selected = id === state.focusedId;
    const hovered = id === state.hoveredId;
    context.beginPath();
    context.arc(screen.x, screen.y, selected ? 13 : hovered ? 11 : 8, 0, Math.PI * 2);
    context.fillStyle = selected ? "#f6f7fb" : hovered ? "#b9d7ff" : "#c8a86b";
    context.fill();
    context.fillStyle = selected ? "#f6f7fb" : "#aab2c4";
    context.font = selected ? "600 13px system-ui" : "12px system-ui";
    context.fillText(node.title.slice(0, 18), screen.x + 16, screen.y + 4);
  }
  return Boolean(state.tween);
}

function scheduleDraw(state) {
  if (!state || state.destroyed || !state.canvasVisible || state.rafId !== null) return;
  state.rafId = requestAnimationFrame((timestamp) => {
    state.rafId = null;
    const continueAnimation = drawCanvas(state, timestamp);
    if (continueAnimation) scheduleDraw(state);
  });
}

function listen(state, target, type, listener, options) {
  if (!target?.addEventListener) return;
  target.addEventListener(type, listener, options);
  state.listeners.push(() => target.removeEventListener(type, listener, options));
}

function bindCanvas(state) {
  const canvas = state.canvas;
  listen(state, canvas, "pointerdown", (event) => {
    canvas.focus();
    state.drag = { pointerId: event.pointerId, start: canvasPoint(state, event), pan: { ...state.pan }, moved: false };
    canvas.setPointerCapture?.(event.pointerId);
  });
  listen(state, canvas, "pointermove", (event) => {
    const point = canvasPoint(state, event);
    if (state.drag && state.drag.pointerId === event.pointerId) {
      const dx = point.x - state.drag.start.x;
      const dy = point.y - state.drag.start.y;
      state.drag.moved = state.drag.moved || Math.abs(dx) + Math.abs(dy) > 4;
      state.pan.x = state.drag.pan.x + dx;
      state.pan.y = state.drag.pan.y + dy;
      scheduleDraw(state);
      return;
    }
    const hovered = nearestNode(state, point);
    if (hovered !== state.hoveredId) {
      state.hoveredId = hovered;
      scheduleDraw(state);
    }
  });
  const clearPointer = (event, releaseCapture = true) => {
    if (!state.drag || state.drag.pointerId !== event.pointerId) return;
    const drag = state.drag;
    state.drag = null;
    if (releaseCapture && canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture?.(event.pointerId);
    return drag;
  };
  const finishPointer = (event) => {
    const drag = clearPointer(event);
    if (drag && !drag.moved) {
      const id = nearestNode(state, canvasPoint(state, event));
      if (id) { focusNode(id); expandNodeFromUi(id); }
    }
  };
  listen(state, canvas, "pointerup", finishPointer);
  listen(state, canvas, "pointercancel", (event) => { clearPointer(event); });
  listen(state, canvas, "lostpointercapture", (event) => { clearPointer(event, false); });
  listen(state, canvas, "pointerleave", () => {
    if (!state.drag) {
      state.hoveredId = null;
      scheduleDraw(state);
    }
  });
  listen(state, canvas, "wheel", (event) => {
    if (document.activeElement !== canvas) return;
    event.preventDefault();
    state.zoom = Math.max(0.58, Math.min(2.2, state.zoom * (event.deltaY < 0 ? 1.1 : 0.9)));
    scheduleDraw(state);
  }, { passive: false });
  listen(state, canvas, "keydown", (event) => {
    const ids = [...state.nodesById.keys()];
    const index = Math.max(0, ids.indexOf(state.focusedId));
    if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
      focusNode(ids[(index + direction + ids.length) % ids.length]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      expandNodeFromUi(state.focusedId);
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault(); state.zoom = Math.min(2.2, state.zoom * 1.1); scheduleDraw(state);
    } else if (event.key === "-") {
      event.preventDefault(); state.zoom = Math.max(0.58, state.zoom * 0.9); scheduleDraw(state);
    }
  });
}

function activateCanvas(state) {
  if (typeof globalThis.IntersectionObserver === "function") {
    state.intersectionObserver = new IntersectionObserver((entries) => {
      const entry = entries.find((candidate) => candidate.target === state.canvas) || entries[0];
      state.canvasVisible = Boolean(entry?.isIntersecting);
      if (state.canvasVisible) scheduleDraw(state);
    }, { rootMargin: "80px" });
    state.intersectionObserver.observe(state.canvas);
  } else {
    state.canvasVisible = true;
    drawCanvas(state, 0);
  }
  if (typeof globalThis.ResizeObserver === "function") {
    state.resizeObserver = new ResizeObserver(() => scheduleDraw(state));
    state.resizeObserver.observe(state.canvas);
  } else if (globalThis.window) {
    listen(state, window, "resize", () => scheduleDraw(state));
  }
}

export function renderUniverse(container, graph) {
  destroyUniverse();
  if (!container) return null;
  const generation = ++lifecycleGeneration;
  if (!nodeId(graph?.focus_id)) return renderEmpty(container, generation);

  const view = element("section", "universe-view route-view--enter");
  const lab = createExplorationLab(container, generation, explorationSeed(graph));
  const header = element("header", "universe-header universe-header--graph");
  header.append(
    element("p", "eyebrow", "空间关系探索"),
    element("h1", "universe-header__title", "关系图谱：沿着作品之间的证据继续漫游"),
    element("p", "universe-header__copy", "上方负责双片碰撞；这里保留口味宇宙星图与完整文字证据，支持聚焦、展开、查看详情和带入今晚推荐。"),
  );
  const focusLabel = element("p", "universe-focus", "尚未聚焦作品");
  focusLabel.setAttribute("aria-live", "polite");
  header.append(focusLabel);

  const workspace = element("div", "universe-workspace");
  const canvasPanel = element("section", "universe-canvas-panel");
  const canvas = element("canvas", "universe-canvas");
  canvas.setAttribute("tabindex", "0");
  canvas.setAttribute("aria-label", "口味宇宙交互星图。方向键切换节点，回车展开，聚焦后滚轮缩放，拖动平移。");
  canvasPanel.append(canvas);
  const evidence = element("aside", "universe-evidence");
  evidence.append(element("h2", "universe-evidence__title", "关系证据"));
  const limitNote = element("p", "universe-limit-note");
  limitNote.setAttribute("role", "status");
  limitNote.hidden = true;
  const relationList = element("ol", "relationship-list");
  evidence.append(limitNote, relationList);
  workspace.append(canvasPanel, evidence);

  const rosterSection = element("section", "universe-roster");
  rosterSection.append(element("h2", "universe-roster__title", "可探索节点"));
  const nodeRoster = element("div", "universe-node-roster");
  rosterSection.append(nodeRoster);
  view.append(lab, header, workspace, rosterSection);

  const state = {
    generation, container, view, canvas, context: canvas.getContext?.("2d") || null,
    focusLabel, relationList, nodeRoster, limitNote,
    nodesById: new Map(), edgesByKey: new Map(), positions: new Map(), nodeButtons: new Map(),
    expandedIds: new Set(), inFlight: new Map(), controllers: new Set(), listeners: [],
    focusedId: nodeId(graph.focus_id), hoveredId: null, zoom: 1, pan: { x: 0, y: 0 }, tween: null,
    drag: null, rafId: null, canvasVisible: false, intersectionObserver: null, resizeObserver: null,
    limitMessage: "", destroyed: false,
  };
  activeUniverse = state;
  universeContainer = container;
  mergeGraph(state, graph, { initial: true });
  rebuildSemanticView(state);
  bindCanvas(state);
  container.replaceChildren(view);
  activateCanvas(state);
  return view;
}

function contextSnapshot(state) {
  return {
    universeFocusId: state.focusedId,
    expandedIds: [...state.expandedIds].slice(-MAX_NODES),
  };
}

function persistContext(state) {
  dependencies.onContextChange(contextSnapshot(state));
}

function applyFocus(state, nodeIdValue) {
  const id = nodeId(nodeIdValue);
  if (!state || state.destroyed || !id || !state.nodesById.has(id)) return { valid: false, changed: false };
  if (state.focusedId === id) return { valid: true, changed: false };
  state.focusedId = id;
  const position = state.positions.get(id);
  const reduceMotion = globalThis.window?.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (position) {
    const target = { x: -position.x * state.zoom, y: -position.y * state.zoom };
    if (reduceMotion) state.pan = target;
    else state.tween = { from: { ...state.pan }, to: target, startedAt: globalThis.performance?.now?.() || 0 };
  }
  syncFocusState(state);
  scheduleDraw(state);
  persistContext(state);
  return { valid: true, changed: true };
}

export function focusNode(nodeIdValue) {
  return applyFocus(activeUniverse, nodeIdValue).valid;
}

export function expandNode(nodeIdValue) {
  const state = activeUniverse;
  const id = nodeId(nodeIdValue);
  if (!state || state.destroyed || !id) return Promise.resolve(null);
  if (state.inFlight.has(id)) return state.inFlight.get(id);
  if (state.expandedIds.has(id)) {
    focusNode(id);
    return Promise.resolve(null);
  }
  const generation = state.generation;
  const controller = new AbortController();
  state.controllers.add(controller);
  const request = dependencies.fetchJson(
    `/api/v2/universe?focus=${encodeURIComponent(id)}&limit=${INITIAL_LIMIT}`,
    { signal: controller.signal },
  ).then((graph) => {
    if (controller.signal.aborted || state.destroyed || activeUniverse !== state || state.generation !== generation) return null;
    mergeGraph(state, graph, { initial: false });
    state.expandedIds.add(id);
    rebuildSemanticView(state);
    const focus = applyFocus(state, id);
    if (!focus.changed) persistContext(state);
    return graph;
  }).catch((error) => {
    if (controller.signal.aborted || state.destroyed || activeUniverse !== state || state.generation !== generation || error?.name === "AbortError") return null;
    state.limitMessage = error?.status === 404
      ? "没有找到这个作品的关系图。你可以返回详情选择另一个稳定作品节点。"
      : "口味宇宙暂时无法继续展开。当前已加载的关系仍然可用，请稍后重试。";
    rebuildSemanticView(state);
    throw error;
  }).finally(() => {
    state.controllers.delete(controller);
    if (state.inFlight.get(id) === request) state.inFlight.delete(id);
  });
  state.inFlight.set(id, request);
  return request;
}

export function destroyUniverse({ preserveDom = false } = {}) {
  lifecycleGeneration += 1;
  const state = activeUniverse;
  const lab = activeExplorationLab;
  activeUniverse = null;
  activeExplorationLab = null;
  const container = state?.container || lab?.container || universeContainer;
  universeContainer = preserveDom ? container : null;
  if (lab) {
    lab.disposed = true;
    if (lab.blendTimer !== null) dependencies.clearTimer?.(lab.blendTimer);
    lab.blendTimer = null;
    lab.blendController?.abort();
    lab.blendController = null;
    for (const slot of Object.values(lab.slots || {})) {
      if (slot.searchTimer !== null) dependencies.clearTimer?.(slot.searchTimer);
      slot.searchTimer = null;
      slot.searchController?.abort();
      slot.searchController = null;
      slot.candidates = [];
    }
  }
  if (!state) {
    if (!preserveDom) container?.replaceChildren();
    return;
  }
  state.destroyed = true;
  if (state.rafId !== null) cancelAnimationFrame(state.rafId);
  state.rafId = null;
  state.intersectionObserver?.disconnect();
  state.resizeObserver?.disconnect();
  for (const controller of state.controllers) controller.abort();
  state.controllers.clear();
  if (state.drag && state.canvas?.hasPointerCapture?.(state.drag.pointerId)) {
    state.canvas.releasePointerCapture?.(state.drag.pointerId);
  }
  state.drag = null;
  for (const remove of state.listeners.splice(0)) remove();
  state.inFlight.clear();
  state.expandedIds.clear();
  state.nodesById.clear();
  state.edgesByKey.clear();
  state.positions.clear();
  state.nodeButtons.clear();
  if (!preserveDom) container?.replaceChildren();
}
