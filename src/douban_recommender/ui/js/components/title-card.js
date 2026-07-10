import { adaptRecommendationMedia, normalizeMediaAsset } from "../core/media.js";
import { renderMediaFrame } from "./media-frame.js";

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function appendText(parent, tagName, className, value) {
  const element = document.createElement(tagName);
  element.className = className;
  element.textContent = value;
  parent.append(element);
  return element;
}

function mediaForItem(item) {
  if (item?.media && typeof item.media === "object" && item.media.kind) {
    return normalizeMediaAsset({
      ...item.media,
      title: textValue(item.media.title, textValue(item.title, item.name)),
      source: textValue(item.media.source, item.source),
    });
  }
  return adaptRecommendationMedia(item);
}

function metadataText(value) {
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string" && item.trim()).join(" · ");
  return textValue(value);
}

function actionList(actions) {
  if (Array.isArray(actions)) return actions;
  if (actions && typeof actions === "object") return Object.values(actions);
  return [];
}

/**
 * Compact title card for horizontal shelves. All copy is assigned through
 * textContent so recommendation or model text stays inert.
 */
export function renderTitleCard(item = {}, actions = []) {
  const record = item && typeof item === "object" ? item : {};
  const card = document.createElement("article");
  card.className = "title-card";
  card.append(renderMediaFrame(mediaForItem(record)));

  const body = document.createElement("div");
  body.className = "title-card__body";
  appendText(body, "h3", "title-card__title", textValue(record.title) || textValue(record.name, "未命名作品"));

  const metadata = metadataText(record.metadata);
  if (metadata) appendText(body, "p", "title-card__metadata", metadata);

  const reason = textValue(record.reason) || textValue(record.description);
  if (reason) appendText(body, "p", "title-card__reason", reason);
  card.append(body);

  const controls = actionList(actions).filter((action) => typeof action?.onClick === "function");
  if (controls.length) {
    const footer = document.createElement("div");
    footer.className = "title-card__actions";
    for (const action of controls) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "title-card__action";
      button.textContent = textValue(action.label, "操作");
      button.addEventListener("click", action.onClick);
      footer.append(button);
    }
    card.append(footer);
  }

  return card;
}
