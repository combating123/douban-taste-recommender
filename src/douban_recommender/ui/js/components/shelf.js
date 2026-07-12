import { renderTitleCard } from "./title-card.js";

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function batchLabel(batchState) {
  if (!batchState || typeof batchState !== "object") return "";
  if (textValue(batchState.label)) return textValue(batchState.label);

  const entries = [
    ["候选", batchState.poolSize],
    ["匹配", batchState.matchedSize],
    ["显示", batchState.visibleSize],
  ].filter(([, value]) => Number.isFinite(value));
  return entries.map(([label, value]) => label + " " + value).join(" · ");
}

/**
 * A bounded horizontal shelf. Consumers may replace its items as batches change;
 * it does not fetch data or own recommendation state.
 */
export function renderShelf({ title = "", items = [], batchState = {} } = {}) {
  const shelf = document.createElement("section");
  shelf.className = "title-shelf";

  const heading = document.createElement("div");
  heading.className = "title-shelf__heading";
  const headingText = document.createElement("h2");
  headingText.className = "title-shelf__title";
  headingText.textContent = textValue(title, "精选片单");
  heading.append(headingText);

  const stateText = batchLabel(batchState);
  if (stateText) {
    const state = document.createElement("p");
    state.className = "title-shelf__state";
    state.textContent = stateText;
    heading.append(state);
  }
  shelf.append(heading);

  const rail = document.createElement("div");
  rail.className = "title-shelf__rail";
  rail.setAttribute("role", "list");
  const safeItems = Array.isArray(items) ? items : [];
  for (const item of safeItems) {
    const entry = document.createElement("div");
    entry.className = "title-shelf__item";
    entry.setAttribute("role", "listitem");
    entry.append(renderTitleCard(item));
    rail.append(entry);
  }
  if (!safeItems.length) {
    const empty = document.createElement("p");
    empty.className = "title-shelf__empty";
    empty.textContent = "???????????";
    rail.append(empty);
  }
  shelf.append(rail);
  return shelf;
}
