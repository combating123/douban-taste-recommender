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
  "[tabindex]",
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

function negativeTabIndex(node) {
  const value = node?.getAttribute?.("tabindex");
  if (value === null || value === undefined || value === "") return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed < 0;
}

function hiddenBySelfOrAncestor(node) {
  for (let current = node; current; current = current.parentElement) {
    if (current.isConnected === false || current.hidden || current.inert) return true;
    if (current.getAttribute?.("aria-hidden") === "true" || current.hasAttribute?.("hidden") || current.hasAttribute?.("inert")) return true;
    if (typeof globalThis.getComputedStyle === "function") {
      try {
        const style = globalThis.getComputedStyle(current);
        if (style?.display === "none" || style?.visibility === "hidden" || style?.visibility === "collapse") return true;
      } catch {
        return true;
      }
    }
  }
  return false;
}

function isFocusable(node) {
  if (!node || typeof node.focus !== "function" || node.disabled || node.hasAttribute?.("disabled")) return false;
  if (negativeTabIndex(node) || hiddenBySelfOrAncestor(node)) return false;
  if (node.tagName === "A" || node.tagName === "AREA") return Boolean(node.getAttribute?.("href"));
  if (node.tagName === "INPUT" && String(node.type || node.getAttribute?.("type") || "").toLowerCase() === "hidden") return false;
  return true;
}

function focusables(element) {
  return candidateNodes(element).filter(isFocusable);
}

export function trapFocus(element, { onEscape } = {}) {
  if (!element || !globalThis.document?.addEventListener) return () => {};
  let released = false;
  const hadTabIndex = Boolean(element.hasAttribute?.("tabindex"));
  const originalTabIndex = element.getAttribute?.("tabindex") ?? null;
  let changedDialogTabIndex = false;
  const focusDialog = () => {
    if (element.getAttribute?.("tabindex") !== "-1") {
      element.setAttribute?.("tabindex", "-1");
      changedDialogTabIndex = true;
    }
    element.focus?.({ preventScroll: true });
  };
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
      focusDialog();
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
    if (changedDialogTabIndex) {
      if (hadTabIndex) element.setAttribute?.("tabindex", originalTabIndex ?? "");
      else element.removeAttribute?.("tabindex");
    }
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
