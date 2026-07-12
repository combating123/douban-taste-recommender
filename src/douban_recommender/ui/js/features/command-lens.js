import { postV2 } from "../core/api.js";
import { trapFocus } from "../core/focus.js";
import { sanitizeCommandLensChips, sanitizeNonSensitiveText } from "../core/store.js";

const ARRAY_FIELDS = Object.freeze({
  media_type: "media_types",
  genre: "genres",
  mood: "moods",
  country: "countries",
  language: "languages",
  avoid: "avoid",
});
const NUMBER_FIELDS = new Set(["runtime_max", "episode_runtime_max", "year_min", "year_max", "quality_floor"]);

let dependencies = { root: null, store: null, api: { postV2 }, onSession: null, onBeforeOpen: null };
let lens = null;
let intentInput = null;
let chipList = null;
let statusLine = null;
let submitButton = null;
let currentIntent = {};
let currentChips = [];
let currentIntentSessionId = null;
let currentSessionId = null;
let keyboardDocument = null;
let keyboardHandler = null;
let intentGeneration = 0;
let intentPending = false;
let releaseLensTrap = null;
let lensTrigger = null;

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function structuredChips(value) {
  return sanitizeCommandLensChips(value);
}

function cloneIntent(intent) {
  if (!intent || typeof intent !== "object" || Array.isArray(intent)) return {};
  return Object.fromEntries(Object.entries(intent).map(([key, value]) => [
    key,
    Array.isArray(value) ? [...value] : value,
  ]));
}

function activeSessionId(state) {
  const recommendation = state?.recommendation;
  const channel = recommendation?.activeChannel || "movie";
  return textValue(recommendation?.channels?.[channel]?.sessionId)
    || textValue(recommendation?.sessionId)
    || null;
}

function chipsAreEditable() {
  return Boolean(!intentPending && currentIntentSessionId && currentIntentSessionId === currentSessionId);
}

function updateStatus(message, tone = "neutral") {
  if (!statusLine) return;
  statusLine.dataset.tone = tone;
  statusLine.textContent = message;
}

function replacementIntent(chip, replacement) {
  const next = cloneIntent(currentIntent);
  const field = ARRAY_FIELDS[chip.key] || chip.key;
  if (ARRAY_FIELDS[chip.key]) {
    const values = Array.isArray(next[field]) ? [...next[field]] : [];
    const index = values.findIndex((value) => String(value) === String(chip.value));
    if (index >= 0) values.splice(index, 1);
    if (replacement !== undefined) values.push(replacement);
    next[field] = values;
  } else if (replacement === undefined) {
    delete next[field];
  } else {
    next[field] = replacement;
  }
  next.free_text = "";
  return next;
}

async function runIntentRequest(payload, workingMessage, successMessage) {
  const generation = ++intentGeneration;
  setIntentPending(true);
  updateStatus(workingMessage, "working");
  try {
    const session = await dependencies.api.postV2("/api/v2/recommend/sessions", payload);
    if (generation !== intentGeneration) return null;
    acceptGroundedSession(session, successMessage);
    return session;
  } catch {
    if (generation !== intentGeneration) return null;
    updateStatus("语言理解服务暂不可用；本地结构化筛选仍可继续使用。", "fallback");
    return null;
  } finally {
    if (generation === intentGeneration) setIntentPending(false);
  }
}

function replaceSession(intent) {
  return runIntentRequest(
    {
      intent,
      batch_size: 9,
      limit: 160,
      per_query: 30,
      fetch_douban: true,
      include_movies: true,
      include_series: true,
      include_anime: true,
    },
    "正在用结构化条件重建今晚片单…",
    "条件已更新，新的批次历史已建立。",
  );
}

function editChip(chip, row) {
  const editor = document.createElement("input");
  editor.className = "intent-chip__editor";
  editor.type = NUMBER_FIELDS.has(chip.key) ? "number" : "text";
  editor.value = String(chip.value);
  editor.setAttribute("aria-label", `编辑${chip.label}`);
  const save = element("button", "intent-chip__save", "应用");
  save.type = "button";
  save.addEventListener("click", () => {
    const rawInput = textValue(editor.value);
    const raw = NUMBER_FIELDS.has(chip.key) ? rawInput : sanitizeNonSensitiveText(rawInput);
    if (rawInput && !raw) {
      updateStatus("检测到可能包含凭据或敏感字段的文本，已拒绝更新。", "fallback");
      return;
    }
    if (!raw) return;
    const value = NUMBER_FIELDS.has(chip.key) ? Number(raw) : raw;
    if (NUMBER_FIELDS.has(chip.key) && !Number.isFinite(value)) return;
    void replaceSession(replacementIntent(chip, value));
  });
  row.replaceChildren(editor, save);
  editor.focus();
}

function renderChips() {
  if (!chipList) return;
  chipList.replaceChildren();
  if (!currentChips.length) {
    chipList.append(element("p", "command-lens__chip-empty", "服务端尚未返回结构化条件。"));
    return;
  }
  for (const chip of currentChips) {
    const row = element("div", "intent-chip");
    const label = element("span", "intent-chip__label", chip.label);
    const edit = element("button", "intent-chip__edit", "编辑");
    edit.type = "button";
    edit.disabled = !chipsAreEditable();
    edit.addEventListener("click", () => editChip(chip, row));
    row.append(label, edit);
    if (chip.removable) {
      const remove = element("button", "intent-chip__remove", "移除");
      remove.type = "button";
      remove.disabled = !chipsAreEditable();
      remove.setAttribute("aria-label", `移除${chip.label}`);
      remove.addEventListener("click", () => replaceSession(replacementIntent(chip)));
      row.append(remove);
    }
    chipList.append(row);
  }
}

function acceptGroundedSession(session, message) {
  currentIntent = cloneIntent(session?.intent);
  currentIntentSessionId = textValue(session?.id) || null;
  currentSessionId = currentIntentSessionId;
  currentChips = structuredChips(session?.chips);
  renderChips();
  dependencies.store?.dispatch?.({ type: "commandLens/grounded", draft: intentInput?.value || "", chips: currentChips });
  dependencies.store?.dispatch?.({ type: "recommendation/sessionReceived", session });
  dependencies.onSession?.(session);
  updateStatus(message, "success");
}

function canRestoreFocus(trigger) {
  if (!trigger || typeof trigger.focus !== "function" || trigger.isConnected === false || trigger.disabled || trigger.hidden || trigger.inert) return false;
  return trigger.getAttribute?.("aria-hidden") !== "true";
}

export function closeCommandLens({ restoreFocus = true } = {}) {
  const trigger = lensTrigger;
  intentGeneration += 1;
  intentPending = false;
  releaseLensTrap?.();
  releaseLensTrap = null;
  dependencies.root?.replaceChildren();
  lens = null;
  intentInput = null;
  chipList = null;
  statusLine = null;
  submitButton = null;
  lensTrigger = null;
  if (restoreFocus && canRestoreFocus(trigger)) trigger.focus({ preventScroll: true });
}

function bindKeyboardShortcut() {
  if (!globalThis.document?.addEventListener || (keyboardDocument === document && keyboardHandler)) return;
  unbindCommandLensShortcut();
  keyboardDocument = document;
  keyboardHandler = (event) => {
    const isCommandShortcut = event.key.toLowerCase() === "k";
    if (!(event.ctrlKey || event.metaKey) || !isCommandShortcut) return;
    event.preventDefault();
    openCommandLens();
  };
  keyboardDocument.addEventListener("keydown", keyboardHandler);
}

export function unbindCommandLensShortcut() {
  if (keyboardDocument && keyboardHandler) keyboardDocument.removeEventListener?.("keydown", keyboardHandler);
  keyboardDocument = null;
  keyboardHandler = null;
}

export function configureCommandLens(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    api: options.api || dependencies.api,
  };
  bindKeyboardShortcut();
}

function setIntentPending(pending) {
  intentPending = pending;
  if (submitButton) submitButton.disabled = pending;
  if (intentInput) intentInput.disabled = pending;
  renderChips();
}

export function syncCommandLensState(state = dependencies.store?.getState?.() || {}) {
  const recommendation = state?.recommendation || {};
  currentSessionId = activeSessionId(state);
  currentIntent = cloneIntent(recommendation.intent);
  currentIntentSessionId = textValue(recommendation.intentSessionId) || null;
  currentChips = structuredChips(state?.commandLens?.chips);
  if (chipList) renderChips();
}

export function openCommandLens(initialText = "") {
  const root = dependencies.root || document.getElementById?.("command-lens-root");
  if (!root) return null;
  dependencies.root = root;
  dependencies.onBeforeOpen?.();
  const trigger = lens ? lensTrigger : document.activeElement;
  if (lens) closeCommandLens({ restoreFocus: false });
  lensTrigger = trigger;

  lens = element("section", "command-lens command-lens--enter");
  lens.setAttribute("role", "dialog");
  lens.setAttribute("aria-modal", "true");
  lens.setAttribute("aria-labelledby", "command-lens-title");

  const header = element("header", "command-lens__header");
  const headingGroup = element("div", "command-lens__heading");
  headingGroup.append(
    element("p", "eyebrow", "COMMAND LENS / Ctrl K"),
    element("h2", "command-lens__title", "告诉 CineScope，今晚想进入哪种电影。"),
  );
  headingGroup.children[1].id = "command-lens-title";
  const close = element("button", "command-lens__close", "关闭");
  close.type = "button";
  close.addEventListener("click", () => closeCommandLens());
  header.append(headingGroup, close);

  const form = element("form", "command-lens__form");
  intentInput = document.createElement("textarea");
  intentInput.className = "command-lens__input";
  intentInput.rows = 3;
  intentInput.maxLength = 2000;
  intentInput.placeholder = "例如：90 分钟内，悬疑但不要太压抑，最好是近十年的电影";
  intentInput.value = sanitizeNonSensitiveText(textValue(initialText), "", 2000)
    || sanitizeNonSensitiveText(textValue(dependencies.store?.getState?.()?.commandLens?.draft), "", 2000);
  intentInput.disabled = intentPending;
  intentInput.setAttribute("aria-label", "今晚观影意图");
  submitButton = element("button", "command-lens__submit", "生成今晚片单");
  submitButton.type = "submit";
  submitButton.disabled = intentPending;
  form.append(intentInput, submitButton);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitIntent(intentInput.value);
  });

  chipList = element("div", "command-lens__chips");
  chipList.setAttribute("aria-label", "服务端结构化意图条件");
  syncCommandLensState(dependencies.store?.getState?.() || {});
  renderChips();
  statusLine = element("p", "command-lens__status", "条件标签只采用服务端结构化结果，不读取模型自由文本。");
  statusLine.setAttribute("aria-live", "polite");
  lens.append(header, form, chipList, statusLine);
  root.replaceChildren(lens);
  releaseLensTrap = trapFocus(lens, { onEscape: () => closeCommandLens() });
  intentInput.focus();
  return lens;
}

export async function submitIntent(text) {
  const candidate = textValue(text);
  const cleanText = sanitizeNonSensitiveText(candidate, "", 2000);
  if (candidate && !cleanText) {
    updateStatus("检测到可能包含 Cookie、令牌或其他敏感凭据的文本，已拒绝提交与保存。", "fallback");
    return null;
  }
  if (!cleanText) {
    updateStatus("先写下一句今晚的观影线索。", "fallback");
    return null;
  }
  return runIntentRequest(
    {
      intent_text: cleanText,
      batch_size: 9,
      limit: 160,
      per_query: 30,
      fetch_douban: true,
      include_movies: true,
      include_series: true,
      include_anime: true,
    },
    "正在把自然语言落成结构化条件…",
    "结构化意图已落地，今晚片单已刷新。",
  );
}
