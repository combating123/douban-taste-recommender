const OVERFLOW_EPSILON = 1;

function finiteMetric(value) {
  const metric = Number(value);
  return Number.isFinite(metric) && metric >= 0 ? metric : null;
}

/**
 * Return true only when the browser has measured content beyond the clamped
 * box.  A missing metric is deliberately treated as "unknown" so contract
 * tests and non-layout renderers can still use the conservative text-length
 * fallback supplied by the caller.
 */
export function isCopyOverflowing(node) {
  if (!node) return false;
  const clientHeight = finiteMetric(node.clientHeight);
  const scrollHeight = finiteMetric(node.scrollHeight);
  const clientWidth = finiteMetric(node.clientWidth);
  const scrollWidth = finiteMetric(node.scrollWidth);
  const vertical = clientHeight !== null && scrollHeight !== null
    && scrollHeight > clientHeight + OVERFLOW_EPSILON;
  const horizontal = clientWidth !== null && scrollWidth !== null
    && scrollWidth > clientWidth + OVERFLOW_EPSILON;
  return vertical || horizontal;
}

function hasLayoutMetrics(node) {
  return finiteMetric(node?.clientHeight) !== null
    && finiteMetric(node?.scrollHeight) !== null;
}

/**
 * Synchronise the visibility of an expandable-copy control with the actual
 * rendered dimensions.  The fallback is used only when the target has not
 * exposed layout metrics (for example while a detached card is being built).
 */
export function syncExpandableCopyControl(control, nodes = [], fallbackVisible = false, expanded = false) {
  if (!control) return false;
  const targets = (Array.isArray(nodes) ? nodes : [nodes]).filter(Boolean);
  const measured = targets.some(hasLayoutMetrics);
  const overflowing = targets.some(isCopyOverflowing);
  const visible = Boolean(expanded) || (measured ? overflowing : Boolean(fallbackVisible));
  control.hidden = !visible;
  if (control.dataset) {
    control.dataset.copyOverflow = measured ? (overflowing ? "true" : "false") : "unknown";
  }
  return visible;
}

function schedule(callback) {
  if (typeof globalThis.requestAnimationFrame === "function") {
    globalThis.requestAnimationFrame(callback);
    return;
  }
  // Do not keep a detached test process alive solely for a measurement pass.
  // Real browsers provide requestAnimationFrame; the synchronous pass below
  // remains sufficient for non-layout environments.
}

/**
 * Bind a copy control to a pair of clamped nodes.  A ResizeObserver keeps the
 * control correct when a responsive grid changes width; the returned cleanup
 * function is safe to call when a card is removed.
 */
export function bindExpandableCopy({ control, nodes = [], fallbackVisible = false, isExpanded = () => false } = {}) {
  const targets = (Array.isArray(nodes) ? nodes : [nodes]).filter(Boolean);
  const update = () => syncExpandableCopyControl(
    control,
    targets,
    fallbackVisible,
    Boolean(isExpanded?.()),
  );
  update();
  schedule(update);

  let observer = null;
  if (typeof globalThis.ResizeObserver === "function" && targets.length) {
    observer = new globalThis.ResizeObserver(update);
    targets.forEach((target) => observer.observe(target));
  }
  return { update, disconnect: () => observer?.disconnect?.() };
}
