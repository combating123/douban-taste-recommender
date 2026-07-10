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
  document.querySelectorAll("[data-route]").forEach((link) => {
    const current = link.getAttribute("href") === path;
    if (current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}
