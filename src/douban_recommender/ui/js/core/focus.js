const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "audio[controls]",
  "video[controls]",
  "[contenteditable]:not([contenteditable='false'])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

let announcementGeneration = 0;

function candidateNodes(element) {
  if (typeof element?.querySelectorAll === "function") {
    return [...element.querySelectorAll(FOCUSABLE_SELECTOR)];
  }
  const nodes = [];
  const visit = (node) => {
    for (const child of node?.children || []) {
      if (["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(child?.tagName)) nodes.push(child);
      visit(child);
    }
  };
  visit(element);
  return nodes;
}

function isFocusable(node) {
  if (!node || typeof node.focus !== "function" || node.disabled || node.hidden || node.inert) return false;
  if (node.isConnected === false || node.getAttribute?.("aria-hidden") === "true") return false;
  if (node.getAttribute?.("tabindex") === "-1") return false;
  if (typeof globalThis.getComputedStyle === "function") {
    const style = globalThis.getComputedStyle(node);
    if (style?.display === "none" || style?.visibility === "hidden") return false;
  }
  return true;
}

function focusables(element) {
  return candidateNodes(element).filter(isFocusable);
}

export function trapFocus(element, { onEscape } = {}) {
  if (!element || !globalThis.document?.addEventListener) return () => {};
  let released = false;
  const onKeyDown = (event) => {
    if (released) return;
    if (event.key === "Escape" && typeof onEscape === "function") {
      event.preventDefault?.();
      onEscape(event);
      return;
    }
    if (event.key !== "Tab") return;
    const available = focusables(element);
    if (!available.length) {
      event.preventDefault?.();
      element.focus?.({ preventScroll: true });
      return;
    }
    const first = available[0];
    const last = available.at(-1);
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !element.contains?.(active))) {
      event.preventDefault?.();
      last.focus({ preventScroll: true });
    } else if (!event.shiftKey && (active === last || !element.contains?.(active))) {
      event.preventDefault?.();
      first.focus({ preventScroll: true });
    }
  };
  document.addEventListener("keydown", onKeyDown);
  return () => {
    if (released) return;
    released = true;
    document.removeEventListener?.("keydown", onKeyDown);
  };
}

export function announce(message) {
  const announcer = globalThis.document?.getElementById?.("a11y-announcer");
  if (!announcer) return false;
  const text = typeof message === "string" ? message.trim() : "";
  const generation = ++announcementGeneration;
  announcer.textContent = "";
  queueMicrotask(() => {
    if (generation === announcementGeneration && announcer.isConnected !== false) announcer.textContent = text;
  });
  return true;
}
