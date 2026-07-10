import { adaptPersonMedia } from "../core/media.js";
import { renderMediaFrame } from "../components/media-frame.js";
import { renderTitleCard, titleRouteForItem } from "../components/title-card.js";

const SAFE_ROUTE_SEGMENT = /^[A-Za-z0-9:._~-]+$/;

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
  overlayRoot: null,
  fetchJson: requestJson,
};
let titleContext = null;
let closeActiveSheet = null;
let sheetGeneration = 0;

export function configurePeople(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    fetchJson: options.fetchJson || dependencies.fetchJson,
  };
}

export function setPersonContext(title = null) {
  titleContext = title && typeof title === "object" ? title : null;
}

function canRestoreFocus(trigger) {
  if (!trigger || typeof trigger.focus !== "function" || trigger.isConnected === false || trigger.disabled === true || trigger.hidden === true) return false;
  if (trigger.inert === true) return false;
  const ariaHidden = typeof trigger.getAttribute === "function" ? trigger.getAttribute("aria-hidden") : null;
  return ariaHidden !== "true";
}

export function closePersonSheet({ restoreFocus = true } = {}) {
  const close = closeActiveSheet;
  if (typeof close !== "function") return false;
  closeActiveSheet = null;
  close({ restoreFocus });
  return true;
}

function contextPerson(personId) {
  const people = Array.isArray(titleContext?.people) ? titleContext.people : [];
  return people.find((person) => textValue(person?.id) === personId) || null;
}

function roleLabel(role) {
  if (role === "director") return "导演";
  if (role === "cast") return "演员";
  return textValue(role, "主创");
}

function personRoute(personId) {
  const cleanId = apiRouteSegment(personId);
  return cleanId ? `/person/${cleanId}` : "";
}

function titleContextLink(onNavigate = () => {}) {
  const route = titleRouteForItem(titleContext || {});
  if (!route) return null;
  const link = element("a", "person-origin__link", `返回《${textValue(titleContext?.title, "当前作品")}》`);
  link.setAttribute("href", route);
  link.setAttribute("data-route", "");
  link.addEventListener("click", onNavigate);
  return link;
}

function renderOriginContext(personId, compact = false, onNavigate = () => {}) {
  const context = element("div", compact ? "person-origin person-origin--compact" : "person-origin");
  const matched = contextPerson(personId);
  const workTitle = textValue(titleContext?.title);
  if (workTitle) {
    context.append(
      element("p", "eyebrow", "ORIGIN TITLE / 原作品上下文"),
      element("p", "person-origin__copy", `${roleLabel(matched?.role)} · 《${workTitle}》`),
    );
    const link = titleContextLink(onNavigate);
    if (link) context.append(link);
  } else {
    context.append(element("p", "person-origin__copy", "资料有限：当前没有可确认的原作品上下文。"));
  }
  return context;
}

function renderPersonIdentity(person, { compact = false } = {}) {
  const identity = element("div", compact ? "person-identity person-identity--compact" : "person-identity");
  const media = element("div", "person-identity__portrait");
  media.append(renderMediaFrame(adaptPersonMedia(person)));
  const copy = element("div", "person-identity__copy");
  copy.append(element("p", "eyebrow", compact ? "PERSON SPOTLIGHT" : "PERSON / LOCAL EVIDENCE"));
  copy.append(element(compact ? "h2" : "h1", "person-identity__name", textValue(person?.name, "未命名人物")));
  const aliases = listValue(person?.aliases);
  if (aliases.length) copy.append(element("p", "person-identity__aliases", aliases.join(" · ")));
  const bio = textValue(person?.bio);
  copy.append(element("p", "person-identity__bio", bio || "资料有限：本地片库暂未记录人物简介。"));
  identity.append(media, copy);
  return identity;
}

function sheetActions(personId, onNavigate = () => {}) {
  const actions = element("div", "person-sheet__actions");
  const fullPage = element("a", "person-sheet__full-link", "进入人物全页");
  fullPage.setAttribute("href", personRoute(personId));
  fullPage.setAttribute("data-route", "");
  fullPage.addEventListener("click", onNavigate);
  actions.append(fullPage);
  return actions;
}

function sheetContent(personId, person, onNavigate = () => {}) {
  const content = element("div", "person-sheet__content");
  content.append(
    renderPersonIdentity(person, { compact: true }),
    sheetActions(personId, onNavigate),
    renderOriginContext(personId, true, onNavigate),
  );
  return content;
}

function sheetFailureContent(personId, onNavigate = () => {}) {
  const content = element("div", "person-sheet__content person-sheet__content--failure");
  const failure = element("div", "person-sheet__failure");
  failure.append(
    element("strong", "person-sheet__failure-title", "人物资料暂时无法读取"),
    element("p", "person-sheet__failure-copy", "原作品上下文仍保留在此处，可继续进入人物全页或返回原作品。"),
  );
  content.append(failure, sheetActions(personId, onNavigate), renderOriginContext(personId, true, onNavigate));
  return content;
}

function fallbackPerson(personId) {
  const matched = contextPerson(personId);
  return {
    id: personId,
    name: textValue(matched?.name, "未命名人物"),
    aliases: [],
    bio: "",
    portrait: matched?.portrait || { url: "", media_status: textValue(matched?.media_status, "pending") },
    media_status: textValue(matched?.media_status, "pending"),
    known_for: [],
    evidence: [],
  };
}

/**
 * Opens a contextual person sheet in #overlay-root. The sheet is always
 * dismissible and restores focus to the element that launched it.
 */
export async function openPersonSheet(personId, originRect = null) {
  const cleanId = apiRouteSegment(personId);
  if (!cleanId) return null;
  closePersonSheet({ restoreFocus: false });

  const overlayRoot = dependencies.overlayRoot || document.getElementById("overlay-root");
  if (!overlayRoot) return null;
  const trigger = document.activeElement;
  const generation = sheetGeneration + 1;
  sheetGeneration = generation;
  const fetchController = new AbortController();

  const backdrop = element("div", "person-sheet-backdrop person-sheet-backdrop--enter");
  const sheet = element("section", "person-sheet");
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");
  sheet.setAttribute("aria-label", "人物聚光灯");
  if (originRect && sheet.style?.setProperty) {
    const x = Number(originRect.left || 0) + Number(originRect.width || 0) / 2;
    const y = Number(originRect.top || 0) + Number(originRect.height || 0) / 2;
    sheet.style.setProperty("--person-origin-x", `${Math.round(x)}px`);
    sheet.style.setProperty("--person-origin-y", `${Math.round(y)}px`);
  }

  const closeButton = element("button", "person-sheet__close", "关闭");
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "关闭人物聚光灯");
  const body = element("div", "person-sheet__body");
  let close = () => {};
  body.append(sheetContent(cleanId, fallbackPerson(cleanId), () => close()));
  sheet.append(closeButton, body);
  backdrop.append(sheet);
  overlayRoot.replaceChildren(backdrop);

  let closed = false;
  close = ({ restoreFocus = true } = {}) => {
    if (closed) return;
    closed = true;
    sheetGeneration += 1;
    fetchController.abort();
    document.removeEventListener("keydown", onKeyDown);
    backdrop.classList?.add("person-sheet-backdrop--leave");
    backdrop.remove();
    if (closeActiveSheet === close) closeActiveSheet = null;
    if (restoreFocus && canRestoreFocus(trigger)) trigger.focus();
  };
  const onKeyDown = (event) => {
    if (event.key === "Escape") close();
  };
  closeActiveSheet = close;
  closeButton.addEventListener("click", close);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close();
  });
  document.addEventListener("keydown", onKeyDown);
  closeButton.focus?.();

  try {
    const person = await dependencies.fetchJson(`/api/v2/people/${cleanId}`, { signal: fetchController.signal });
    if (closed || generation !== sheetGeneration) return null;
    body.replaceChildren(sheetContent(cleanId, person, () => close()));
    return person;
  } catch {
    if (closed || generation !== sheetGeneration) return null;
    body.replaceChildren(sheetFailureContent(cleanId, () => close()));
    return null;
  }
}

function evidenceSection(person) {
  const section = element("section", "person-credits");
  section.id = "credits";
  section.append(
    element("p", "eyebrow", "KNOWN FOR / LOCAL EVIDENCE"),
    element("h2", "person-section-title", "本地片库中的参与证据"),
  );
  const knownFor = Array.isArray(person?.known_for) ? person.known_for : [];
  const evidence = Array.isArray(person?.evidence) ? person.evidence : [];
  if (knownFor.length) {
    const rail = element("div", "person-known-for");
    rail.setAttribute("role", "list");
    for (const title of knownFor.slice(0, 8)) {
      const item = element("div", "person-known-for__item");
      item.setAttribute("role", "listitem");
      item.append(renderTitleCard({
        ...title,
        item_key: textValue(title?.item_key) || textValue(title?.id),
        metadata: [title.year ? String(title.year) : "", textValue(title.media_type)].filter(Boolean),
      }));
      rail.append(item);
    }
    section.append(rail);
  }
  if (evidence.length) {
    const list = element("ul", "person-evidence-list");
    for (const record of evidence.slice(0, 8)) {
      const roles = listValue(record?.roles).map(roleLabel).join(" / ");
      const item = element("li", "person-evidence-list__item", `${textValue(record?.title, "未命名作品")} · ${roles || "参与记录"}`);
      list.append(item);
    }
    section.append(list);
  }
  if (!knownFor.length && !evidence.length) {
    const limited = element("div", "person-limited-data");
    limited.append(
      element("strong", "person-limited-data__title", "资料有限"),
      element("p", "person-limited-data__copy", "当前没有足够的 known_for 或 evidence 数据，以下仅保留已确认的原作品上下文。"),
      renderOriginContext(textValue(person?.id)),
    );
    section.append(limited);
  }
  return section;
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
  if (typeof document.startViewTransition !== "function") return update();
  let transition;
  try {
    transition = document.startViewTransition(update);
  } catch {
    return committed || update();
  }
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

function personRecovery(personId, retry) {
  const panel = element("section", "route-recovery person-recovery");
  panel.append(
    element("p", "eyebrow", "PERSON / RECOVERY"),
    element("h1", "route-recovery__title", "人物资料暂时无法打开"),
    element("p", "route-recovery__copy", "本地人物记录可能尚未建立，原页面在此恢复面板准备好之前不会被清空。"),
  );
  const button = element("button", "route-recovery__action", "重试");
  button.type = "button";
  button.addEventListener("click", retry);
  panel.append(button, renderOriginContext(personId));
  return panel;
}

export async function renderPersonPage(personId, options = {}) {
  const cleanId = apiRouteSegment(personId);
  if (!cleanId) return null;
  try {
    const person = await dependencies.fetchJson(`/api/v2/people/${cleanId}`, { signal: options.signal });
    if (options.signal?.aborted || (typeof options.isCurrent === "function" && !options.isCurrent())) return null;
    const page = element("article", "person-page route-view--enter");
    page.append(renderPersonIdentity(person), renderOriginContext(cleanId), evidenceSection(person));
    return await commitView(page, { heading: textValue(person?.name, "人物详情") }, options) ? page : null;
  } catch (error) {
    if (options.signal?.aborted || error?.name === "AbortError") return null;
    const recovery = personRecovery(cleanId, () => { void renderPersonPage(cleanId, options); });
    return await commitView(recovery, { heading: "人物资料恢复" }, options) ? recovery : null;
  }
}
