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
 * only after the same hidden mounted Image element has loaded, decoded, and
 * retained non-zero intrinsic width.
 */
export function renderMediaFrame(asset = {}, options = {}) {
  const normalized = normalizeMediaAsset(asset);
  const frame = createElement("div", "media-frame media-frame--" + normalized.kind);
  frame.dataset.mediaState = "fallback";
  frame.dataset.mediaSource = normalized.source;

  const fallback = designedFallback(normalized);
  frame.append(fallback);

  let generation = 0;
  let disposed = false;
  let activePreload = null;
  const dispose = () => {
    if (disposed) return false;
    disposed = true;
    generation += 1;
    const hadActivePreload = Boolean(activePreload);
    activePreload?.cancel?.();
    activePreload = null;
    if (hadActivePreload) {
      frame.replaceChildren(fallback);
      frame.dataset.mediaState = "fallback";
      fallback.dataset.mediaState = "fallback";
    }
    return true;
  };
  frame.disposeMediaFrame = dispose;

  if (normalized.status !== "ready" || !isLocalMediaUrl(normalized.localUrl)) return frame;

  const showError = () => {
    if (disposed) return;
    if (frame.firstElementChild !== fallback) frame.replaceChildren(fallback);
    frame.dataset.mediaState = "error";
    fallback.dataset.mediaState = "error";
    const status = fallback.querySelector?.(".media-fallback__status") || fallback.children?.[2];
    if (status) status.textContent = STATUS_LABELS.error || "\u5a92\u4f53\u52a0\u8f7d\u5931\u8d25";
    const retry = createElement("button", "media-frame__retry", "\u91cd\u8bd5");
    retry.type = "button";
    if (typeof retry.addEventListener === "function") retry.addEventListener("click", () => load());
    else retry.onclick = () => load();
    frame.append(retry);
  };
  const load = () => {
    if (disposed) return;
    activePreload?.cancel?.();
    const requestGeneration = ++generation;
    frame.dataset.mediaState = "loading";
    fallback.dataset.mediaState = "loading";
    frame.replaceChildren(fallback);
    const request = preloadLocalMedia(normalized.localUrl, frame, {
      priority: options.priority,
      coordinator: options.coordinator,
      backgroundOnly: options.backgroundOnly,
    });
    activePreload = request;
    request.then((image) => {
      if (activePreload === request) activePreload = null;
      if (disposed || requestGeneration !== generation) return;
      if (!image) {
        showError();
        return;
      }
      image.tagName ||= "IMG";
      image.hidden = false;
      image.alt = normalized.title + " " + IMAGE_ALT_LABELS[normalized.kind];
      image.className = "media-frame__image";
      frame.replaceChildren(image);
      frame.dataset.mediaState = "ready";
    }).catch(() => {
      if (activePreload === request) activePreload = null;
      if (!disposed && requestGeneration === generation) showError();
    });
  };
  load();

  return frame;
}

export function disposeMediaFrame(frame) {
  return frame?.disposeMediaFrame?.() || false;
}
