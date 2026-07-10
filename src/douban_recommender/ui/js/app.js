export function bootstrapCineScopeShell() {
  const appView = document.getElementById("app-view");
  const status = document.getElementById("shell-status");

  if (!appView || !status) return;

  appView.dataset.route = window.location.pathname;
  status.textContent = "CineScope 工作台已就绪";
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrapCineScopeShell, { once: true });
} else {
  bootstrapCineScopeShell();
}
