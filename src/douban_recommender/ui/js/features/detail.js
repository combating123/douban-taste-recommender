import { postV2 } from "../core/api.js";
import { adaptCatalogMedia, adaptPersonMedia } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";
import { renderTitleCard } from "../components/title-card.js";
import { openPersonSheet, setPersonContext } from "./people.js";

const RELATION_LIMIT = 9;
const RELATION_BUDGET_MS = 900;
const SAFE_ROUTE_SEGMENT = /^[A-Za-z0-9:._~-]+$/;
const portraitPrefetchInFlight = new Set();
const portraitPrefetched = new Set();

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function listValue(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()) : [];
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
  api: { postV2 },
  openPersonSheet,
  onExploreUniverse: () => {},
};

export function configureDetail(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    fetchJson: options.fetchJson || dependencies.fetchJson,
    api: options.api || { postV2: options.postV2 || dependencies.api.postV2 },
    openPersonSheet: options.openPersonSheet || dependencies.openPersonSheet,
    onExploreUniverse: options.onExploreUniverse || dependencies.onExploreUniverse,
  };
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

function renderHero(title) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const hero = element("section", "detail-hero");
  hero.id = "overview";
  const backdrop = element("div", "detail-backdrop");
  backdrop.append(renderMediaFrame(adaptCatalogMedia(title, "backdrop")));

  const content = element("div", "detail-hero__content");
  const poster = element("div", "detail-poster");
  poster.append(renderMediaFrame(adaptCatalogMedia(title, "poster")));
  const copy = element("div", "detail-hero__copy");
  copy.append(element("p", "eyebrow", "TITLE DETAIL / CINEMATIC SPACE"));
  copy.append(element("h1", "detail-hero__title", textValue(title?.title, "未命名作品")));
  const metadata = [
    Number.isFinite(title?.year) ? String(title.year) : "",
    textValue(title?.media_type),
    textValue(title?.state),
  ].filter(Boolean);
  if (metadata.length) copy.append(element("p", "detail-hero__metadata", metadata.join(" · ")));
  copy.append(element("p", "detail-hero__summary", textValue(item.summary) || textValue(item.intro) || "资料有限：本地片库暂未记录作品简介。"));
  const source = element("p", "detail-verified-note", "已核对范围：当前本地片库记录；缺失字段不会自动补写。");
  copy.append(source);
  content.append(poster, copy);
  hero.append(backdrop, content);
  return hero;
}

function renderTabs() {
  const tabs = element("nav", "detail-tabs");
  tabs.setAttribute("aria-label", "作品详情分区");
  for (const [href, label] of [["#overview", "概览"], ["#scores", "评分解释"], ["#facts", "已核事实"], ["#people", "演职人员"], ["#relations", "本地关联"]]) {
    const link = element("a", "detail-tab", label);
    link.setAttribute("href", href);
    tabs.append(link);
  }
  return tabs;
}

function renderScores(title) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const section = element("section", "detail-section detail-scores");
  section.id = "scores";
  section.append(element("p", "eyebrow", "EXPLAINABLE SIGNALS"), element("h2", "detail-section__title", "评分与匹配如何理解"));
  const grid = element("div", "detail-score-grid");
  const genreSignals = [...listValue(item.genres), ...listValue(item.directors).slice(0, 2)];
  grid.append(
    scoreCard("豆瓣评分", numericText(item.douban_rating), "来自本地目录中保存的公开评分字段。"),
    scoreCard("我的评分", numericText(item.my_rating), Number.isFinite(item.my_rating) ? "来自你的本地观影记录。" : "本地记录中尚未评分。"),
    scoreCard("观看状态", textValue(title?.state, "资料有限"), "来自本地片库状态，不推断未记录行为。"),
    scoreCard("匹配线索", genreSignals.length ? genreSignals.join(" / ") : "资料有限", genreSignals.length ? "展示已记录的类型与主创线索，不代表算法重新打分。" : "缺少可解释的类型或主创字段。"),
  );
  section.append(grid);
  return section;
}

function renderFacts(title) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const section = element("section", "detail-section detail-facts");
  section.id = "facts";
  section.append(element("p", "eyebrow", "VERIFIED FACTS / LOCAL CATALOG"), element("h2", "detail-section__title", "已记录事实"));
  const values = [
    ["年份", Number.isFinite(title?.year) ? String(title.year) : ""],
    ["媒介类型", textValue(title?.media_type)],
    ["国家 / 地区", listValue(item.countries).join(" / ")],
    ["类型", listValue(item.genres).join(" / ")],
    ["导演", listValue(item.directors).join(" / ")],
    ["片长", Number.isFinite(item.duration) ? `${item.duration} 分钟` : ""],
    ["集数", Number.isFinite(item.episode_count) ? String(item.episode_count) : ""],
  ].filter(([, value]) => value);
  if (!values.length) {
    section.append(element("p", "detail-limited", "资料有限：本地片库尚未记录可核对的事实字段。"));
    return section;
  }
  const facts = element("dl", "detail-facts__grid");
  for (const [label, value] of values) facts.append(fact(label, value));
  section.append(facts);
  return section;
}

function renderPeople(title) {
  const section = element("section", "detail-section detail-people");
  section.id = "people";
  section.append(element("p", "eyebrow", "CAST & CREW"), element("h2", "detail-section__title", "演职人员"));
  const people = Array.isArray(title?.people) ? title.people : [];
  if (!people.length) {
    section.append(element("p", "detail-limited", "资料有限：本地片库尚未记录演职人员身份。"));
    return section;
  }
  const rail = element("div", "detail-people-rail");
  rail.setAttribute("role", "list");
  for (const person of people) {
    const entry = element("div", "detail-people-rail__item");
    entry.setAttribute("role", "listitem");
    const button = element("button", "person-card");
    button.type = "button";
    button.setAttribute("aria-label", `打开${textValue(person?.name, "未命名人物")}人物聚光灯`);
    const portrait = element("div", "person-card__portrait");
    portrait.append(renderMediaFrame(adaptPersonMedia(person)));
    const copy = element("div", "person-card__copy");
    copy.append(
      element("span", "person-card__role", roleLabel(person?.role)),
      element("strong", "person-card__name", textValue(person?.name, "未命名人物")),
      element("span", "person-card__status", adaptPersonMedia(person).status === "ready" ? "本地肖像已就绪" : "身份卡 · 肖像待补"),
    );
    button.append(portrait, copy);
    button.addEventListener("click", () => {
      const rect = typeof button.getBoundingClientRect === "function" ? button.getBoundingClientRect() : null;
      void dependencies.openPersonSheet(textValue(person?.id), rect);
    });
    entry.append(button);
    rail.append(entry);
  }
  section.append(rail);
  return section;
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
    element("p", "eyebrow", "LOCAL RELATIONSHIPS / CATALOG EVIDENCE"),
    element("h2", "detail-section__title", "本地关联路径"),
    element("p", "detail-section__deck", "以下关系来自本地片库共同字段，只用于关系预览，不代表经过服务端验证的推荐结论。"),
  );
  const universeAction = element("button", "detail-universe-action route-recovery__action", "在口味宇宙展开");
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

  const worksHeading = element("h3", "detail-related-works__title", "关联作品区");
  const works = element("div", "detail-related-works");
  works.setAttribute("role", "list");
  for (const node of nodes) {
    const itemKey = relationNodeKey(node);
    const edge = edgeFor(universe, itemKey);
    const item = element("div", "detail-related-works__item");
    item.setAttribute("role", "listitem");
    item.append(renderTitleCard({
      ...node,
      item_key: itemKey,
      metadata: [node.year ? String(node.year) : "", textValue(node.media_type)].filter(Boolean),
      reason: relationReason(edge, "本地关联"),
    }));
    works.append(item);
  }
  section.append(preview, worksHeading, works);
  return section;
}

function renderDetailPage(title, universe) {
  const page = element("article", "detail-page route-view--enter");
  page.append(renderHero(title), renderTabs(), renderScores(title), renderFacts(title), renderPeople(title), renderRelations(title, universe));
  return page;
}

function recoveryPanel(titleId, retry) {
  const panel = element("section", "route-recovery detail-recovery");
  panel.append(
    element("p", "eyebrow", "TITLE / RECOVERY"),
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

async function boundedUniverse(titleId, signal) {
  const request = dependencies.fetchJson(
    `/api/v2/universe?focus=${encodeURIComponent(titleId)}&limit=${RELATION_LIMIT}`,
    { signal },
  ).catch(() => null);
  let timeoutId = null;
  const timeout = new Promise((resolve) => {
    timeoutId = setTimeout(() => resolve(null), RELATION_BUDGET_MS);
  });
  try {
    return await Promise.race([request, timeout]);
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Enqueues only directors and the first eight cast portraits. Name matching is
 * exact against title.people, while every job uses the backend-provided person id.
 */
export function prefetchVisiblePeople(title = {}) {
  const item = title?.item && typeof title.item === "object" ? title.item : {};
  const people = Array.isArray(title?.people) ? title.people : [];
  const directors = listValue(item.directors);
  const casts = listValue(item.casts);
  const requestedNames = [...directors, ...casts.slice(0, 8)];
  const uniquePeople = [];
  const seen = new Set();
  for (const name of requestedNames) {
    const person = people.find((candidate) => textValue(candidate?.name) === name);
    const personId = textValue(person?.id);
    if (!personId || seen.has(personId)) continue;
    seen.add(personId);
    if (adaptPersonMedia(person).status === "ready" || portraitPrefetchInFlight.has(personId) || portraitPrefetched.has(personId)) continue;
    uniquePeople.push(person);
  }

  const jobs = uniquePeople.map(async (person) => {
    const personId = textValue(person.id);
    portraitPrefetchInFlight.add(personId);
    try {
      const job = await dependencies.api.postV2("/api/v2/media/jobs", {
        kind: "portrait",
        identity_key: personId,
        person_name: textValue(person.name),
        occupations: [textValue(person.role, "cast")],
        work_context: [textValue(title?.title, textValue(item.title, "当前作品"))],
        priority: 0,
      });
      if (job && typeof job === "object") portraitPrefetched.add(personId);
      return job;
    } catch {
      return null;
    } finally {
      portraitPrefetchInFlight.delete(personId);
    }
  });
  return Promise.all(jobs);
}

export async function renderTitleDetail(titleId, options = {}) {
  const cleanId = apiRouteSegment(titleId);
  if (!cleanId) return null;
  try {
    const universePromise = boundedUniverse(cleanId, options.signal);
    const title = await dependencies.fetchJson(`/api/v2/titles/${cleanId}`, { signal: options.signal });
    if (options.signal?.aborted || (typeof options.isCurrent === "function" && !options.isCurrent())) return null;
    const universe = await universePromise;
    if (options.signal?.aborted || (typeof options.isCurrent === "function" && !options.isCurrent())) return null;
    const page = renderDetailPage(title, universe || {});
    const committed = await commitView(page, { heading: textValue(title?.title, "作品详情") }, options);
    if (!committed) return null;
    setPersonContext(title);
    void prefetchVisiblePeople(title);
    return page;
  } catch (error) {
    if (options.signal?.aborted || error?.name === "AbortError") return null;
    const recovery = recoveryPanel(cleanId, () => { void renderTitleDetail(cleanId, options); });
    return await commitView(recovery, { heading: "作品详情恢复" }, options) ? recovery : null;
  }
}
