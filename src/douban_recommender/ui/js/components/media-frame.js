import { isLocalMediaUrl, normalizeMediaAsset, preloadLocalMedia } from "../core/media.js";

const KIND_LABELS = {
  poster: "作品海报",
  backdrop: "作品背景",
  portrait: "人物肖像",
};

const IMAGE_ALT_LABELS = {
  poster: "海报",
  backdrop: "背景",
  portrait: "肖像",
};

const STATUS_LABELS = {
  error: "媒体加载失败",
  pending: "正在准备本地素材",
  processing: "正在处理本地素材",
  unavailable: "本地素材不可用",
  unverified: "本地素材待验证",
  missing: "本地素材缺失",
};

function createElement(tagName, className, text = "") {
  const element = document.createElement(tagName);
  element.className = className;
  if (text) element.textContent = text;
  return element;
}

/**
 * A named identity surface used whenever local media is unavailable. It is
 * intentionally pure DOM/CSS rather than an image placeholder.
 */
export function designedFallback(asset = {}) {
  const kind = asset.kind || "poster";
  const fallback = createElement("div", "media-fallback media-fallback--" + kind);
  fallback.setAttribute("role", "img");
  fallback.setAttribute("aria-label", asset.title + " · " + KIND_LABELS[kind]);

  const glyph = createElement("span", "media-fallback__glyph", kind === "portrait" ? "人" : "CS");
  glyph.setAttribute("aria-hidden", "true");
  const title = createElement("strong", "media-fallback__title", asset.title);
  const status = createElement(
    "span",
    "media-fallback__status",
    STATUS_LABELS[asset.status] || "本地素材待显示",
  );

  fallback.append(glyph, title, status);
  return fallback;
}

/**
 * Renders a stable frame immediately. A visible image replaces its fallback
 * only after the same off-DOM Image element has loaded, decoded, and retained
 * non-zero intrinsic width.
 */
export function renderMediaFrame(asset = {}) {
  const normalized = normalizeMediaAsset(asset);
  const frame = createElement("div", "media-frame media-frame--" + normalized.kind);
  frame.dataset.mediaState = "fallback";
  frame.dataset.mediaSource = normalized.source;

  const fallback = designedFallback(normalized);
  frame.append(fallback);

  if (normalized.status !== "ready" || !isLocalMediaUrl(normalized.localUrl)) return frame;

  let generation = 0;
  const showError = () => {
    if (frame.firstElementChild !== fallback) frame.replaceChildren(fallback);
    frame.dataset.mediaState = "error";
    fallback.dataset.mediaState = "error";
    const status = fallback.querySelector?.(".media-fallback__status") || fallback.children?.[2];
    if (status) status.textContent = STATUS_LABELS.error || "媒体加载失败";
    const retry = createElement("button", "media-frame__retry", "重试");
    retry.type = "button";
    if (typeof retry.addEventListener === "function") retry.addEventListener("click", () => load());
    else retry.onclick = () => load();
    frame.append(retry);
  };
  const load = () => {
    const requestGeneration = ++generation;
    frame.dataset.mediaState = "loading";
    fallback.dataset.mediaState = "loading";
    frame.replaceChildren(fallback);
    preloadLocalMedia(normalized.localUrl).then((image) => {
      if (requestGeneration !== generation) return;
      if (!image) {
        showError();
        return;
      }
      image.tagName ||= "IMG";
      image.alt = normalized.title + " " + IMAGE_ALT_LABELS[normalized.kind];
      image.className = "media-frame__image";
      frame.replaceChildren(image);
      frame.dataset.mediaState = "ready";
    }).catch(() => {
      if (requestGeneration === generation) showError();
    });
  };
  load();

  return frame;
}
