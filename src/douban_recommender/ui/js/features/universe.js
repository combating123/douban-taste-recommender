import { adaptCatalogMedia } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";

const INITIAL_LIMIT = 9;
const MAX_NODES = 36;
const FOCUS_TWEEN_MS = 260;
const SAFE_NODE_ID = /^[A-Za-z0-9:._~-]{1,256}$/;

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

async function requestJson(path, { signal } = {}) {
  const response = await fetch(path, { method: "GET", headers: { Accept: "application/json" }, signal });
  if (!response.ok) {
    const error = new Error(`Universe request failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

let dependencies = {
  fetchJson: requestJson,
  onContextChange: () => {},
};
let activeUniverse = null;
let lifecycleGeneration = 0;
let universeContainer = null;

export function configureUniverse(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    fetchJson: options.fetchJson || dependencies.fetchJson,
    onContextChange: options.onContextChange || dependencies.onContextChange,
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

function renderEmpty(container) {
  const empty = element("section", "universe-empty route-view--enter");
  empty.append(
    element("p", "eyebrow", "TASTE UNIVERSE / AWAITING A FOCUS"),
    element("h1", "universe-empty__title", "先选择一部作品，再展开你的口味宇宙"),
    element("p", "universe-empty__copy", "这里不会凭空绘制关系。请先从片库或今晚推荐打开作品详情，CineScope 会使用稳定作品 ID 作为探索起点。"),
  );
  const action = element("a", "universe-empty__action", "前往片库选择作品");
  action.setAttribute("href", "/library");
  action.setAttribute("data-route", "");
  empty.append(action);
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
  expand.addEventListener("click", () => { void expandNode(edge.target); });
  controls.append(expand);
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
    button.addEventListener("click", () => { focusNode(node.id); void expandNode(node.id); });
    state.nodeButtons.set(node.id, button);
    state.nodeRoster.append(button);
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
      if (id) { focusNode(id); void expandNode(id); }
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
      void expandNode(state.focusedId);
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
  if (!nodeId(graph?.focus_id)) return renderEmpty(container);

  const generation = ++lifecycleGeneration;
  const view = element("section", "universe-view route-view--enter");
  const header = element("header", "universe-header");
  header.append(
    element("p", "eyebrow", "TASTE UNIVERSE / LOCAL RELATION GRAPH"),
    element("h1", "universe-header__title", "沿着作品之间的证据，探索你的口味宇宙"),
    element("p", "universe-header__copy", "星图用于空间浏览；右侧关系清单始终提供完整、可操作的文字证据。"),
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
  view.append(header, workspace, rosterSection);

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

export function destroyUniverse() {
  lifecycleGeneration += 1;
  const state = activeUniverse;
  activeUniverse = null;
  const container = state?.container || universeContainer;
  universeContainer = null;
  if (!state) {
    container?.replaceChildren();
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
  container?.replaceChildren();
}
