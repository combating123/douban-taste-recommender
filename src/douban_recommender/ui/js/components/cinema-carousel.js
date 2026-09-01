function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function element(tagName, className = "", text = "") {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function safeId(value, fallback) {
  const text = textValue(value, fallback);
  return text.replace(/[^\w:-]+/g, "-").replace(/^-+|-+$/g, "") || fallback;
}

function trustedVisualUrl(value) {
  const text = textValue(value);
  if (!text) return "";
  if (text.startsWith("/media/") || text.startsWith("/api/image-proxy?url=")) return text;
  if (/^https?:\/\//i.test(text)) return `/api/image-proxy?url=${encodeURIComponent(text)}`;
  return "";
}

function mediaFromSlide(slide = {}) {
  const media = slide.media && typeof slide.media === "object" ? slide.media : {};
  const url = trustedVisualUrl(media.localUrl || media.url || slide.image || slide.backdrop || slide.poster);
  return {
    url,
    kind: textValue(media.kind, "backdrop"),
    status: textValue(media.status, url ? "ready" : "missing"),
    title: textValue(media.title, textValue(slide.title, "影院精选")),
  };
}

function reducedMotion() {
  try {
    return Boolean(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
  } catch {
    return false;
  }
}

function renderVisual(slide) {
  const media = mediaFromSlide(slide);
  const frame = element("div", `cinema-carousel__visual cinema-carousel__visual--${media.kind}`);
  frame.dataset.mediaState = media.url ? "loading" : "missing";
  if (!media.url) {
    frame.append(
      element("span", "cinema-carousel__visual-mark", "CS"),
      element("span", "cinema-carousel__visual-title", media.title),
      element("span", "cinema-carousel__visual-status", "视觉资料准备中"),
    );
    return frame;
  }
  const image = document.createElement("img");
  image.className = "cinema-carousel__image";
  image.alt = `${media.title}宽幅剧照`;
  image.loading = "eager";
  image.decoding = "async";
  image.hidden = true;
  const loading = element("div", "cinema-carousel__loading");
  loading.setAttribute("aria-hidden", "true");
  loading.append(
    element("span", "cinema-carousel__loading-mark", "CS"),
    element("span", "cinema-carousel__loading-line"),
    element("span", "cinema-carousel__loading-line cinema-carousel__loading-line--short"),
  );
  const fallback = () => {
    if (frame.dataset.mediaState === "error") return;
    frame.dataset.mediaState = "error";
    frame.replaceChildren(
      element("span", "cinema-carousel__visual-mark", "CS"),
      element("span", "cinema-carousel__visual-title", media.title),
      element("span", "cinema-carousel__visual-status", "视觉资料暂不可用"),
    );
  };
  image.addEventListener?.("load", () => {
    const naturalWidth = Number(image.naturalWidth);
    if (Number.isFinite(naturalWidth) && naturalWidth <= 0) {
      fallback();
      return;
    }
    image.hidden = false;
    frame.dataset.mediaState = "ready";
    loading.remove?.();
  }, { once: true });
  image.addEventListener?.("error", fallback, { once: true });
  frame.append(loading, image);
  image.src = media.url;
  return frame;
}

function normalizeSlides(values) {
  const source = Array.isArray(values) ? values : [];
  const seen = new Set();
  return source.flatMap((value, index) => {
    const slide = value && typeof value === "object" ? { ...value } : { title: value };
    const id = safeId(slide.id || slide.itemKey || slide.item_key, `slide-${index + 1}`);
    if (seen.has(id)) return [];
    seen.add(id);
    return [{ ...slide, id, title: textValue(slide.title, `精选 ${index + 1}`) }];
  });
}

/**
 * A quiet, cinema-style carousel: one clear stage, a large filmstrip, and
 * explicit controls. It never auto-rotates, so focus and reading position stay
 * under the viewer's control.
 */
export function renderCinemaCarousel({
  slides = [],
  title = "影院精选",
  ariaLabel = "影院精选轮播",
  initialIndex = 0,
  renderContent = null,
  onSelect = null,
} = {}) {
  const items = normalizeSlides(slides);
  const root = element("section", "cinema-carousel");
  root.setAttribute("role", "region");
  root.setAttribute("aria-roledescription", "carousel");
  root.setAttribute("aria-label", ariaLabel);
  root.setAttribute("tabindex", "0");
  root.dataset.title = title;
  root.dataset.index = "0";

  const stage = element("div", "cinema-carousel__stage");
  const stageMedia = element("div", "cinema-carousel__stage-media");
  const stageShade = element("div", "cinema-carousel__stage-shade");
  const stageContent = element("div", "cinema-carousel__stage-content");
  const previous = element("button", "cinema-carousel__arrow cinema-carousel__arrow--previous", "‹");
  previous.type = "button";
  previous.dataset.carouselPrevious = "true";
  previous.setAttribute("aria-label", "上一部推荐");
  const next = element("button", "cinema-carousel__arrow cinema-carousel__arrow--next", "›");
  next.type = "button";
  next.dataset.carouselNext = "true";
  next.setAttribute("aria-label", "下一部推荐");
  stage.append(stageMedia, stageShade, stageContent, previous, next);

  const track = element("div", "cinema-carousel__track");
  track.dataset.carouselTrack = "true";
  track.setAttribute("role", "listbox");
  track.setAttribute("aria-label", "选择推荐影片");
  if (track.style) {
    track.style.scrollSnapType = "x mandatory"; // scroll-snap baseline when stylesheets load late
    track.style.overscrollBehaviorInline = "contain";
  }

  let activeIndex = 0;
  let pointerStartX = null;
  let pointerStartY = null;
  let capturedPointerId = null;
  let suppressClick = false;
  const slideButtons = [];

  const announce = (item, index) => {
    root.dataset.index = String(index);
    root.dataset.activeId = item.id;
    root.setAttribute("aria-label", `${ariaLabel}：${item.title}，第 ${index + 1} / ${items.length} 部`);
  };

  const show = (nextIndex, { notify = true } = {}) => {
    if (!items.length) return;
    activeIndex = (nextIndex + items.length) % items.length;
    const item = items[activeIndex];
    stageMedia.replaceChildren(renderVisual(item));
    stageContent.replaceChildren(
      typeof renderContent === "function"
        ? renderContent(item, activeIndex)
        : element("h2", "cinema-carousel__title", item.title),
    );
    slideButtons.forEach((button, index) => {
      const active = index === activeIndex;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.setAttribute("aria-current", active ? "true" : "false");
      button.dataset.active = active ? "true" : "false";
    });
    const activeButton = slideButtons[activeIndex];
    activeButton?.scrollIntoView?.({
      behavior: reducedMotion() ? "auto" : "smooth",
      block: "nearest",
      inline: "center",
    });
    announce(item, activeIndex);
    if (notify && typeof onSelect === "function") onSelect(item, activeIndex);
  };

  items.forEach((item, index) => {
    const button = element("button", "cinema-carousel__slide");
    button.type = "button";
    button.dataset.carouselSlide = item.id;
    button.dataset.index = String(index);
    button.setAttribute("role", "option");
    button.setAttribute("aria-label", `显示 ${item.title}`);
    const thumbnail = element("span", "cinema-carousel__slide-thumb");
    thumbnail.append(renderVisual(item));
    const meta = element("span", "cinema-carousel__slide-meta");
    meta.append(
      element("span", "cinema-carousel__slide-index", String(index + 1).padStart(2, "0")),
      element("span", "cinema-carousel__slide-title", item.title),
    );
    button.append(thumbnail, meta);
    button.addEventListener?.("click", (event) => {
      if (suppressClick) {
        suppressClick = false;
        event.preventDefault?.();
        return;
      }
      show(index);
    });
    track.append(button);
    slideButtons.push(button);
  });

  const move = (delta) => show(activeIndex + delta);
  previous.addEventListener?.("click", () => move(-1));
  next.addEventListener?.("click", () => move(1));
  root.addEventListener?.("keydown", (event) => {
    if (event.key === "ArrowLeft") { event.preventDefault?.(); move(-1); }
    if (event.key === "ArrowRight") { event.preventDefault?.(); move(1); }
    if (event.key === "Home") { event.preventDefault?.(); show(0); }
    if (event.key === "End") { event.preventDefault?.(); show(items.length - 1); }
  });
  track.addEventListener?.("wheel", (event) => {
    const deltaX = Number(event.deltaX) || 0;
    const deltaY = Number(event.deltaY) || 0;
    const intendedDelta = event.shiftKey && !deltaX ? deltaY : deltaX;
    if (!intendedDelta) return;
    if (!event.shiftKey && Math.abs(deltaX) < Math.abs(deltaY)) return;
    if (Math.abs(intendedDelta) < 12) return;
    event.preventDefault?.();
    move(intendedDelta > 0 ? 1 : -1);
  }, { passive: false });
  const captureDragPointer = (pointerId) => {
    if (capturedPointerId !== null || !Number.isFinite(Number(pointerId))) return;
    if (typeof track.setPointerCapture !== "function") return;
    try {
      track.setPointerCapture(pointerId);
      capturedPointerId = pointerId;
    } catch (_) {}
  };
  const releaseDragPointer = () => {
    if (capturedPointerId === null) return;
    try {
      if (typeof track.releasePointerCapture === "function"
        && (typeof track.hasPointerCapture !== "function" || track.hasPointerCapture(capturedPointerId))) {
        track.releasePointerCapture(capturedPointerId);
      }
    } catch (_) {}
    capturedPointerId = null;
  };
  track.addEventListener?.("pointerdown", (event) => {
    pointerStartX = Number(event.clientX);
    pointerStartY = Number(event.clientY);
  });
  track.addEventListener?.("pointermove", (event) => {
    if (pointerStartX === null) return;
    const dx = Number(event.clientX) - pointerStartX;
    const dy = Number(event.clientY) - (pointerStartY ?? Number(event.clientY));
    if (Math.abs(dx) > 24 && Math.abs(dx) > Math.abs(dy)) {
      track.dataset.dragging = "true";
      captureDragPointer(event.pointerId);
    }
  });
  track.addEventListener?.("pointerup", (event) => {
    if (pointerStartX === null) return;
    const dx = Number(event.clientX) - pointerStartX;
    if (Math.abs(dx) > 42) {
      suppressClick = true;
      move(dx < 0 ? 1 : -1);
      globalThis.setTimeout?.(() => { suppressClick = false; }, 0);
    }
    releaseDragPointer();
    pointerStartX = null;
    pointerStartY = null;
    track.dataset.dragging = "false";
  });
  track.addEventListener?.("pointercancel", () => {
    releaseDragPointer();
    pointerStartX = null;
    pointerStartY = null;
    suppressClick = false;
    track.dataset.dragging = "false";
  });
  track.addEventListener?.("click", (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.preventDefault?.();
    event.stopPropagation?.();
  }, true);
  track.addEventListener?.("touchstart", (event) => {
    pointerStartX = event.touches?.[0]?.clientX ?? null;
  }, { passive: true });
  track.addEventListener?.("touchend", (event) => {
    if (pointerStartX === null) return;
    const endX = event.changedTouches?.[0]?.clientX;
    if (Number.isFinite(endX) && Math.abs(endX - pointerStartX) > 42) move(endX < pointerStartX ? 1 : -1);
    pointerStartX = null;
  }, { passive: true });

  root.append(stage, track);
  if (!items.length) {
    root.dataset.state = "empty";
    stageContent.append(element("p", "cinema-carousel__empty", "今晚还没有可展示的推荐"));
    previous.disabled = true;
    next.disabled = true;
    return root;
  }
  show(Math.max(0, Math.min(items.length - 1, Number(initialIndex) || 0)), { notify: false });
  return root;
}
