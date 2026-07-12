import { renderRoutePlaceholder, setCurrentNavigation, setText } from "./core/dom.js";
import { postV2 } from "./core/api.js";
import { createRouter } from "./core/router.js";
import { createStore, persistUiState, restoreUiState, sanitizeCommandLensChips, sanitizeNonSensitiveText, sanitizeNonSensitiveValue, saveScrollByRoute } from "./core/store.js";
import { migrateLegacyClientState } from "./core/migrate.js";
import { configureRecoveryBoundary, invalidateRecoveryRender, rememberLastStableState, renderSafely } from "./core/recovery.js";
import { announce } from "./core/focus.js";
import { installAuditHook } from "./core/audit.js";
import { installAcceptanceHook } from "./core/acceptance.js";
import { closeCommandLens, configureCommandLens, openCommandLens, syncCommandLensState, unbindCommandLensShortcut } from "./features/command-lens.js";
import { configureTonight, renderTonight, restoreTonightSession, syncTonightSessionState } from "./features/tonight.js";
import { configureDetail, renderTitleDetail } from "./features/detail.js";
import { closePersonSheet, configurePeople, openPersonSheet, renderPersonPage } from "./features/people.js";
import { configureUniverse, destroyUniverse, expandNode, renderUniverse } from "./features/universe.js";
import { renderLibrary } from "./features/library.js";
import { renderTasteDna } from "./features/taste.js";
import { renderHealth } from "./features/health.js";

const APP_ROUTES = [
  { pattern: "/tonight", name: "tonight" },
  { pattern: "/tonight/anime-series", name: "tonight-anime" },
  { pattern: "/tonight/:channel", name: "tonight-channel" },
  { pattern: "/universe", name: "universe" },
  { pattern: "/library", name: "library" },
  { pattern: "/taste", name: "taste" },
  { pattern: "/health", name: "health" },
  { pattern: "/title/:id", name: "title" },
  { pattern: "/person/:id", name: "person" },
];

const ROUTE_COPY = {
  tonight: ["今晚", "正在恢复你的本地观影会话。"],
  "tonight-anime": ["今晚 / 动漫", "正在恢复动漫频道的独立批次。"],
  "tonight-channel": ["今晚", "正在恢复此频道的独立批次。"],
  universe: ["宇宙", "正在恢复你上次浏览的关联路径。"],
  library: ["片库", "正在恢复你的片库视图。"],
  taste: ["口味", "正在恢复你的口味档案。"],
  health: ["健康", "正在恢复本地服务健康状态。"],
  title: ["作品详情", "正在打开此作品的本地详情。"],
  person: ["人物详情", "正在打开此人物的本地详情。"],
  "not-found": ["未找到页面", "这个地址不属于 CineScope 工作台。"],
};

const ROUTE_CHANNELS = Object.freeze({
  movie: "电影",
  series: "电视剧",
  "anime-series": "动漫",
});

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function channelSlug(route) {
  if (route.name === "tonight-anime") return "anime-series";
  return Object.hasOwn(ROUTE_CHANNELS, route.params?.channel) ? route.params.channel : "movie";
}

function sessionIdForChannel(state, channel) {
  const recommendation = state?.recommendation || {};
  return recommendation.channels?.[channel]?.sessionId || recommendation.sessionId || null;
}

export function createTonightRestoreGate({ store, restoreSession = restoreTonightSession, setStatus = () => {} }) {
  let generation = 0;
  let controller = null;

  const invalidate = () => {
    generation += 1;
    controller?.abort();
    controller = null;
    return generation;
  };

  const restore = async (route, heading) => {
    const requestGeneration = invalidate();
    const expectedRoute = route.path;
    const channel = channelSlug(route);
    const expectedSessionId = sessionIdForChannel(store.getState(), channel);
    if (!expectedSessionId) {
      if (store.getState().activePath === expectedRoute && generation === requestGeneration) {
        setStatus(`CineScope 正在浏览：${heading}`);
      }
      return null;
    }

    const requestController = new AbortController();
    controller = requestController;
    try {
      const session = await restoreSession(expectedSessionId, { signal: requestController.signal });
      const currentState = store.getState();
      if (
        requestController.signal.aborted
        || generation !== requestGeneration
        || currentState.activePath !== expectedRoute
        || sessionIdForChannel(currentState, channel) !== expectedSessionId
        || session?.id !== expectedSessionId
      ) return null;

      store.dispatch({
        type: "recommendation/sessionReceived",
        session,
        source: "restore",
        expectedSessionId,
        channel,
        route: expectedRoute,
        generation: requestGeneration,
      });
      if (
        generation === requestGeneration
        && store.getState().activePath === expectedRoute
        && sessionIdForChannel(store.getState(), channel) === expectedSessionId
      ) setStatus(`CineScope 正在浏览：${heading}`);
      return session;
    } catch (error) {
      if (requestController.signal.aborted || generation !== requestGeneration) return null;
      if (
        store.getState().activePath === expectedRoute
        && sessionIdForChannel(store.getState(), channel) === expectedSessionId
      ) setStatus("今晚会话暂时无法恢复，可用 Command Lens 创建新片单");
      return null;
    } finally {
      if (controller === requestController) controller = null;
    }
  };

  return { invalidate, restore };
}

function backendChannelsToState(session, previous = {}, { preserveOtherSessions = false } = {}) {
  const result = {};
  for (const [slug, backend] of Object.entries(ROUTE_CHANNELS)) {
    const previousChannel = previous[slug] && typeof previous[slug] === "object" ? previous[slug] : {};
    if (preserveOtherSessions && previousChannel.sessionId && previousChannel.sessionId !== session?.id) {
      result[slug] = previousChannel;
      continue;
    }
    const sameSession = previousChannel.sessionId === session?.id;
    const current = sameSession ? previousChannel : { sessionId: session?.id || null, batchIndex: 0, batchIds: [] };
    const rawCandidateCounts = session?.candidate_counts && typeof session.candidate_counts === "object"
      ? session.candidate_counts
      : {};
    const hasExplicitUnknownTarget = Object.prototype.hasOwnProperty.call(rawCandidateCounts, "target_size")
      && rawCandidateCounts.target_size === null;
    const candidateCounts = {
      target_size: hasExplicitUnknownTarget
        ? null
        : (
          Number.isInteger(rawCandidateCounts.target_size) && rawCandidateCounts.target_size >= 0
            ? rawCandidateCounts.target_size
            : Number.isInteger(current.candidate_counts?.target_size) && current.candidate_counts.target_size >= 0
              ? current.candidate_counts.target_size
              : null
        ),
      returned_size: Number.isInteger(rawCandidateCounts.returned_size) && rawCandidateCounts.returned_size >= 0
        ? rawCandidateCounts.returned_size
        : Number.isInteger(current.candidate_counts?.returned_size) && current.candidate_counts.returned_size >= 0
          ? current.candidate_counts.returned_size
          : null,
    };
    const incoming = session?.channels?.[backend] && typeof session.channels[backend] === "object"
      ? session.channels[backend]
      : {};
    const batch = incoming.batch && typeof incoming.batch === "object" ? incoming.batch : {};
    const batchIds = [...(Array.isArray(current.batchIds) ? current.batchIds : [])];
    if (typeof batch.id === "string" && batch.id && !batchIds.includes(batch.id)) batchIds.push(batch.id);
    result[slug] = {
      ...current,
      ...incoming,
      sessionId: typeof session?.id === "string" ? session.id : current.sessionId,
      candidate_counts: candidateCounts,
      batchIndex: Number.isInteger(batch.index) ? batch.index : current.batchIndex || 0,
      batchIds: batchIds.slice(-50),
    };
  }
  return result;
}

function batchChannelState(current, payload) {
  const batch = payload?.batch && typeof payload.batch === "object" ? payload.batch : {};
  const batchIds = [...(Array.isArray(current.batchIds) ? current.batchIds : [])];
  if (typeof batch.id === "string" && batch.id && !batchIds.includes(batch.id)) batchIds.push(batch.id);
  return {
    ...current,
    pool_size: Number.isFinite(batch.pool_size) ? batch.pool_size : current.pool_size,
    matched_size: Number.isFinite(batch.matched_size) ? batch.matched_size : current.matched_size,
    visible_size: Number.isFinite(batch.visible_size) ? batch.visible_size : current.visible_size,
    active_batch: Number.isInteger(batch.index) ? batch.index : current.active_batch,
    batch,
    batchIndex: Number.isInteger(batch.index) ? batch.index : current.batchIndex || 0,
    batchIds: batchIds.slice(-50),
  };
}

export function reduceUiState(state, action) {
  switch (action.type) {
    case "route/changed":
      return {
        ...state,
        activePath: action.route.path,
        activeParams: action.route.params,
        recommendation: action.route.path.startsWith("/tonight")
          ? { ...state.recommendation, activeChannel: channelSlug(action.route) }
          : state.recommendation,
      };
    case "recommendation/channelSelected":
      if (!Object.hasOwn(ROUTE_CHANNELS, action.channel)) return state;
      return {
        ...state,
        activePath: action.path,
        activeParams: { channel: action.channel },
        recommendation: { ...state.recommendation, activeChannel: action.channel },
      };
    case "route/scrollSaved": {
      const scrollByRoute = saveScrollByRoute(state.scrollByRoute, action.path, action.y);
      if (!scrollByRoute) return state;
      return { ...state, scrollByRoute };
    }
    case "rail/changed":
      return { ...state, rail: { mode: action.mode } };
    case "library/filterChanged":
      return { ...state, library: { state: action.state } };
    case "sync/stateChanged":
      return {
        ...state,
        sync: {
          profile: typeof action.sync?.profile === "string" ? action.sync.profile : "",
          options: action.sync?.options && typeof action.sync.options === "object" ? { ...action.sync.options } : {},
          knownJobIds: Array.isArray(action.sync?.knownJobIds) ? [...action.sync.knownJobIds] : [],
        },
      };
    case "recovery/restored": {
      const stable = action.state && typeof action.state === "object" ? action.state : {};
      const activeChannel = stable.recommendation?.activeChannel || "movie";
      const channels = stable.recommendation?.channels || state.recommendation.channels;
      return {
        ...state,
        activePath: stable.activePath || state.activePath,
        activeParams: stable.activeParams || {},
        scrollByRoute: stable.scrollByRoute || {},
        rail: stable.rail || { mode: "expanded" },
        recommendation: {
          sessionId: channels?.[activeChannel]?.sessionId || null,
          activeChannel,
          personalization: sanitizeNonSensitiveValue(stable.recommendation?.personalization) || {},
          channels,
        },
        candidateTray: { itemIds: [], context: stable.candidateTray?.context || {} },
        commandLens: { draft: "", chips: [] },
        library: stable.library || { state: "all" },
        sync: stable.sync || state.sync,
      };
    }
    case "universe/contextChanged":
      return {
        ...state,
        candidateTray: {
          ...state.candidateTray,
          context: { ...state.candidateTray?.context, ...action.context },
        },
      };
    case "candidateTray/nodeAdded": {
      const itemId = stableUniverseId(action.itemId);
      if (!itemId) return state;
      const itemIds = [...(Array.isArray(state.candidateTray?.itemIds) ? state.candidateTray.itemIds : [])]
        .filter((candidateId) => candidateId !== itemId);
      itemIds.push(itemId);
      return {
        ...state,
        candidateTray: { ...state.candidateTray, itemIds: itemIds.slice(-24) },
      };
    }
    case "recommendation/sessionReceived":
      if (action.source === "restore") {
        const expectedChannel = action.channel;
        const currentChannel = state.recommendation.channels[expectedChannel] || {};
        if (
          state.activePath !== action.route
          || currentChannel.sessionId !== action.expectedSessionId
          || action.session?.id !== action.expectedSessionId
        ) return state;
      }
      return {
        ...state,
        commandLens: {
          ...state.commandLens,
          chips: Array.isArray(action.session?.chips) ? sanitizeCommandLensChips(action.session.chips) : state.commandLens.chips,
        },
        recommendation: {
          ...state.recommendation,
          sessionId: action.session?.id || state.recommendation.sessionId,
          intent: sanitizeNonSensitiveValue(action.session?.intent) || {},
          intentSessionId: action.session?.id || null,
          personalization: sanitizeNonSensitiveValue(action.session?.personalization) || state.recommendation.personalization || {},
          channels: backendChannelsToState(action.session, state.recommendation.channels, {
            preserveOtherSessions: action.source === "restore",
          }),
        },
      };
    case "recommendation/batchReceived":
      if (
        action.expectedSessionId
        && (
          state.recommendation.channels[action.channel]?.sessionId !== action.expectedSessionId
          || (action.batch?.session_id && action.batch.session_id !== action.expectedSessionId)
        )
      ) return state;
      return {
        ...state,
        recommendation: {
          ...state.recommendation,
          channels: {
            ...state.recommendation.channels,
            [action.channel]: batchChannelState(state.recommendation.channels[action.channel] || {}, action.batch),
          },
        },
      };
    case "commandLens/grounded":
      return {
        ...state,
        commandLens: {
          draft: sanitizeNonSensitiveText(action.draft, "", 2000),
          chips: sanitizeCommandLensChips(action.chips),
        },
      };
    default:
      return state;
  }
}

function applyRailMode(mode) {
  const body = document.body;
  const collapseButton = document.getElementById("rail-collapse-toggle");
  const hideButton = document.getElementById("rail-hide-toggle");
  const restoreButton = document.getElementById("rail-restore");
  const hidden = mode === "hidden";
  const collapsed = mode === "collapsed";

  body.classList.toggle("rail-collapsed", collapsed);
  body.classList.toggle("rail-hidden", hidden);
  if (collapseButton) collapseButton.setAttribute("aria-expanded", String(!collapsed && !hidden));
  if (hideButton) hideButton.setAttribute("aria-expanded", String(!hidden));
  if (restoreButton) {
    restoreButton.hidden = !hidden;
    restoreButton.setAttribute("aria-expanded", String(!hidden));
  }
}

function bindNavigation(router) {
  const onClick = (event) => {
    const link = event.target.closest("a[data-route]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    router.navigate(link.getAttribute("href"));
  };
  document.addEventListener("click", onClick);
  return () => document.removeEventListener("click", onClick);
}

export function prepareRouteChange() {
  closeCommandLens({ restoreFocus: false });
  closePersonSheet({ restoreFocus: false });
  destroyUniverse({ preserveDom: true });
}

function stableUniverseId(value) {
  const clean = textValue(value);
  return /^[A-Za-z0-9:._~-]{1,256}$/.test(clean) ? clean : "";
}

export function createUniverseRouteGate({
  root,
  getContext = () => ({}),
  render = renderUniverse,
  expand = expandNode,
  destroy = destroyUniverse,
  setStatus = () => {},
} = {}) {
  let generation = 0;
  const invalidate = (options = {}) => {
    generation += 1;
    destroy(options);
    return generation;
  };
  const renderRoute = async () => {
    const requestGeneration = invalidate();
    const focusId = stableUniverseId(getContext()?.universeFocusId);
    if (!focusId) {
      render(root, null);
      setStatus("CineScope 口味宇宙正在等待一个作品焦点");
      return null;
    }
    render(root, { focus_id: focusId, nodes: [], edges: [] });
    try {
      const graph = await expand(focusId);
      if (generation === requestGeneration) setStatus("CineScope 正在浏览：口味宇宙");
      return generation === requestGeneration ? graph : null;
    } catch {
      if (generation === requestGeneration) setStatus("口味宇宙暂时无法展开；已保留恢复入口");
      return null;
    }
  };
  return { invalidate, render: renderRoute };
}

export function createUniverseExplorer({ store, navigate = () => {} } = {}) {
  return (id) => {
    const focusId = stableUniverseId(id);
    if (!focusId || !store?.getState || !store?.dispatch) return false;
    const previous = store.getState().candidateTray?.context || {};
    store.dispatch({
      type: "universe/contextChanged",
      context: { universeFocusId: focusId, expandedIds: Array.isArray(previous.expandedIds) ? previous.expandedIds : [] },
    });
    return navigate("/universe");
  };
}

export function createUniverseRecommendationHandler({ store, navigate = () => {}, openLens = openCommandLens } = {}) {
  let handoffGeneration = 0;
  return async (node) => {
    const requestGeneration = ++handoffGeneration;
    const itemId = stableUniverseId(node?.id);
    if (!itemId || !store?.dispatch) return false;
    let committedRoute;
    try {
      committedRoute = await Promise.resolve(navigate("/tonight"));
    } catch {
      return false;
    }
    if (
      requestGeneration !== handoffGeneration
      || committedRoute?.path !== "/tonight"
      || store.getState?.().activePath !== "/tonight"
    ) return false;
    store.dispatch({ type: "candidateTray/nodeAdded", itemId });
    const title = sanitizeNonSensitiveText(textValue(node?.title), "这部作品", 160) || "这部作品";
    openLens(`以《${title}》为线索，生成今晚推荐；请确认或补充条件。`);
    return true;
  };
}

function explorationRecovery(route, retry) {
  if (typeof document.createElement !== "function") return { className: "route-recovery", route: route.path };
  const panel = document.createElement("section");
  panel.className = "route-recovery route-recovery--exploration";
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = route.name === "person" ? "PERSON / RECOVERY" : "TITLE / RECOVERY";
  const title = document.createElement("h1");
  title.className = "route-recovery__title";
  title.textContent = route.name === "person" ? "人物资料暂时无法打开" : "作品详情暂时无法打开";
  const copy = document.createElement("p");
  copy.className = "route-recovery__copy";
  copy.textContent = "本地记录可能不存在或服务暂时不可用。你可以重试，或返回上一条稳定路径。";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "route-recovery__action";
  button.textContent = "重试";
  button.addEventListener("click", retry);
  panel.append(eyebrow, title, copy, button);
  return panel;
}

async function replacePreparedView(root, view, isCurrent = () => true) {
  if (!root || !view || !isCurrent()) return false;
  let committed = false;
  const update = () => {
    if (committed || !isCurrent()) return false;
    root.replaceChildren(view);
    committed = true;
    return true;
  };
  const reduceMotion = globalThis.window?.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (reduceMotion || typeof document.startViewTransition !== "function") return update();

  let transition;
  try {
    transition = document.startViewTransition(update);
  } catch {
    return committed || update();
  }
  if (transition?.ready) void Promise.resolve(transition.ready).catch(() => {});
  const updateDone = transition?.updateCallbackDone || transition?.finished;
  if (transition?.finished && transition.finished !== updateDone) {
    void Promise.resolve(transition.finished).catch(() => {});
  }
  if (!updateDone || typeof updateDone.then !== "function") return committed || update();
  try {
    await updateDone;
  } catch {
    if (!committed && isCurrent()) return update();
    return committed;
  }
  return committed;
}

export function createExplorationRouteGate({
  root,
  getActivePath = () => "",
  renderTitle = renderTitleDetail,
  renderPerson = renderPersonPage,
  setStatus = () => {},
} = {}) {
  let generation = 0;
  let controller = null;

  const invalidate = () => {
    generation += 1;
    controller?.abort();
    controller = null;
    return generation;
  };

  const render = async (route, fallbackHeading = "CineScope") => {
    const requestGeneration = invalidate();
    const expectedPath = route.path;
    const requestController = new AbortController();
    controller = requestController;
    const isCurrent = () => (
      !requestController.signal.aborted
      && generation === requestGeneration
      && getActivePath() === expectedPath
    );
    const commit = async (view, meta = {}) => {
      if (!isCurrent() || !root || !view) return false;
      const committed = await replacePreparedView(root, view, isCurrent);
      if (!committed || !isCurrent()) return false;
      setStatus(`CineScope 正在浏览：${textValue(meta.heading, fallbackHeading)}`);
      return true;
    };
    const renderer = route.name === "person" ? renderPerson : renderTitle;

    try {
      return await renderer(route.params?.id, {
        signal: requestController.signal,
        isCurrent,
        commit,
      });
    } catch {
      if (!isCurrent()) return null;
      const recovery = explorationRecovery(route, () => { void render(route, fallbackHeading); });
      await commit(recovery, { heading: fallbackHeading });
      return recovery;
    } finally {
      if (controller === requestController) controller = null;
    }
  };

  return { invalidate, render };
}

export function createAppRouteHandler({
  appView,
  store,
  restoreGate,
  explorationGate,
  universeGate,
  prepare = prepareRouteChange,
  setNavigation = setCurrentNavigation,
  renderTonightView = renderTonight,
  renderPlaceholder = renderRoutePlaceholder,
  renderLibraryView = renderLibrary,
  renderTasteView = renderTasteDna,
  renderHealthView = renderHealth,
  setStatus = () => {},
  announceRoute = announce,
} = {}) {
  let activeSpace = null;
  configureRecoveryBoundary({
    root: appView,
    getCurrentPath: () => store.getState?.().activePath || "",
    getStableState: () => store.getState?.() || null,
  });
  const disposeActiveSpace = () => {
    const space = activeSpace;
    activeSpace = null;
    space?.dispose?.();
  };
  const handler = async (route) => {
    const [heading, description] = ROUTE_COPY[route.name] ?? ROUTE_COPY["not-found"];
    const renderResult = await renderSafely(route, async () => {
      const previousPath = store.getState?.().activePath || "";
      const keepTonightMounted = previousPath.startsWith("/tonight")
        && route.path.startsWith("/tonight")
        && Boolean(appView.querySelector?.(".tonight-page"));
      store.dispatch({ type: "route/changed", route });
      if (keepTonightMounted) {
        appView.dataset.route = route.path;
        setNavigation("/tonight");
        await renderTonightView(store.getState());
        await restoreGate.restore(route, heading);
        setStatus(`CineScope 正在浏览：${heading}`);
        return;
      }
      disposeActiveSpace();
      prepare();
      appView.dataset.route = route.path;
      setNavigation(route.path.startsWith("/tonight") ? "/tonight" : route.path);
      if (route.path.startsWith("/tonight")) {
        universeGate.invalidate();
        explorationGate.invalidate();
        await renderTonightView(store.getState());
        await restoreGate.restore(route, heading);
      } else if (route.name === "title" || route.name === "person") {
        universeGate.invalidate({ preserveDom: true });
        restoreGate.invalidate();
        await explorationGate.render(route, heading);
      } else if (route.name === "universe") {
        restoreGate.invalidate();
        explorationGate.invalidate();
        await universeGate.render();
      } else if (route.name === "library") {
        universeGate.invalidate();
        restoreGate.invalidate();
        explorationGate.invalidate();
        activeSpace = await renderLibraryView(appView, {
          filters: store.getState().library || { state: "all" },
          onFilterChange: (state) => store.dispatch({ type: "library/filterChanged", state }),
        });
        setStatus("CineScope 正在浏览：片库");
      } else if (route.name === "taste") {
        universeGate.invalidate();
        restoreGate.invalidate();
        explorationGate.invalidate();
        activeSpace = await renderTasteView(appView);
        setStatus("CineScope 正在浏览：口味 DNA");
      } else if (route.name === "health") {
        universeGate.invalidate();
        restoreGate.invalidate();
        explorationGate.invalidate();
        activeSpace = await renderHealthView(appView, {
          syncState: store.getState().sync || {},
          onSyncStateChange: (sync) => store.dispatch({ type: "sync/stateChanged", sync }),
        });
        setStatus("CineScope 正在浏览：健康与同步");
      } else {
        universeGate.invalidate();
        restoreGate.invalidate();
        explorationGate.invalidate();
        await renderPlaceholder(appView, { heading, description });
        setStatus(`CineScope 正在浏览：${heading}`);
      }
    }, {
      root: appView,
      getCurrentPath: () => store.getState?.().activePath || "",
      getStableState: () => store.getState?.() || null,
    });
    if (renderResult.stale || store.getState?.().activePath !== route.path) return false;
    if (renderResult.recovered) {
      const stableState = renderResult.previousStable;
      if (stableState?.activePath) {
        store.dispatch({ type: "recovery/restored", state: stableState });
        persistUiState(store.getState());
        applyRailMode(store.getState().rail.mode);
        appView.dataset.route = stableState.activePath;
        setNavigation(stableState.activePath.startsWith("/tonight") ? "/tonight" : stableState.activePath);
        const browser = globalThis.window;
        if (browser?.history?.replaceState) {
          browser.history.replaceState({}, "", stableState.activePath);
        }
      }
      setStatus("CineScope 已进入恢复状态");
      announceRoute("恢复：已保留上次稳定页面");
      return false;
    }
    const focusTarget = appView.querySelector?.("h1") || appView;
    if (focusTarget && typeof focusTarget.focus === "function") {
      focusTarget.setAttribute?.("tabindex", "-1");
      focusTarget.focus({ preventScroll: true });
    }
    announceRoute(textValue(focusTarget?.textContent, heading));
    return true;
  };
  handler.dispose = () => {
    invalidateRecoveryRender(appView);
    disposeActiveSpace();
    restoreGate.invalidate();
    explorationGate.invalidate();
    universeGate.invalidate();
  };
  return handler;
}

export function bootstrapCineScopeShell() {
  migrateLegacyClientState();
  const appView = document.getElementById("app-view");
  const status = document.getElementById("shell-status");
  if (!appView || !status) return;

  const store = createStore(restoreUiState(), reduceUiState);
  const restoreGate = createTonightRestoreGate({
    store,
    restoreSession: restoreTonightSession,
    setStatus: (message) => setText(status, message),
  });
  const unsubscribe = store.subscribe((state, action) => {
    persistUiState(state);
    if (action.type === "recommendation/sessionReceived" && action.source !== "restore") restoreGate.invalidate();
    if (["recommendation/sessionReceived", "route/changed"].includes(action.type)) {
      syncCommandLensState(state);
    }
    if (action.type === "recommendation/sessionReceived") {
      syncTonightSessionState(state);
    }
    if (state.activePath?.startsWith("/tonight") && ["recommendation/sessionReceived", "recommendation/batchReceived", "recommendation/channelSelected"].includes(action.type)) {
      renderTonight(state);
    }
  });
  configureCommandLens({
    root: document.getElementById("command-lens-root"),
    store,
    api: { postV2 },
    onBeforeOpen: () => closePersonSheet(),
  });
  configureTonight({ store, api: { postV2 }, root: appView, openCommandLens });
  configurePeople({
    root: appView,
    overlayRoot: document.getElementById("overlay-root"),
    onBeforeOpen: () => closeCommandLens(),
  });
  let router = null;
  configureRecoveryBoundary({
    root: appView,
    getCurrentPath: () => store.getState().activePath || "",
    getStableState: () => store.getState(),
    onRetry: (stableState) => {
      store.dispatch({ type: "recovery/restored", state: stableState });
      persistUiState(store.getState());
      applyRailMode(store.getState().rail.mode);
      if (stableState.activePath) void router?.navigate(stableState.activePath);
    },
  });
  if (store.getState().activePath) rememberLastStableState(store.getState());
  const recommendUniverseNode = createUniverseRecommendationHandler({
    store,
    navigate: (path) => router?.navigate(path),
    openLens: openCommandLens,
  });
  configureUniverse({
    onContextChange: (context) => {
      const previous = store.getState().candidateTray?.context || {};
      const expandedIds = [...new Set([
        ...(Array.isArray(previous.expandedIds) ? previous.expandedIds : []),
        ...(Array.isArray(context.expandedIds) ? context.expandedIds : []),
      ])].slice(-36);
      store.dispatch({ type: "universe/contextChanged", context: { ...context, expandedIds } });
    },
    onRecommendNode: recommendUniverseNode,
  });
  const exploreUniverse = createUniverseExplorer({ store, navigate: (path) => router?.navigate(path) });
  configureDetail({
    root: appView,
    api: { postV2 },
    openPersonSheet,
    onExploreUniverse: exploreUniverse,
  });
  const explorationGate = createExplorationRouteGate({
    root: appView,
    getActivePath: () => store.getState().activePath,
    setStatus: (message) => setText(status, message),
  });
  const universeGate = createUniverseRouteGate({
    root: appView,
    getContext: () => store.getState().candidateTray?.context || {},
    setStatus: (message) => setText(status, message),
  });
  const commandTrigger = document.getElementById("command-lens-trigger");
  const onCommandTrigger = () => openCommandLens();
  commandTrigger?.addEventListener("click", onCommandTrigger);
  const setRailMode = (mode) => {
    store.dispatch({ type: "rail/changed", mode });
    persistUiState(store.getState());
    applyRailMode(mode);
  };

  applyRailMode(store.getState().rail.mode);
  const collapseToggle = document.getElementById("rail-collapse-toggle");
  const hideToggle = document.getElementById("rail-hide-toggle");
  const railRestore = document.getElementById("rail-restore");
  const onCollapse = () => {
    setRailMode(store.getState().rail.mode === "collapsed" ? "expanded" : "collapsed");
  };
  const onHide = () => setRailMode("hidden");
  const onRestore = () => setRailMode("expanded");
  collapseToggle?.addEventListener("click", onCollapse);
  hideToggle?.addEventListener("click", onHide);
  railRestore?.addEventListener("click", onRestore);

  const routeHandler = createAppRouteHandler({
    appView,
    store,
    restoreGate,
    explorationGate,
    universeGate,
    setStatus: (message) => setText(status, message),
  });
  router = createRouter(APP_ROUTES, {
    onRoute: routeHandler,
    onScrollSaved: (path, y) => store.dispatch({ type: "route/scrollSaved", path, y }),
  });

  const uninstallAuditHook = installAuditHook();
  const uninstallAcceptanceHook = installAcceptanceHook({ store, router });
  const uninstallBrowserHooks = () => {
    uninstallAcceptanceHook();
    uninstallAuditHook();
  };
  const unbindNavigation = bindNavigation(router);
  router.start();
  return {
    router,
    store,
    destroy() {
      uninstallBrowserHooks();
      closeCommandLens({ restoreFocus: false });
      unbindCommandLensShortcut();
      routeHandler.dispose();
      router.destroy();
      unbindNavigation();
      unsubscribe();
      commandTrigger?.removeEventListener("click", onCommandTrigger);
      collapseToggle?.removeEventListener("click", onCollapse);
      hideToggle?.removeEventListener("click", onHide);
      railRestore?.removeEventListener("click", onRestore);
      closePersonSheet({ restoreFocus: false });
      destroyUniverse();
    },
  };
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrapCineScopeShell, { once: true });
} else {
  bootstrapCineScopeShell();
}
