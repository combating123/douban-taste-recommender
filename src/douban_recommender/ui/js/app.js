import { renderRoutePlaceholder, setCurrentNavigation, setText } from "./core/dom.js";
import { createRouter } from "./core/router.js";
import { createStore, persistUiState, restoreUiState } from "./core/store.js";

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

function reduceUiState(state, action) {
  switch (action.type) {
    case "route/changed":
      return { ...state, activePath: action.route.path, activeParams: action.route.params };
    case "rail/changed":
      return { ...state, rail: { mode: action.mode } };
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
      persistUiState(store.getState());
      appView.dataset.route = route.path;
      const [heading, description] = ROUTE_COPY[route.name] ?? ROUTE_COPY["not-found"];
      renderRoutePlaceholder(appView, { heading, description });
      setCurrentNavigation(route.path);
      setText(status, `CineScope 正在浏览：${heading}`);
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
