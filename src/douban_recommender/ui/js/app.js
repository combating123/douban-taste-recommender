import { renderRoutePlaceholder, setCurrentNavigation, setText } from "./core/dom.js";
import { postV2 } from "./core/api.js";
import { createRouter } from "./core/router.js";
import { createStore, persistUiState, restoreUiState } from "./core/store.js";
import { configureCommandLens, openCommandLens, syncCommandLensState } from "./features/command-lens.js";
import { configureTonight, renderTonight, restoreTonightSession, syncTonightSessionState } from "./features/tonight.js";
import { configureDetail, renderTitleDetail } from "./features/detail.js";
import { closePersonSheet, configurePeople, openPersonSheet, renderPersonPage } from "./features/people.js";
import { configureUniverse, destroyUniverse, expandNode, renderUniverse } from "./features/universe.js";

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
    case "rail/changed":
      return { ...state, rail: { mode: action.mode } };
    case "universe/contextChanged":
      return {
        ...state,
        candidateTray: {
          ...state.candidateTray,
          context: { ...state.candidateTray?.context, ...action.context },
        },
      };
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
          chips: Array.isArray(action.session?.chips) ? action.session.chips : state.commandLens.chips,
        },
        recommendation: {
          ...state.recommendation,
          sessionId: action.session?.id || state.recommendation.sessionId,
          intent: action.session?.intent && typeof action.session.intent === "object" ? action.session.intent : {},
          intentSessionId: action.session?.id || null,
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
        commandLens: { draft: action.draft || "", chips: Array.isArray(action.chips) ? action.chips : [] },
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
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-route]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    router.navigate(link.getAttribute("href"));
  });
}

export function prepareRouteChange() {
  closePersonSheet();
  destroyUniverse();
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
  const invalidate = () => {
    generation += 1;
    destroy();
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
  if (typeof document.startViewTransition !== "function") return update();

  let transition;
  try {
    transition = document.startViewTransition(update);
  } catch {
    return committed || update();
  }
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
  setStatus = () => {},
} = {}) {
  return async (route) => {
    prepare();
    store.dispatch({ type: "route/changed", route });
    appView.dataset.route = route.path;
    setNavigation(route.path.startsWith("/tonight") ? "/tonight" : route.path);
    const [heading, description] = ROUTE_COPY[route.name] ?? ROUTE_COPY["not-found"];
    if (route.path.startsWith("/tonight")) {
      universeGate.invalidate();
      explorationGate.invalidate();
      renderTonightView(store.getState());
      await restoreGate.restore(route, heading);
    } else if (route.name === "title" || route.name === "person") {
      universeGate.invalidate();
      restoreGate.invalidate();
      await explorationGate.render(route, heading);
    } else if (route.name === "universe") {
      restoreGate.invalidate();
      explorationGate.invalidate();
      await universeGate.render();
    } else {
      universeGate.invalidate();
      restoreGate.invalidate();
      explorationGate.invalidate();
      renderPlaceholder(appView, { heading, description });
      setStatus(`CineScope 正在浏览：${heading}`);
    }
  };
}

export function bootstrapCineScopeShell() {
  const appView = document.getElementById("app-view");
  const status = document.getElementById("shell-status");
  if (!appView || !status) return;

  const store = createStore(restoreUiState(), reduceUiState);
  const restoreGate = createTonightRestoreGate({
    store,
    restoreSession: restoreTonightSession,
    setStatus: (message) => setText(status, message),
  });
  store.subscribe((state, action) => {
    persistUiState(state);
    if (action.type === "recommendation/sessionReceived" && action.source !== "restore") restoreGate.invalidate();
    if (["recommendation/sessionReceived", "route/changed"].includes(action.type)) {
      syncCommandLensState(state);
    }
    if (action.type === "recommendation/sessionReceived") {
      syncTonightSessionState(state);
    }
    if (state.activePath?.startsWith("/tonight") && ["recommendation/sessionReceived", "recommendation/batchReceived"].includes(action.type)) {
      renderTonight(state);
    }
  });
  configureCommandLens({ root: document.getElementById("command-lens-root"), store, api: { postV2 } });
  configureTonight({ store, api: { postV2 }, root: appView, openCommandLens });
  configurePeople({ root: appView, overlayRoot: document.getElementById("overlay-root") });
  configureUniverse({
    onContextChange: (context) => {
      const previous = store.getState().candidateTray?.context || {};
      const expandedIds = [...new Set([
        ...(Array.isArray(previous.expandedIds) ? previous.expandedIds : []),
        ...(Array.isArray(context.expandedIds) ? context.expandedIds : []),
      ])].slice(-36);
      store.dispatch({ type: "universe/contextChanged", context: { ...context, expandedIds } });
    },
  });
  let router = null;
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
  document.getElementById("command-lens-trigger")?.addEventListener("click", () => openCommandLens());
  const setRailMode = (mode) => {
    store.dispatch({ type: "rail/changed", mode });
    persistUiState(store.getState());
    applyRailMode(mode);
  };

  applyRailMode(store.getState().rail.mode);
  document.getElementById("rail-collapse-toggle")?.addEventListener("click", () => {
    setRailMode(store.getState().rail.mode === "collapsed" ? "expanded" : "collapsed");
  });
  document.getElementById("rail-hide-toggle")?.addEventListener("click", () => setRailMode("hidden"));
  document.getElementById("rail-restore")?.addEventListener("click", () => setRailMode("expanded"));

  router = createRouter(APP_ROUTES, {
    onRoute: createAppRouteHandler({
      appView,
      store,
      restoreGate,
      explorationGate,
      universeGate,
      setStatus: (message) => setText(status, message),
    }),
  });

  bindNavigation(router);
  router.start();
  return { router, store };
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrapCineScopeShell, { once: true });
} else {
  bootstrapCineScopeShell();
}
