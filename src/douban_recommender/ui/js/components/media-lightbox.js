import { attachResilientImage, MEDIA_LOAD_PRIORITY, preloadLocalMedia } from "../core/media.js";

let activeLightbox = null;

function element(documentTarget, tagName, className, text = "") {
  const node = documentTarget.createElement(tagName);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function normalizeItems(items) {
  const seen = new Set();
  return (Array.isArray(items) ? items : []).flatMap((item, index) => {
    const value = item && typeof item === "object" ? item : { url: item };
    const url = typeof value.url === "string" ? value.url.trim() : "";
    if (!url || seen.has(url)) return [];
    seen.add(url);
    return [{
      url,
      label: typeof value.label === "string" && value.label.trim() ? value.label.trim() : `剧照 ${index + 1}`,
      kind: typeof value.kind === "string" ? value.kind : "still",
    }];
  });
}

function wrappedIndex(index, length) {
  if (!length) return 0;
  return ((Number(index) || 0) % length + length) % length;
}

function preloadNeighbours(items, index) {
  if (items.length < 2) return [];
  const handles = [];
  const seen = new Set();
  for (const offset of [-2, -1, 1, 2]) {
    const candidate = items[wrappedIndex(index + offset, items.length)];
    if (!candidate?.url || seen.has(candidate.url)) continue;
    seen.add(candidate.url);
    handles.push(preloadLocalMedia(candidate.url, null, {
      priority: MEDIA_LOAD_PRIORITY.background,
    }));
  }
  return handles;
}

export function closeMediaLightbox() {
  activeLightbox?.close?.();
}

export function openMediaLightbox({
  items = [],
  index = 0,
  title = "作品剧照",
  detailHref = "",
  trigger = null,
  documentTarget = globalThis.document,
  windowTarget = globalThis.window,
} = {}) {
  const media = normalizeItems(items);
  if (!media.length || !documentTarget?.createElement || !documentTarget?.body) return null;

  activeLightbox?.close?.({ restoreFocus: false });

  let currentIndex = wrappedIndex(index, media.length);
  let closed = false;
  let mountedImage = null;
  let neighbourPreloads = [];
  const body = documentTarget.body;
  const previousOverflow = body.style?.overflow || "";
  const backdrop = element(documentTarget, "div", "media-lightbox__backdrop");
  const dialog = element(documentTarget, "section", "media-lightbox");
  const header = element(documentTarget, "header", "media-lightbox__header");
  const heading = element(documentTarget, "div", "media-lightbox__heading");
  const eyebrow = element(documentTarget, "span", "media-lightbox__eyebrow", "CINEMATIC GALLERY");
  const titleNode = element(documentTarget, "h2", "media-lightbox__title", title || "作品剧照");
  const counter = element(documentTarget, "span", "media-lightbox__counter");
  const closeButton = element(documentTarget, "button", "media-lightbox__close", "关闭");
  const stage = element(documentTarget, "div", "media-lightbox__stage");
  const previousButton = element(documentTarget, "button", "media-lightbox__nav media-lightbox__nav--previous", "上一张");
  const nextButton = element(documentTarget, "button", "media-lightbox__nav media-lightbox__nav--next", "下一张");
  const figure = element(documentTarget, "figure", "media-lightbox__figure");
  const imageMount = element(documentTarget, "div", "media-lightbox__image-mount");
  const caption = element(documentTarget, "figcaption", "media-lightbox__caption");
  const footer = element(documentTarget, "footer", "media-lightbox__footer");

  backdrop.setAttribute("role", "presentation");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-label", `${title || "作品"}剧照查看器`);
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "关闭剧照查看器");
  previousButton.type = "button";
  previousButton.setAttribute("aria-label", "查看上一张剧照");
  nextButton.type = "button";
  nextButton.setAttribute("aria-label", "查看下一张剧照");

  heading.append(eyebrow, titleNode);
  header.append(heading, counter, closeButton);
  figure.append(imageMount, caption);
  stage.append(previousButton, figure, nextButton);

  if (detailHref) {
    const detailLink = element(documentTarget, "a", "media-lightbox__detail", "查看完整详情");
    detailLink.setAttribute("href", detailHref);
    detailLink.setAttribute("data-route", "");
    footer.append(detailLink);
  } else {
    footer.append(element(documentTarget, "span", "media-lightbox__detail media-lightbox__detail--disabled", "查看完整详情"));
  }

  dialog.append(header, stage, footer);
  backdrop.append(dialog);

  const cancelNeighbourPreloads = () => {
    for (const preload of neighbourPreloads) preload?.cancel?.();
    neighbourPreloads = [];
  };

  const renderCurrent = () => {
    const item = media[currentIndex];
    mountedImage?.cancel?.();
    cancelNeighbourPreloads();
    imageMount.replaceChildren();
    imageMount.dataset.state = "loading";
    const image = documentTarget.createElement("img");
    image.className = "media-lightbox__image";
    image.alt = `${title || "作品"} · ${item.label}`;
    image.decoding = "async";
    image.fetchPriority = "high";
    image.hidden = true;
    const loading = element(documentTarget, "div", "media-lightbox__loading");
    loading.setAttribute("aria-hidden", "true");
    loading.append(
      element(documentTarget, "span", "media-lightbox__loading-mark", "CS"),
      element(documentTarget, "span", "media-lightbox__loading-copy", "正在加载高清剧照"),
    );
    const fallback = () => {
      imageMount.dataset.state = "error";
      imageMount.replaceChildren(element(documentTarget, "p", "media-lightbox__fallback", "这张图片暂时无法显示，可继续查看相邻剧照。"));
    };
    image.addEventListener?.("load", () => {
      const naturalWidth = Number(image.naturalWidth);
      if (Number.isFinite(naturalWidth) && naturalWidth <= 0) {
        fallback();
        return;
      }
      image.hidden = false;
      imageMount.dataset.state = "ready";
      loading.remove?.();
    }, { once: true });
    imageMount.append(loading, image);
    mountedImage = attachResilientImage(image, item.url, {
      maxRetries: 0,
      priority: MEDIA_LOAD_PRIORITY.foreground,
      onFailure: fallback,
    });
    counter.textContent = `${currentIndex + 1} / ${media.length}`;
    caption.textContent = item.label;
    previousButton.disabled = media.length < 2;
    nextButton.disabled = media.length < 2;
    neighbourPreloads = preloadNeighbours(media, currentIndex);
  };

  const show = (nextIndex) => {
    currentIndex = wrappedIndex(nextIndex, media.length);
    renderCurrent();
  };
  const previous = () => show(currentIndex - 1);
  const next = () => show(currentIndex + 1);

  const handleKeydown = (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault?.();
      previous();
    } else if (event.key === "ArrowRight") {
      event.preventDefault?.();
      next();
    } else if (event.key === "Escape") {
      event.preventDefault?.();
      close();
    }
  };

  const close = ({ restoreFocus = true } = {}) => {
    if (closed) return;
    closed = true;
    mountedImage?.cancel?.();
    cancelNeighbourPreloads();
    documentTarget.removeEventListener?.("keydown", handleKeydown, true);
    backdrop.remove?.();
    if (body.style) body.style.overflow = previousOverflow;
    if (activeLightbox?.element === backdrop) activeLightbox = null;
    if (restoreFocus) trigger?.focus?.();
  };

  closeButton.addEventListener("click", () => close());
  previousButton.addEventListener("click", previous);
  nextButton.addEventListener("click", next);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close();
  });
  documentTarget.addEventListener?.("keydown", handleKeydown, true);
  if (body.style) body.style.overflow = "hidden";
  body.append(backdrop);
  renderCurrent();
  closeButton.focus?.({ preventScroll: true });

  activeLightbox = {
    element: backdrop,
    close,
    next,
    previous,
    get index() { return currentIndex; },
  };
  return activeLightbox;
}
