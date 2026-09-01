const PROVIDER_LABELS = Object.freeze({
  tmdb: "TMDb",
  omdb: "IMDb",
  imdb: "IMDb",
  tvmaze: "TVMaze",
  anilist: "AniList",
  jikan: "MAL",
  apple_movies: "Apple TV",
  mal: "MAL",
});

function textValue(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function providerList(value) {
  const values = Array.isArray(value) ? value : [];
  const providers = [];
  for (const entry of values) {
    const provider = textValue(entry).toLowerCase();
    if (provider && !providers.includes(provider)) providers.push(provider);
  }
  return providers;
}

function sourceProviders(source) {
  const providers = [];
  for (const segment of source.toLowerCase().split("|").map((part) => part.trim())) {
    if (!segment.startsWith("global:")) continue;
    const suffix = segment.slice("global:".length);
    for (const provider of Object.keys(PROVIDER_LABELS)) {
      if (suffix === provider || suffix.startsWith(`${provider}_`) || suffix.startsWith(`${provider}:`)) {
        const canonical = provider === "omdb" ? "imdb" : (provider === "mal" ? "jikan" : provider);
        if (!providers.includes(canonical)) providers.push(canonical);
        break;
      }
    }
  }
  return providers;
}

function onlineLabel(providers) {
  const labels = providers.map((provider) => PROVIDER_LABELS[provider] || provider).filter(Boolean);
  return labels.length ? `\u5728\u7ebf\u53d1\u73b0 \u00b7 ${labels.join(" / ")}` : "\u5728\u7ebf\u53d1\u73b0";
}

export function candidateOrigin(item = {}) {
  const record = item && typeof item === "object" ? item : {};
  const declared = record.candidate_origin && typeof record.candidate_origin === "object"
    ? record.candidate_origin
    : null;
  if (declared && ["online", "catalog"].includes(textValue(declared.kind))) {
    const kind = textValue(declared.kind);
    const providers = providerList(declared.providers);
    const label = textValue(
      declared.label,
      kind === "online" ? onlineLabel(providers) : "\u7cbe\u9009\u5019\u9009",
    );
    return { kind, label, providers };
  }

  const source = textValue(record.source);
  const folded = source.toLowerCase();
  const segments = folded.split("|").map((part) => part.trim()).filter(Boolean);
  const cachedGlobal = folded.startsWith("global-cache:");
  const providers = providerList(record.discovery_sources);
  for (const provider of sourceProviders(source)) {
    if (!providers.includes(provider)) providers.push(provider);
  }
  if (!cachedGlobal && (providers.length || segments.some((segment) => segment.startsWith("global:")))) {
    return { kind: "online", label: onlineLabel(providers), providers };
  }
  if (["global-cache:", "douban_user:", "douban-sync:", "local", "csv"].some((prefix) => folded.startsWith(prefix))) {
    return { kind: "catalog", label: "\u672c\u673a\u7247\u5e93", providers: [] };
  }
  if (["douban_explore:", "douban_plan:", "douban_page:"].some((prefix) => folded.startsWith(prefix))) {
    return { kind: "catalog", label: "\u8c46\u74e3\u5019\u9009", providers: [] };
  }
  return { kind: "catalog", label: "\u7cbe\u9009\u5019\u9009", providers: [] };
}

export function isOnlineCandidate(item = {}) {
  return candidateOrigin(item).kind === "online";
}
