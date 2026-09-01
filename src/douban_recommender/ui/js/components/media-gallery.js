import { isLocalMediaUrl } from "../core/media.js";
import { renderMediaFrame } from "./media-frame.js";

let gallerySequence = 0;

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function element(tagName, className, text = "") {
  const node = document.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function cleanAssets(values) {
  const source = Array.isArray(values) ? values : [];
  const seen = new Set();
  return source.flatMap((value, index) => {
    const record = value && typeof value === "object" ? value : {};
    const url = textValue(record.url) || textValue(record.localUrl);
    if (!isLocalMediaUrl(url) || seen.has(url)) return [];
    seen.add(url);
    return [{
      id: textValue(record.id, `media-${index + 1}`),
      url,
      label: textValue(record.label, `视觉资料 ${index + 1}`),
      status: textValue(record.media_status) || textValue(record.status, "ready"),
      source: textValue(record.source, "verified-gallery"),
    }];
  }).slice(0, 10);
}

export function renderMediaGallery({ assets = [], title = "", ariaLabel = "作品视觉画廊" } = {}) {
  const items = cleanAssets(assets);
  const gallery = element("section", "media-gallery");
  const galleryId = `media-gallery-${++gallerySequence}`;
  const stageId = `${galleryId}-stage`;
  gallery.id = galleryId;
  gallery.setAttribute("role", "region");
  gallery.setAttribute("aria-label", ariaLabel);
  gallery.setAttribute("aria-roledescription", "轮播画廊");
  gallery.setAttribute("tabindex", "0");

  if (!items.length) {
    gallery.dataset.state = "empty";
    gallery.append(element("p", "media-gallery__empty", "视觉资料正在准备"));
    return gallery;
  }

  let activeIndex = 0;
  let touchStartX = null;
  const stage = element("div", "media-gallery__stage");
  stage.id = stageId;
  stage.setAttribute("role", "group");
  stage.setAttribute("aria-roledescription", "slide");
  const stageMedia = element("div", "media-gallery__stage-media");
  const caption = element("p", "media-gallery__caption");
  caption.setAttribute("aria-live", "polite");
  const counter = element("span", "media-gallery__counter");
  const filmstrip = element("div", "media-gallery__filmstrip");
  filmstrip.setAttribute("role", "tablist");
  filmstrip.setAttribute("aria-label", "选择视觉资料");
  const previous = element("button", "media-gallery__arrow media-gallery__arrow--previous", "‹");
  previous.type = "button";
  previous.title = "上一张";
  previous.setAttribute("aria-label", "上一张");
  const next = element("button", "media-gallery__arrow media-gallery__arrow--next", "›");
  next.type = "button";
  next.title = "下一张";
  next.setAttribute("aria-label", "下一张");

  const thumbnailButtons = items.map((item, index) => {
    const button = element("button", "media-gallery__thumbnail");
    button.type = "button";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-label", `显示第 ${index + 1} 张：${item.label}`);
    const frame = element("span", "media-gallery__thumbnail-frame");
    frame.append(renderMediaFrame({
      localUrl: item.url,
      kind: "backdrop",
      title: item.label,
      status: item.status,
      source: item.source,
    }));
    button.append(frame, element("span", "media-gallery__thumbnail-index", String(index + 1).padStart(2, "0")));
    button.addEventListener("click", () => show(index));
    filmstrip.append(button);
    return button;
  });

  function show(index) {
    activeIndex = (index + items.length) % items.length;
    const item = items[activeIndex];
    stageMedia.replaceChildren(renderMediaFrame({
      localUrl: item.url,
      kind: "backdrop",
      title: textValue(title, "作品"),
      status: item.status,
      source: item.source,
    }));
    caption.textContent = item.label;
    counter.textContent = `${String(activeIndex + 1).padStart(2, "0")} / ${String(items.length).padStart(2, "0")}`;
    stage.setAttribute("aria-label", `${activeIndex + 1} / ${items.length}: ${item.label}`);
    thumbnailButtons.forEach((button, thumbnailIndex) => {
      const active = thumbnailIndex === activeIndex;
      button.tabIndex = active ? 0 : -1;
      button.setAttribute("aria-selected", active ? "true" : "false");
      if (active) button.setAttribute("aria-current", "true");
      else button.removeAttribute?.("aria-current");
    });
    const activeButton = thumbnailButtons[activeIndex];
    if (gallery.isConnected && typeof activeButton?.scrollIntoView === "function") {
      const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      activeButton.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest", inline: "center" });
    }
    gallery.dataset.index = String(activeIndex);
  }

  previous.addEventListener("click", () => show(activeIndex - 1));
  next.addEventListener("click", () => show(activeIndex + 1));
  gallery.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault?.();
      show(activeIndex - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault?.();
      show(activeIndex + 1);
    } else if (event.key === "Home") {
      event.preventDefault?.();
      show(0);
    } else if (event.key === "End") {
      event.preventDefault?.();
      show(items.length - 1);
    }
  });
  gallery.addEventListener("touchstart", (event) => {
    touchStartX = event.touches?.[0]?.clientX ?? null;
  }, { passive: true });
  gallery.addEventListener("touchend", (event) => {
    if (touchStartX === null) return;
    const endX = event.changedTouches?.[0]?.clientX;
    if (Number.isFinite(endX) && Math.abs(endX - touchStartX) > 42) show(activeIndex + (endX < touchStartX ? 1 : -1));
    touchStartX = null;
  }, { passive: true });

  const chrome = element("div", "media-gallery__chrome");
  chrome.append(caption, counter);
  stage.append(stageMedia, previous, next);
  gallery.append(stage, chrome, filmstrip);
  show(0);
  return gallery;
}
