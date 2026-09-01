import { getV2 } from "../core/api.js";

const GROUPS = Object.freeze([
  ["stable", "核心偏好", "长期稳定命中的题材、创作者与地区线索。"],
  ["conflicting", "口味张力", "你对这些方向既有喜欢，也有保留。"],
  ["recent", "近期活跃", "最近进入档案的有效信号，不虚构固定时间窗口。"],
  ["negative", "明确避雷", "低分记录与主动反馈形成的回避方向。"],
  ["unexplored", "待探索", "想看或尚未评分的方向，用来保持推荐的新鲜感。"],
]);

const SOURCE_LABELS = Object.freeze({
  "library-rating": "豆瓣评分记录",
  "douban-sync": "豆瓣同步",
  feedback: "你的反馈",
  wishlist: "想看清单",
  unrated: "未评分片库",
  library: "本地片库",
  rating: "评分记录",
  sync: "同步记录",
  wish: "想看记录",
});

const FEATURE_LABELS = Object.freeze({
  genre: "题材",
  country: "地区",
  director: "导演",
  cast: "演员",
  media_type: "类型",
  mood: "氛围",
  pace: "节奏",
  term: "关键词",
  item: "作品",
});

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function stableItemKey(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return /^[A-Za-z0-9:._~-]{1,256}$/.test(text) ? text : "";
}

function countValue(value) {
  return Number.isInteger(value) && value >= 0 ? value : 0;
}

function featureCopy(rawFeature, groupKey) {
  const feature = typeof rawFeature === "string" && rawFeature.trim() ? rawFeature.trim() : "未命名线索";
  const separator = feature.indexOf(":");
  if (separator < 1) return feature;
  const kind = feature.slice(0, separator);
  const value = feature.slice(separator + 1).trim();
  if (!value) return FEATURE_LABELS[kind] || feature;
  if (groupKey === "negative") return `回避${value}`;
  if (groupKey === "conflicting") return `对${value}存在分歧`;
  if (groupKey === "unexplored") return `待探索：${value}`;
  if (kind === "genre") return `偏爱${value}`;
  if (kind === "director") return `关注导演 ${value}`;
  if (kind === "cast") return `熟悉演员 ${value}`;
  if (kind === "country") return `常看${value}作品`;
  if (kind === "media_type") return `偏好${value}`;
  return `${FEATURE_LABELS[kind] || "偏好"}：${value}`;
}

function signalStrength(value) {
  const score = typeof value === "number" && Number.isFinite(value) ? Math.abs(value) : 0;
  if (score >= 20) return ["非常鲜明", 100];
  if (score >= 10) return ["鲜明", 82];
  if (score >= 5) return ["稳定", 66];
  if (score >= 2) return ["可参考", 48];
  return ["探索中", 30];
}

function sourceCopy(sources) {
  const values = Array.isArray(sources)
    ? sources.map((source) => SOURCE_LABELS[source] || "本地行为记录").filter(Boolean)
    : [];
  return [...new Set(values)].join(" · ") || "本地行为记录";
}

function evidenceEntries(signal) {
  const rows = Array.isArray(signal?.evidence_titles) ? signal.evidence_titles : [];
  return rows.flatMap((entry) => {
    const id = stableItemKey(entry?.id);
    const title = typeof entry?.title === "string" && entry.title.trim() ? entry.title.trim() : "";
    return id && title ? [{ id, title }] : [];
  }).slice(0, 4);
}

function signalCard(signal, groupKey) {
  const card = element("article", "taste-signal");
  const heading = element("div", "taste-signal__heading");
  const feature = element("h3", "taste-signal__feature", featureCopy(signal?.feature, groupKey));
  const [strengthLabel, strengthPercent] = signalStrength(signal?.score);
  const strength = element("span", "taste-signal__strength", strengthLabel);
  strength.dataset.strength = String(strengthPercent);
  heading.append(feature, strength);

  const meter = element("div", "taste-signal__meter");
  meter.setAttribute("aria-label", `信号强度：${strengthLabel}`);
  meter.append(element("span", "taste-signal__meter-fill"));
  meter.firstElementChild.style.setProperty("--taste-strength", `${strengthPercent}%`);

  const count = Number.isInteger(signal?.evidence_count)
    ? Math.max(0, signal.evidence_count)
    : Array.isArray(signal?.evidence_item_ids) ? signal.evidence_item_ids.length : 0;
  const context = element("p", "taste-signal__context", `来自 ${count} 部作品 · ${sourceCopy(signal?.sources)}`);
  const evidence = element("div", "taste-signal__evidence");
  evidence.append(element("span", "taste-signal__evidence-label", "代表作品"));
  for (const entry of evidenceEntries(signal)) {
    const link = element("a", "taste-signal__evidence-link", entry.title);
    link.setAttribute("href", `/title/${encodeURIComponent(entry.id)}`);
    link.setAttribute("data-route", "");
    evidence.append(link);
  }
  if (evidence.children.length === 1) evidence.append(element("span", "taste-signal__empty", "证据已计入模型，暂无可打开标题"));
  card.append(heading, meter, context, evidence);
  return card;
}

function summaryMetric(label, value, detail) {
  const card = element("article", "taste-overview__metric");
  card.append(
    element("span", "taste-overview__label", label),
    element("strong", "taste-overview__value", String(countValue(value))),
    element("span", "taste-overview__detail", detail),
  );
  return card;
}

function renderPayload(section, payload) {
  const summary = payload?.summary && typeof payload.summary === "object" ? payload.summary : {};
  const overview = element("section", "taste-overview");
  overview.setAttribute("aria-label", "口味档案概览");
  overview.append(
    summaryMetric("评分证据", summary.rated_count, "真实参与个性化排序"),
    summaryMetric("高分偏好", summary.liked_count, "用于寻找剧情与品质同类"),
    summaryMetric("低分避雷", summary.disliked_count, "用于降低踩雷概率"),
  );

  const groups = payload?.groups && typeof payload.groups === "object" ? payload.groups : {};
  const grid = element("div", "taste-groups");
  for (const [key, label, description] of GROUPS) {
    const group = element("details", "taste-group");
    group.dataset.tasteGroup = key;
    group.open = key === "stable";
    const signals = Array.isArray(groups[key]) ? groups[key] : [];
    const summaryRow = element("summary", "taste-group__summary");
    const summaryCopy = element("span", "taste-group__summary-copy");
    summaryCopy.append(
      element("strong", "taste-group__title", label),
      element("span", "taste-group__description", description),
    );
    summaryRow.append(summaryCopy, element("span", "taste-group__count", `${signals.length} 条`));
    const body = element("div", "taste-group__body");
    if (signals.length) body.append(...signals.map((signal) => signalCard(signal, key)));
    else body.append(element("p", "space-empty", "当前没有可展示的有效信号。"));
    group.append(summaryRow, body);
    grid.append(group);
  }
  section.append(overview, grid);
}

let activeController = null;

export function renderTasteDna(root, { fetchJson = getV2, profileKey = "default" } = {}) {
  if (!root) throw new TypeError("Taste DNA requires a root element");
  activeController?.dispose();
  const controller = new AbortController();
  let disposed = false;
  const section = element("section", "space space--taste");
  section.dataset.space = "taste";
  const header = element("header", "space-header taste-header");
  const copy = element("div", "space-header__copy");
  const title = element("h1", "space-title taste-title");
  title.append(
    element("span", "taste-title__line", "你的口味，"),
    element("span", "taste-title__line", "不是一串标签。"),
  );
  copy.append(
    element("p", "eyebrow", "可读口味画像"),
    title,
  );
  header.append(copy, element("p", "space-summary", "这里把豆瓣评分、想看记录与主动反馈整理成可解释的偏好地图。机器 ID 默认隐藏，只保留你看得懂、能点开的作品证据。"));
  section.append(header, element("div", "taste-loading", "正在整理你的口味证据…"));
  root.replaceChildren(section);

  const safeProfile = /^[A-Za-z0-9._~-]{1,128}$/.test(profileKey) ? profileKey : "default";
  const ready = fetchJson(`/api/v2/taste?profile_key=${encodeURIComponent(safeProfile)}`, { signal: controller.signal })
    .then((payload) => {
      if (!disposed && !controller.signal.aborted) {
        section.querySelector?.(".taste-loading")?.remove?.();
        renderPayload(section, payload);
      }
      return payload;
    })
    .catch(() => {
      if (!disposed && !controller.signal.aborted) {
        section.querySelector?.(".taste-loading")?.remove?.();
        section.append(element("p", "space-error", "口味档案暂时无法读取。"));
      }
      return null;
    });

  const api = {
    ready,
    dispose() { disposed = true; controller.abort(); },
  };
  activeController = api;
  return api;
}

export function destroyTasteDna() {
  activeController?.dispose();
  activeController = null;
}
