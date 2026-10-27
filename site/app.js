"use strict";

const TZ = "Asia/Shanghai";
const FEED_URL = "data/gallery.json";
const CACHE_KEY = "memeRadar:gallery:feed:v2";
const FAV_KEY = "memeRadar:gallery:favorites:v1";
const SEEN_KEY = "memeRadar:gallery:seen:v1";
const THEME_KEY = "memeRadar:gallery:theme:v1";
const PAGE_SIZE = 24;
const THEMES = ["auto", "light", "dark"];
const THEME_LABELS = { auto: "跟随系统", light: "浅色", dark: "深色" };
const SOURCE_LABELS = { reddit: "Reddit", tieba: "贴吧" };

const state = {
  feed: null,
  mode: "latest",
  source: "all",
  query: "",
  tag: "",
  favoritesOnly: false,
  hideSeen: false,
  visible: PAGE_SIZE,
  randomSeed: 1,
  favorites: new Set(),
  seen: new Set(),
  theme: "auto",
  loading: true,
  fromCache: false,
  error: null,
  currentItem: null,
  toastTimer: 0,
  searchTimer: 0,
  deferredPrompt: null,
  imageFailures: new Set(),
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const els = {
  grid: $("#grid"),
  empty: $("#empty"),
  emptyTitle: $("#emptyTitle"),
  emptyText: $("#emptyText"),
  emptyAction: $("#emptyAction"),
  loadMoreWrap: $("#loadMoreWrap"),
  loadMore: $("#loadMore"),
  resultMeta: $("#resultMeta"),
  banner: $("#banner"),
  imageNote: $("#imageNote"),
  statusPill: $("#statusPill"),
  heroMeta: $("#heroMeta"),
  statTotal: $("#statTotal"),
  statNew: $("#statNew"),
  statSource: $("#statSource"),
  countAll: $("#countAll"),
  countReddit: $("#countReddit"),
  countTieba: $("#countTieba"),
  favCount: $("#favCount"),
  favOnly: $("#favOnly"),
  hideSeen: $("#hideSeen"),
  searchInput: $("#searchInput"),
  clearSearch: $("#clearSearch"),
  trendChips: $("#trendChips"),
  shuffleBtn: $("#shuffleBtn"),
  healthPanel: $("#healthPanel"),
  healthSummary: $("#healthSummary"),
  healthList: $("#healthList"),
  themeToggle: $("#themeToggle"),
  installBtn: $("#installBtn"),
  lightbox: $("#lightbox"),
  lightboxClose: $("#lightboxClose"),
  lightboxImage: $("#lightboxImage"),
  lightboxLoading: $("#lightboxLoading"),
  lightboxMedia: $(".lightbox-media"),
  lightboxFallback: $("#lightboxFallback"),
  lightboxFallbackLink: $("#lightboxFallbackLink"),
  lightboxSource: $("#lightboxSource"),
  lightboxCommunity: $("#lightboxCommunity"),
  lightboxTime: $("#lightboxTime"),
  lightboxTitle: $("#lightboxTitle"),
  lightboxSummary: $("#lightboxSummary"),
  lightboxTags: $("#lightboxTags"),
  lightboxFav: $("#lightboxFav"),
  lightboxSeen: $("#lightboxSeen"),
  lightboxPost: $("#lightboxPost"),
  lightboxStats: $("#lightboxStats"),
  lightboxRelated: $("#lightboxRelated"),
  toast: $("#toast"),
  template: $("#cardTemplate"),
};

function safeGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_error) {
    return null;
  }
}

function safeSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_error) {
    /* Storage can be unavailable in private mode. */
  }
}

function loadSet(key) {
  const raw = safeGet(key);
  if (!raw) return new Set();
  try {
    const value = JSON.parse(raw);
    return new Set(Array.isArray(value) ? value.filter((entry) => typeof entry === "string") : []);
  } catch (_error) {
    return new Set();
  }
}

function saveSet(key, value) {
  safeSet(key, JSON.stringify(Array.from(value)));
}

function initTheme() {
  const saved = safeGet(THEME_KEY);
  state.theme = THEMES.includes(saved) ? saved : "auto";
  applyTheme();
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  const label = `主题：${THEME_LABELS[state.theme]}（点击切换）`;
  els.themeToggle.setAttribute("aria-label", label);
  els.themeToggle.title = label;
}

function cycleTheme() {
  const index = THEMES.indexOf(state.theme);
  state.theme = THEMES[(index + 1) % THEMES.length];
  safeSet(THEME_KEY, state.theme);
  applyTheme();
  showToast(`主题：${THEME_LABELS[state.theme]}`);
}

function loadLocalState() {
  state.favorites = loadSet(FAV_KEY);
  state.seen = loadSet(SEEN_KEY);
  updateFavoriteCount();
}

function updateFavoriteCount() {
  els.favCount.textContent = String(state.favorites.size);
  els.favOnly.setAttribute("aria-pressed", String(state.favoritesOnly));
  els.hideSeen.setAttribute("aria-pressed", String(state.hideSeen));
}

function toggleFavorite(id) {
  const active = state.favorites.has(id);
  if (active) state.favorites.delete(id);
  else state.favorites.add(id);
  saveSet(FAV_KEY, state.favorites);
  updateFavoriteCount();
  updateCardState(id);
  if (state.currentItem?.id === id) syncLightboxFavorite();
  showToast(active ? "已取消收藏" : "已收藏，仅保存在这台设备");
  if (state.favoritesOnly && active) renderGrid();
}

function markSeen(id, silent = false) {
  if (!id || state.seen.has(id)) return;
  state.seen.add(id);
  saveSet(SEEN_KEY, state.seen);
  updateCardState(id);
  if (!silent) showToast("已标记为已看");
}

function updateCardState(id) {
  const card = $(`.card[data-id="${cssEscape(id)}"]`, els.grid);
  if (!card) return;
  const fav = state.favorites.has(id);
  const seen = state.seen.has(id);
  card.classList.toggle("is-favorite", fav);
  card.classList.toggle("is-seen", seen);
  const favButton = $(".fav-btn", card);
  if (favButton) {
    favButton.setAttribute("aria-pressed", String(fav));
    favButton.setAttribute("aria-label", fav ? "取消收藏" : "收藏");
  }
  const seenPill = $(".seen-pill", card);
  if (seenPill) seenPill.hidden = !seen;
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function normalize(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("zh-CN")
    .replace(/\s+/g, "");
}

function itemText(item) {
  return normalize(
    [
      item.title,
      item.summary,
      item.community,
      item.source_name,
      ...(item.tags || []),
      ...(item.related || []).map((entry) => entry.title),
    ]
      .filter(Boolean)
      .join(" ")
  );
}

function itemTime(item) {
  return Date.parse(item.created_at || item.collected_at || "") || 0;
}

function formatParts(iso) {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return null;
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: TZ,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(
    formatter.formatToParts(date).map((part) => [part.type, part.value])
  );
  parts.hour = parts.hour === "24" ? "00" : parts.hour;
  return parts;
}

function formatWhen(iso) {
  const parts = formatParts(iso);
  if (!parts) return "时间未知";
  const now = formatParts(new Date().toISOString());
  const sameDay = now && now.year === parts.year && now.month === parts.month && now.day === parts.day;
  const clock = `${parts.hour}:${parts.minute}`;
  if (sameDay) return `今天 ${clock}`;
  if (now && now.year === parts.year) return `${Number(parts.month)}月${Number(parts.day)}日 ${clock}`;
  return `${parts.year}年${Number(parts.month)}月${Number(parts.day)}日`;
}

function formatAge(iso) {
  const timestamp = Date.parse(iso || "");
  if (!Number.isFinite(timestamp)) return "时间未知";
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`;
  return formatWhen(iso);
}

function formatNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  if (value >= 10000) return `${(value / 10000).toFixed(1).replace(".0", "")}万`;
  return String(value);
}

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source || "来源";
}

function allItems() {
  return state.feed?.items || [];
}

function counts() {
  const items = allItems();
  return {
    all: items.length,
    reddit: items.filter((item) => item.source === "reddit").length,
    tieba: items.filter((item) => item.source === "tieba").length,
  };
}

function hashString(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function filteredItems() {
  let items = allItems().slice();
  if (state.favoritesOnly) items = items.filter((item) => state.favorites.has(item.id));
  if (state.source !== "all") items = items.filter((item) => item.source === state.source);
  if (state.hideSeen) items = items.filter((item) => !state.seen.has(item.id));
  const query = normalize(state.query);
  if (query) items = items.filter((item) => itemText(item).includes(query));
  if (state.tag) {
    items = items.filter(
      (item) =>
        (item.tags || []).some((tag) => tag === state.tag) ||
        normalize(item.title).includes(normalize(state.tag)) ||
        normalize(item.summary).includes(normalize(state.tag))
    );
  }
  if (state.mode === "hot") {
    items.sort((a, b) => (b.rank_score || 0) - (a.rank_score || 0) || itemTime(b) - itemTime(a));
  } else if (state.mode === "random") {
    items.sort(
      (a, b) =>
        hashString(`${a.id}:${state.randomSeed}`) - hashString(`${b.id}:${state.randomSeed}`)
    );
  } else {
    items.sort((a, b) => itemTime(b) - itemTime(a));
  }
  return items;
}

function setStatus(text, kind) {
  els.statusPill.textContent = text;
  els.statusPill.className = `status-pill ${kind || ""}`.trim();
}

function renderHero() {
  const values = counts();
  els.statTotal.textContent = state.feed ? String(values.all) : "—";
  els.statNew.textContent = state.feed ? String(state.feed.run?.items_new ?? 0) : "—";
  els.statSource.textContent = state.feed
    ? String(
        (state.feed.sources || []).filter(
          (entry) =>
            (entry.source === "reddit" || entry.source === "tieba") &&
            (entry.status === "ok" || entry.status === "degraded")
        ).length
      )
    : "—";
  els.countAll.textContent = String(values.all);
  els.countReddit.textContent = String(values.reddit);
  els.countTieba.textContent = String(values.tieba);

  if (state.loading) {
    setStatus("连接中", "is-loading");
    els.heroMeta.textContent = "正在接收 Reddit 与贴吧的公开图片…";
    return;
  }
  if (state.error) {
    setStatus("连接失败", "is-error");
    els.heroMeta.textContent = "没有读到图库数据，请稍后重试。";
    return;
  }
  if (!state.feed) {
    setStatus("无信号", "is-error");
    return;
  }
  const health = state.feed.health || {};
  const updated = state.feed.generated_at ? formatAge(state.feed.generated_at) : "尚未成功采集";
  const bits = [
    `更新 ${updated}`,
    state.feed.trends?.keywords?.length ? `${state.feed.trends.keywords.length} 个热点候选词` : "",
    `${state.feed.items?.length || 0} 张图`,
  ].filter(Boolean);
  if (state.fromCache) bits.push("本机缓存");
  els.heroMeta.textContent = bits.join(" · ");

  if (state.feed.stale) setStatus("数据过期", "is-warn");
  else if (health.status === "blocked") setStatus("来源中断", "is-error");
  else if (health.status === "degraded") setStatus("部分降级", "is-warn");
  else if (state.fromCache) setStatus("缓存阅读", "is-warn");
  else setStatus("已更新", "is-live");
}

function showBanner(message, kind, actionLabel, action) {
  els.banner.replaceChildren();
  els.banner.className = `banner ${kind || ""}`.trim();
  els.banner.hidden = false;
  els.banner.append(document.createTextNode(message));
  if (actionLabel && action) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = actionLabel;
    button.addEventListener("click", action);
    els.banner.append(button);
  }
}

function hideBanner() {
  els.banner.hidden = true;
  els.banner.replaceChildren();
}

function renderImageNote() {
  if (!state.imageFailures.size) {
    els.imageNote.hidden = true;
    els.imageNote.textContent = "";
    return;
  }
  els.imageNote.hidden = false;
  els.imageNote.textContent = `${state.imageFailures.size} 张图片在当前网络无法加载（多为 Reddit 图片域或已过期链接），卡片已显示原帖入口；这不是伪造成功。`;
}

function markImageFailure(id) {
  if (!id) return;
  state.imageFailures.add(id);
  renderImageNote();
}

function openHealth() {
  if (els.healthPanel.hidden) return;
  const details = $("details", els.healthPanel);
  if (details) details.open = true;
  els.healthPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderBanner() {
  hideBanner();
  if (state.loading) return;
  if (state.error) {
    showBanner(`加载失败：${state.error.message || "网络错误"}。`, "is-error", "重新加载", () => loadFeed(true));
    return;
  }
  if (!state.feed) return;
  if (state.fromCache) {
    showBanner("网络不可用，正在显示本机上次缓存的图片数据。", "is-warn", "重试", () => loadFeed(true));
    return;
  }
  if (state.feed.stale) {
    showBanner(
      `${state.feed.stale_reason || "本轮没有成功更新。"} 最后成功更新：${
        state.feed.generated_at ? formatWhen(state.feed.generated_at) : "暂无"
      }。`,
      "is-error",
      "查看数据源",
      openHealth
    );
    return;
  }
  const health = state.feed.health || {};
  const alerts = health.alerts || [];
  if (health.status === "degraded" || alerts.length) {
    const sourceIssue = (state.feed.sources || []).find(
      (entry) => entry.status === "blocked" || entry.status === "degraded"
    );
    const reason = sourceIssue && sourceIssue.status === "degraded"
      ? `${sourceIssue.name} 处于降级采集，内容仍来自真实公开页面。`
      : "部分来源本次不可用，已保留历史图片。";
    showBanner(`${reason} ${alerts.join("；")}`.trim(), "is-warn", "数据源详情", openHealth);
  }
}

function renderChips() {
  const keywords = state.feed?.trends?.keywords || [];
  els.trendChips.replaceChildren();
  if (!keywords.length) {
    els.trendChips.hidden = true;
    return;
  }
  els.trendChips.hidden = false;
  for (const keyword of keywords.slice(0, 9)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.dataset.tag = keyword.word;
    button.textContent = `${keyword.word} ${keyword.count}`;
    button.setAttribute("aria-pressed", String(state.tag === keyword.word));
    button.addEventListener("click", () => {
      state.tag = state.tag === keyword.word ? "" : keyword.word;
      state.visible = PAGE_SIZE;
      renderChips();
      renderGrid();
    });
    els.trendChips.append(button);
  }
}

function renderHealth() {
  const feed = state.feed;
  if (!feed || !Array.isArray(feed.sources) || !feed.sources.length) {
    els.healthPanel.hidden = true;
    return;
  }
  const health = feed.health || {};
  const statusLabel = {
    ok: "正常",
    degraded: "降级",
    blocked: "中断",
    planned: "计划中",
    disabled: "未启用",
  };
  els.healthSummary.textContent = `${statusLabel[health.status] || health.status || "未知"} · ${
    feed.generated_at ? formatWhen(feed.generated_at) : "尚未成功"
  }`;
  els.healthList.replaceChildren();
  for (const source of feed.sources) {
    const row = document.createElement("div");
    row.className = "health-row";
    const dot = document.createElement("span");
    dot.className = `health-dot ${source.status || ""}`;
    dot.setAttribute("aria-hidden", "true");
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = source.name || source.source;
    const detail = document.createElement("small");
    const bits = [statusLabel[source.status] || source.status || "未知"];
    if (source.error) bits.push(source.error);
    else if (source.source === "reddit") bits.push("官方公开 Atom/RSS");
    else if (source.source === "tieba") bits.push("公开热点页；详情页 403，已降级");
    else if (source.source === "trends") bits.push("用于候选关键词，不直接生成图片");
    else if (source.status === "planned") bits.push("尚未实现，不会显示为运行中");
    detail.textContent = bits.filter(Boolean).join(" · ");
    copy.append(name, detail);
    const count = document.createElement("span");
    count.className = "health-count";
    count.textContent = source.item_count ? `${source.item_count} 条` : "";
    row.append(dot, copy, count);
    els.healthList.append(row);
  }
  els.healthPanel.hidden = false;
}

function renderFilterState() {
  $$(".mode-btn").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.mode === state.mode));
  });
  $$(".filter-btn[data-source]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.source === state.source));
  });
  els.favOnly.setAttribute("aria-pressed", String(state.favoritesOnly));
  els.hideSeen.setAttribute("aria-pressed", String(state.hideSeen));
  els.shuffleBtn.hidden = state.mode !== "random";
  els.clearSearch.hidden = !els.searchInput.value;
}

function createCard(item, index) {
  const card = els.template.content.firstElementChild.cloneNode(true);
  card.dataset.id = item.id;
  card.dataset.source = item.source;
  card.classList.toggle("is-favorite", state.favorites.has(item.id));
  card.classList.toggle("is-seen", state.seen.has(item.id));
  card.style.setProperty("--i", String(Math.min(index, 12)));

  const image = $(".card-media img", card);
  image.alt = item.title || "";
  image.loading = "lazy";
  image.decoding = "async";
  image.referrerPolicy = "no-referrer";
  if (item.image_width && item.image_height) {
    image.width = item.image_width;
    image.height = item.image_height;
    image.style.aspectRatio = `${item.image_width} / ${item.image_height}`;
  }
  image.src = item.thumbnail_url || item.image_url;
  image.addEventListener("load", () => {
    image.dataset.loading = "false";
  });
  image.addEventListener("error", () => {
    image.hidden = true;
    const fallback = $(".media-fallback", card);
    fallback.hidden = false;
    const fallbackLink = $("a", fallback);
    fallbackLink.href = item.post_url;
    markImageFailure(item.id);
  });

  const source = $(".source-pill", card);
  source.textContent = sourceLabel(item.source);
  source.dataset.source = item.source;

  const related = $(".related-pill", card);
  if (item.group_size > 1) {
    related.hidden = false;
    related.textContent = `同图 +${item.group_size - 1}`;
  }

  const seen = $(".seen-pill", card);
  seen.hidden = !state.seen.has(item.id);

  const favButton = $(".fav-btn", card);
  favButton.dataset.id = item.id;
  favButton.setAttribute("aria-pressed", String(state.favorites.has(item.id)));
  favButton.setAttribute("aria-label", state.favorites.has(item.id) ? "取消收藏" : "收藏");
  favButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleFavorite(item.id);
  });

  $(".card-title", card).textContent = item.title;
  const summary = $(".card-summary", card);
  summary.textContent = item.summary || "";

  $(".community", card).textContent = item.community || sourceLabel(item.source);
  $(".time", card).textContent = item.created_at ? formatWhen(item.created_at) : `收录 ${formatWhen(item.collected_at)}`;
  const comments = $(".comments", card);
  if (typeof item.comment_count === "number") {
    comments.textContent = `${formatNumber(item.comment_count)} 评论`;
  } else if (item.score !== null && item.score !== undefined) {
    comments.textContent = `${formatNumber(item.score)} 分`;
  } else {
    comments.hidden = true;
  }

  const tags = $(".card-tags", card);
  const visibleTags = (item.tags || [])
    .filter((tag) => tag !== "reddit" && tag !== "贴吧" && tag !== item.community)
    .slice(0, 3);
  visibleTags.forEach((tag) => {
    const element = document.createElement("span");
    element.className = "tag";
    element.textContent = tag;
    tags.append(element);
  });

  card.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) return;
    openLightbox(item);
  });
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openLightbox(item);
    }
  });
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `${item.title}，打开大图和原帖`);
  return card;
}

function renderEmptyState(items) {
  const filtered = items.length;
  if (state.error) {
    renderEmpty("图库暂时失联", "没有加载到 data/gallery.json。如果你刚部署，请确认 Pages 已生成数据文件。", "重新加载", () => loadFeed(true));
    return;
  }
  if (!state.feed) {
    renderEmpty("还没有信号", "采集器尚未生成图库数据，稍后再来看看。", null, null);
    return;
  }
  if (!allItems().length) {
    renderEmpty("还没有真实图片", "首次采集可能尚未完成；没有数据时不会展示假图。", "重新加载", () => loadFeed(true));
    return;
  }
  if (state.favoritesOnly) {
    renderEmpty("收藏夹是空的", "点卡片右上角的爱心，把喜欢的图保存在这台手机上。", "回到图库", resetFilters);
    return;
  }
  if (filtered === 0 && (state.query || state.tag || state.source !== "all" || state.hideSeen)) {
    renderEmpty("没有匹配的图", "当前筛选条件太窄了，清除筛选再看看。", "清除筛选", resetFilters);
    return;
  }
  renderEmpty("暂时没有更多图", "本轮采集没有新增内容，稍后会自动尝试。", "重新加载", () => loadFeed(true));
}

function renderEmpty(title, text, actionLabel, action) {
  els.emptyTitle.textContent = title;
  els.emptyText.textContent = text;
  if (actionLabel && action) {
    els.emptyAction.hidden = false;
    els.emptyAction.textContent = actionLabel;
    els.emptyAction.onclick = action;
  } else {
    els.emptyAction.hidden = true;
    els.emptyAction.onclick = null;
  }
  els.empty.hidden = false;
}

function resetFilters() {
  state.source = "all";
  state.query = "";
  state.tag = "";
  state.favoritesOnly = false;
  state.hideSeen = false;
  state.visible = PAGE_SIZE;
  els.searchInput.value = "";
  els.clearSearch.hidden = true;
  updateFavoriteCount();
  renderChips();
  renderFilterState();
  renderGrid();
}

function updateResultMeta(items, shown) {
  const bits = [];
  if (state.favoritesOnly) bits.push(`收藏 ${items.length} 张`);
  else bits.push(`共 ${items.length} 张`);
  if (state.query) bits.push(`搜索「${state.query}」`);
  if (state.tag) bits.push(`标签「${state.tag}」`);
  if (state.source !== "all") bits.push(sourceLabel(state.source));
  if (state.hideSeen) bits.push("隐藏已看");
  if (items.length > shown) bits.push(`已显示 ${shown}`);
  if (state.mode === "random") bits.push("随机顺序");
  els.resultMeta.textContent = bits.join(" · ");
}

function renderGrid() {
  const items = filteredItems();
  els.grid.replaceChildren();
  els.grid.setAttribute("aria-busy", "false");
  els.empty.hidden = true;
  els.loadMoreWrap.hidden = true;
  if (state.error || !state.feed || !allItems().length) {
    updateResultMeta(items, 0);
    renderEmptyState(items);
    return;
  }
  if (!items.length) {
    updateResultMeta(items, 0);
    renderEmptyState(items);
    return;
  }
  const shown = Math.min(state.visible, items.length);
  updateResultMeta(items, shown);
  const fragment = document.createDocumentFragment();
  items.slice(0, shown).forEach((item, index) => fragment.append(createCard(item, index)));
  els.grid.append(fragment);
  els.loadMoreWrap.hidden = shown >= items.length;
}

function renderAll() {
  renderHero();
  renderBanner();
  renderImageNote();
  renderChips();
  renderHealth();
  renderFilterState();
  renderGrid();
}

function renderLoading() {
  els.grid.setAttribute("aria-busy", "true");
  els.grid.replaceChildren();
  for (let index = 0; index < 4; index += 1) {
    const card = document.createElement("div");
    card.className = "skeleton-card";
    const image = document.createElement("div");
    image.className = `skeleton-img${index % 2 ? " tall" : ""}`;
    const line = document.createElement("div");
    line.className = "skeleton-line";
    const short = document.createElement("div");
    short.className = "skeleton-line short";
    card.append(image, line, short);
    els.grid.append(card);
  }
  els.empty.hidden = true;
  els.loadMoreWrap.hidden = true;
  els.resultMeta.textContent = "正在整理图片…";
}

function readCache() {
  const raw = safeGet(CACHE_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (value && Array.isArray(value.items)) return value;
  } catch (_error) {
    return null;
  }
  return null;
}

async function loadFeed(force = false) {
  state.loading = true;
  state.error = null;
  renderLoading();
  renderHero();
  hideBanner();
  try {
    const response = await fetch(`${FEED_URL}?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data || !Array.isArray(data.items)) throw new Error("gallery.json 格式不正确");
    state.feed = data;
    state.fromCache = false;
    state.loading = false;
    state.visible = PAGE_SIZE;
    state.imageFailures.clear();
    safeSet(CACHE_KEY, JSON.stringify(data));
    renderAll();
  } catch (error) {
    const cached = readCache();
    if (cached) {
      state.feed = cached;
      state.fromCache = true;
      state.loading = false;
      state.visible = PAGE_SIZE;
      state.imageFailures.clear();
      renderAll();
    } else {
      state.feed = null;
      state.loading = false;
      state.error = error instanceof Error ? new Error(error.message === "Failed to fetch" ? "网络请求失败" : error.message) : new Error(String(error));
      renderAll();
    }
  }
  if (force && state.fromCache) showToast("仍无法连接，继续显示本机缓存");
}

function openLightbox(item) {
  state.currentItem = item;
  markSeen(item.id, true);
  els.lightbox.hidden = false;
  document.body.classList.add("is-locked");
  els.lightboxSource.textContent = sourceLabel(item.source);
  els.lightboxSource.dataset.source = item.source;
  els.lightboxCommunity.textContent = item.community || "";
  els.lightboxTime.textContent = item.created_at ? formatWhen(item.created_at) : `收录 ${formatWhen(item.collected_at)}`;
  els.lightboxTitle.textContent = item.title;
  els.lightboxSummary.textContent = item.summary || "原帖没有额外正文摘要。";
  els.lightboxTags.replaceChildren();
  (item.tags || []).slice(0, 8).forEach((tag) => {
    const element = document.createElement("span");
    element.className = "tag";
    element.textContent = tag;
    els.lightboxTags.append(element);
  });
  els.lightboxPost.href = item.post_url;
  els.lightboxFallbackLink.href = item.post_url;
  els.lightboxImage.hidden = false;
  els.lightboxFallback.hidden = true;
  els.lightboxLoading.hidden = false;
  els.lightboxMedia.classList.remove("is-loaded");
  let triedThumbnail = false;
  els.lightboxImage.onload = () => {
    els.lightboxMedia.classList.add("is-loaded");
    els.lightboxLoading.hidden = true;
  };
  els.lightboxImage.onerror = () => {
    if (!triedThumbnail && item.thumbnail_url && item.thumbnail_url !== item.image_url) {
      triedThumbnail = true;
      els.lightboxImage.src = item.thumbnail_url;
      return;
    }
    els.lightboxImage.hidden = true;
    els.lightboxLoading.hidden = true;
    els.lightboxFallback.hidden = false;
    markImageFailure(item.id);
  };
  els.lightboxImage.src = item.image_url;
  els.lightboxImage.alt = item.title;
  syncLightboxFavorite();
  updateLightboxSeen();
  const stats = [];
  if (typeof item.comment_count === "number") stats.push(`评论 ${formatNumber(item.comment_count)}`);
  if (typeof item.score === "number") stats.push(`得分 ${formatNumber(item.score)}`);
  if (!stats.length) stats.push(item.source === "reddit" ? "Reddit RSS 未提供互动数" : "来源未提供互动数");
  if (item.time_source === "collection") stats.push("发布时间未公开，按收录时间排序");
  els.lightboxStats.textContent = stats.join(" · ");
  els.lightboxRelated.replaceChildren();
  if (item.group_size > 1 && Array.isArray(item.related) && item.related.length) {
    els.lightboxRelated.hidden = false;
    const label = document.createElement("span");
    label.textContent = `同一图片还有 ${item.group_size - 1} 条相关记录：`;
    els.lightboxRelated.append(label);
    item.related.forEach((entry, index) => {
      if (index) els.lightboxRelated.append(document.createTextNode(" · "));
      const link = document.createElement("a");
      link.href = entry.post_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer nofollow";
      link.textContent = `${sourceLabel(entry.source)} ${entry.title || ""}`.slice(0, 60);
      els.lightboxRelated.append(link);
    });
  } else {
    els.lightboxRelated.hidden = true;
  }
  els.lightboxClose.focus();
}

function syncLightboxFavorite() {
  if (!state.currentItem) return;
  const active = state.favorites.has(state.currentItem.id);
  els.lightboxFav.textContent = active ? "已收藏" : "收藏";
  els.lightboxFav.classList.toggle("is-active", active);
  els.lightboxFav.setAttribute("aria-pressed", String(active));
}

function updateLightboxSeen() {
  if (!state.currentItem) return;
  const seen = state.seen.has(state.currentItem.id);
  els.lightboxSeen.textContent = seen ? "已看" : "标为已看";
  els.lightboxSeen.setAttribute("aria-pressed", String(seen));
}

function closeLightbox() {
  els.lightbox.hidden = true;
  document.body.classList.remove("is-locked");
  els.lightboxImage.removeAttribute("src");
  els.lightboxMedia.classList.remove("is-loaded");
  state.currentItem = null;
  if (state.hideSeen) renderGrid();
}

function showToast(message) {
  window.clearTimeout(state.toastTimer);
  els.toast.textContent = message;
  els.toast.classList.add("is-visible");
  state.toastTimer = window.setTimeout(() => els.toast.classList.remove("is-visible"), 1900);
}

function bindEvents() {
  els.themeToggle.addEventListener("click", cycleTheme);

  $$(".mode-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode || "latest";
      state.visible = PAGE_SIZE;
      renderFilterState();
      renderGrid();
    });
  });

  $$(".filter-btn[data-source]").forEach((button) => {
    button.addEventListener("click", () => {
      state.source = button.dataset.source || "all";
      state.visible = PAGE_SIZE;
      renderFilterState();
      renderGrid();
    });
  });

  els.favOnly.addEventListener("click", () => {
    state.favoritesOnly = !state.favoritesOnly;
    state.visible = PAGE_SIZE;
    updateFavoriteCount();
    renderFilterState();
    renderGrid();
  });

  els.hideSeen.addEventListener("click", () => {
    state.hideSeen = !state.hideSeen;
    state.visible = PAGE_SIZE;
    updateFavoriteCount();
    renderFilterState();
    renderGrid();
  });

  els.searchInput.addEventListener("input", () => {
    const value = els.searchInput.value;
    els.clearSearch.hidden = !value;
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      state.query = value.trim();
      state.visible = PAGE_SIZE;
      renderGrid();
    }, 120);
  });

  els.clearSearch.addEventListener("click", () => {
    els.searchInput.value = "";
    els.clearSearch.hidden = true;
    state.query = "";
    state.visible = PAGE_SIZE;
    renderGrid();
    els.searchInput.focus();
  });

  els.shuffleBtn.addEventListener("click", () => {
    state.randomSeed = (state.randomSeed + 7919) % 100000000;
    state.visible = PAGE_SIZE;
    renderGrid();
  });

  els.loadMore.addEventListener("click", () => {
    state.visible += PAGE_SIZE;
    renderGrid();
  });

  els.lightboxClose.addEventListener("click", closeLightbox);
  els.lightbox.addEventListener("click", (event) => {
    if (event.target === els.lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.lightbox.hidden) closeLightbox();
  });

  els.lightboxFav.addEventListener("click", () => {
    if (state.currentItem) toggleFavorite(state.currentItem.id);
  });
  els.lightboxSeen.addEventListener("click", () => {
    if (!state.currentItem) return;
    if (state.seen.has(state.currentItem.id)) {
      state.seen.delete(state.currentItem.id);
      saveSet(SEEN_KEY, state.seen);
    } else {
      state.seen.add(state.currentItem.id);
      saveSet(SEEN_KEY, state.seen);
    }
    updateCardState(state.currentItem.id);
    updateLightboxSeen();
    showToast(state.seen.has(state.currentItem.id) ? "已标记为已看" : "已取消已看");
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.deferredPrompt = event;
    els.installBtn.hidden = false;
  });
  els.installBtn.addEventListener("click", async () => {
    if (!state.deferredPrompt) return;
    state.deferredPrompt.prompt();
    await state.deferredPrompt.userChoice;
    state.deferredPrompt = null;
    els.installBtn.hidden = true;
  });
  window.addEventListener("appinstalled", () => {
    els.installBtn.hidden = true;
    showToast("已添加到主屏幕");
  });
  if (window.matchMedia("(display-mode: standalone)").matches) els.installBtn.hidden = true;
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register("sw.js", { scope: "./" });
  } catch (error) {
    // PWA is optional; the page still works without a service worker.
    console.warn("service worker registration failed", error);
  }
}

function init() {
  initTheme();
  loadLocalState();
  bindEvents();
  registerServiceWorker();
  loadFeed();
}

init();
