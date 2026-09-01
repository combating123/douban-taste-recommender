import { candidateOrigin } from "./candidate-origin.js";
import { renderTitleCard } from "./title-card.js";

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function batchLabel(batchState) {
  if (!batchState || typeof batchState !== "object") return "";
  if (textValue(batchState.label)) return textValue(batchState.label);

  const entries = [
    ["\u5019\u9009", batchState.poolSize],
    ["\u5339\u914d", batchState.matchedSize],
    ["\u663e\u793a", batchState.visibleSize],
  ].filter(([, value]) => Number.isFinite(value));
  return entries.map(([label, value]) => label + " " + value).join(" \u00b7 ");
}

function normalizeFilter(value) {
  return ["all", "catalog", "online"].includes(value) ? value : "all";
}

function filterItems(items, filter) {
  if (filter === "all") return items;
  return items.filter((item) => candidateOrigin(item).kind === filter);
}

/**
 * A bounded horizontal shelf. Consumers may replace its items as batches change;
 * it does not fetch data or own recommendation state.
 */
export function renderShelf({
  title = "",
  items = [],
  batchState = {},
  actionsForItem = null,
  originFilter = "all",
  onOriginFilterChange = null,
  itemLimit = null,
} = {}) {
  const shelf = document.createElement("section");
  shelf.className = "title-shelf";

  const heading = document.createElement("div");
  heading.className = "title-shelf__heading";
  const headingText = document.createElement("h2");
  headingText.className = "title-shelf__title";
  headingText.textContent = textValue(title, "\u7cbe\u9009\u7247\u5355");
  heading.append(headingText);

  const stateText = batchLabel(batchState);
  if (stateText) {
    const state = document.createElement("p");
    state.className = "title-shelf__state";
    state.textContent = stateText;
    heading.append(state);
  }
  shelf.append(heading);

  const safeItems = Array.isArray(items) ? items : [];
  const safeItemLimit = Number.isInteger(itemLimit) && itemLimit > 0 ? itemLimit : safeItems.length;
  const counts = safeItems.reduce((summary, item) => {
    summary[candidateOrigin(item).kind] += 1;
    return summary;
  }, { online: 0, catalog: 0 });
  counts.all = safeItems.length;

  const filters = document.createElement("div");
  filters.className = "title-shelf__source-switcher";
  filters.setAttribute("aria-label", "\u5019\u9009\u6765\u6e90\u7b5b\u9009");
  const rail = document.createElement("div");
  rail.className = "title-shelf__rail";
  rail.setAttribute("role", "list");
  let activeFilter = normalizeFilter(originFilter);

  const filterDefinitions = [
    { key: "all", label: "\u5168\u90e8" },
    { key: "catalog", label: "\u7247\u5e93 / \u7cbe\u9009" },
    { key: "online", label: "\u5728\u7ebf\u65b0\u589e" },
  ];

  const renderRail = () => {
    rail.replaceChildren();
    const visibleItems = filterItems(safeItems, activeFilter).slice(0, safeItemLimit);
    for (const item of visibleItems) {
      const entry = document.createElement("div");
      entry.className = "title-shelf__item";
      entry.setAttribute("role", "listitem");
      const actions = typeof actionsForItem === "function" ? actionsForItem(item) : [];
      entry.append(renderTitleCard(item, actions));
      rail.append(entry);
    }
    if (!visibleItems.length) {
      const empty = document.createElement("p");
      empty.className = "title-shelf__empty";
      empty.textContent = activeFilter === "all"
        ? "\u5f53\u524d\u6279\u6b21\u6682\u65e0\u53ef\u5c55\u793a\u4f5c\u54c1"
        : "\u8be5\u6765\u6e90\u4e0b\u6682\u65e0\u53ef\u5c55\u793a\u4f5c\u54c1";
      rail.append(empty);
    }
  };

  const renderFilters = () => {
    filters.replaceChildren();
    for (const definition of filterDefinitions) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `title-shelf__filter${activeFilter === definition.key ? " title-shelf__filter--active" : ""}`;
      button.dataset.origin = definition.key;
      button.setAttribute("aria-pressed", activeFilter === definition.key ? "true" : "false");
      button.textContent = `${definition.label} ${counts[definition.key]}`;
      button.addEventListener("click", (event) => {
        event?.preventDefault?.();
        if (activeFilter === definition.key) return;
        activeFilter = definition.key;
        renderFilters();
        renderRail();
        if (typeof onOriginFilterChange === "function") onOriginFilterChange(activeFilter);
      });
      filters.append(button);
    }
  };

  renderFilters();
  renderRail();
  shelf.append(filters, rail);
  return shelf;
}
