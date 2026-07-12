import { persistUiState, restoreUiState, saveScroll } from "./store.js";

function browserWindow() {
  if (!globalThis.window) throw new Error("CineScope router requires a browser window");
  return globalThis.window;
}

function normalisePath(path) {
  const candidate = typeof path === "string" ? path : "/";
  const withoutQuery = candidate.split(/[?#]/, 1)[0] || "/";
  const prefixed = withoutQuery.startsWith("/") ? withoutQuery : `/${withoutQuery}`;
  return prefixed.length > 1 ? prefixed.replace(/\/+$/, "") : prefixed;
}

function decodeSegment(segment) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function compileRoute(route) {
  if (!route || typeof route.pattern !== "string" || !route.pattern.startsWith("/")) {
    throw new TypeError("Routes require an absolute pattern");
  }

  const segments = normalisePath(route.pattern).split("/").filter(Boolean);
  return { ...route, pattern: normalisePath(route.pattern), segments };
}

function matchCompiledRoute(route, path) {
  const segments = normalisePath(path).split("/").filter(Boolean);
  if (segments.length !== route.segments.length) return null;

  const params = {};
  for (let index = 0; index < route.segments.length; index += 1) {
    const expected = route.segments[index];
    const actual = segments[index];
    if (expected.startsWith(":")) {
      if (!actual) return null;
      params[expected.slice(1)] = decodeSegment(actual);
    } else if (expected !== actual) {
      return null;
    }
  }

  return {
    name: route.name ?? route.pattern,
    pattern: route.pattern,
    path: normalisePath(path),
    params,
  };
}

function routeForPath(compiledRoutes, path) {
  for (const route of compiledRoutes) {
    const matched = matchCompiledRoute(route, path);
    if (matched) return matched;
  }
  return null;
}

function nextFrame(browser) {
  const schedule = browser.requestAnimationFrame ?? globalThis.requestAnimationFrame;
  if (typeof schedule !== "function") return Promise.resolve();
  return new Promise((resolve) => schedule.call(browser, resolve));
}

function persistActiveRoute(route) {
  const state = restoreUiState();
  state.activePath = route.path;
  state.activeParams = route.params;
  persistUiState(state);
}

export function navigate(path, state = {}) {
  const browser = browserWindow();
  const targetPath = normalisePath(path);
  browser.history.pushState(state, "", targetPath);
  const PopState = browser.PopStateEvent ?? globalThis.PopStateEvent;
  const event = typeof PopState === "function"
    ? new PopState("popstate", { state })
    : { type: "popstate", state };
  browser.dispatchEvent(event);
}

export function createRouter(routes, { onRoute, onScrollSaved } = {}) {
  if (!Array.isArray(routes)) throw new TypeError("createRouter requires a route list");
  if (typeof onRoute !== "function") throw new TypeError("createRouter requires an onRoute callback");
  if (onScrollSaved !== undefined && typeof onScrollSaved !== "function") {
    throw new TypeError("createRouter onScrollSaved must be a function");
  }

  const compiledRoutes = routes.map(compileRoute);
  let currentRoute = null;
  let started = false;
  let lastNavigation = Promise.resolve(null);
  let navigationGeneration = 0;
  let pendingDeparture = null;

  function releasePendingDeparture(requestGeneration) {
    if (pendingDeparture?.generation === requestGeneration) pendingDeparture = null;
  }

  async function renderLocation(path, state) {
    const browser = browserWindow();
    const requestGeneration = ++navigationGeneration;
    const nextRoute = routeForPath(compiledRoutes, path) ?? {
      name: "not-found",
      pattern: null,
      path: normalisePath(path),
      params: {},
    };

    if (currentRoute && pendingDeparture?.path === currentRoute.path) {
      if (onScrollSaved) onScrollSaved(currentRoute.path, browser.scrollY);
      else saveScroll(currentRoute.path, browser.scrollY);
      pendingDeparture = { ...pendingDeparture, generation: requestGeneration };
    } else if (currentRoute && currentRoute.path !== nextRoute.path) {
      if (onScrollSaved) onScrollSaved(currentRoute.path, browser.scrollY);
      else saveScroll(currentRoute.path, browser.scrollY);
      pendingDeparture = { path: currentRoute.path, generation: requestGeneration };
    }

    let routeResult;
    try {
      routeResult = await onRoute(nextRoute, state);
    } catch (error) {
      releasePendingDeparture(requestGeneration);
      throw error;
    }
    if (
      routeResult === false
      || requestGeneration !== navigationGeneration
      || normalisePath(browser.location.pathname) !== nextRoute.path
    ) {
      releasePendingDeparture(requestGeneration);
      return null;
    }

    currentRoute = nextRoute;
    releasePendingDeparture(requestGeneration);
    persistActiveRoute(nextRoute);

    const savedPosition = restoreUiState().scrollByRoute[nextRoute.path] ?? 0;
    await nextFrame(browser);
    if (
      requestGeneration !== navigationGeneration
      || currentRoute !== nextRoute
      || normalisePath(browser.location.pathname) !== nextRoute.path
    ) return null;
    browser.scrollTo({ top: savedPosition, left: 0, behavior: "auto" });
    return nextRoute;
  }

  function onPopState(event) {
    const browser = browserWindow();
    lastNavigation = renderLocation(browser.location.pathname, event?.state);
    return lastNavigation;
  }

  return {
    match(path) {
      return routeForPath(compiledRoutes, path);
    },
    get currentRoute() {
      return currentRoute;
    },
    async start() {
      if (started) return lastNavigation;
      const browser = browserWindow();
      started = true;
      if (browser.history && "scrollRestoration" in browser.history) browser.history.scrollRestoration = "manual";
      browser.addEventListener("popstate", onPopState);
      lastNavigation = renderLocation(browser.location.pathname, browser.history?.state);
      return lastNavigation;
    },
    navigate(path, state = {}) {
      navigate(path, state);
      return lastNavigation;
    },
    destroy() {
      if (!started) return;
      browserWindow().removeEventListener("popstate", onPopState);
      started = false;
      navigationGeneration += 1;
      pendingDeparture = null;
    },
  };
}
