import { postV2 } from "../core/api.js";

const ARRAY_FIELDS = Object.freeze({
  media_type: "media_types",
  genre: "genres",
  mood: "moods",
  country: "countries",
  language: "languages",
  avoid: "avoid",
});
const NUMBER_FIELDS = new Set(["runtime_max", "episode_runtime_max", "year_min", "year_max", "quality_floor"]);

let dependencies = { root: null, store: null, api: { postV2 }, onSession: null };
let lens = null;
let intentInput = null;
let chipList = null;
let statusLine = null;
let currentIntent = {};
let currentChips = [];
let keyboardDocument = null;

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
  if (!Array.isArray(value)) return [];
  return value.flatMap((chip) => {
    if (!chip || typeof chip !== "object" || Array.isArray(chip)) return [];
    const key = textValue(chip.key);
    const label = textValue(chip.label);
    if (!key || !label || chip.value === undefined || chip.value === null) return [];
    return [{ key, label, value: chip.value, removable: Boolean(chip.removable) }];
  });
}

function cloneIntent(intent) {
  if (!intent || typeof intent !== "object" || Array.isArray(intent)) return {};
  return Object.fromEntries(Object.entries(intent).map(([key, value]) => [
    key,
    Array.isArray(value) ? [...value] : value,
  ]));
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
    next[field] = NUMBER_FIELDS.has(field) ? null : "";
  } else {
    next[field] = replacement;
  }
  next.free_text = "";
  return next;
}

async function replaceSession(intent) {
  updateStatus("正在用结构化条件重建今晚片单…", "working");
  try {
    const session = await dependencies.api.postV2("/api/v2/recommend/sessions", {
      intent,
      batch_size: 9,
    });
    acceptGroundedSession(session, "条件已更新，新的批次历史已建立。");
    return session;
  } catch (error) {
    updateStatus("语言理解服务暂不可用；本地结构化筛选仍可继续使用。", "fallback");
    throw error;
  }
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
    const raw = textValue(editor.value);
    if (!raw) return;
    const value = NUMBER_FIELDS.has(chip.key) ? Number(raw) : raw;
    if (NUMBER_FIELDS.has(chip.key) && !Number.isFinite(value)) return;
    replaceSession(replacementIntent(chip, value)).catch(() => {});
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
    edit.addEventListener("click", () => editChip(chip, row));
    row.append(label, edit);
    if (chip.removable) {
      const remove = element("button", "intent-chip__remove", "移除");
      remove.type = "button";
      remove.setAttribute("aria-label", `移除${chip.label}`);
      remove.addEventListener("click", () => replaceSession(replacementIntent(chip)).catch(() => {}));
      row.append(remove);
    }
    chipList.append(row);
  }
}

function acceptGroundedSession(session, message) {
  currentIntent = cloneIntent(session?.intent);
  currentChips = structuredChips(session?.chips);
  renderChips();
  dependencies.store?.dispatch?.({ type: "commandLens/grounded", draft: intentInput?.value || "", chips: currentChips });
  dependencies.store?.dispatch?.({ type: "recommendation/sessionReceived", session });
  dependencies.onSession?.(session);
  updateStatus(message, "success");
}

function closeCommandLens() {
  dependencies.root?.replaceChildren();
  lens = null;
  intentInput = null;
  chipList = null;
  statusLine = null;
}

function bindKeyboardShortcut() {
  if (!globalThis.document?.addEventListener || keyboardDocument === document) return;
  keyboardDocument = document;
  document.addEventListener("keydown", (event) => {
    const isCommandShortcut = event.key.toLowerCase() === "k";
    if (!(event.ctrlKey || event.metaKey) || !isCommandShortcut) return;
    event.preventDefault();
    openCommandLens();
  });
}

export function configureCommandLens(options = {}) {
  dependencies = {
    ...dependencies,
    ...options,
    api: options.api || dependencies.api,
  };
  bindKeyboardShortcut();
}

export function openCommandLens(initialText = "") {
  const root = dependencies.root || document.getElementById?.("command-lens-root");
  if (!root) return null;
  dependencies.root = root;

  lens = element("section", "command-lens motion-enter");
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
  close.addEventListener("click", closeCommandLens);
  header.append(headingGroup, close);

  const form = element("form", "command-lens__form");
  intentInput = document.createElement("textarea");
  intentInput.className = "command-lens__input";
  intentInput.rows = 3;
  intentInput.maxLength = 2000;
  intentInput.placeholder = "例如：90 分钟内，悬疑但不要太压抑，最好是近十年的电影";
  intentInput.value = textValue(initialText) || textValue(dependencies.store?.getState?.()?.commandLens?.draft);
  intentInput.setAttribute("aria-label", "今晚观影意图");
  const submit = element("button", "command-lens__submit", "生成今晚片单");
  submit.type = "submit";
  form.append(intentInput, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitIntent(intentInput.value).catch(() => {});
  });

  chipList = element("div", "command-lens__chips");
  chipList.setAttribute("aria-label", "服务端结构化意图条件");
  currentIntent = cloneIntent(dependencies.store?.getState?.()?.recommendation?.intent);
  currentChips = structuredChips(dependencies.store?.getState?.()?.commandLens?.chips);
  renderChips();
  statusLine = element("p", "command-lens__status", "条件标签只采用服务端结构化结果，不读取模型自由文本。");
  statusLine.setAttribute("aria-live", "polite");
  lens.append(header, form, chipList, statusLine);
  root.replaceChildren(lens);
  intentInput.focus();
  return lens;
}

export async function submitIntent(text) {
  const cleanText = textValue(text);
  if (!cleanText) {
    updateStatus("先写下一句今晚的观影线索。", "fallback");
    return null;
  }
  updateStatus("正在把自然语言落成结构化条件…", "working");
  try {
    const session = await dependencies.api.postV2("/api/v2/recommend/sessions", {
      intent_text: cleanText,
      batch_size: 9,
    });
    acceptGroundedSession(session, "结构化意图已落地，今晚片单已刷新。");
    return session;
  } catch (error) {
    updateStatus("语言理解服务暂不可用；本地结构化筛选仍可继续使用。", "fallback");
    throw error;
  }
}
