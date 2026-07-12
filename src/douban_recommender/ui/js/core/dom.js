export function setText(element, value) {
  if (element) element.textContent = value;
}

export function renderRoutePlaceholder(container, { heading, description }) {
  if (!container) return;

  const section = document.createElement("section");
  section.className = "route-placeholder";
  const title = document.createElement("h1");
  const copy = document.createElement("p");
  title.textContent = heading;
  copy.textContent = description;
  section.append(title, copy);
  container.replaceChildren(section);
}

export function setCurrentNavigation(path) {
  const links = [...document.querySelectorAll("[data-route]")];
  const mobile = globalThis.window?.matchMedia?.("(max-width: 720px)")?.matches;
  const matches = links.filter((link) => link.getAttribute("href") === path);
  const preferred = (mobile && matches.find((link) => link.closest?.(".bottom-nav")))
    || matches.find((link) => !link.closest?.(".bottom-nav"))
    || matches[0]
    || null;
  links.forEach((link) => {
    if (link === preferred) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}
