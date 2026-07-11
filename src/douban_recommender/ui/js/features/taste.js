import { getV2 } from "../core/api.js";

const GROUPS = Object.freeze([
  ["stable", "稳定偏好"],
  ["conflicting", "冲突信号"],
  ["recent", "最近信号（无固定时间窗）"],
  ["negative", "负向偏好"],
  ["unexplored", "未探索方向"],
]);

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

function scoreText(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
}

function signalCard(signal) {
  const card = element("article", "taste-signal");
  const feature = element("h3", "taste-signal__feature", typeof signal?.feature === "string" ? signal.feature : "未命名信号");
  const score = element("p", "taste-signal__score", `信号分数 ${scoreText(signal?.score)}`);
  const sources = Array.isArray(signal?.sources) ? signal.sources.filter((source) => typeof source === "string" && source.trim()) : [];
  const source = element("p", "taste-signal__sources", sources.length ? `来源：${sources.join(" · ")}` : "来源：尚未提供");
  const evidence = element("div", "taste-signal__evidence");
  evidence.append(element("span", "taste-signal__evidence-label", "本地证据"));
  const ids = Array.isArray(signal?.evidence_item_ids) ? signal.evidence_item_ids : [];
  for (const rawId of ids) {
    const id = stableItemKey(rawId);
    if (!id) continue;
    const link = element("a", "taste-signal__evidence-link", id);
    link.setAttribute("href", `/title/${encodeURIComponent(id)}`);
    link.setAttribute("data-route", "");
    evidence.append(link);
  }
  if (evidence.children.length === 1) evidence.append(element("span", "taste-signal__empty", "暂无本地证据链接"));
  card.append(feature, score, source, evidence);
  return card;
}

function renderPayload(section, payload) {
  const groups = payload?.groups && typeof payload.groups === "object" ? payload.groups : {};
  const grid = element("div", "taste-groups");
  for (const [key, label] of GROUPS) {
    const group = element("section", "taste-group");
    group.dataset.tasteGroup = key;
    group.append(element("h2", "taste-group__title", label));
    const signals = Array.isArray(groups[key]) ? groups[key] : [];
    if (signals.length) group.append(...signals.map(signalCard));
    else group.append(element("p", "space-empty", "当前没有可展示的信号。"));
    grid.append(group);
  }
  section.append(grid);
}

let activeController = null;

export function renderTasteDna(root, { fetchJson = getV2, profileKey = "default" } = {}) {
  if (!root) throw new TypeError("Taste DNA requires a root element");
  activeController?.dispose();
  const controller = new AbortController();
  let disposed = false;
  const section = element("section", "space space--taste");
  section.dataset.space = "taste";
  const header = element("header", "space-header");
  const copy = element("div", "space-header__copy");
  copy.append(element("p", "eyebrow", "TASTE DNA / EVIDENCE"), element("h1", "space-title", "口味 DNA"));
  header.append(copy, element("p", "space-summary", "五组信号均来自现有档案；“最近”不代表固定天数。"));
  section.append(header);
  root.replaceChildren(section);

  const safeProfile = /^[A-Za-z0-9._~-]{1,128}$/.test(profileKey) ? profileKey : "default";
  const ready = fetchJson(`/api/v2/taste?profile_key=${encodeURIComponent(safeProfile)}`, { signal: controller.signal })
    .then((payload) => {
      if (!disposed && !controller.signal.aborted) renderPayload(section, payload);
      return payload;
    })
    .catch((error) => {
      if (!disposed && !controller.signal.aborted) section.append(element("p", "space-error", "口味档案暂时无法读取。"));
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
