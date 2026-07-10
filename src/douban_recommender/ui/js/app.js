import { renderRoutePlaceholder, setCurrentNavigation, setText } from "./core/dom.js";
import { postV2 } from "./core/api.js";
import { createRouter } from "./core/router.js";
import { createStore, persistUiState, restoreUiState } from "./core/store.js";
import { configureCommandLens, openCommandLens } from "./features/command-lens.js";
import { configureTonight, renderTonight, restoreTonightSession } from "./features/tonight.js";

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

function channelSlug(route) {
  if (route.name === "tonight-anime") return "anime-series";
  return Object.hasOwn(ROUTE_CHANNELS, route.params?.channel) ? route.params.channel : "movie";
}

function backendChannelsToState(session, previous = {}) {
  const result = {};
  for (const [slug, backend] of Object.entries(ROUTE_CHANNELS)) {
    const current = previous[slug] && typeof previous[slug] === "object" ? previous[slug] : {};
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

function reduceUiState(state, action) {
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
    case "recommendation/sessionReceived":
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
          channels: backendChannelsToState(action.session, state.recommendation.channels),
        },
      };
    case "recommendation/batchReceived":
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

export function bootstrapCineScopeShell() {
  const appView = document.getElementById("app-view");
  const status = document.getElementById("shell-status");
  if (!appView || !status) return;

  const store = createStore(restoreUiState(), reduceUiState);
  store.subscribe((state, action) => {
    persistUiState(state);
    if (state.activePath?.startsWith("/tonight") && ["recommendation/sessionReceived", "recommendation/batchReceived"].includes(action.type)) {
      renderTonight(state);
    }
  });
  configureCommandLens({ root: document.getElementById("command-lens-root"), store, api: { postV2 } });
  configureTonight({ store, api: { postV2 }, root: appView, openCommandLens });
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

  const router = createRouter(APP_ROUTES, {
    onRoute: async (route) => {
      store.dispatch({ type: "route/changed", route });
      appView.dataset.route = route.path;
      const [heading, description] = ROUTE_COPY[route.name] ?? ROUTE_COPY["not-found"];
      if (route.path.startsWith("/tonight")) {
        renderTonight(store.getState());
        const sessionId = store.getState().recommendation.sessionId;
        let restoreFailed = false;
        if (sessionId) {
          try {
            await restoreTonightSession(sessionId);
          } catch {
            restoreFailed = true;
          }
        }
        setText(status, restoreFailed
          ? "今晚会话暂时无法恢复，可用 Command Lens 创建新片单"
          : `CineScope 正在浏览：${heading}`);
      } else {
        renderRoutePlaceholder(appView, { heading, description });
        setText(status, `CineScope 正在浏览：${heading}`);
      }
      setCurrentNavigation(route.path.startsWith("/tonight") ? "/tonight" : route.path);
    },
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
