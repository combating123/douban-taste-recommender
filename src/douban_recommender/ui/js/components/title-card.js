import { adaptRecommendationMedia, normalizeMediaAsset } from "../core/media.js";
import { bindExpandableCopy } from "./expandable-copy.js";
import { candidateOrigin } from "./candidate-origin.js";
import { renderMediaFrame } from "./media-frame.js";

const SAFE_ROUTE_SEGMENT = /^[A-Za-z0-9:._~-]+$/;
const RATING_LABELS = Object.freeze({
  douban: "豆瓣",
  imdb: "IMDb",
  tmdb: "TMDb",
  tvmaze: "TVMaze",
  anilist: "AniList",
  jikan: "MAL",
});
const GENERATED_SUMMARY_PREFIXES = Object.freeze([
  "正在补齐这部",
  "资料有限：本地片库暂未记录作品简介",
  "由 CineScope 精选扩展池补入的",
  "详情：点击卡片查看简介",
]);

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

export function mediaBadgeLabel(record = {}, fallback = "") {
  const badge = record?.media_badge && typeof record.media_badge === "object" ? record.media_badge : {};
  return textValue(badge.label)
    || textValue(record?.media_type)
    || textValue(record?.item?.media_type)
    || fallback;
}

export function displayTitle(record = {}, fallback = "未命名作品") {
  const item = record?.item && typeof record.item === "object" ? record.item : {};
  return textValue(record?.display_title)
    || textValue(record?.displayTitle)
    || textValue(item?.display_title)
    || textValue(item?.displayTitle)
    || textValue(record?.title)
    || textValue(record?.name)
    || textValue(item?.title)
    || textValue(item?.name)
    || fallback;
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
      title: textValue(item.media.title, displayTitle(item, "作品")),
      source: textValue(item.media.source, item.source),
    });
  }
  return adaptRecommendationMedia(item);
}

function metadataText(value) {
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string" && item.trim()).join(" · ");
  return textValue(value);
}

function listValue(value) {
  return Array.isArray(value)
    ? value.map((entry) => textValue(entry)).filter(Boolean)
    : [];
}

function reasonEvidenceRows(record = {}) {
  const rawRows = Array.isArray(record.reason_evidence)
    ? record.reason_evidence
    : Array.isArray(record.fusion_dimensions) ? record.fusion_dimensions : [];
  const rows = [];
  const seen = new Set();
  for (const raw of rawRows) {
    if (typeof raw === "string") {
      const [label, ...rest] = raw.split(/[：:]/);
      const value = rest.join("：").trim();
      if (!textValue(label) || !value) continue;
      const token = `${label.trim()}|${value}`;
      if (seen.has(token)) continue;
      seen.add(token);
      rows.push({ key: "signal", label: label.trim().replace(/^共同/, ""), value, strength: 0 });
      continue;
    }
    if (!raw || typeof raw !== "object") continue;
    const label = textValue(raw.label);
    const value = textValue(raw.value);
    if (!label || !value) continue;
    const token = `${label}|${value}`;
    if (seen.has(token)) continue;
    seen.add(token);
    rows.push({
      key: textValue(raw.key, "signal"),
      label,
      value,
      strength: Number.isFinite(Number(raw.strength)) ? Number(raw.strength) : 0,
    });
  }
  return rows.slice(0, 4);
}

export function recommendationReason(record = {}) {
  return textValue(record.primary_reason)
    || textValue(record.reason)
    || (typeof record.explanation === "string" ? textValue(record.explanation) : "")
    || textValue(record.short_reason)
    || "依据内容连接、作品口碑与当前口味进入本批推荐。";
}

function recommendationChips(record = {}, evidence = []) {
  const explicit = listValue(record.reason_chips);
  const derived = evidence.map((row) => `${row.label} · ${row.value}`);
  const values = [...explicit, ...derived];
  return [...new Set(values.map((value) => textValue(value)).filter(Boolean))].slice(0, 3);
}

function safeDomToken(value) {
  const token = textValue(value).replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return token || "item";
}

export function isGeneratedSummary(value) {
  const summary = textValue(value);
  return !summary || GENERATED_SUMMARY_PREFIXES.some((prefix) => summary.startsWith(prefix));
}

export function isLargelyLatinSummary(value) {
  const summary = textValue(value);
  if (!summary) return false;
  const characters = [...summary];
  const cjkCount = characters.filter((character) => /[\u3400-\u9fff]/u.test(character)).length;
  const latinCount = characters.filter((character) => /[A-Za-z]/u.test(character)).length;
  return cjkCount === 0 && latinCount >= 24 && latinCount >= characters.length * 0.45;
}

export function needsLocalizedSummary(value) {
  return isGeneratedSummary(value) || isLargelyLatinSummary(value);
}

export function decisionSummary(record, genres, mediaType) {
  const summary = textValue(record.summary) || textValue(record.description);
  if (!needsLocalizedSummary(summary)) return summary;
  const genericGenres = new Set(["作品", "媒体", "电影", "电视剧", "动漫", mediaType]);
  const specificGenres = genres.filter((genre) => !genericGenres.has(genre));
  const genreCopy = specificGenres.length ? specificGenres.join(" / ") : "故事与人物";
  if (isLargelyLatinSummary(summary)) {
    return `这是一部以${genreCopy}为核心的${mediaType}；中文剧情简介正在自动补齐。`;
  }
  return `这是一部以${genreCopy}为核心的${mediaType}；剧情简介与主创资料正在后台核对。`;
}

function ratingEntries(record) {
  const entries = [];
  const seen = new Set();
  const add = (provider, value) => {
    const score = Number(value);
    const key = textValue(provider).toLowerCase();
    if (!key || !Number.isFinite(score) || score <= 0 || seen.has(key)) return;
    seen.add(key);
    entries.push({ provider: key, label: RATING_LABELS[key] || provider, score: Math.round(score * 10) / 10 });
  };
  add("douban", record.douban_rating);
  const sourceRatings = record.source_ratings && typeof record.source_ratings === "object"
    ? record.source_ratings
    : {};
  Object.entries(sourceRatings).forEach(([provider, score]) => add(provider, score));
  return entries.slice(0, 3);
}

function appendPill(parent, className, value) {
  const pill = document.createElement("span");
  pill.className = className;
  pill.textContent = value;
  parent.append(pill);
  return pill;
}

function actionList(actions) {
  if (Array.isArray(actions)) return actions;
  if (actions && typeof actions === "object") return Object.values(actions);
  return [];
}

export function stableTitleKey(item = {}) {
  const record = item && typeof item === "object" ? item : {};
  const itemKey = textValue(record.item_key) || textValue(record.itemKey);
  if (itemKey) return itemKey;
  const doubanId = textValue(record.douban_id) || textValue(record.doubanId);
  return doubanId ? `douban:${doubanId}` : "";
}

export function titleRouteForItem(item = {}) {
  const key = stableTitleKey(item);
  return key && SAFE_ROUTE_SEGMENT.test(key) ? `/title/${key}` : "";
}

/** A high-density decision card. All external copy stays inert via textContent. */
export function renderTitleCard(item = {}, actions = []) {
  const record = item && typeof item === "object" ? item : {};
  const card = document.createElement("article");
  card.className = "title-card";

  const route = titleRouteForItem(record);
  const content = document.createElement(route ? "a" : "div");
  content.className = "title-card__link";
  if (route) {
    content.setAttribute("href", route);
    content.setAttribute("data-route", "");
    content.setAttribute("aria-label", `打开《${displayTitle(record)}》详情`);
  }
  const visual = document.createElement("div");
  visual.className = "title-card__visual";
  visual.append(renderMediaFrame(mediaForItem(record)));
  content.append(visual);

  const body = document.createElement("div");
  body.className = "title-card__body";
  const ratings = document.createElement("div");
  ratings.className = "title-card__ratings";
  const origin = candidateOrigin(record);
  appendPill(
    ratings,
    `title-card__origin title-card__origin--${origin.kind}`,
    origin.label,
  );
  const scoreRows = ratingEntries(record);
  if (scoreRows.length) {
    scoreRows.forEach(({ provider, label, score }) => appendPill(
      ratings,
      `title-card__rating title-card__rating--${provider}`,
      `${label} ${score}`,
    ));
  } else {
    appendPill(ratings, "title-card__rating title-card__rating--pending", "评分补全中");
  }
  body.append(ratings);

  const titleText = displayTitle(record);
  const title = appendText(body, "h3", "title-card__title", titleText);
  const titleLength = [...titleText].length;
  title.dataset.length = titleLength > 30 ? "extreme" : titleLength > 20 ? "long" : "normal";
  title.setAttribute("title", titleText);
  title.setAttribute("aria-label", titleText);

  const genres = listValue(record.genres).slice(0, 4);
  const metadata = document.createElement("div");
  metadata.className = "title-card__genres";
  const mediaType = mediaBadgeLabel(record, "作品");
  appendPill(metadata, "title-card__genre title-card__genre--type", mediaType);
  if (Number.isFinite(record.year)) appendPill(metadata, "title-card__genre", String(record.year));
  (genres.length ? genres : [metadataText(record.metadata)]).filter(Boolean).slice(0, 4).forEach((genre) => {
    if (genre !== mediaType) appendPill(metadata, "title-card__genre", genre);
  });
  body.append(metadata);

  const summary = decisionSummary(record, genres, mediaType);
  const summaryNode = appendText(body, "p", "title-card__summary", summary);
  summaryNode.setAttribute("title", summary);
  summaryNode.setAttribute("aria-label", summary);

  const evidence = reasonEvidenceRows(record);
  const reason = recommendationReason(record);
  const reasonBlock = document.createElement("section");
  reasonBlock.className = "title-card__reason-block";
  reasonBlock.setAttribute("aria-label", "推荐依据");
  const reasonHeading = document.createElement("div");
  reasonHeading.className = "title-card__reason-heading";
  reasonHeading.append(
    appendText(document.createElement("span"), "strong", "title-card__reason-title", "推荐依据"),
    appendText(
      document.createElement("span"),
      "small",
      "title-card__reason-count",
      evidence.length ? `${evidence.length} 项可核对信号` : "综合排序信号",
    ),
  );
  reasonBlock.append(reasonHeading);
  const reasonNode = appendText(reasonBlock, "p", "title-card__why", reason);
  reasonNode.setAttribute("title", reason);
  reasonNode.setAttribute("aria-label", `推荐依据：${reason}`);
  const reasonChips = recommendationChips(record, evidence);
  if (reasonChips.length) {
    const chipRow = document.createElement("div");
    chipRow.className = "title-card__reason-chips";
    reasonChips.forEach((chip) => appendPill(chipRow, "title-card__reason-chip", chip));
    reasonBlock.append(chipRow);
  }
  body.append(reasonBlock);
  content.append(body);
  card.append(content);

  // Full copy is rendered in an in-card overlay. Expanding one item therefore
  // never changes the row height or pushes neighbouring cards out of alignment.
  const summaryLength = [...summary].length;
  const reasonLength = [...reason].length;
  // Create the control for copy that can plausibly wrap on a narrow card;
  // bindExpandableCopy hides it again when the actual rendered dimensions fit.
  // This avoids relying on a desktop-oriented character threshold on mobile.
  if (titleLength > 24 || summaryLength > 24 || reasonLength > 36) {
    const expand = document.createElement("button");
    expand.type = "button";
    expand.className = "title-card__expand";
    expand.hidden = true;
    expand.setAttribute("aria-expanded", "false");
    const panelId = `title-card-copy-${safeDomToken(stableTitleKey(record) || titleText)}`;
    expand.setAttribute("aria-controls", panelId);
    expand.setAttribute("aria-label", `查看《${titleText}》的完整简介与推荐依据`);
    expand.textContent = "完整简介";
    const panel = document.createElement("section");
    panel.className = "title-card__expanded-panel";
    panel.id = panelId;
    panel.hidden = true;
    panel.setAttribute("aria-label", `《${titleText}》完整简介与推荐依据`);
    const panelHeader = document.createElement("header");
    panelHeader.className = "title-card__expanded-header";
    panelHeader.append(
      appendText(document.createElement("span"), "strong", "title-card__expanded-title", titleText),
      appendText(document.createElement("span"), "small", "title-card__expanded-kicker", "完整简介与推荐依据"),
    );
    const close = document.createElement("button");
    close.type = "button";
    close.className = "title-card__expanded-close";
    close.textContent = "关闭";
    close.setAttribute("aria-label", `关闭《${titleText}》完整说明`);
    panelHeader.append(close);
    const panelCopy = document.createElement("div");
    panelCopy.className = "title-card__expanded-copy";
    panelCopy.append(
      appendText(document.createElement("section"), "strong", "title-card__expanded-label", "剧情简介"),
      appendText(document.createElement("section"), "p", "title-card__expanded-summary", summary),
      appendText(document.createElement("section"), "strong", "title-card__expanded-label", "为什么推荐"),
      appendText(document.createElement("section"), "p", "title-card__expanded-reason", reason),
    );
    if (evidence.length) {
      const evidenceGrid = document.createElement("div");
      evidenceGrid.className = "title-card__expanded-evidence";
      evidence.forEach((row) => {
        const evidenceItem = document.createElement("span");
        evidenceItem.className = `title-card__expanded-evidence-item title-card__expanded-evidence-item--${safeDomToken(row.key)}`;
        evidenceItem.append(
          appendText(document.createElement("span"), "small", "title-card__expanded-evidence-label", row.label),
          appendText(document.createElement("span"), "strong", "title-card__expanded-evidence-value", row.value),
        );
        evidenceGrid.append(evidenceItem);
      });
      panelCopy.append(evidenceGrid);
    }
    panel.append(panelHeader, panelCopy);
    let copyBinding;
    const setExpanded = (expanded) => {
      if (card.classList?.toggle) card.classList.toggle("title-card--expanded", expanded);
      else card.className = `${card.className || ""} ${expanded ? "title-card--expanded" : ""}`.trim();
      card.dataset.expanded = expanded ? "true" : "false";
      panel.hidden = !expanded;
      expand.setAttribute("aria-expanded", String(expanded));
      expand.textContent = expanded ? "关闭说明" : "完整简介";
      expand.setAttribute(
        "aria-label",
        `${expanded ? "关闭" : "查看"}《${titleText}》的完整简介与推荐依据`,
      );
      if (expanded) close.focus?.();
      copyBinding?.update?.();
    };
    expand.addEventListener("click", (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      setExpanded(card.dataset.expanded !== "true");
    });
    close.addEventListener("click", (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      setExpanded(false);
      expand.focus?.();
    });
    panel.addEventListener("keydown", (event) => {
      if (event?.key !== "Escape") return;
      event.preventDefault?.();
      setExpanded(false);
      expand.focus?.();
    });
    card.append(expand, panel);
    copyBinding = bindExpandableCopy({
      control: expand,
      nodes: [summaryNode, reasonNode],
      fallbackVisible: titleLength > 34 || summaryLength > 108 || reasonLength > 92,
      isExpanded: () => card.dataset.expanded === "true",
    });
  }

  const controls = actionList(actions).filter((action) => typeof action?.onClick === "function");
  if (controls.length) {
    const footer = document.createElement("div");
    footer.className = "title-card__actions";
    for (const action of controls) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `title-card__action${textValue(action.className) ? ` ${textValue(action.className)}` : ""}`;
      button.textContent = textValue(action.label, "操作");
      button.disabled = Boolean(action.disabled);
      button.setAttribute("aria-label", textValue(action.ariaLabel, button.textContent));
      button.addEventListener("click", (event) => {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        action.onClick(event);
      });
      footer.append(button);
    }
    card.append(footer);
  }

  return card;
}
