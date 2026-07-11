const ALLOWED_OVERFLOW_CLASSES = new Set([
  "title-shelf__rail",
  "detail-tabs",
  "detail-people-rail",
  "library-window",
  "universe-evidence",
  "universe-roster",
  "universe-node-roster",
  "command-lens",
  "person-sheet",
  "person-sheet__body",
]);

function locationUrl(locationLike) {
  if (!locationLike) return null;
  try {
    if (typeof locationLike.href === "string" && locationLike.href) return new URL(locationLike.href);
    if (typeof locationLike.origin === "string" && locationLike.origin !== "null") {
      return new URL(`${locationLike.pathname || "/"}${locationLike.search || ""}${locationLike.hash || ""}`, locationLike.origin);
    }
    const protocol = typeof locationLike.protocol === "string" ? locationLike.protocol : "";
    let hostname = typeof locationLike.hostname === "string" ? locationLike.hostname : "";
    if (hostname.includes(":") && !hostname.startsWith("[")) hostname = `[${hostname}]`;
    const port = locationLike.port ? `:${locationLike.port}` : "";
    if (protocol && hostname) return new URL(`${protocol}//${hostname}${port}${locationLike.pathname || "/"}`);
    return new URL(String(locationLike));
  } catch {
    return null;
  }
}

export function isLocalHookLocation(locationLike = globalThis.location) {
  const url = locationUrl(locationLike);
  if (!url || !["http:", "https:"].includes(url.protocol)) return false;
  const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (hostname === "localhost" || hostname.endsWith(".localhost") || hostname === "::1") return true;
  const octets = hostname.split(".");
  return octets.length === 4
    && octets.every((octet) => /^\d{1,3}$/.test(octet) && Number(octet) <= 255)
    && Number(octets[0]) === 127;
}

function computedStyle(node) {
  try {
    return globalThis.getComputedStyle?.(node) || {};
  } catch {
    return {};
  }
}

function isVisible(node) {
  if (!node || node.hidden) return false;
  if (node.closest?.("[hidden]")) return false;
  const style = computedStyle(node);
  if (style.display === "none" || ["hidden", "collapse"].includes(style.visibility)) return false;
  if (typeof node.getClientRects === "function" && node.getClientRects().length === 0) return false;
  return true;
}

function numberDimension(value) {
  return Number.isFinite(Number(value)) ? Math.max(0, Math.round(Number(value))) : 0;
}

function structuralPath(node) {
  const parts = [];
  for (let current = node; current?.tagName; current = current.parentElement) {
    const tag = String(current.tagName).toLowerCase();
    const siblings = Array.from(current.parentElement?.children || [])
      .filter((sibling) => sibling?.tagName === current.tagName);
    const suffix = siblings.length > 1 ? `:nth-of-type(${siblings.indexOf(current) + 1})` : "";
    parts.push(`${tag}${suffix}`);
  }
  return parts.reverse().join(">");
}

function describeNode(node) {
  return {
    tag: String(node?.tagName || "unknown").toLowerCase(),
    path: structuralPath(node),
    dimensions: {
      client: [numberDimension(node?.clientWidth), numberDimension(node?.clientHeight)],
      scroll: [numberDimension(node?.scrollWidth), numberDimension(node?.scrollHeight)],
    },
  };
}

function describe(nodes) {
  return nodes.map(describeNode);
}

function isAllowedOverflowNode(node) {
  return [...ALLOWED_OVERFLOW_CLASSES].some((className) => node?.classList?.contains?.(className));
}

function validMediaImage(image, locationLike) {
  const page = locationUrl(locationLike);
  if (!page) return false;
  try {
    const source = new URL(image.currentSrc || image.src, page.href);
    return source.origin === page.origin && source.pathname.startsWith("/media/");
  } catch {
    return false;
  }
}

function isUsableFocusTarget(node) {
  if (
    !isVisible(node)
    || node.inert
    || node.closest?.("[inert]")
    || node.disabled
    || node.hasAttribute?.("disabled")
    || node.getAttribute?.("aria-disabled") === "true"
  ) return false;
  const actualTabIndex = Number(node.tabIndex);
  if (Number.isFinite(actualTabIndex)) return actualTabIndex >= 0;
  const tag = String(node.tagName || "").toLowerCase();
  if (["button", "select", "textarea"].includes(tag)) return true;
  if (tag === "input") return String(node.type || node.getAttribute?.("type") || "").toLowerCase() !== "hidden";
  if (tag === "a" && Boolean(node.getAttribute?.("href") || node.href)) return true;
  const tabindex = node.getAttribute?.("tabindex");
  return tabindex !== null && Number(tabindex) >= 0;
}

function modalDialogs(documentRef) {
  return [...(documentRef?.querySelectorAll?.('[role="dialog"][aria-modal="true"], dialog[open]') || [])]
    .filter((dialog) => {
      if (!isVisible(dialog)) return false;
      if (dialog.getAttribute?.("aria-modal") === "true") return true;
      try {
        return dialog.matches?.(":modal") === true;
      } catch {
        return false;
      }
    });
}

export function runAudit({
  browser = globalThis.window,
  documentRef = globalThis.document,
  locationLike = browser?.location || globalThis.location,
} = {}) {
  const images = [...(documentRef?.images || [])].filter(isVisible);
  const brokenImages = images.filter((image) => image.complete && image.naturalWidth === 0);
  const externalImages = images.filter((image) => !validMediaImage(image, locationLike));
  const overflowNodes = [...(documentRef?.querySelectorAll?.("body *") || [])].filter((node) => {
    if (!isVisible(node) || isAllowedOverflowNode(node)) return false;
    const style = computedStyle(node);
    return Number(node.scrollWidth) > Number(node.clientWidth) + 2 && style.overflowX === "visible";
  });
  const main = documentRef?.querySelector?.("#app-view") || documentRef?.querySelector?.("main");
  const focusFailures = modalDialogs(documentRef).filter((dialog) => {
    const activeElement = documentRef?.activeElement;
    const activeInside = Boolean(activeElement && dialog.contains?.(activeElement));
    const focusTargets = [dialog, ...(dialog.querySelectorAll?.("*") || [])].filter(isUsableFocusTarget);
    return !activeInside || focusTargets.length === 0;
  });

  return {
    route: locationUrl(locationLike)?.pathname || "/",
    viewport: [
      numberDimension(browser?.innerWidth ?? globalThis.innerWidth),
      numberDimension(browser?.innerHeight ?? globalThis.innerHeight),
    ],
    brokenImages: describe(brokenImages),
    externalImages: describe(externalImages),
    overflowNodes: describe(overflowNodes),
    emptyMain: !String(main?.textContent || "").trim(),
    focusFailures: describe(focusFailures),
    reducedMotion: Boolean(browser?.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches),
  };
}

export function installAuditHook({ browser = globalThis.window } = {}) {
  if (!browser || !isLocalHookLocation(browser.location)) return () => {};
  const hook = () => runAudit({ browser, documentRef: browser.document || globalThis.document, locationLike: browser.location });
  browser.__CINESCOPE_AUDIT__ = hook;
  return () => {
    if (browser.__CINESCOPE_AUDIT__ === hook) delete browser.__CINESCOPE_AUDIT__;
  };
}
