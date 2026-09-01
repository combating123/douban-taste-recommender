import { getV2 } from "../core/api.js";
import { adaptCatalogMedia, createMediaLoadCoordinator, MEDIA_LOAD_PRIORITY } from "../core/media.js";
import { bindExpandableCopy } from "../components/expandable-copy.js";
import { renderMediaFrame } from "../components/media-frame.js";

const SAFE_ROUTE_SEGMENT = /^[A-Za-z0-9:._~-]{1,256}$/;
const FILTERS = Object.freeze([
  { key: "all", label: "全部", mediaType: "" },
  { key: "movie", label: "电影", mediaType: "电影" },
  { key: "series", label: "剧集", mediaType: "电视剧" },
  { key: "anime", label: "动画", mediaType: "动漫" },
]);
const PROVIDER_LABELS = Object.freeze({
  douban: "豆瓣",
  tmdb: "TMDb",
  imdb: "IMDb",
  omdb: "OMDb",
  tvmaze: "TVMaze",
  anilist: "AniList",
  jikan: "MAL",
  apple_movies: "Apple TV",
});
const MEDIA_TONES = Object.freeze({
  电影: { core: "#f0c277", glow: "rgba(240, 194, 119, 0.38)" },
  电视剧: { core: "#a88cff", glow: "rgba(168, 140, 255, 0.36)" },
  动漫: { core: "#70e4dc", glow: "rgba(112, 228, 220, 0.34)" },
});
const AUTO_REFRESH_MS = 5 * 60_000;
const MAX_GRAPH_SEEDS = 3;
const GRAPH_DISCOVERY_LIMIT = 24;
const FOCUS_SEARCH_LIMIT = 6;
const FOCUS_SEARCH_DEBOUNCE_MS = 420;

function element(tagName, className = "", text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function listValue(value) {
  return Array.isArray(value) ? value.filter((entry) => entry !== null && entry !== undefined) : [];
}

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function numberValue(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function normalizedItem(record = {}) {
  const source = objectValue(record);
  const nested = objectValue(source.item);
  return {
    ...nested,
    ...source,
    item: nested,
    genres: listValue(source.genres).length ? listValue(source.genres) : listValue(nested.genres),
    countries: listValue(source.countries).length ? listValue(source.countries) : listValue(nested.countries),
    summary: textValue(source.summary) || textValue(nested.summary),
    douban_rating: Number.isFinite(Number(source.douban_rating)) ? Number(source.douban_rating) : nested.douban_rating,
    vote_count: Number.isFinite(Number(source.vote_count)) ? Number(source.vote_count) : nested.vote_count,
  };
}

function displayTitle(item = {}) {
  return textValue(item.display_title) || textValue(item.title) || "未命名作品";
}

function mediaLabel(item = {}) {
  return textValue(objectValue(item.media_badge).label)
    || ({ 电影: "电影", 电视剧: "剧集", 动漫: "动画" }[textValue(item.media_type)] || textValue(item.media_type, "作品"));
}

function titleRoute(item = {}) {
  const key = textValue(item.item_key) || textValue(item.id);
  return key && SAFE_ROUTE_SEGMENT.test(key) ? `/title/${key}` : "";
}

function graphItemKey(item = {}) {
  const source = objectValue(item);
  const nested = objectValue(source.item);
  const nestedKey = textValue(nested.item_key) || textValue(nested.id);
  if (nestedKey) return nestedKey;
  const direct = textValue(source.item_key) || textValue(source.id);
  return direct.startsWith("live:") ? direct.slice(5) : direct;
}

function graphSeedRecord(item = {}) {
  const source = objectValue(item);
  const record = normalizedItem(Object.keys(objectValue(source.item)).length ? source.item : source);
  const itemKey = graphItemKey(source);
  return {
    ...record,
    id: itemKey,
    item_key: itemKey,
    display_title: displayTitle(record),
  };
}

function graphIdentityTokens(item = {}) {
  const source = objectValue(item);
  const nested = objectValue(source.item);
  const raw = objectValue(source.raw).identity_tokens;
  const nestedRaw = objectValue(nested.raw).identity_tokens;
  const values = [
    ...listValue(source.identity_tokens),
    ...listValue(nested.identity_tokens),
    ...listValue(raw),
    ...listValue(nestedRaw),
  ].map((value) => textValue(value)).filter(Boolean);
  return new Set(values);
}

function graphFingerprint(item = {}) {
  const source = objectValue(item);
  const nested = objectValue(source.item);
  const title = textValue(source.display_title)
    || textValue(source.title)
    || textValue(nested.display_title)
    || textValue(nested.title);
  const normalizedTitle = String(title)
    .normalize("NFKC")
    .toLocaleLowerCase("zh-CN")
    .replace(/[\s·:：\-—_（）()《》\[\]【】'"“”!?！？.,，。/\\]+/g, "")
    || "";
  const year = Number.isFinite(Number(source.year))
    ? Math.floor(Number(source.year))
    : Number.isFinite(Number(nested.year)) ? Math.floor(Number(nested.year)) : 0;
  const mediaType = textValue(source.media_type) || textValue(nested.media_type);
  if (!normalizedTitle) return "";
  return `${normalizedTitle}|${year || "?"}|${mediaType}`;
}

export function nextGraphSeeds(current = [], item = {}, maxSeeds = MAX_GRAPH_SEEDS) {
  const seed = graphSeedRecord(item);
  const key = graphItemKey(seed);
  if (!key) return listValue(current).map(graphSeedRecord).filter((entry) => graphItemKey(entry));
  const normalized = listValue(current).map(graphSeedRecord).filter((entry) => graphItemKey(entry));
  if (normalized.some((entry) => graphItemKey(entry) === key)) {
    return normalized.filter((entry) => graphItemKey(entry) !== key);
  }
  const limit = Math.max(1, Math.min(5, Math.floor(numberValue(maxSeeds, MAX_GRAPH_SEEDS))));
  return [...normalized, seed].slice(-limit);
}

export function multiFocusDiscoveryPath(seeds = [], limit = GRAPH_DISCOVERY_LIMIT, roundIndex = 0) {
  const focuses = listValue(seeds).map(graphItemKey).filter(Boolean).slice(-MAX_GRAPH_SEEDS);
  if (!focuses.length) return "";
  const params = [
    ...focuses.map((focus) => `focus=${encodeURIComponent(focus)}`),
    `limit=${Math.max(3, Math.min(30, Math.floor(numberValue(limit, GRAPH_DISCOVERY_LIMIT))))}`,
    `round=${Math.max(0, Math.min(99, Math.floor(numberValue(roundIndex))))}`,
    "complete_media=1",
  ];
  return `/api/v2/discovery/multi?${params.join("&")}`;
}

function exactDate(value) {
  const match = textValue(value).match(/^((?:19|20)\d{2})-(\d{2})-(\d{2})/);
  if (!match) return "日期待补齐";
  return `${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日`;
}

function formatTimestamp(value) {
  const milliseconds = numberValue(value) * 1000;
  if (!milliseconds) return "尚未刷新";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(milliseconds));
  } catch {
    return "时间待确认";
  }
}

function compactNumber(value) {
  const count = Math.max(0, Math.floor(numberValue(value)));
  if (!count) return "0";
  try {
    return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(count);
  } catch {
    return String(count);
  }
}

function providerLabel(value) {
  const key = textValue(value).toLowerCase().replace(/_(?:popularity|weight|votes)$/, "");
  return PROVIDER_LABELS[key] || key.toUpperCase();
}

function ratingEntries(item = {}) {
  const ratings = objectValue(item.source_ratings);
  const votes = objectValue(item.rating_votes);
  const rows = Object.entries(ratings).flatMap(([provider, score]) => {
    const numeric = Number(score);
    if (!Number.isFinite(numeric) || numeric <= 0) return [];
    return [{
      provider,
      label: providerLabel(provider),
      score: numeric.toFixed(1),
      votes: numberValue(votes[provider]),
    }];
  });
  if (!rows.length && Number.isFinite(Number(item.douban_rating)) && Number(item.douban_rating) > 0) {
    rows.push({
      provider: "douban",
      label: "豆瓣",
      score: Number(item.douban_rating).toFixed(1),
      votes: numberValue(item.vote_count),
    });
  }
  return rows.sort((left, right) => right.votes - left.votes || Number(right.score) - Number(left.score)).slice(0, 3);
}

export function hasRenderablePoster(item = {}) {
  const asset = adaptCatalogMedia(normalizedItem(item), "poster");
  return asset.status === "ready" && Boolean(asset.localUrl);
}

function sourceStateCopy(latest = {}) {
  const visible = listValue(latest.items).map(normalizedItem).filter(hasRenderablePoster);
  const live = visible.filter((item) => item.is_live).length;
  const fallback = visible.length - live;
  if (latest.is_stale && visible.length) return `网络波动，保留上次可展示结果 · ${visible.length} 条`;
  if (live && fallback) return `当前展示 ${visible.length} 条 · 在线 ${live} 条 · 本地补位 ${fallback} 条`;
  if (live) return `当前展示 ${live} 条在线候选`;
  if (fallback) return `当前展示 ${fallback} 条本地高质量候选`;
  if (latest.is_stale) return "网络波动，上次结果暂无完整素材";
  return "在线源暂未返回可展示内容";
}

function mediaTone(mediaType) {
  return MEDIA_TONES[textValue(mediaType)] || { core: "#b8c6e8", glow: "rgba(184, 198, 232, 0.28)" };
}

function translateReason(value) {
  const text = textValue(value);
  const replacements = [
    [/shared director/gi, "共同导演"],
    [/shared cast/gi, "共同演员"],
    [/shared genre/gi, "共同类型"],
    [/shared country/gi, "共同地区"],
    [/same media type/gi, "相同媒介"],
    [/same decade/gi, "同一年代"],
  ];
  return replacements.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), text) || "可解释的口味邻近";
}

function appendPill(parent, className, copy) {
  const text = textValue(copy);
  if (!text) return null;
  const pill = element("span", className, text);
  parent.append(pill);
  return pill;
}

function nodeLogicCopy(node = {}) {
  const breakdown = objectValue(node.score_breakdown);
  const coverage = numberValue(breakdown.coverage || node.matched_seed_count);
  const quality = numberValue(breakdown.quality || node.fused_rating);
  const components = objectValue(breakdown.components);
  const parts = [];
  if (coverage > 0) {
    const total = Math.max(1, Math.floor(numberValue(node.total_seed_count)) || 1);
    const matched = Math.max(0, Math.round(coverage * total));
    parts.push(`覆盖 ${matched}/${total} 个焦点`);
  }
  if (components.structural > 0) parts.push(`类型/主创 ${Math.round(components.structural * 100)}%`);
  if (components.semantic > 0) parts.push(`语义 ${Math.round(components.semantic * 100)}%`);
  if (quality > 0) parts.push(`口碑 ${quality.toFixed(1)}`);
  return parts.slice(0, 3).join(" · ");
}

function disposeFrames(frames) {
  for (const frame of frames) frame?.disposeMediaFrame?.();
  frames.clear();
}

function hashSeed(value) {
  let hash = 2166136261;
  for (const character of textValue(value, "cinescope")) {
    hash ^= character.codePointAt(0) || 0;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function seededRandom(seedValue) {
  let seed = hashSeed(seedValue) || 1;
  return () => {
    seed ^= seed << 13;
    seed ^= seed >>> 17;
    seed ^= seed << 5;
    return (seed >>> 0) / 4294967296;
  };
}

export function buildExplorationGraph(payload = {}) {
  const source = objectValue(payload);
  const graph = objectValue(source.graph);
  const suppliedNodes = listValue(graph.nodes);
  const fallbackSeeds = listValue(source.seeds).map((seed) => ({
    ...objectValue(seed),
    id: graphItemKey(seed),
    is_seed: true,
  }));
  const fallbackItems = listValue(source.items).map((item) => ({
    ...objectValue(item),
    id: graphItemKey(item),
  }));
  const rawNodes = suppliedNodes.length ? suppliedNodes : [...fallbackSeeds, ...fallbackItems];
  const rawEdges = listValue(graph.edges).length
    ? listValue(graph.edges)
    : fallbackItems.flatMap((item) => Object.entries(objectValue(item.evidence_by_seed)).map(([seedId, evidence]) => ({
      source: seedId,
      target: graphItemKey(item),
      score: numberValue(item.rank_score),
      reason: listValue(evidence)[0] || textValue(item.fusion_summary),
      reasons: listValue(evidence),
      matched: listValue(item.matched_seed_ids).includes(seedId),
    })));
  const nodes = rawNodes.map((node) => ({
    ...objectValue(node),
    online: Boolean(objectValue(node).online),
  }));
  const edges = rawEdges.map((edge) => ({
    ...objectValue(edge),
    reason: translateReason(edge?.reason),
    reasons: listValue(edge?.reasons).map(translateReason),
  }));
  const recentItems = listValue(objectValue(payload.recent).items).map(normalizedItem);
  const latestItems = listValue(objectValue(payload.latest).items).map(normalizedItem);
  const fallbackFocusIds = fallbackSeeds.map(graphItemKey).filter(Boolean);
  const focusId = textValue(graph.focus_id) || fallbackFocusIds[0] || textValue(nodes[0]?.id) || textValue(recentItems[0]?.item_key);
  const focusIds = listValue(graph.focus_ids).map((value) => textValue(value)).filter(Boolean);
  const existing = new Set(nodes.map((node) => textValue(node.id)));
  const existingFingerprints = new Set(nodes.map(graphFingerprint).filter(Boolean));
  const existingIdentityTokens = new Set();
  nodes.forEach((node) => graphIdentityTokens(node).forEach((token) => existingIdentityTokens.add(token)));
  const focusGenres = new Set(listValue(recentItems[0]?.genres).map((genre) => textValue(genre)).filter(Boolean));

  for (const item of latestItems.filter((entry) => entry.is_live && hasRenderablePoster(entry)).slice(0, 6)) {
    const id = `live:${textValue(item.item_key)}`;
    const fingerprint = graphFingerprint(item);
    const identityTokens = graphIdentityTokens(item);
    const sharesIdentity = [...identityTokens].some((token) => existingIdentityTokens.has(token));
    if (!textValue(item.item_key) || existing.has(id) || (fingerprint && existingFingerprints.has(fingerprint)) || sharesIdentity) continue;
    const sharedGenres = listValue(item.genres).map((genre) => textValue(genre)).filter((genre) => focusGenres.has(genre));
    const ratings = ratingEntries(item);
    const score = Math.max(0.8, sharedGenres.length * 1.8 + numberValue(ratings[0]?.score) / 10 + 0.5);
    nodes.push({
      id,
      title: displayTitle(item),
      media_type: item.media_type,
      year: item.year,
      media_badge: item.media_badge,
      poster: item.poster,
      online: true,
      item,
    });
    if (focusId) {
      const reason = sharedGenres.length
        ? `实时热度 · 共同类型：${sharedGenres.slice(0, 2).join(" / ")}`
        : "实时热度 · 进入你的探索半径";
      edges.push({ source: focusId, target: id, score, reason, reasons: [reason], online: true });
    }
    existing.add(id);
    if (fingerprint) existingFingerprints.add(fingerprint);
    identityTokens.forEach((token) => existingIdentityTokens.add(token));
  }
  return {
    focus_id: focusId,
    focus_ids: focusIds.length ? focusIds : (fallbackFocusIds.length ? fallbackFocusIds : (focusId ? [focusId] : [])),
    nodes,
    edges,
  };
}

function edgeSignal(edge = {}) {
  const copy = [textValue(edge.reason), ...listValue(edge.reasons).map(textValue)].filter(Boolean).join(" · ");
  if (/导演|演员|主创/.test(copy)) return { key: "creator", label: "共同主创", rgb: "240, 194, 119" };
  if (/地区|年代/.test(copy)) return { key: "context", label: "地区 / 年代", rgb: "168, 140, 255" };
  if (/气质|语义|叙事|风格/.test(copy)) return { key: "semantic", label: "气质 / 语义", rgb: "238, 132, 190" };
  if (/类型|媒介/.test(copy)) return { key: "genre", label: "共同类型", rgb: "112, 228, 220" };
  return { key: "similarity", label: "综合相似", rgb: "160, 183, 235" };
}

function compactEdgeReason(edge = {}) {
  const source = [textValue(edge.reason), ...listValue(edge.reasons).map(textValue)]
    .map((value) => translateReason(value).replace(/\s+/g, " ").trim())
    .find(Boolean);
  const signal = edgeSignal(edge);
  let copy = source || signal.label;
  const replacements = [
    [/^实时热度\s*[·・]\s*/i, "实时 · "],
    [/^共同类型\s*[：:]\s*/i, "类型 · "],
    [/^共同导演\s*[：:]\s*/i, "导演 · "],
    [/^共同演员\s*[：:]\s*/i, "演员 · "],
    [/^共同主创\s*[：:]\s*/i, "主创 · "],
    [/^共同地区\s*[：:]\s*/i, "地区 · "],
    [/^相同媒介\s*[：:]\s*/i, "媒介 · "],
    [/^同一年代\s*[：:]\s*/i, "年代 · "],
    [/^共同气质\s*[：:]\s*/i, "气质 · "],
    [/^共同语义\s*[：:]\s*/i, "语义 · "],
  ];
  copy = replacements.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), copy)
    .replace(/\s*[；;]\s*/g, " · ")
    .replace(/\s*\/\s*/g, " / ")
    .trim();
  const characters = [...copy];
  return characters.length > 24 ? `${characters.slice(0, 23).join("")}…` : copy;
}

function nodeRating(node = {}) {
  const direct = numberValue(node.fused_rating || node.douban_rating);
  if (direct > 0) return Math.max(0, Math.min(10, direct));
  const ratings = ratingEntries(node);
  return Math.max(0, Math.min(10, numberValue(ratings[0]?.score)));
}

function nodeReasonChips(node = {}) {
  const explicit = listValue(node.reason_chips).map(textValue).filter(Boolean);
  if (explicit.length) return explicit.slice(0, 3);
  const dimensions = listValue(node.fusion_dimensions).map(objectValue);
  const derived = dimensions
    .filter((row) => textValue(row.label) && textValue(row.value))
    .map((row) => `${textValue(row.label)} ${textValue(row.value)}`);
  return derived.slice(0, 3);
}

function pointerPosition(event, canvas) {
  const rect = canvas.getBoundingClientRect?.() || { left: 0, top: 0 };
  return {
    x: numberValue(event?.clientX) - numberValue(rect.left),
    y: numberValue(event?.clientY) - numberValue(rect.top),
  };
}

function createInertNeuralController(graph) {
  let selectedId = textValue(graph.focus_id) || textValue(graph.nodes?.[0]?.id);
  return {
    dispose() {},
    focusNode(id) { selectedId = textValue(id, selectedId); },
    zoomIn() {},
    zoomOut() {},
    resetView() {},
    snapshot() {
      return {
        nodeCount: listValue(graph.nodes).length,
        edgeCount: listValue(graph.edges).length,
        selectedId,
        running: false,
        zoom: 1,
        fitZoom: 1,
        userAdjustedView: false,
        pan: { x: 0, y: 0 },
        minimumNodeGap: 0,
        layoutExtentX: 0,
        layoutExtentY: 0,
        labelCount: listValue(graph.nodes).length,
        edgeLabelCount: 0,
      };
    },
  };
}

export function createNeuralCanvas({
  canvas,
  graph,
  onActivate = () => {},
  onSelectionChange = () => {},
  onHoverChange = () => {},
  onViewChange = () => {},
  requestFrame = globalThis.requestAnimationFrame?.bind(globalThis) || ((callback) => setTimeout(() => callback(Date.now()), 16)),
  cancelFrame = globalThis.cancelAnimationFrame?.bind(globalThis) || clearTimeout,
  windowTarget = globalThis.window,
  documentTarget = globalThis.document,
} = {}) {
  const context = canvas?.getContext?.("2d");
  const sourceGraph = graph && typeof graph === "object" ? graph : { nodes: [], edges: [] };
  if (!canvas || !context) return createInertNeuralController(sourceGraph);

  const sourceNodes = listValue(sourceGraph.nodes);
  const sourceEdges = listValue(sourceGraph.edges);
  const focusId = textValue(sourceGraph.focus_id) || textValue(sourceNodes[0]?.id);
  const focusIds = new Set(listValue(sourceGraph.focus_ids).map((value) => textValue(value)).filter(Boolean));
  if (focusId) focusIds.add(focusId);
  const focusOrder = new Map([...focusIds].map((id, index) => [id, index]));
  const random = seededRandom(focusId || sourceNodes.map((node) => node?.id).join("|"));
  let width = 960;
  let height = 560;
  let dpr = 1;
  let frameId = null;
  let disposed = false;
  let running = false;
  let lastTime = 0;
  let selectedId = focusId;
  let hoveredId = "";
  let drag = null;
  let pan = { x: 0, y: 0 };
  let zoom = 1;
  let fitZoom = 1;
  let userAdjustedView = false;
  let moved = false;
  const reduceMotion = Boolean(windowTarget?.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
  const nodeById = new Map();
  const candidateCount = sourceNodes.filter((source, index) => {
    const id = textValue(source?.id, `node-${index}`);
    return !focusIds.has(id);
  }).length;

  function seedSlot(seedIndex) {
    if (focusIds.size <= 1) return { x: 0, y: 0 };
    if (focusIds.size === 2) return { x: seedIndex === 0 ? -118 : 118, y: 0 };
    const angle = -Math.PI / 2 + seedIndex * (Math.PI * 2 / focusIds.size);
    return { x: Math.cos(angle) * 148, y: Math.sin(angle) * 112 };
  }

  function candidateOrbitSlot(candidateIndex) {
    if (candidateCount <= 9) {
      const angle = -Math.PI / 2 + candidateIndex * (Math.PI * 2 / Math.max(1, candidateCount));
      return { x: Math.cos(angle) * 365, y: Math.sin(angle) * 265, ring: 0 };
    }
    const innerCount = Math.min(8, Math.max(6, Math.round(candidateCount * 0.34)));
    const isInner = candidateIndex < innerCount;
    const ringIndex = isInner ? candidateIndex : candidateIndex - innerCount;
    const ringCount = isInner ? innerCount : Math.max(1, candidateCount - innerCount);
    const phase = isInner ? -Math.PI / 2 + 0.11 : -Math.PI / 2 + Math.PI / ringCount + 0.07;
    const angle = phase + ringIndex * (Math.PI * 2 / ringCount);
    const radiusX = isInner ? 345 : 575;
    const radiusY = isInner ? 250 : 395;
    return { x: Math.cos(angle) * radiusX, y: Math.sin(angle) * radiusY, ring: isInner ? 0 : 1 };
  }

  let candidateOrdinal = 0;
  const nodes = sourceNodes.map((source, index) => {
    const id = textValue(source?.id, `node-${index}`);
    const isSeed = focusIds.has(id);
    const seedIndex = focusOrder.get(id) ?? 0;
    const candidateIndex = isSeed ? -1 : candidateOrdinal++;
    const slot = isSeed ? seedSlot(seedIndex) : candidateOrbitSlot(candidateIndex);
    const node = {
      source: objectValue(source),
      id,
      index,
      seedIndex,
      candidateIndex,
      orbitRing: slot.ring ?? -1,
      x: slot.x,
      y: slot.y,
      targetX: slot.x,
      targetY: slot.y,
      vx: 0,
      vy: 0,
      radius: isSeed
        ? 29
        : 14.5
          + Math.min(5.5, Math.max(0, numberValue(source?.matched_seed_count) - 1) * 2.4)
          + Math.min(2.4, nodeRating(source) * 0.24),
      fixed: isSeed,
      seed: isSeed,
    };
    nodeById.set(node.id, node);
    return node;
  });
  const edges = sourceEdges.flatMap((source, edgeIndex) => {
    const edge = objectValue(source);
    const left = nodeById.get(textValue(edge.source));
    const right = nodeById.get(textValue(edge.target));
    return left && right ? [{ source: edge, left, right, index: edgeIndex }] : [];
  });
  const connectedNodeIds = new Map(nodes.map((node) => [node.id, new Set()]));
  for (const edge of edges) {
    connectedNodeIds.get(edge.left.id)?.add(edge.right.id);
    connectedNodeIds.get(edge.right.id)?.add(edge.left.id);
  }
  const microNodes = Array.from({ length: 46 }, (_, index) => ({
    x: (random() - 0.5) * 980,
    y: (random() - 0.5) * 620,
    radius: 0.7 + random() * 1.8,
    phase: random() * Math.PI * 2,
    speed: 0.12 + random() * 0.3,
    depth: 0.25 + random() * 0.75,
    index,
  }));
  const layoutExtentX = Math.max(390, ...nodes.map((node) => Math.abs(node.targetX) + node.radius + 118));
  const layoutExtentY = Math.max(290, ...nodes.map((node) => Math.abs(node.targetY) + node.radius + 82));
  let lastLabelCount = 0;
  let lastEdgeLabelCount = 0;
  const nodeLabelChoices = new Map();
  const edgeLabelChoices = new Map();

  function minimumTargetGap() {
    let minimum = Number.POSITIVE_INFINITY;
    for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
        const left = nodes[leftIndex];
        const right = nodes[rightIndex];
        minimum = Math.min(
          minimum,
          Math.hypot(right.targetX - left.targetX, right.targetY - left.targetY) - left.radius - right.radius,
        );
      }
    }
    return Number.isFinite(minimum) ? Math.max(0, minimum) : 0;
  }
  const minimumNodeGap = minimumTargetGap();

  function fittedZoom() {
    return Math.max(
      0.38,
      Math.min(1.12, (width - 64) / (layoutExtentX * 2), (height - 64) / (layoutExtentY * 2)),
    );
  }

  function restoreFittedView() {
    fitZoom = fittedZoom();
    zoom = fitZoom;
    pan = { x: 0, y: 0 };
    userAdjustedView = false;
    onViewChange({ zoom, fitZoom, userAdjustedView, pan: { ...pan } });
  }

  function centeredZoom(nextZoom) {
    const minimumZoom = width < 640 ? 0.38 : Math.max(0.5, fitZoom * 0.72);
    const maximumZoom = Math.max(1.85, fitZoom * 2.1);
    const next = Math.max(minimumZoom, Math.min(maximumZoom, numberValue(nextZoom, zoom)));
    if (Math.abs(next - zoom) < 0.0001) return false;
    const center = { x: width / 2, y: height / 2 };
    const worldAtCenter = screenToWorld(center);
    zoom = next;
    // Preserve the world coordinate under the viewport centre.  Pointer
    // location must never pull the graph toward a corner while zooming.
    pan = {
      x: -worldAtCenter.x * zoom,
      y: -worldAtCenter.y * zoom,
    };
    userAdjustedView = true;
    onViewChange({ zoom, fitZoom, userAdjustedView, pan: { ...pan } });
    draw(globalThis.performance?.now?.() || Date.now());
    return true;
  }

  function resize() {
    if (disposed) return;
    const rect = canvas.getBoundingClientRect?.() || {};
    width = Math.max(320, Math.floor(numberValue(rect.width, canvas.clientWidth || 960)));
    height = Math.max(340, Math.floor(numberValue(rect.height, canvas.clientHeight || 560)));
    dpr = Math.max(1, Math.min(2, numberValue(windowTarget?.devicePixelRatio, 1)));
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    fitZoom = fittedZoom();
    if (!userAdjustedView) {
      zoom = fitZoom;
      pan = { x: 0, y: 0 };
    }
    onViewChange({ zoom, fitZoom, userAdjustedView, pan: { ...pan } });
    draw(globalThis.performance?.now?.() || Date.now());
  }

  function worldToScreen(node) {
    return {
      x: width / 2 + pan.x + node.x * zoom,
      y: height / 2 + pan.y + node.y * zoom,
    };
  }

  function screenToWorld(point) {
    return {
      x: (point.x - width / 2 - pan.x) / zoom,
      y: (point.y - height / 2 - pan.y) / zoom,
    };
  }

  function hitTest(point) {
    const world = screenToWorld(point);
    const hitSlop = width < 640 ? 14 : 10;
    for (let index = nodes.length - 1; index >= 0; index -= 1) {
      const node = nodes[index];
      if (Math.hypot(world.x - node.x, world.y - node.y) <= node.radius + hitSlop / zoom) return node;
    }
    return null;
  }

  function textPixelWidth(value, fontSize = 12) {
    const copy = textValue(value);
    if (typeof context.measureText === "function") {
      const measured = numberValue(context.measureText(copy)?.width);
      if (measured > 0) return measured;
    }
    return [...copy].reduce((total, character) => {
      if (/\s/.test(character)) return total + fontSize * 0.34;
      if (/[\u0000-\u00ff]/.test(character)) return total + fontSize * 0.58;
      return total + fontSize;
    }, 0);
  }

  function wrapCanvasText(value, maxWidth, fontSize, maxLines = 2) {
    const characters = [...textValue(value, "未命名作品")];
    const lines = [];
    let cursor = 0;
    while (cursor < characters.length && lines.length < maxLines) {
      let line = "";
      while (cursor < characters.length) {
        const next = `${line}${characters[cursor]}`;
        if (line && textPixelWidth(next, fontSize) > maxWidth) break;
        line = next;
        cursor += 1;
      }
      if (!line && cursor < characters.length) {
        line = characters[cursor];
        cursor += 1;
      }
      if (lines.length === maxLines - 1 && cursor < characters.length) {
        while (line.length > 1 && textPixelWidth(`${line}…`, fontSize) > maxWidth) line = [...line].slice(0, -1).join("");
        line = `${line}…`;
        cursor = characters.length;
      }
      lines.push(line.trim() || line);
    }
    return lines.filter(Boolean);
  }

  function overlapArea(left, right, padding = 0) {
    const overlapWidth = Math.max(0, Math.min(left.x + left.width, right.x + right.width + padding) - Math.max(left.x, right.x - padding));
    const overlapHeight = Math.max(0, Math.min(left.y + left.height, right.y + right.height + padding) - Math.max(left.y, right.y - padding));
    return overlapWidth * overlapHeight;
  }

  function reservedLabelBoxes() {
    if (width < 720) {
      return [
        { x: 8, y: 8, width: Math.min(252, width - 16), height: 48 },
        { x: 8, y: 58, width: Math.max(0, width - 16), height: 128 },
        { x: 8, y: Math.max(0, height - 54), width: Math.max(0, width - 16), height: 46 },
      ];
    }
    return [
      { x: 12, y: 12, width: 272, height: 58 },
      { x: Math.max(12, width - 380), y: 12, width: Math.min(368, width - 24), height: 210 },
      { x: Math.max(12, width - 480), y: Math.max(12, height - 58), width: Math.min(468, width - 24), height: 46 },
    ];
  }

  function nodeBodyBoxes(extraPadding = 8) {
    return nodes.map((node) => {
      const position = worldToScreen(node);
      const radius = Math.max(6, node.radius * zoom) + extraPadding;
      return {
        x: position.x - radius,
        y: position.y - radius,
        width: radius * 2,
        height: radius * 2,
        nodeId: node.id,
      };
    });
  }

  function drawRoundedPanel(box, {
    fill = "rgba(5, 9, 17, 0.9)",
    stroke = "rgba(189, 211, 255, 0.2)",
    radius = 7,
    shadow = "rgba(0, 0, 0, 0.32)",
  } = {}) {
    context.save();
    context.fillStyle = fill;
    context.strokeStyle = stroke;
    context.lineWidth = 1;
    context.shadowBlur = 12;
    context.shadowColor = shadow;
    const rounded = typeof context.roundRect === "function";
    const curved = typeof context.quadraticCurveTo === "function";
    if (rounded || curved) {
      context.beginPath();
      if (rounded) {
        context.roundRect(box.x, box.y, box.width, box.height, Math.min(radius, box.height / 2));
      } else {
        const edge = Math.min(radius, box.width / 2, box.height / 2);
        context.moveTo(box.x + edge, box.y);
        context.lineTo(box.x + box.width - edge, box.y);
        context.quadraticCurveTo(box.x + box.width, box.y, box.x + box.width, box.y + edge);
        context.lineTo(box.x + box.width, box.y + box.height - edge);
        context.quadraticCurveTo(box.x + box.width, box.y + box.height, box.x + box.width - edge, box.y + box.height);
        context.lineTo(box.x + edge, box.y + box.height);
        context.quadraticCurveTo(box.x, box.y + box.height, box.x, box.y + box.height - edge);
        context.lineTo(box.x, box.y + edge);
        context.quadraticCurveTo(box.x, box.y, box.x + edge, box.y);
        context.closePath?.();
      }
      context.fill();
      context.shadowBlur = 0;
      context.stroke();
    } else {
      context.fillRect(box.x, box.y, box.width, box.height);
      context.shadowBlur = 0;
      context.strokeRect?.(box.x, box.y, box.width, box.height);
    }
    context.restore();
  }

  function boundedBox(centerX, centerY, boxWidth, boxHeight, margin = 8) {
    return {
      x: Math.max(margin, Math.min(width - boxWidth - margin, centerX - boxWidth / 2)),
      y: Math.max(margin, Math.min(height - boxHeight - margin, centerY - boxHeight / 2)),
      width: boxWidth,
      height: boxHeight,
    };
  }

  function placementScore(box, blockers, preference = 0) {
    let collisionCount = 0;
    let collisionArea = 0;
    for (const blocker of blockers) {
      const area = overlapArea(box, blocker, 5);
      if (area > 0) {
        collisionCount += 1;
        collisionArea += area;
      }
    }
    return collisionCount * 12000 + collisionArea * 18 + preference;
  }

  function radialVector(node) {
    const distance = Math.hypot(node.x, node.y);
    if (distance > 18) return { x: node.x / distance, y: node.y / distance };
    if (node.seed && focusIds.size > 1) {
      const angle = -Math.PI / 2 + node.seedIndex * (Math.PI * 2 / focusIds.size);
      return { x: Math.cos(angle), y: Math.sin(angle) };
    }
    return { x: 0, y: 1 };
  }

  function applyForces(delta) {
    const step = Math.min(1.8, Math.max(0.2, delta / 16.67));
    for (const edge of edges) {
      const dx = edge.right.x - edge.left.x;
      const dy = edge.right.y - edge.left.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const desired = edge.source.online ? 265 : 225 + Math.min(70, numberValue(edge.source.score) * 14);
      const force = (distance - desired) * 0.00018 * step;
      const fx = dx / distance * force;
      const fy = dy / distance * force;
      if (!edge.left.fixed && drag?.node !== edge.left) { edge.left.vx += fx; edge.left.vy += fy; }
      if (!edge.right.fixed && drag?.node !== edge.right) { edge.right.vx -= fx; edge.right.vy -= fy; }
    }
    for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
      const left = nodes[leftIndex];
      for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
        const right = nodes[rightIndex];
        let dx = right.x - left.x;
        let dy = right.y - left.y;
        const distanceSquared = Math.max(250, dx * dx + dy * dy);
        const distance = Math.sqrt(distanceSquared);
        const repulsion = Math.min(0.09, 260 / distanceSquared) * step;
        dx /= distance;
        dy /= distance;
        if (!left.fixed && drag?.node !== left) { left.vx -= dx * repulsion; left.vy -= dy * repulsion; }
        if (!right.fixed && drag?.node !== right) { right.vx += dx * repulsion; right.vy += dy * repulsion; }
      }
    }
    for (const node of nodes) {
      if (node.fixed || drag?.node === node) continue;
      node.vx += (node.targetX - node.x) * 0.0042 * step;
      node.vy += (node.targetY - node.y) * 0.0042 * step;
      node.vx *= 0.91;
      node.vy *= 0.91;
      node.x += node.vx * step;
      node.y += node.vy * step;
    }
  }

  function drawBackground(time) {
    context.clearRect(0, 0, width, height);
    const background = context.createRadialGradient(width * 0.45, height * 0.42, 20, width * 0.45, height * 0.42, Math.max(width, height) * 0.72);
    background.addColorStop(0, "rgba(38, 51, 86, 0.28)");
    background.addColorStop(0.52, "rgba(13, 18, 32, 0.22)");
    background.addColorStop(1, "rgba(5, 7, 13, 0.08)");
    context.fillStyle = background;
    context.fillRect(0, 0, width, height);

    context.save();
    context.translate(width / 2 + pan.x * 0.14, height / 2 + pan.y * 0.14);
    for (const micro of microNodes) {
      const pulse = reduceMotion ? 0.65 : 0.55 + Math.sin(time * 0.00055 * micro.speed + micro.phase) * 0.24;
      context.globalAlpha = Math.max(0.12, pulse * micro.depth);
      context.fillStyle = micro.index % 5 === 0 ? "#f1c782" : "#9eb8ed";
      context.beginPath();
      context.arc(micro.x, micro.y, micro.radius, 0, Math.PI * 2);
      context.fill();
    }
    context.restore();
    context.globalAlpha = 1;

    if (focusIds.size > 1) {
      const centerX = width / 2 + pan.x;
      const centerY = height / 2 + pan.y;
      for (let index = 0; index < 3; index += 1) {
        const phase = reduceMotion ? index * 0.18 : (time * 0.00012 + index * 0.24) % 1;
        const radius = 34 + phase * 92;
        context.strokeStyle = `rgba(240, 194, 119, ${0.22 * (1 - phase)})`;
        context.lineWidth = 1.2;
        context.beginPath();
        context.arc(centerX, centerY, radius, 0, Math.PI * 2);
        context.stroke();
      }
    }
  }

  function relationLabelEdges() {
    const anchorId = hoveredId || selectedId || focusId;
    const anchor = nodeById.get(anchorId);
    if (!anchor) return [];
    const connected = edges
      .filter((edge) => edge.left.id === anchorId || edge.right.id === anchorId)
      .sort((left, right) => {
        const leftOther = left.left.id === anchorId ? left.right : left.left;
        const rightOther = right.left.id === anchorId ? right.right : right.left;
        const seedPriority = Number(rightOther.seed) - Number(leftOther.seed);
        const intersectionPriority = numberValue(rightOther.source?.matched_seed_count) - numberValue(leftOther.source?.matched_seed_count);
        return seedPriority || intersectionPriority || numberValue(right.source.score) - numberValue(left.source.score);
      });
    let limit = hoveredId ? (anchor.seed ? 6 : 3) : 3;
    if (width < 640) limit = Math.min(limit, hoveredId ? 3 : 2);
    const selected = [];
    const usedSignals = new Set();
    for (const edge of connected) {
      const key = edgeSignal(edge.source).key;
      if (usedSignals.has(key)) continue;
      selected.push(edge);
      usedSignals.add(key);
      if (selected.length >= limit) return selected;
    }
    for (const edge of connected) {
      if (selected.includes(edge)) continue;
      selected.push(edge);
      if (selected.length >= limit) break;
    }
    return selected;
  }

  function drawEdges(time) {
    const selectedNode = nodeById.get(selectedId);
    const relationFocusId = hoveredId || (selectedNode && !selectedNode.seed ? selectedId : "");
    const labelAnchorId = hoveredId || selectedId || focusId;
    const labelledEdges = relationLabelEdges();
    const labelledEdgeIndexes = new Set(labelledEdges.map((edge) => edge.index));
    const labels = [];
    for (const edge of edges) {
      const left = worldToScreen(edge.left);
      const right = worldToScreen(edge.right);
      const labelled = labelledEdgeIndexes.has(edge.index);
      const highlighted = labelled || (Boolean(relationFocusId)
        && (relationFocusId === edge.left.id || relationFocusId === edge.right.id));
      const intersection = numberValue(edge.right.source?.matched_seed_count) > 1 || numberValue(edge.left.source?.matched_seed_count) > 1;
      const signal = edgeSignal(edge.source);
      const strength = Math.max(0.18, Math.min(1, numberValue(edge.source.score, 0.28)));
      const quietAlpha = relationFocusId
        ? 0.025 + strength * 0.025
        : intersection ? 0.1 + strength * 0.075 : 0.045 + strength * 0.05;
      context.strokeStyle = `rgba(${signal.rgb}, ${highlighted ? 0.78 : quietAlpha})`;
      context.lineWidth = highlighted ? 2.15 : intersection ? 1.05 + strength * 0.5 : 0.72 + strength * 0.3;
      context.beginPath();
      context.moveTo(left.x, left.y);
      context.lineTo(right.x, right.y);
      context.stroke();

      const particleCount = highlighted ? 2 : 0;
      for (let index = 0; index < particleCount; index += 1) {
        const progress = reduceMotion ? (index + 1) / (particleCount + 1) : ((time * 0.000085 * (1 + index * 0.12) + index / particleCount) % 1);
        const x = left.x + (right.x - left.x) * progress;
        const y = left.y + (right.y - left.y) * progress;
        const glow = context.createRadialGradient(x, y, 0, x, y, highlighted ? 8 : 5);
        glow.addColorStop(0, `rgba(${signal.rgb}, 0.95)`);
        glow.addColorStop(1, `rgba(${signal.rgb}, 0)`);
        context.fillStyle = glow;
        context.beginPath();
        context.arc(x, y, highlighted ? 8 : 5, 0, Math.PI * 2);
        context.fill();
      }

      if (labelled) {
        const anchorIsLeft = edge.left.id === labelAnchorId;
        const origin = anchorIsLeft ? left : right;
        const destination = anchorIsLeft ? right : left;
        const dx = destination.x - origin.x;
        const dy = destination.y - origin.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const anchor = nodeById.get(labelAnchorId);
        const progress = anchor?.seed ? 0.56 : 0.5;
        const side = hashSeed(`${edge.left.id}|${edge.right.id}|${edge.index}`) % 2 ? 1 : -1;
        labels.push({
          key: `${edge.left.id}|${edge.right.id}|${edge.index}`,
          copy: compactEdgeReason(edge.source),
          x: origin.x + dx * progress,
          y: origin.y + dy * progress,
          normalX: (-dy / distance) * side,
          normalY: (dx / distance) * side,
          tangentX: dx / distance,
          tangentY: dy / distance,
          signal,
          score: numberValue(edge.source.score),
        });
      }
    }
    return labels;
  }

  function drawEdgeLabels(labels) {
    const placed = [];
    const blockers = [...reservedLabelBoxes(), ...nodeBodyBoxes(10)];
    const offsets = [
      { normal: 17, tangent: 0 },
      { normal: 27, tangent: 0 },
      { normal: 18, tangent: 30 },
      { normal: 18, tangent: -30 },
      { normal: -17, tangent: 0 },
      { normal: 34, tangent: 45 },
      { normal: 34, tangent: -45 },
      { normal: -27, tangent: 34 },
      { normal: -27, tangent: -34 },
      { normal: 48, tangent: 0 },
    ];
    for (const label of [...labels].sort((left, right) => right.score - left.score)) {
      const fontSize = width < 640 ? 10 : 12;
      context.font = `760 ${fontSize}px Inter, "Microsoft YaHei", sans-serif`;
      const maxTextWidth = width < 640 ? 106 : 178;
      const copy = wrapCanvasText(label.copy, maxTextWidth, fontSize, 1)[0] || label.copy;
      const boxWidth = Math.max(48, Math.min(maxTextWidth + 16, textPixelWidth(copy, fontSize) + 16));
      const boxHeight = width < 640 ? 22 : 25;
      const previousChoice = edgeLabelChoices.get(label.key);
      let best = null;
      offsets.forEach((offset, index) => {
        const centerX = label.x + label.normalX * offset.normal + label.tangentX * offset.tangent;
        const centerY = label.y + label.normalY * offset.normal + label.tangentY * offset.tangent;
        const box = boundedBox(centerX, centerY, boxWidth, boxHeight);
        const preference = index * 4 - (index === previousChoice ? 760 : 0);
        const score = placementScore(box, [...blockers, ...placed], preference);
        if (!best || score < best.score) best = { box, score, index };
      });
      if (!best) continue;
      edgeLabelChoices.set(label.key, best.index);
      drawRoundedPanel(best.box, {
        fill: "rgba(4, 8, 16, 0.94)",
        stroke: `rgba(${label.signal.rgb}, 0.52)`,
        radius: 7,
        shadow: `rgba(${label.signal.rgb}, 0.18)`,
      });
      context.save();
      context.font = `760 ${fontSize}px Inter, "Microsoft YaHei", sans-serif`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.lineWidth = 3;
      context.strokeStyle = "rgba(2, 5, 10, 0.9)";
      context.strokeText?.(copy, best.box.x + best.box.width / 2, best.box.y + best.box.height / 2 + 0.5);
      context.fillStyle = "rgba(239, 246, 255, 0.96)";
      context.fillText(copy, best.box.x + best.box.width / 2, best.box.y + best.box.height / 2 + 0.5);
      context.restore();
      placed.push(best.box);
    }
    lastEdgeLabelCount = placed.length;
    return placed;
  }

  function drawNodeBody(node, time) {
    const selectedNode = nodeById.get(selectedId);
    const relationFocusId = hoveredId || (selectedNode && !selectedNode.seed ? selectedId : "");
    const related = !relationFocusId
      || node.id === relationFocusId
      || connectedNodeIds.get(relationFocusId)?.has(node.id);
    context.save();
    context.globalAlpha = related ? 1 : 0.34;
    const position = worldToScreen(node);
    const active = node.id === selectedId;
    const hovered = node.id === hoveredId;
    const tone = mediaTone(node.source.media_type);
    const pulse = reduceMotion ? 1 : 1 + Math.sin(time * 0.0012 + hashSeed(node.id) % 11) * 0.035;
    const radius = node.radius * zoom * pulse;
    const rating = nodeRating(node.source);
    const ratingStrength = rating > 0 ? Math.max(0.18, Math.min(1, rating / 10)) : 0;
    const matchCount = Math.max(0, Math.floor(numberValue(node.source.matched_seed_count)));
    const haloRadius = radius * (active ? 2.25 : node.seed ? 2 : hovered ? 1.85 : 1.5);
    const halo = context.createRadialGradient(position.x, position.y, radius * 0.35, position.x, position.y, haloRadius);
    halo.addColorStop(0, active ? tone.glow.replace(/0\.\d+\)/, "0.66)") : tone.glow);
    halo.addColorStop(1, "rgba(0, 0, 0, 0)");
    context.fillStyle = halo;
    context.beginPath();
    context.arc(position.x, position.y, haloRadius, 0, Math.PI * 2);
    context.fill();

    context.shadowBlur = active ? 28 : 14;
    context.shadowColor = tone.core;
    const core = context.createRadialGradient(
      position.x - radius * 0.28,
      position.y - radius * 0.32,
      Math.max(1, radius * 0.08),
      position.x,
      position.y,
      Math.max(6, radius),
    );
    core.addColorStop(0, "rgba(255, 255, 255, 0.98)");
    core.addColorStop(0.32, active || node.seed ? "rgba(239, 247, 255, 0.98)" : tone.core);
    core.addColorStop(1, active || node.seed ? tone.core : "rgba(8, 13, 24, 0.96)");
    context.fillStyle = core;
    context.beginPath();
    context.arc(position.x, position.y, Math.max(5, radius), 0, Math.PI * 2);
    context.fill();
    context.shadowBlur = 0;
    context.lineWidth = active ? 2.3 : node.seed ? 1.8 : 1;
    context.strokeStyle = active || node.seed ? tone.core : "rgba(255, 255, 255, 0.5)";
    context.stroke();

    if (ratingStrength > 0) {
      const ringRadius = Math.max(9, radius + (node.seed ? 8 : 5));
      context.lineWidth = active ? 2.5 : 1.6;
      context.strokeStyle = "rgba(240, 194, 119, 0.16)";
      context.beginPath();
      context.arc(position.x, position.y, ringRadius, 0, Math.PI * 2);
      context.stroke();
      context.strokeStyle = `rgba(240, 194, 119, ${active ? 0.98 : 0.72})`;
      context.beginPath();
      context.arc(position.x, position.y, ringRadius, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * ratingStrength);
      context.stroke();
    }

    if (node.seed) {
      context.strokeStyle = "rgba(240, 194, 119, 0.42)";
      context.lineWidth = 1;
      context.beginPath();
      context.arc(position.x, position.y, Math.max(8, radius + 7), 0, Math.PI * 2);
      context.stroke();
    }

    if (node.seed || matchCount > 1) {
      context.save();
      context.font = `900 ${Math.max(8, Math.min(11, radius * 0.44))}px Inter, sans-serif`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillStyle = node.seed ? "rgba(7, 13, 23, 0.9)" : "rgba(238, 247, 255, 0.92)";
      context.fillText(node.seed ? String(node.seedIndex + 1).padStart(2, "0") : `${matchCount}`, position.x, position.y + 0.5);
      context.restore();
    }
    context.restore();
  }

  function drawNodeLabels(edgeLabelBoxes = []) {
    const selectedNode = nodeById.get(selectedId);
    const relationFocusId = hoveredId || (selectedNode && !selectedNode.seed ? selectedId : "");
    const bodyBoxes = nodeBodyBoxes(9);
    const occupied = [...reservedLabelBoxes(), ...edgeLabelBoxes];
    const placed = [];
    const offsets = [
      { outward: 0, tangent: 0 },
      { outward: 0, tangent: 22 },
      { outward: 0, tangent: -22 },
      { outward: 20, tangent: 0 },
      { outward: 20, tangent: 30 },
      { outward: 20, tangent: -30 },
      { outward: 42, tangent: 0 },
      { outward: 42, tangent: 46 },
      { outward: 42, tangent: -46 },
      { outward: 68, tangent: 0 },
      { outward: 68, tangent: 66 },
      { outward: 68, tangent: -66 },
      { outward: 92, tangent: 0 },
      { outward: 28, tangent: 78 },
      { outward: 28, tangent: -78 },
    ];
    const priority = (node) => {
      if (node.id === selectedId || node.id === hoveredId) return 0;
      if (node.seed) return 1;
      if (node.orbitRing === 0) return 2;
      return 3;
    };
    const orderedNodes = [...nodes].sort((left, right) => (
      priority(left) - priority(right)
      || [...displayTitle(right.source)].length - [...displayTitle(left.source)].length
      || left.index - right.index
    ));

    for (const node of orderedNodes) {
      const position = worldToScreen(node);
      const active = node.id === selectedId;
      const hovered = node.id === hoveredId;
      const related = !relationFocusId
        || node.id === relationFocusId
        || connectedNodeIds.get(relationFocusId)?.has(node.id);
      const fontSize = width < 640
        ? (active || hovered ? 11 : 10)
        : Math.max(12, Math.min(active || hovered ? 14.4 : 13.2, (active || hovered ? 13.6 : 12.5) * Math.max(0.92, zoom)));
      const fontWeight = active || node.seed ? 760 : 680;
      context.font = `${fontWeight} ${fontSize}px Inter, "Microsoft YaHei", sans-serif`;
      const maxTextWidth = width < 640
        ? (active || node.seed ? 98 : 78)
        : (active ? 162 : node.seed ? 148 : 116);
      const lines = wrapCanvasText(displayTitle(node.source), maxTextWidth, fontSize, 2);
      const lineHeight = fontSize * 1.24;
      const statusCopy = active || hovered
        ? (node.seed ? "推荐焦点" : node.source.match_kind === "intersection" ? "严格交集" : node.source.online ? "实时候选" : "推荐候选")
        : "";
      const statusHeight = statusCopy ? (width < 640 ? 9 : 10.5) : 0;
      const boxWidth = Math.max(
        width < 640 ? 48 : 58,
        Math.min(maxTextWidth + 16, ...lines.map((line) => textPixelWidth(line, fontSize) + 16)),
      );
      const boxHeight = Math.max(22, lines.length * lineHeight + statusHeight + (width < 640 ? 8 : 10));
      const radial = radialVector(node);
      const tangent = { x: -radial.y, y: radial.x };
      const nodeRadius = Math.max(5, node.radius * zoom);
      const projectedHalf = Math.abs(radial.x) * boxWidth / 2 + Math.abs(radial.y) * boxHeight / 2;
      const baseDistance = nodeRadius + 10 + projectedHalf;
      const previousChoice = nodeLabelChoices.get(node.id);
      let best = null;
      offsets.forEach((offset, index) => {
        const distance = baseDistance + offset.outward;
        const centerX = position.x + radial.x * distance + tangent.x * offset.tangent;
        const centerY = position.y + radial.y * distance + tangent.y * offset.tangent;
        const box = boundedBox(centerX, centerY, boxWidth, boxHeight);
        const preference = index * 5 + offset.outward * 0.08 - (index === previousChoice ? 820 : 0);
        const score = placementScore(box, [...occupied, ...bodyBoxes], preference);
        if (!best || score < best.score) best = { box, score, index };
      });
      if (!best) continue;
      nodeLabelChoices.set(node.id, best.index);

      const centerX = best.box.x + best.box.width / 2;
      const centerY = best.box.y + best.box.height / 2;
      const leaderDx = centerX - position.x;
      const leaderDy = centerY - position.y;
      const leaderDistance = Math.max(1, Math.hypot(leaderDx, leaderDy));
      const leaderX = leaderDx / leaderDistance;
      const leaderY = leaderDy / leaderDistance;
      const panelProjection = Math.abs(leaderX) * best.box.width / 2 + Math.abs(leaderY) * best.box.height / 2;
      context.save();
      context.globalAlpha = related ? 1 : 0.78;
      context.strokeStyle = active || node.seed ? "rgba(240, 194, 119, 0.44)" : "rgba(167, 190, 237, 0.24)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(position.x + leaderX * (nodeRadius + 3), position.y + leaderY * (nodeRadius + 3));
      context.lineTo(centerX - leaderX * (panelProjection + 2), centerY - leaderY * (panelProjection + 2));
      context.stroke();
      const tone = mediaTone(node.source.media_type);
      drawRoundedPanel(best.box, {
        fill: active
          ? "rgba(24, 22, 24, 0.96)"
          : node.seed ? "rgba(19, 20, 25, 0.94)" : "rgba(5, 9, 17, 0.91)",
        stroke: active || node.seed ? "rgba(240, 194, 119, 0.56)" : tone.glow,
        radius: 8,
        shadow: active ? "rgba(240, 194, 119, 0.24)" : tone.glow,
      });
      const titleBlockHeight = lines.length * lineHeight;
      const contentHeight = statusHeight + titleBlockHeight;
      let textY = best.box.y + (best.box.height - contentHeight) / 2;
      if (statusCopy) {
        context.font = `820 ${width < 640 ? 7.5 : 8.5}px Inter, "Microsoft YaHei", sans-serif`;
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillStyle = node.seed ? "rgba(240, 194, 119, 0.92)" : "rgba(112, 228, 220, 0.92)";
        context.fillText(statusCopy, centerX, textY + statusHeight / 2);
        textY += statusHeight;
      }
      context.font = `${fontWeight} ${fontSize}px Inter, "Microsoft YaHei", sans-serif`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.lineWidth = 3;
      context.strokeStyle = "rgba(2, 5, 10, 0.92)";
      context.fillStyle = active ? "rgba(255, 255, 255, 0.99)" : "rgba(235, 241, 253, 0.94)";
      lines.forEach((line, lineIndex) => {
        const y = textY + lineHeight * (lineIndex + 0.5);
        context.strokeText?.(line, centerX, y);
        context.fillText(line, centerX, y);
      });
      context.restore();
      occupied.push(best.box);
      placed.push(best.box);
    }
    lastLabelCount = placed.length;
    return placed;
  }

  function draw(time) {
    if (disposed) return;
    drawBackground(time);
    const edgeLabels = drawEdges(time);
    const edgeLabelBoxes = drawEdgeLabels(edgeLabels);
    for (const node of nodes) drawNodeBody(node, time);
    drawNodeLabels(edgeLabelBoxes);
  }

  function tick(time) {
    if (disposed || !running) return;
    const delta = lastTime ? time - lastTime : 16.67;
    lastTime = time;
    applyForces(delta);
    draw(time);
    frameId = requestFrame(tick);
  }

  function start() {
    if (disposed || running || reduceMotion || documentTarget?.visibilityState === "hidden") return;
    running = true;
    lastTime = 0;
    frameId = requestFrame(tick);
  }

  function stop() {
    running = false;
    if (frameId !== null) cancelFrame(frameId);
    frameId = null;
  }

  function selectNode(node) {
    selectedId = node?.id || selectedId;
    onSelectionChange(node?.source || null);
    draw(globalThis.performance?.now?.() || Date.now());
  }

  function onPointerDown(event) {
    const point = pointerPosition(event, canvas);
    const node = hitTest(point);
    moved = false;
    drag = node
      ? { node, pointerId: event.pointerId, start: point, nodeStart: { x: node.x, y: node.y } }
      : { node: null, pointerId: event.pointerId, start: point, panStart: { ...pan } };
    canvas.setPointerCapture?.(event.pointerId);
    if (node) selectNode(node);
  }

  function onPointerMove(event) {
    const point = pointerPosition(event, canvas);
    if (!drag) {
      const next = hitTest(point)?.id || "";
      if (next !== hoveredId) {
        hoveredId = next;
        canvas.style.cursor = next ? "pointer" : "grab";
        onHoverChange(next ? nodeById.get(next)?.source || null : null);
        draw(globalThis.performance?.now?.() || Date.now());
      }
      return;
    }
    const dx = point.x - drag.start.x;
    const dy = point.y - drag.start.y;
    if (Math.hypot(dx, dy) > 4) moved = true;
    if (drag.node) {
      drag.node.x = drag.nodeStart.x + dx / zoom;
      drag.node.y = drag.nodeStart.y + dy / zoom;
      drag.node.vx = 0;
      drag.node.vy = 0;
    } else {
      userAdjustedView = true;
      pan = { x: drag.panStart.x + dx, y: drag.panStart.y + dy };
    }
    event.preventDefault?.();
    draw(globalThis.performance?.now?.() || Date.now());
  }

  function onPointerUp(event) {
    const activeDrag = drag;
    drag = null;
    canvas.releasePointerCapture?.(event.pointerId);
    if (activeDrag?.node && moved) {
      activeDrag.node.targetX = activeDrag.node.x;
      activeDrag.node.targetY = activeDrag.node.y;
      activeDrag.node.vx = 0;
      activeDrag.node.vy = 0;
    } else if (activeDrag?.node) {
      onActivate(activeDrag.node.source);
    }
  }

  function onPointerLeave() {
    if (drag) return;
    hoveredId = "";
    canvas.style.cursor = "grab";
    onHoverChange(null);
    draw(globalThis.performance?.now?.() || Date.now());
  }

  function onWheel(event) {
    // A normal vertical wheel gesture belongs to the page.  Browsers also
    // expose trackpad pinch as Ctrl/Meta + wheel, so only that deliberate
    // gesture is captured by the graph.
    if (!event?.ctrlKey && !event?.metaKey) return;
    const factor = Math.exp(-numberValue(event.deltaY) * 0.0012);
    event.preventDefault?.();
    centeredZoom(zoom * factor);
  }

  function onKeyDown(event) {
    if (!nodes.length) return;
    const currentIndex = Math.max(0, nodes.findIndex((node) => node.id === selectedId));
    if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
      selectNode(nodes[(currentIndex + direction + nodes.length) % nodes.length]);
      event.preventDefault?.();
    } else if (event.key === "Enter" || event.key === " ") {
      onActivate(nodes[currentIndex].source);
      event.preventDefault?.();
    } else if (event.key === "0") {
      restoreFittedView();
      draw(globalThis.performance?.now?.() || Date.now());
      event.preventDefault?.();
    } else if (event.key === "+" || event.key === "=") {
      centeredZoom(zoom * 1.16);
      event.preventDefault?.();
    } else if (event.key === "-" || event.key === "_") {
      centeredZoom(zoom / 1.16);
      event.preventDefault?.();
    }
  }

  function onVisibilityChange() {
    if (documentTarget?.visibilityState === "hidden") stop();
    else start();
  }

  canvas.tabIndex = 0;
  canvas.setAttribute("role", "application");
  canvas.setAttribute("aria-label", "口味神经漫游图。单击节点加入或移除推荐焦点，拖动节点；普通滚轮上下翻页，按住 Ctrl 或 Command 再滚动可居中缩放，方向键切换作品。 ");
  canvas.style.cursor = "grab";
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);
  canvas.addEventListener("pointerleave", onPointerLeave);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.addEventListener("keydown", onKeyDown);
  documentTarget?.addEventListener?.("visibilitychange", onVisibilityChange);
  let resizeObserver = null;
  if (typeof globalThis.ResizeObserver === "function") {
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
  } else {
    windowTarget?.addEventListener?.("resize", resize);
  }
  resize();
  selectNode(nodeById.get(selectedId) || nodes[0]);
  start();

  return {
    focusNode(id) {
      const node = nodeById.get(textValue(id));
      if (node) selectNode(node);
    },
    zoomIn() { centeredZoom(zoom * 1.16); },
    zoomOut() { centeredZoom(zoom / 1.16); },
    resetView() {
      restoreFittedView();
      draw(globalThis.performance?.now?.() || Date.now());
    },
    snapshot() {
      return {
        nodeCount: nodes.length,
        edgeCount: edges.length,
        selectedId,
        focusIds: [...focusIds],
        running,
        zoom,
        fitZoom,
        userAdjustedView,
        compactView: width < 640 && zoom < 0.58,
        pan: { ...pan },
        minimumNodeGap,
        layoutExtentX,
        layoutExtentY,
        labelCount: lastLabelCount,
        edgeLabelCount: lastEdgeLabelCount,
      };
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      stop();
      resizeObserver?.disconnect?.();
      if (!resizeObserver) windowTarget?.removeEventListener?.("resize", resize);
      documentTarget?.removeEventListener?.("visibilitychange", onVisibilityChange);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("keydown", onKeyDown);
    },
  };
}

function renderRecentCard(item, frames, coordinator) {
  const record = normalizedItem(item);
  const card = element("article", "observatory-recent-card");
  const route = titleRoute(record);
  const content = element(route ? "a" : "div", "observatory-recent-card__content");
  if (route) {
    content.href = route;
    content.dataset.route = "";
    content.setAttribute("aria-label", `打开《${displayTitle(record)}》详情`);
  }
  const visual = element("div", "observatory-recent-card__visual");
  const frame = renderMediaFrame(adaptCatalogMedia(record, "poster"), {
    priority: MEDIA_LOAD_PRIORITY.foreground,
    coordinator,
  });
  frames.add(frame);
  visual.append(frame);
  const dateBadge = element("time", "observatory-recent-card__date", textValue(record.watched_relative, exactDate(record.watched_date)));
  dateBadge.dateTime = textValue(record.watched_at_iso) || textValue(record.watched_date);
  visual.append(dateBadge);

  const body = element("div", "observatory-recent-card__body");
  const meta = element("div", "observatory-recent-card__meta");
  appendPill(meta, "observatory-pill observatory-pill--type", mediaLabel(record));
  if (record.year) appendPill(meta, "observatory-pill", String(record.year));
  const rating = Number(record.douban_rating);
  if (Number.isFinite(rating) && rating > 0) appendPill(meta, "observatory-pill observatory-pill--rating", `豆瓣 ${rating.toFixed(1)}`);
  const title = element("h3", "observatory-recent-card__title", displayTitle(record));
  title.title = displayTitle(record);
  const exact = element("p", "observatory-recent-card__exact", exactDate(record.watched_date));
  const source = element("p", "observatory-recent-card__source", textValue(record.watch_source_label, "观影记录"));
  body.append(meta, title, exact, source);

  const progress = objectValue(record.watch_progress);
  if (textValue(progress.label)) {
    const progressWrap = element("div", "observatory-progress");
    const progressCopy = element("span", "observatory-progress__copy", progress.label);
    const track = element("span", "observatory-progress__track");
    const value = element("span", "observatory-progress__value");
    value.style.width = `${Math.max(4, Math.min(100, numberValue(progress.percent, 8)))}%`;
    track.append(value);
    progressWrap.append(progressCopy, track);
    body.append(progressWrap);
  }
  content.append(visual, body);
  card.append(content);
  return card;
}

function renderLatestCard(item, frames, onExplore, onPrewarm = () => {}, onNavigate = () => {}, media = {}) {
  const record = normalizedItem(item);
  const card = element("article", `observatory-live-card${record.is_live ? " is-live" : " is-local"}`);
  const route = titleRoute(record);
  const visual = element(route ? "a" : "div", "observatory-live-card__visual");
  if (route) {
    visual.href = route;
    visual.dataset.route = "";
    visual.setAttribute("aria-label", `查看《${displayTitle(record)}》详情`);
    visual.addEventListener("pointerenter", () => onPrewarm(route));
    visual.addEventListener("focus", () => onPrewarm(route));
    visual.addEventListener("pointerdown", () => onPrewarm(route));
  }
  const frame = renderMediaFrame(adaptCatalogMedia(record, "poster"), {
    priority: Number.isFinite(media.priority) ? media.priority : MEDIA_LOAD_PRIORITY.visible,
    coordinator: media.coordinator,
  });
  frames.add(frame);
  visual.append(frame);
  appendPill(visual, `observatory-live-card__signal${record.is_live ? " is-online" : ""}`, record.is_live ? "实时在线" : "本地精选");
  if (textValue(record.release_date)) appendPill(visual, "observatory-live-card__release", exactDate(record.release_date));

  const body = element("div", "observatory-live-card__body");
  const meta = element("div", "observatory-live-card__meta");
  appendPill(meta, "observatory-pill observatory-pill--type", mediaLabel(record));
  if (record.year) appendPill(meta, "observatory-pill", String(record.year));
  listValue(record.genres).slice(0, 2).forEach((genre) => appendPill(meta, "observatory-pill", textValue(genre)));
  const title = element("h3", "observatory-live-card__title");
  title.title = displayTitle(record);
  const titleCopy = element(route ? "a" : "span", "observatory-live-card__title-link", displayTitle(record));
  if (route) {
    titleCopy.href = route;
    titleCopy.dataset.route = "";
    titleCopy.addEventListener("pointerenter", () => onPrewarm(route));
    titleCopy.addEventListener("focus", () => onPrewarm(route));
  }
  title.append(titleCopy);
  const ratings = element("div", "observatory-live-card__ratings");
  const ratingRows = ratingEntries(record);
  if (ratingRows.length) {
    for (const rating of ratingRows) {
      const score = element("span", `observatory-score observatory-score--${rating.provider}`);
      score.append(element("strong", "observatory-score__value", rating.score), element("span", "observatory-score__label", rating.label));
      if (rating.votes) score.append(element("small", "observatory-score__votes", `${compactNumber(rating.votes)} 人评价`));
      ratings.append(score);
    }
  } else {
    ratings.append(element("span", "observatory-score observatory-score--pending", "评分样本补全中"));
  }
  const summary = element(
    "p",
    "observatory-live-card__summary",
    textValue(record.review_excerpt) || textValue(record.summary) || "已确认作品身份与上线状态，更多中文资料正在聚合。",
  );
  const summaryText = summary.textContent || "";
  const summaryToggle = summaryText.length > 24
    ? element("button", "observatory-live-card__expand", "展开说明")
    : null;
  let summaryBinding;
  if (summaryToggle) {
    summaryToggle.type = "button";
    summaryToggle.hidden = true;
    summaryToggle.setAttribute("aria-expanded", "false");
    summaryToggle.setAttribute("aria-controls", `observatory-summary-${textValue(record.item_key || record.id, "card")}`);
    summary.id = summaryToggle.getAttribute("aria-controls");
    summary.dataset.expanded = "false";
    summaryToggle.addEventListener("click", (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      const expanded = summary.dataset.expanded === "true";
      summary.dataset.expanded = expanded ? "false" : "true";
      card.classList?.toggle?.("observatory-live-card--expanded", !expanded);
      if (!card.classList?.toggle) {
        card.className = `${card.className || ""}`
          .replace(/\sobservatory-live-card--expanded\b/g, "")
          .concat(!expanded ? " observatory-live-card--expanded" : "");
      }
      summaryToggle.setAttribute("aria-expanded", String(!expanded));
      summaryToggle.textContent = expanded ? "展开说明" : "收起说明";
      summaryBinding?.update?.();
    });
    summaryBinding = bindExpandableCopy({
      control: summaryToggle,
      nodes: [summary],
      fallbackVisible: summaryText.length > 108,
      isExpanded: () => summary.dataset.expanded === "true",
    });
  }
  const decisions = element("div", "observatory-live-card__decisions");
  const decisionRows = [
    [record.vote_count, "总评价"],
    [record.comment_count, "短评"],
    [record.review_count, "影评"],
  ].filter(([value]) => numberValue(value) > 0);
  for (const [value, label] of decisionRows.slice(0, 3)) {
    const signal = element("span", "observatory-decision");
    signal.append(element("strong", "observatory-decision__value", compactNumber(value)), element("small", "observatory-decision__label", label));
    decisions.append(signal);
  }
  body.append(meta, title, ratings);
  if (decisionRows.length) body.append(decisions);
  body.append(summary);
  if (summaryToggle) body.append(summaryToggle);
  if (route) {
    body.classList.add("is-openable");
    body.addEventListener("click", (event) => {
      if (event?.target?.closest?.("a, button")) return;
      onPrewarm(route);
      onNavigate(route);
    });
  }

  const footer = element("footer", "observatory-live-card__footer");
  const sources = listValue(record.source_labels).length
    ? listValue(record.source_labels)
    : listValue(record.discovery_sources).map(providerLabel);
  footer.append(element("span", "observatory-live-card__sources", sources.slice(0, 3).join(" / ") || "本地片库"));
  const actions = element("div", "observatory-live-card__actions");
  if (route) {
    const action = element("a", "observatory-live-card__action", "查看详情");
    action.href = route;
    action.dataset.route = "";
    action.addEventListener("pointerenter", () => onPrewarm(route));
    action.addEventListener("focus", () => onPrewarm(route));
    actions.append(action);
  }
  const explore = element("button", "observatory-live-card__action observatory-live-card__action--secondary", "围绕它找片");
  explore.type = "button";
  explore.addEventListener("click", () => onExplore(record));
  actions.append(explore);
  footer.append(actions);
  body.append(footer);
  card.append(visual, body);
  return card;
}

export function createObservatoryController({
  root,
  fetchJson = getV2,
  onNavigate = () => {},
  onExplore = () => {},
  setIntervalFn = globalThis.setInterval?.bind(globalThis) || (() => null),
  clearIntervalFn = globalThis.clearInterval?.bind(globalThis) || (() => {}),
  requestFrame,
  cancelFrame,
  windowTarget = globalThis.window,
  documentTarget = globalThis.document,
} = {}) {
  if (!root) throw new TypeError("Observatory requires a root element");
  let disposed = false;
  let generation = 0;
  let latestGeneration = 0;
  let graphGeneration = 0;
  let controller = null;
  let requestController = null;
  let latestController = null;
  let graphRequestController = null;
  let refreshTimer = null;
  let payload = {};
  let explorationPayload = null;
  let selectedSeeds = [];
  let manualFocusSelectionStarted = false;
  let focusSearchCandidates = [];
  let focusSearchController = null;
  let focusSearchTimer = null;
  let focusSearchSequence = 0;
  let focusSearchComposing = false;
  let focusSearchQuery = "";
  let activeGraphNode = null;
  let graphSelectionInitialized = false;
  let graphRound = 0;
  let graphElapsedMs = 0;
  let activeFilter = "all";
  const latestCache = new Map();
  // Keep graph batches in a short-lived client tier as well as the API tier.
  // This makes the second/third "换一批" interaction paint immediately even
  // when the browser is recovering from a cold network connection.
  const graphPayloadCache = new Map();
  const GRAPH_CACHE_TTL_MS = 10 * 60_000;
  const graphPrefetchTimers = new Map();
  const graphPrefetchControllers = new Map();
  const GRAPH_PREFETCH_LIMIT = 2;
  const detailPrewarm = new Set();
  const recentFrames = new Set();
  const latestFrames = new Set();
  const recentMediaCoordinator = createMediaLoadCoordinator({
    maxConcurrent: 4,
    maxBackgroundConcurrent: 3,
    foregroundPriority: MEDIA_LOAD_PRIORITY.interaction,
  });
  const latestMediaCoordinator = createMediaLoadCoordinator({
    maxConcurrent: 6,
    maxBackgroundConcurrent: 4,
    foregroundPriority: MEDIA_LOAD_PRIORITY.interaction,
  });

  const section = element("section", "space space--observatory");
  section.dataset.space = "observatory";
  const header = element("header", "space-header observatory-header");
  const heading = element("div", "space-header__copy");
  heading.append(element("p", "eyebrow", "实时口味图谱"), element("h1", "space-title", "观影雷达"));
  const headerTools = element("div", "observatory-header__tools");
  headerTools.append(element("p", "space-summary", "把最近看过、当前口味关系与在线新片放进同一个可解释的漫游空间。"));
  const refreshButton = element("button", "observatory-refresh", "刷新在线资料");
  refreshButton.type = "button";
  const updated = element("span", "observatory-updated", "准备连接在线来源");
  headerTools.append(refreshButton, updated);
  header.append(heading, headerTools);

  const metrics = element("section", "observatory-metrics");
  metrics.setAttribute("aria-label", "观影雷达摘要");
  const metricNodes = new Map();
  for (const [key, label] of [["recent", "最近记录"], ["live", "在线更新"], ["nodes", "可漫游节点"], ["sources", "活跃来源"]]) {
    const metric = element("article", `observatory-metric observatory-metric--${key}`);
    const value = element("strong", "observatory-metric__value", "—");
    metricNodes.set(key, value);
    metric.append(element("span", "observatory-metric__label", label), value);
    metrics.append(metric);
  }

  const neural = element("section", "observatory-panel observatory-neural");
  const neuralHeader = element("header", "observatory-panel__header");
  const neuralCopy = element("div");
  neuralCopy.append(element("p", "eyebrow", "可解释神经漫游"), element("h2", "observatory-panel__title", "口味神经漫游"));
  const neuralHeaderAside = element("div", "observatory-neural__header-aside");
  const neuralDescription = element("p", "observatory-panel__summary", "单击一部作品会重建相似邻域；继续选择最多三部作品，系统会优先寻找它们的内容交集。 ");
  const detailAction = element("a", "observatory-neural__detail-action", "打开当前作品详情");
  detailAction.hidden = true;
  detailAction.addEventListener("pointerenter", () => prewarmDetailRoute(detailAction.getAttribute?.("href") || detailAction.href));
  detailAction.addEventListener("focus", () => prewarmDetailRoute(detailAction.getAttribute?.("href") || detailAction.href));
  neuralHeaderAside.append(neuralDescription, detailAction);
  neuralHeader.append(neuralCopy, neuralHeaderAside);

  const focusComposer = element("section", "observatory-focus-composer");
  focusComposer.setAttribute("aria-label", "手动选择并融合推荐焦点");
  const focusComposerIntro = element("div", "observatory-focus-composer__intro");
  const focusComposerHeading = element("div", "observatory-focus-composer__heading");
  const focusComposerTitleWrap = element("div", "observatory-focus-composer__title-wrap");
  focusComposerTitleWrap.append(
    element("span", "observatory-focus-composer__kicker", "焦点配方台"),
    element("strong", "observatory-focus-composer__title", "搜索作品，组合你的观影兴趣"),
  );
  const resetFocusStart = element("button", "observatory-focus-composer__reset", "重新选择起点");
  resetFocusStart.type = "button";
  focusComposerHeading.append(focusComposerTitleWrap, resetFocusStart);
  const focusComposerCopy = element("p", "observatory-focus-composer__copy", "首次手动选择会替换系统起点；之后可继续加入两部作品，让系统寻找共同类型、气质、主创与口碑交集。 ");
  focusComposerIntro.append(focusComposerHeading, focusComposerCopy);
  const focusSearchArea = element("div", "observatory-focus-composer__search-area");
  const focusSearchForm = element("form", "observatory-focus-composer__search");
  focusSearchForm.setAttribute("role", "search");
  const focusSearchInput = element("input", "observatory-focus-composer__input");
  focusSearchInput.type = "search";
  focusSearchInput.placeholder = "输入电影、剧集或动画，例如：星际穿越";
  focusSearchInput.autocomplete = "off";
  focusSearchInput.setAttribute("aria-label", "搜索要加入推荐融合的作品");
  focusSearchInput.setAttribute("aria-controls", "observatory-focus-search-results");
  const focusSearchButton = element("button", "observatory-focus-composer__search-button", "查找影片");
  focusSearchButton.type = "button";
  focusSearchForm.append(focusSearchInput, focusSearchButton);
  const focusSearchStatus = element("p", "observatory-focus-composer__status", "可直接输入片名，也可以继续单击关系图中的节点。 ");
  focusSearchStatus.setAttribute("role", "status");
  focusSearchStatus.setAttribute("aria-live", "polite");
  focusSearchArea.append(focusSearchForm, focusSearchStatus);
  const focusSearchResults = element("div", "observatory-focus-composer__results");
  focusSearchResults.id = "observatory-focus-search-results";
  focusSearchResults.hidden = true;
  focusSearchResults.setAttribute("aria-label", "作品搜索候选");
  focusComposer.append(focusComposerIntro, focusSearchArea, focusSearchResults);

  const seedBar = element("div", "observatory-neural__seed-bar");
  const seedStatus = element("div", "observatory-neural__seed-status");
  const seedLabel = element("span", "observatory-neural__seed-label", "当前焦点");
  const seedMode = element("strong", "observatory-neural__seed-mode", "单击节点开始探索");
  seedStatus.append(seedLabel, seedMode);
  const seedTray = element("div", "observatory-neural__seed-tray");
  const seedActions = element("div", "observatory-neural__seed-actions");
  const composeGraph = element("button", "observatory-neural__compose", "生成推荐");
  composeGraph.type = "button";
  composeGraph.disabled = true;
  const shuffleGraph = element("button", "observatory-neural__shuffle", "换一批");
  shuffleGraph.type = "button";
  shuffleGraph.disabled = true;
  const clearSeeds = element("button", "observatory-neural__clear", "清空焦点");
  clearSeeds.type = "button";
  clearSeeds.disabled = true;
  seedActions.append(composeGraph, shuffleGraph, clearSeeds);
  seedBar.append(seedStatus, seedTray, seedActions);
  const fusionReadout = element("section", "observatory-neural__fusion-readout");
  fusionReadout.hidden = true;
  fusionReadout.setAttribute("aria-live", "polite");
  const visualKey = element("div", "observatory-neural__visual-key");
  visualKey.setAttribute("aria-label", "关系图视觉编码");
  for (const [tone, label, copy] of [
    ["media", "节点颜色", "电影 / 剧集 / 动画"],
    ["coverage", "节点大小", "覆盖焦点越多越大"],
    ["rating", "金色外环", "多来源口碑强度"],
    ["relation", "连线颜色", "类型 / 主创 / 地区 / 气质"],
  ]) {
    const key = element("span", `observatory-neural__visual-key-item observatory-neural__visual-key-item--${tone}`);
    key.append(
      element("i", "observatory-neural__visual-key-swatch"),
      element("strong", "observatory-neural__visual-key-label", label),
      element("small", "observatory-neural__visual-key-copy", copy),
    );
    visualKey.append(key);
  }
  const canvasShell = element("div", "observatory-neural__canvas-shell");
  const canvas = element("canvas", "observatory-neural__canvas");
  const viewControls = element("div", "observatory-neural__view-controls");
  viewControls.setAttribute("aria-label", "关系图视图控制");
  const zoomOutButton = element("button", "observatory-neural__view-button", "−");
  zoomOutButton.type = "button";
  zoomOutButton.setAttribute("aria-label", "缩小关系图");
  const viewScale = element("output", "observatory-neural__view-scale", "100%");
  viewScale.setAttribute("aria-label", "当前关系图缩放比例");
  const zoomInButton = element("button", "observatory-neural__view-button", "+");
  zoomInButton.type = "button";
  zoomInButton.setAttribute("aria-label", "放大关系图");
  const resetViewButton = element("button", "observatory-neural__view-button observatory-neural__view-button--reset", "居中");
  resetViewButton.type = "button";
  resetViewButton.setAttribute("aria-label", "恢复居中适配视图");
  viewControls.append(zoomOutButton, viewScale, zoomInButton, resetViewButton);

  const nodeInspector = element("aside", "observatory-neural__inspector");
  nodeInspector.dataset.state = "idle";
  nodeInspector.setAttribute("aria-label", "当前节点速读");
  const inspectorKicker = element("span", "observatory-neural__inspector-kicker", "节点速读");
  const inspectorTitle = element("strong", "observatory-neural__inspector-title", "指向一个节点查看依据");
  const inspectorMeta = element("span", "observatory-neural__inspector-meta", "每个作品名始终可见，重点连线会直接标出推荐依据。 ");
  const inspectorReason = element("p", "observatory-neural__inspector-reason", "指向节点可展开更多关系；普通滚轮浏览页面，Ctrl / ⌘ + 滚轮居中缩放。 ");
  const inspectorChips = element("div", "observatory-neural__inspector-chips");
  nodeInspector.append(inspectorKicker, inspectorTitle, inspectorMeta, inspectorReason, inspectorChips);

  const neuralHint = element("p", "observatory-neural__hint", "普通滚轮上下翻页 · Ctrl / ⌘ + 滚轮居中缩放 · 拖动空白平移");
  const rebuildStatus = element("div", "observatory-neural__rebuild-status");
  rebuildStatus.setAttribute("role", "status");
  rebuildStatus.setAttribute("aria-live", "polite");
  rebuildStatus.append(
    element("span", "observatory-neural__rebuild-spinner"),
    element("strong", "observatory-neural__rebuild-copy", "正在重组推荐神经网络"),
  );
  canvasShell.append(canvas, viewControls, nodeInspector, neuralHint, rebuildStatus);
  const legend = element("div", "observatory-neural__legend");
  legend.setAttribute("aria-label", "可漫游作品节点");
  neural.append(neuralHeader, focusComposer, seedBar, fusionReadout, visualKey, canvasShell, legend);

  function renderViewScale(view = {}) {
    const fit = Math.max(0.001, numberValue(view.fitZoom, 1));
    const current = Math.max(0.001, numberValue(view.zoom, fit));
    viewScale.textContent = `${Math.round(current / fit * 100)}%`;
  }

  function renderNodeInspector(node) {
    const record = objectValue(node);
    if (!textValue(record.id) && !textValue(record.item_key)) {
      nodeInspector.dataset.state = "idle";
      inspectorKicker.textContent = "节点速读";
      inspectorTitle.textContent = "指向一个节点查看依据";
      inspectorMeta.textContent = "每个作品名始终可见，重点连线会直接标出推荐依据。 ";
      inspectorReason.textContent = "指向节点可展开更多关系；普通滚轮浏览页面，Ctrl / ⌘ + 滚轮居中缩放。 ";
      inspectorChips.replaceChildren();
      return;
    }
    nodeInspector.dataset.state = record.is_seed ? "seed" : textValue(record.match_kind, "candidate");
    inspectorKicker.textContent = record.is_seed ? "当前推荐焦点" : record.match_kind === "intersection" ? "多焦点严格交集" : record.match_kind === "blend" ? "跨焦点混合候选" : "节点推荐依据";
    inspectorTitle.textContent = displayTitle(record);
    const coverage = Math.max(0, Math.floor(numberValue(record.matched_seed_count)));
    const total = Math.max(coverage, Math.floor(numberValue(record.total_seed_count)) || selectedSeeds.length || 1);
    const rating = nodeRating(record);
    inspectorMeta.textContent = [
      mediaLabel(record),
      Number.isFinite(record.year) ? String(record.year) : "",
      coverage ? `覆盖 ${coverage}/${total} 个焦点` : "",
      rating > 0 ? `口碑 ${rating.toFixed(1)}` : "",
    ].filter(Boolean).join(" · ");
    const reason = textValue(record.primary_reason)
      || textValue(record.explanation)
      || textValue(record.fusion_summary)
      || nodeReasonChips(record).slice(0, 2).join("；")
      || (record.is_seed ? "这是当前重组焦点；与它相连的候选会按类型、主创、气质语义和口碑共同排序。" : "该候选通过内容结构、观看气质与口碑信号进入当前关系图。 ");
    inspectorReason.textContent = reason;
    inspectorChips.replaceChildren();
    const chips = [...new Set([
      ...listValue(record.genres).slice(0, 2),
      ...nodeReasonChips(record),
    ].map(textValue).filter(Boolean))].slice(0, 3);
    chips.forEach((chip) => appendPill(inspectorChips, "observatory-neural__inspector-chip", chip));
  }

  const onZoomOut = () => controller?.zoomOut?.();
  const onZoomIn = () => controller?.zoomIn?.();
  const onResetView = () => controller?.resetView?.();
  zoomOutButton.addEventListener("click", onZoomOut);
  zoomInButton.addEventListener("click", onZoomIn);
  resetViewButton.addEventListener("click", onResetView);

  const recentPanel = element("section", "observatory-panel observatory-recent");
  const recentHeader = element("header", "observatory-panel__header");
  const recentCopy = element("div");
  recentCopy.append(element("p", "eyebrow", "观影日记"), element("h2", "observatory-panel__title", "最近看过"));
  recentHeader.append(recentCopy, element("p", "observatory-panel__summary", "优先使用豆瓣看过日期，其次使用你在应用内标记“已看过”的时间。"));
  const recentRail = element("div", "observatory-recent__rail");
  recentRail.setAttribute("role", "list");
  recentPanel.append(recentHeader, recentRail);

  const livePanel = element("section", "observatory-panel observatory-live");
  const liveHeader = element("header", "observatory-panel__header observatory-live__header");
  const liveCopy = element("div");
  liveCopy.append(element("p", "eyebrow", "多来源在线发现"), element("h2", "observatory-panel__title", "在线最新与口碑"));
  const liveStatus = element("p", "observatory-live__status", "正在聚合在线来源");
  liveHeader.append(liveCopy, liveStatus);
  const liveToolbar = element("div", "observatory-live__toolbar");
  const filters = element("div", "segmented-filter observatory-live__filters");
  filters.setAttribute("aria-label", "在线内容类型筛选");
  const filterButtons = new Map();
  for (const filter of FILTERS) {
    const button = element("button", "segmented-filter__button", filter.label);
    button.type = "button";
    button.dataset.observatoryFilter = filter.key;
    button.setAttribute("aria-pressed", String(filter.key === activeFilter));
    filterButtons.set(filter.key, button);
    filters.append(button);
  }
  const sourceStrip = element("div", "observatory-live__sources");
  liveToolbar.append(filters, sourceStrip);
  const liveGrid = element("div", "observatory-live__grid");
  livePanel.append(liveHeader, liveToolbar, liveGrid);

  section.append(header, metrics, neural, recentPanel, livePanel);
  root.replaceChildren(section);

  function prewarmDetailRoute(route) {
    const key = textValue(route).replace(/^\/title\//, "");
    if (!key || detailPrewarm.has(key)) return;
    detailPrewarm.add(key);
    void Promise.resolve(fetchJson(`/api/v2/titles/${key}`, { ttlMs: 120_000 }))
      .catch(() => detailPrewarm.delete(key));
  }

  function prewarmGraphForNode(node) {
    if (disposed) return;
    const candidateSeeds = nextGraphSeeds(selectedSeeds, node, MAX_GRAPH_SEEDS);
    const path = multiFocusDiscoveryPath(candidateSeeds, GRAPH_DISCOVERY_LIMIT, 0);
    if (!path || graphPayloadCache.has(path) || graphPrefetchTimers.has(path) || graphPrefetchControllers.has(path)) return;
    if (graphPrefetchControllers.size + graphPrefetchTimers.size >= GRAPH_PREFETCH_LIMIT) return;
    const schedule = windowTarget?.setTimeout || globalThis.setTimeout;
    if (typeof schedule !== "function") return;
    const timer = schedule(() => {
      graphPrefetchTimers.delete(path);
      if (disposed || graphPayloadCache.has(path) || graphPrefetchControllers.size >= GRAPH_PREFETCH_LIMIT) return;
      const requestController = new AbortController();
      graphPrefetchControllers.set(path, requestController);
      void Promise.resolve(fetchJson(path, {
        signal: requestController.signal,
        force: false,
        ttlMs: 120_000,
      })).then((nextPayload) => {
        if (!disposed) graphPayloadCache.set(path, { payload: objectValue(nextPayload), expiresAt: Date.now() + GRAPH_CACHE_TTL_MS });
      }).catch(() => {}).finally(() => {
        graphPrefetchControllers.delete(path);
      });
    }, 90);
    graphPrefetchTimers.set(path, timer);
  }

  function clearFocusSearchTimer() {
    if (focusSearchTimer === null) return;
    try { (windowTarget?.clearTimeout || globalThis.clearTimeout)?.(focusSearchTimer); } catch { /* optional timer */ }
    focusSearchTimer = null;
  }

  function setFocusSearchStatus(copy = "", state = "") {
    focusSearchStatus.textContent = textValue(copy);
    if (state) focusSearchStatus.dataset.state = state;
    else delete focusSearchStatus.dataset.state;
  }

  function focusCandidateAction(item = {}) {
    const key = graphItemKey(item);
    const selected = selectedSeeds.some((seed) => graphItemKey(seed) === key);
    if (selected && manualFocusSelectionStarted) return "移出配方";
    if (!manualFocusSelectionStarted && selectedSeeds.length) return "设为首焦点";
    if (!selectedSeeds.length) return "设为首焦点";
    if (selectedSeeds.length < MAX_GRAPH_SEEDS) return "加入融合";
    return "替换最早焦点";
  }

  function renderFocusSearchResults() {
    focusSearchResults.replaceChildren();
    const selectedIds = new Set(selectedSeeds.map(graphItemKey));
    for (const candidate of focusSearchCandidates) {
      const key = graphItemKey(candidate);
      if (!key) continue;
      const selected = selectedIds.has(key);
      const card = element("button", `observatory-focus-candidate${selected ? " is-selected" : ""}`);
      card.type = "button";
      card.dataset.itemId = key;
      card.setAttribute("aria-pressed", String(selected));
      card.setAttribute("aria-label", `${focusCandidateAction(candidate)}《${displayTitle(candidate)}》`);
      const badge = element("span", "observatory-focus-candidate__badge", mediaLabel(candidate));
      badge.dataset.tone = textValue(candidate.media_type, "作品");
      const copy = element("span", "observatory-focus-candidate__copy");
      const rating = nodeRating(candidate);
      copy.append(
        element("strong", "observatory-focus-candidate__title", displayTitle(candidate)),
        element("small", "observatory-focus-candidate__meta", [
          Number.isFinite(Number(candidate.year)) ? String(Math.floor(Number(candidate.year))) : "",
          rating > 0 ? `口碑 ${rating.toFixed(1)}` : "",
        ].filter(Boolean).join(" · ") || "作品资料已匹配"),
      );
      const action = element("span", "observatory-focus-candidate__action", focusCandidateAction(candidate));
      card.append(badge, copy, action);
      card.addEventListener("pointerenter", () => prewarmDetailRoute(titleRoute(candidate)));
      card.addEventListener("focus", () => prewarmDetailRoute(titleRoute(candidate)));
      card.addEventListener("click", () => { void selectManualFocusCandidate(candidate); });
      focusSearchResults.append(card);
    }
    focusSearchResults.hidden = focusSearchResults.children.length === 0;
  }

  function updateFocusComposerCopy({ loading = false } = {}) {
    focusComposer.dataset.mode = !manualFocusSelectionStarted
      ? "automatic"
      : selectedSeeds.length > 1 ? "fusion" : selectedSeeds.length ? "manual" : "empty";
    resetFocusStart.disabled = loading;
    composeGraph.disabled = !selectedSeeds.length || loading;
    composeGraph.textContent = selectedSeeds.length > 1 ? "生成融合推荐" : "生成相似推荐";
    if (!manualFocusSelectionStarted && selectedSeeds.length) {
      focusComposerCopy.textContent = `当前由系统选择《${displayTitle(selectedSeeds[0])}》作为起点；首次手动选择会直接替换它，之后还可加入两部作品。`;
    } else if (!selectedSeeds.length) {
      focusComposerCopy.textContent = "先搜索并选择一部作品作为起点；随后最多再加入两部，让系统寻找真正的内容交集。";
    } else if (selectedSeeds.length < MAX_GRAPH_SEEDS) {
      focusComposerCopy.textContent = `已手动选择 ${selectedSeeds.length}/${MAX_GRAPH_SEEDS} 个焦点；继续搜索或单击图中节点，即可加入融合配方。`;
    } else {
      focusComposerCopy.textContent = "融合配方已选满 3 部；继续选择会替换最早焦点，也可以先从下方焦点条移除一部。";
    }
    if (focusSearchCandidates.length) renderFocusSearchResults();
  }

  async function selectManualFocusCandidate(item = {}) {
    const seed = graphSeedRecord(item);
    const key = graphItemKey(seed);
    if (!key || disposed) return false;
    graphSelectionInitialized = true;
    const previousIds = new Set(selectedSeeds.map(graphItemKey));
    const replacingAutomaticStart = !manualFocusSelectionStarted;
    manualFocusSelectionStarted = true;
    selectedSeeds = replacingAutomaticStart ? [seed] : nextGraphSeeds(selectedSeeds, seed, MAX_GRAPH_SEEDS);
    graphRound = 0;
    focusSearchInput.value = "";
    focusSearchQuery = "";
    focusSearchCandidates = [];
    renderFocusSearchResults();
    updateDetailAction(selectedSeeds.find((entry) => graphItemKey(entry) === key) || selectedSeeds.at(-1) || null);
    const stillSelected = selectedSeeds.some((entry) => graphItemKey(entry) === key);
    const actionCopy = replacingAutomaticStart
      ? `已将《${displayTitle(seed)}》设为你的首焦点，正在生成推荐。`
      : stillSelected && !previousIds.has(key)
        ? `已将《${displayTitle(seed)}》加入融合，正在重组推荐。`
        : stillSelected
          ? `《${displayTitle(seed)}》已保留在融合配方中。`
          : `已从融合配方移除《${displayTitle(seed)}》。`;
    setFocusSearchStatus(actionCopy, "busy");
    const rebuilt = await rebuildGraph();
    if (!disposed && rebuilt) {
      setFocusSearchStatus(
        selectedSeeds.length > 1
          ? `融合完成：当前由 ${selectedSeeds.length} 部作品共同生成推荐。`
          : selectedSeeds.length === 1
            ? `已围绕《${displayTitle(selectedSeeds[0])}》生成新的推荐邻域。`
            : "焦点已清空，可以重新选择起点。",
        "success",
      );
    }
    return rebuilt;
  }

  async function searchFocusCandidates(queryValue, { selectFirst = false } = {}) {
    const query = textValue(queryValue);
    if (!query || disposed) {
      focusSearchCandidates = [];
      renderFocusSearchResults();
      setFocusSearchStatus("输入一部作品的名称后开始查找。", "error");
      return [];
    }
    clearFocusSearchTimer();
    focusSearchController?.abort?.();
    const requestController = new AbortController();
    focusSearchController = requestController;
    const requestSequence = ++focusSearchSequence;
    focusSearchQuery = query;
    focusSearchButton.disabled = true;
    focusComposer.dataset.state = "loading";
    setFocusSearchStatus(`正在辨认“${query}”的不同版本…`, "busy");
    try {
      const response = await fetchJson(
        `/api/v2/titles/search?q=${encodeURIComponent(query)}&limit=${FOCUS_SEARCH_LIMIT}`,
        { signal: requestController.signal, ttlMs: 60_000 },
      );
      if (disposed || requestController.signal.aborted || requestSequence !== focusSearchSequence) return focusSearchCandidates;
      const seen = new Set();
      focusSearchCandidates = listValue(response?.items)
        .map(graphSeedRecord)
        .filter((candidate) => {
          const key = graphItemKey(candidate);
          if (!key || seen.has(key)) return false;
          seen.add(key);
          return true;
        })
        .slice(0, FOCUS_SEARCH_LIMIT);
      renderFocusSearchResults();
      if (selectFirst && focusSearchCandidates.length) {
        return selectManualFocusCandidate(focusSearchCandidates[0]);
      }
      setFocusSearchStatus(
        focusSearchCandidates.length > 1
          ? `找到 ${focusSearchCandidates.length} 个候选，请根据媒介、年份和评分选择正确版本。`
          : focusSearchCandidates.length === 1
            ? "找到 1 个高可信候选，点击即可加入推荐配方。"
            : `没有找到“${query}”的明确作品，请尝试更完整的名称。`,
        focusSearchCandidates.length ? "success" : "error",
      );
      return focusSearchCandidates;
    } catch (error) {
      if (disposed || requestController.signal.aborted || requestSequence !== focusSearchSequence || error?.name === "AbortError") return focusSearchCandidates;
      focusSearchCandidates = [];
      renderFocusSearchResults();
      setFocusSearchStatus("作品检索暂时不可用，当前焦点和关系图不会丢失。", "error");
      return [];
    } finally {
      if (!disposed && requestSequence === focusSearchSequence) {
        focusSearchButton.disabled = false;
        delete focusComposer.dataset.state;
      }
      if (focusSearchController === requestController) focusSearchController = null;
    }
  }

  function scheduleFocusSearch() {
    clearFocusSearchTimer();
    if (focusSearchComposing || disposed) return;
    const query = textValue(focusSearchInput.value);
    if (!query) {
      focusSearchController?.abort?.();
      focusSearchCandidates = [];
      focusSearchQuery = "";
      renderFocusSearchResults();
      setFocusSearchStatus("可直接输入片名，也可以继续单击关系图中的节点。 ");
      return;
    }
    const schedule = windowTarget?.setTimeout || globalThis.setTimeout;
    focusSearchTimer = schedule?.(() => {
      focusSearchTimer = null;
      void searchFocusCandidates(query);
    }, FOCUS_SEARCH_DEBOUNCE_MS) ?? null;
  }

  function beginManualFocusSelection() {
    manualFocusSelectionStarted = true;
    clearGraphSeeds();
    focusSearchInput.value = "";
    focusSearchCandidates = [];
    focusSearchQuery = "";
    renderFocusSearchResults();
    setFocusSearchStatus("输入你真正想作为起点的作品；选择后会立即生成新的推荐邻域。", "success");
    focusSearchInput.focus?.();
  }

  function currentGraph() {
    if (objectValue(explorationPayload).graph) {
      return buildExplorationGraph(objectValue(explorationPayload));
    }
    return buildExplorationGraph(payload);
  }

  function scheduleNextGraphBatch(path) {
    const callback = () => {
      if (disposed || graphPayloadCache.has(path)) return;
      void fetchJson(path, { force: false, ttlMs: 120_000 })
        .then((nextPayload) => {
          if (!disposed) graphPayloadCache.set(path, { payload: objectValue(nextPayload), expiresAt: Date.now() + GRAPH_CACHE_TTL_MS });
        })
        .catch(() => {});
    };
    if (typeof windowTarget?.requestIdleCallback === "function") {
      windowTarget.requestIdleCallback(callback, { timeout: 900 });
      return;
    }
    const schedule = windowTarget?.setTimeout || globalThis.setTimeout;
    schedule?.(callback, 180);
  }

  function updateDetailAction(node) {
    activeGraphNode = node ? objectValue(node) : null;
    const route = titleRoute(activeGraphNode?.item || activeGraphNode || {});
    if (!route) {
      detailAction.hidden = true;
      detailAction.removeAttribute?.("href");
      return;
    }
    detailAction.hidden = false;
    detailAction.href = route;
    detailAction.setAttribute("href", route);
    detailAction.dataset.route = "";
    detailAction.textContent = `打开《${displayTitle(activeGraphNode)}》详情`;
  }

  function renderFusionReadout() {
    const profile = objectValue(objectValue(explorationPayload).fusion_profile);
    const dimensions = listValue(profile.dimensions).map(objectValue).filter((row) => textValue(row.value));
    if (!selectedSeeds.length || (!textValue(profile.headline) && !dimensions.length)) {
      fusionReadout.hidden = true;
      fusionReadout.replaceChildren();
      return;
    }
    fusionReadout.hidden = false;
    const copy = element("div", "observatory-neural__fusion-copy");
    copy.append(
      element("span", "observatory-neural__fusion-label", "本轮重组配方"),
      element("strong", "observatory-neural__fusion-title", textValue(profile.headline, "多维口味重组")),
      element("p", "observatory-neural__fusion-strategy", textValue(profile.strategy, "按类型、气质、主创与口碑共同排序。")),
    );
    const dimensionGrid = element("div", "observatory-neural__fusion-dimensions");
    for (const row of dimensions.slice(0, 5)) {
      const dimension = element("div", `observatory-neural__fusion-dimension observatory-neural__fusion-dimension--${textValue(row.key, "signal")}`);
      dimension.append(
        element("span", "observatory-neural__fusion-dimension-label", textValue(row.label, "分析维度")),
        element("strong", "observatory-neural__fusion-dimension-value", textValue(row.value)),
      );
      dimensionGrid.append(dimension);
    }
    const weights = objectValue(profile.weights);
    const weightRow = element("div", "observatory-neural__fusion-weights");
    for (const [label, value] of Object.entries(weights).slice(0, 4)) {
      const numeric = numberValue(value);
      if (!numeric) continue;
      appendPill(weightRow, "observatory-neural__fusion-weight", `${label} ${Math.round(numeric * 100)}%`);
    }
    fusionReadout.replaceChildren(copy, dimensionGrid, weightRow);
  }

  function renderSeedSelection({ loading = false, failed = false } = {}) {
    seedTray.replaceChildren();
    selectedSeeds.forEach((seed, index) => {
      const button = element("button", "observatory-neural__seed");
      button.type = "button";
      button.dataset.seedId = graphItemKey(seed);
      button.setAttribute("aria-label", `移除焦点《${displayTitle(seed)}》`);
      button.append(
        element("span", "observatory-neural__seed-index", String(index + 1).padStart(2, "0")),
        element("span", "observatory-neural__seed-title", displayTitle(seed)),
        element("span", "observatory-neural__seed-remove", "×"),
      );
      button.addEventListener("click", () => { void toggleGraphSeed(seed); });
      seedTray.append(button);
    });
    const hasMore = Boolean(objectValue(explorationPayload).has_more);
    clearSeeds.disabled = !selectedSeeds.length || loading;
    shuffleGraph.disabled = !selectedSeeds.length || loading || !hasMore;
    composeGraph.disabled = !selectedSeeds.length || loading;
    shuffleGraph.textContent = graphRound > 0 ? `换一批 · 第 ${graphRound + 1} 批` : "换一批";
    updateFocusComposerCopy({ loading });
    seedBar.dataset.state = failed ? "error" : loading ? "loading" : selectedSeeds.length > 1 ? "fusion" : selectedSeeds.length ? "single" : "idle";
    if (loading) {
      seedMode.textContent = selectedSeeds.length > 1 ? `正在计算 ${selectedSeeds.length} 个焦点的交集` : "正在重建相似作品邻域";
    } else if (failed) {
      seedMode.textContent = "本轮重建未完成，已保留上一张关系图";
    } else if (selectedSeeds.length > 1) {
      const strictCount = Math.max(0, Math.floor(numberValue(objectValue(explorationPayload).strict_count)));
      const poolSize = Math.max(0, Math.floor(numberValue(objectValue(explorationPayload).candidate_pool_size)));
      const ratingCoverage = Math.max(0, Math.floor(numberValue(objectValue(objectValue(explorationPayload).rating_coverage).percent)));
      seedMode.textContent = `多焦点交集 · ${strictCount ? `${strictCount} 个严格交集` : "混合补位"}${poolSize ? ` · ${poolSize} 部候选` : ""}${ratingCoverage ? ` · 评分覆盖 ${ratingCoverage}%` : ""}`;
    } else if (selectedSeeds.length === 1) {
      const resultCount = listValue(objectValue(explorationPayload).items).length;
      seedMode.textContent = `单焦点扩散 · 围绕《${displayTitle(selectedSeeds[0])}》${resultCount ? ` · ${resultCount} 个多样化节点` : ""}`;
    } else {
      seedMode.textContent = "单击节点开始探索";
    }
    if (!loading && !failed && selectedSeeds.length && graphElapsedMs > 0) {
      seedMode.setAttribute("title", `本轮重组耗时 ${Math.max(1, Math.round(graphElapsedMs))} 毫秒`);
    }
  }

  async function rebuildGraph() {
    const path = multiFocusDiscoveryPath(selectedSeeds, GRAPH_DISCOVERY_LIMIT, graphRound);
    if (!path) {
      explorationPayload = null;
      graphElapsedMs = 0;
      renderSeedSelection();
      renderFusionReadout();
      renderGraph();
      renderMetrics();
      return true;
    }
    const requestGeneration = ++graphGeneration;
    graphRequestController?.abort?.();
    const requestController = new AbortController();
    graphRequestController = requestController;
    canvasShell.classList.add("is-rebuilding");
    canvasShell.setAttribute("aria-busy", "true");
    fusionReadout.dataset.loading = "true";
    renderSeedSelection({ loading: true });
    const requestStartedAt = globalThis.performance?.now?.() || Date.now();
    const cachedGraph = graphPayloadCache.get(path);
    if (cachedGraph && Number(cachedGraph.expiresAt) > Date.now()) {
      explorationPayload = objectValue(cachedGraph.payload);
      graphElapsedMs = 0;
      renderGraph();
      renderMetrics();
      renderSeedSelection();
      renderFusionReadout();
      canvasShell.classList.remove("is-rebuilding");
      canvasShell.setAttribute("aria-busy", "false");
      delete fusionReadout.dataset.loading;
      if (graphRequestController === requestController) graphRequestController = null;
      return true;
    }
    try {
      const result = await fetchJson(path, {
        signal: requestController.signal,
        force: false,
        ttlMs: 120_000,
      });
      if (disposed || requestGeneration !== graphGeneration || requestController.signal.aborted) return false;
      explorationPayload = objectValue(result);
      graphPayloadCache.set(path, { payload: explorationPayload, expiresAt: Date.now() + GRAPH_CACHE_TTL_MS });
      while (graphPayloadCache.size > 12) graphPayloadCache.delete(graphPayloadCache.keys().next().value);
      graphRound = Math.max(0, Math.floor(numberValue(explorationPayload.round, graphRound)));
      graphElapsedMs = Math.max(
        numberValue(explorationPayload.calculation_ms),
        (globalThis.performance?.now?.() || Date.now()) - requestStartedAt,
      );
      const responseSeeds = listValue(explorationPayload.seeds).map(graphSeedRecord).filter((seed) => graphItemKey(seed));
      if (responseSeeds.length) selectedSeeds = responseSeeds.slice(-MAX_GRAPH_SEEDS);
      renderGraph();
      renderMetrics();
      renderSeedSelection();
      renderFusionReadout();
      // Warm the next batch after the current frame has settled. The server
      // rank cache means this is a small, non-blocking request and the next
      // click can be rendered without waiting for similarity scoring again.
      if (Boolean(explorationPayload.has_more) && selectedSeeds.length) {
        const nextPath = multiFocusDiscoveryPath(selectedSeeds, GRAPH_DISCOVERY_LIMIT, graphRound + 1);
        if (nextPath && !graphPayloadCache.has(nextPath)) {
          scheduleNextGraphBatch(nextPath);
        }
      }
      return true;
    } catch (error) {
      if (disposed || requestGeneration !== graphGeneration || requestController.signal.aborted || error?.name === "AbortError") return false;
      globalThis.console?.error?.("[CineScope] graph rebuild failed", error);
      renderSeedSelection({ failed: true });
      return false;
    } finally {
      if (!disposed && requestGeneration === graphGeneration) {
        canvasShell.classList.remove("is-rebuilding");
        canvasShell.setAttribute("aria-busy", "false");
        delete fusionReadout.dataset.loading;
        if (graphRequestController === requestController) graphRequestController = null;
      }
    }
  }

  async function toggleGraphSeed(node) {
    graphSelectionInitialized = true;
    manualFocusSelectionStarted = true;
    selectedSeeds = nextGraphSeeds(selectedSeeds, node);
    graphRound = 0;
    updateDetailAction(node);
    return rebuildGraph();
  }

  async function composeCurrentGraph() {
    if (!selectedSeeds.length || composeGraph.disabled) return false;
    graphRound = 0;
    setFocusSearchStatus(
      selectedSeeds.length > 1 ? `正在融合 ${selectedSeeds.length} 部作品的共同特征…` : `正在围绕《${displayTitle(selectedSeeds[0])}》生成推荐…`,
      "busy",
    );
    const rebuilt = await rebuildGraph();
    if (!disposed && rebuilt) setFocusSearchStatus(selectedSeeds.length > 1 ? "融合推荐已更新。" : "相似推荐已更新。", "success");
    return rebuilt;
  }

  async function shuffleGraphRound() {
    if (!selectedSeeds.length || shuffleGraph.disabled) return false;
    graphRound += 1;
    return rebuildGraph();
  }

  function clearGraphSeeds() {
    graphSelectionInitialized = true;
    manualFocusSelectionStarted = true;
    graphGeneration += 1;
    graphRequestController?.abort?.();
    graphRequestController = null;
    canvasShell.classList.remove("is-rebuilding");
    canvasShell.setAttribute("aria-busy", "false");
    selectedSeeds = [];
    explorationPayload = null;
    graphRound = 0;
    graphElapsedMs = 0;
    updateDetailAction(null);
    renderSeedSelection();
    renderFusionReadout();
    renderGraph();
    renderMetrics();
    setFocusSearchStatus("焦点已清空，可以搜索一部作品重新开始。", "success");
  }

  function renderMetrics() {
    const recent = objectValue(payload.recent);
    const latest = objectValue(payload.latest);
    const graph = currentGraph();
    const sourceCounts = objectValue(latest.source_counts);
    metricNodes.get("recent").textContent = compactNumber(recent.count);
    metricNodes.get("live").textContent = compactNumber(latest.live_count);
    metricNodes.get("nodes").textContent = compactNumber(graph.nodes.length);
    metricNodes.get("sources").textContent = compactNumber(Object.values(sourceCounts).filter((count) => numberValue(count) > 0).length);
    updated.textContent = `${formatTimestamp(latest.fetched_at || payload.generated_at)} 更新 · 自动刷新 5 分钟`;
  }

  function renderGraph() {
    controller?.dispose?.();
    const graph = currentGraph();
    const initialNode = graph.nodes.find((node) => textValue(node.id) === textValue(graph.focus_id)) || graph.nodes[0] || null;
    activeGraphNode = initialNode ? objectValue(initialNode) : null;
    updateDetailAction(activeGraphNode);
    renderNodeInspector(activeGraphNode);
    legend.replaceChildren();
    const legendButtons = new Map();
    const selectedIds = new Set(selectedSeeds.map(graphItemKey));
    for (const node of graph.nodes) {
      const nodeKey = graphItemKey(node);
      const matchKind = textValue(node.match_kind, node.is_seed ? "seed" : "similar");
      const button = element("button", `observatory-node-chip observatory-node-chip--${matchKind}${node.online ? " is-live" : ""}${selectedIds.has(nodeKey) ? " is-selected" : ""}`);
      button.type = "button";
      button.dataset.nodeId = textValue(node.id);
      button.dataset.matchKind = matchKind;
      button.setAttribute("aria-pressed", String(selectedIds.has(nodeKey)));
      const dot = element("span", "observatory-node-chip__dot");
      dot.style.setProperty("--node-tone", mediaTone(node.media_type).core);
      dot.style.setProperty("--node-strength", `${Math.round(Math.max(0.08, nodeRating(node) / 10) * 360)}deg`);
      const copy = element("span", "observatory-node-chip__copy");
      const matchCount = Math.max(0, Math.floor(numberValue(node.matched_seed_count)));
      const totalCount = Math.max(matchCount, Math.floor(numberValue(node.total_seed_count)) || (selectedSeeds.length || 1));
      const coverage = matchCount ? ` · 覆盖 ${matchCount}/${totalCount}` : "";
      const score = numberValue(node.fused_rating || node.rank_score);
      const scoreMeta = score > 0 ? ` · ${node.fused_rating ? "评分" : "匹配"} ${score.toFixed(node.fused_rating ? 1 : 2)}` : "";
      const matchMeta = node.match_kind === "blend" ? " · 混合补位" : "";
      const logic = nodeLogicCopy(node);
      const reasonChips = nodeReasonChips(node);
      const reason = reasonChips[0]
        || textValue(node.fusion_summary)
        || textValue(node.explanation)
        || (node.is_seed ? "当前推荐焦点" : "综合相似候选");
      copy.append(
        element("strong", "observatory-node-chip__title", displayTitle(node)),
        element("small", "observatory-node-chip__meta", `${mediaLabel(node)}${node.online ? " · 实时" : ""}${coverage}${scoreMeta}${matchMeta}`),
        element("small", "observatory-node-chip__reason", reason),
      );
      if (logic) button.setAttribute("title", `${textValue(node.fusion_summary) || "推荐节点"} · ${logic}`);
      button.append(dot, copy);
      if (textValue(node.fusion_summary)) button.setAttribute("title", `${textValue(node.fusion_summary)}${logic ? ` · ${logic}` : ""}`);
      button.addEventListener("pointerenter", () => {
        controller?.focusNode?.(node.id);
        prewarmDetailRoute(titleRoute(node.item || node));
        prewarmGraphForNode(node);
      });
      button.addEventListener("focus", () => {
        controller?.focusNode?.(node.id);
        prewarmGraphForNode(node);
      });
      button.addEventListener("click", () => { void toggleGraphSeed(node); });
      legendButtons.set(textValue(node.id), button);
      legend.append(button);
    }
    controller = createNeuralCanvas({
      canvas,
      graph,
      requestFrame,
      cancelFrame,
      windowTarget,
      documentTarget,
      onActivate: (node) => { void toggleGraphSeed(node); },
      onSelectionChange: (node) => {
        for (const [id, button] of legendButtons) button.setAttribute("aria-current", id === textValue(node?.id) ? "true" : "false");
        updateDetailAction(node);
        renderNodeInspector(node);
        neuralDescription.textContent = node
          ? `当前查看《${displayTitle(node)}》；具体类型、推荐理由与证据已集中在画布右上角。单击节点可加入或移除推荐焦点。`
          : "单击一部作品会重建相似邻域；继续选择最多三部作品，系统会优先寻找它们的内容交集。";
      },
      onHoverChange: (node) => renderNodeInspector(node || activeGraphNode),
      onViewChange: renderViewScale,
    });
  }

  function renderRecent() {
    const preservedScrollLeft = Math.max(0, numberValue(recentRail.scrollLeft));
    disposeFrames(recentFrames);
    const items = listValue(objectValue(payload.recent).items);
    recentRail.replaceChildren();
    if (!items.length) {
      recentRail.append(element("p", "observatory-empty", "同步豆瓣“看过”或在推荐卡片中标记“已看过”后，这里会形成按日期排列的观影时间线。"));
      return;
    }
    for (const item of items) {
      const card = renderRecentCard(item, recentFrames, recentMediaCoordinator);
      card.setAttribute("role", "listitem");
      recentRail.append(card);
    }
    recentRail.scrollLeft = preservedScrollLeft;
  }

  function renderSourceStrip(latest) {
    sourceStrip.replaceChildren();
    const statuses = objectValue(latest.source_status);
    const counts = objectValue(latest.source_counts);
    const keys = [...new Set([...Object.keys(statuses), ...Object.keys(counts)])].slice(0, 8);
    if (!keys.length) {
      sourceStrip.append(element("span", "observatory-source observatory-source--idle", "等待在线来源"));
      return;
    }
    for (const source of keys) {
      const state = textValue(objectValue(statuses[source]).state, numberValue(counts[source]) ? "ready" : "idle");
      const chip = element("span", `observatory-source observatory-source--${state}`);
      chip.append(element("strong", "observatory-source__name", providerLabel(source)), element("span", "observatory-source__count", compactNumber(counts[source])));
      sourceStrip.append(chip);
    }
  }

  function renderLatest(latest = objectValue(payload.latest)) {
    disposeFrames(latestFrames);
    liveGrid.replaceChildren();
    liveStatus.textContent = sourceStateCopy(latest);
    renderSourceStrip(latest);
    const items = listValue(latest.items).map(normalizedItem).filter(hasRenderablePoster);
    if (!items.length) {
      liveGrid.append(element("p", "observatory-empty", "本轮在线来源没有返回同时具备可靠图片与作品身份的内容，因此未展示半成品。稍后可再次刷新。"));
      return;
    }
    items.forEach((item, index) => {
      liveGrid.append(renderLatestCard(
        item,
        latestFrames,
        onExplore,
        prewarmDetailRoute,
        onNavigate,
        {
          coordinator: latestMediaCoordinator,
          priority: index < 6 ? MEDIA_LOAD_PRIORITY.foreground : MEDIA_LOAD_PRIORITY.visible,
        },
      ));
    });
  }

  function applyPayload(nextPayload, { preferredFilter = "all", preservedLatest = null } = {}) {
    payload = objectValue(nextPayload);
    latestCache.set("all", objectValue(payload.latest));
    activeFilter = FILTERS.some((entry) => entry.key === preferredFilter) ? preferredFilter : "all";
    if (activeFilter !== "all" && preservedLatest) latestCache.set(activeFilter, objectValue(preservedLatest));
    for (const [key, button] of filterButtons) button.setAttribute("aria-pressed", String(key === activeFilter));
    if (!graphSelectionInitialized) {
      const graph = buildExplorationGraph(payload);
      const focus = graph.nodes.find((node) => textValue(node.id) === textValue(graph.focus_id)) || graph.nodes[0];
      selectedSeeds = focus ? [graphSeedRecord(focus)] : [];
      manualFocusSelectionStarted = false;
      graphRound = 0;
      graphSelectionInitialized = true;
    }
    renderSeedSelection();
    renderFusionReadout();
    renderMetrics();
    renderGraph();
    renderRecent();
    renderLatest(latestCache.get(activeFilter) || objectValue(payload.latest));
  }

  async function load({ refresh = false } = {}) {
    const requestGeneration = ++generation;
    const preferredFilter = refresh ? activeFilter : "all";
    const preservedLatest = preferredFilter === "all" ? null : latestCache.get(preferredFilter);
    requestController?.abort?.();
    requestController = new AbortController();
    refreshButton.disabled = true;
    refreshButton.textContent = refresh ? "正在刷新在线资料" : "正在载入观影雷达";
    section.dataset.loading = "true";
    try {
      const query = `/api/v2/observatory?profile_key=default&limit=30${refresh ? "&refresh=1" : ""}`;
      const nextPayload = await fetchJson(query, { signal: requestController.signal, force: refresh, ttlMs: refresh ? 0 : 45_000 });
      if (disposed || requestGeneration !== generation || requestController.signal.aborted) return false;
      latestCache.clear();
      applyPayload(nextPayload, { preferredFilter, preservedLatest });
      if (preferredFilter !== "all") await selectFilter(preferredFilter, { refresh: true });
      section.dataset.state = "ready";
      if (!refresh && objectValue(nextPayload.latest).is_stale) {
        void Promise.resolve().then(() => {
          if (!disposed && generation === requestGeneration) void load({ refresh: true });
        });
      }
      return true;
    } catch (error) {
      if (disposed || requestController.signal.aborted || error?.name === "AbortError") return false;
      section.dataset.state = "error";
      liveStatus.textContent = "在线资料暂时不可用；最近观看与本地片库仍保持原样。";
      if (!payload.recent) {
        recentRail.replaceChildren(element("p", "observatory-empty", "观影雷达暂时无法读取数据，请稍后重试。"));
        liveGrid.replaceChildren(element("p", "observatory-empty", "在线来源连接失败，未展示不完整结果。"));
      }
      return false;
    } finally {
      if (!disposed && requestGeneration === generation) {
        refreshButton.disabled = false;
        refreshButton.textContent = "刷新在线资料";
        delete section.dataset.loading;
      }
    }
  }

  async function selectFilter(key, { refresh = false } = {}) {
    const filter = FILTERS.find((entry) => entry.key === key) || FILTERS[0];
    activeFilter = filter.key;
    for (const [filterKey, button] of filterButtons) button.setAttribute("aria-pressed", String(filterKey === activeFilter));
    const cached = latestCache.get(activeFilter);
    if (cached && !refresh) {
      renderLatest(cached);
      return true;
    }
    const requestGeneration = ++latestGeneration;
    latestController?.abort?.();
    latestController = new AbortController();
    livePanel.dataset.loading = "true";
    liveStatus.textContent = `正在更新${filter.label}在线资料`;
    try {
      const query = `/api/v2/discovery/latest?profile_key=default&limit=24&media_type=${encodeURIComponent(filter.mediaType)}${refresh ? "&refresh=1" : ""}`;
      const latest = await fetchJson(query, { signal: latestController.signal, force: refresh, ttlMs: refresh ? 0 : 45_000 });
      if (disposed || requestGeneration !== latestGeneration || latestController.signal.aborted || activeFilter !== filter.key) return false;
      latestCache.set(filter.key, objectValue(latest));
      renderLatest(latest);
      return true;
    } catch (error) {
      if (disposed || latestController.signal.aborted || error?.name === "AbortError") return false;
      liveStatus.textContent = `${filter.label}在线源暂时不可用，保留上一批结果。`;
      return false;
    } finally {
      if (!disposed && requestGeneration === latestGeneration) delete livePanel.dataset.loading;
    }
  }

  const onRefresh = () => { void load({ refresh: true }); };
  const onFocusSearchButton = () => { void searchFocusCandidates(focusSearchInput.value); };
  const onFocusSearchSubmit = (event) => {
    event?.preventDefault?.();
    const query = textValue(focusSearchInput.value);
    const reusableCandidates = query && query === focusSearchQuery && focusSearchCandidates.length;
    if (reusableCandidates) void selectManualFocusCandidate(focusSearchCandidates[0]);
    else void searchFocusCandidates(query, { selectFirst: true });
  };
  const onFocusSearchKeyDown = (event) => {
    if (event?.key !== "Escape") return;
    clearFocusSearchTimer();
    focusSearchController?.abort?.();
    focusSearchCandidates = [];
    focusSearchQuery = "";
    renderFocusSearchResults();
    setFocusSearchStatus("候选已收起，当前焦点保持不变。 ");
    event.preventDefault?.();
  };
  const onFocusCompositionStart = () => { focusSearchComposing = true; };
  const onFocusCompositionEnd = () => { focusSearchComposing = false; scheduleFocusSearch(); };
  refreshButton.addEventListener("click", onRefresh);
  focusSearchButton.addEventListener("click", onFocusSearchButton);
  focusSearchForm.addEventListener("submit", onFocusSearchSubmit);
  focusSearchInput.addEventListener("input", scheduleFocusSearch);
  focusSearchInput.addEventListener("keydown", onFocusSearchKeyDown);
  focusSearchInput.addEventListener("compositionstart", onFocusCompositionStart);
  focusSearchInput.addEventListener("compositionend", onFocusCompositionEnd);
  resetFocusStart.addEventListener("click", beginManualFocusSelection);
  composeGraph.addEventListener("click", composeCurrentGraph);
  shuffleGraph.addEventListener("click", shuffleGraphRound);
  clearSeeds.addEventListener("click", clearGraphSeeds);
  for (const [key, button] of filterButtons) button.addEventListener("click", () => { void selectFilter(key); });
  refreshTimer = setIntervalFn(() => {
    if (!disposed && documentTarget?.visibilityState !== "hidden") void load({ refresh: true });
  }, AUTO_REFRESH_MS);

  return {
    ready: Promise.resolve(false),
    mount() {
      this.ready = load();
      return this.ready;
    },
    refresh: () => load({ refresh: true }),
    selectFilter,
    snapshot: () => ({
      disposed,
      activeFilter,
      recentCount: listValue(objectValue(payload.recent).items).length,
      latestCount: listValue((latestCache.get(activeFilter) || objectValue(payload.latest)).items).map(normalizedItem).filter(hasRenderablePoster).length,
      graph: controller?.snapshot?.() || {},
      selectedSeedIds: selectedSeeds.map(graphItemKey),
      selectionMode: textValue(objectValue(explorationPayload).selection_mode, selectedSeeds.length > 1 ? "hybrid" : selectedSeeds.length ? "single" : "idle"),
      graphRound,
      graphElapsedMs,
      candidatePoolSize: Math.max(0, Math.floor(numberValue(objectValue(explorationPayload).candidate_pool_size))),
      ratingCoverage: Math.max(0, numberValue(objectValue(objectValue(explorationPayload).rating_coverage).percent)),
      manualFocusSelectionStarted,
      focusSearchCandidateCount: focusSearchCandidates.length,
      focusSearchQuery,
      autoRefreshMs: AUTO_REFRESH_MS,
    }),
    dispose() {
      if (disposed) return;
      disposed = true;
      generation += 1;
      latestGeneration += 1;
      graphGeneration += 1;
      requestController?.abort?.();
      latestController?.abort?.();
      graphRequestController?.abort?.();
      focusSearchController?.abort?.();
      focusSearchController = null;
      clearFocusSearchTimer();
      for (const timer of graphPrefetchTimers.values()) {
        try { (windowTarget?.clearTimeout || globalThis.clearTimeout)?.(timer); } catch { /* optional timer */ }
      }
      graphPrefetchTimers.clear();
      for (const request of graphPrefetchControllers.values()) request.abort?.();
      graphPrefetchControllers.clear();
      controller?.dispose?.();
      disposeFrames(recentFrames);
      disposeFrames(latestFrames);
      if (refreshTimer !== null) clearIntervalFn(refreshTimer);
      refreshTimer = null;
      refreshButton.removeEventListener("click", onRefresh);
      focusSearchButton.removeEventListener("click", onFocusSearchButton);
      focusSearchForm.removeEventListener("submit", onFocusSearchSubmit);
      focusSearchInput.removeEventListener("input", scheduleFocusSearch);
      focusSearchInput.removeEventListener("keydown", onFocusSearchKeyDown);
      focusSearchInput.removeEventListener("compositionstart", onFocusCompositionStart);
      focusSearchInput.removeEventListener("compositionend", onFocusCompositionEnd);
      resetFocusStart.removeEventListener("click", beginManualFocusSelection);
      composeGraph.removeEventListener("click", composeCurrentGraph);
      shuffleGraph.removeEventListener("click", shuffleGraphRound);
      clearSeeds.removeEventListener("click", clearGraphSeeds);
      zoomOutButton.removeEventListener("click", onZoomOut);
      zoomInButton.removeEventListener("click", onZoomIn);
      resetViewButton.removeEventListener("click", onResetView);
    },
  };
}

let activeController = null;

export function renderObservatory(root, options = {}) {
  activeController?.dispose?.();
  const controller = createObservatoryController({ root, ...options });
  activeController = controller;
  controller.mount();
  return controller;
}

export function destroyObservatory() {
  activeController?.dispose?.();
  activeController = null;
}
