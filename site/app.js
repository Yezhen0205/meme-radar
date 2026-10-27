"use strict";

const TZ = "Asia/Shanghai";
const FEED_URL = "data/feed.json";
const CACHE_KEY = "memeRadar:feed:v1";
const FAV_KEY = "memeRadar:favorites:v1";
const THEME_KEY = "memeRadar:theme:v1";
const PAGE_SIZE = 40;
const CATEGORY_LABELS = {
  meme: "热梗",
  reply: "神回复",
  comment: "评论金句",
  hot: "热点",
};
const THEMES = ["auto", "light", "dark"];
const THEME_LABELS = {
  auto: "跟随系统",
  light: "浅色",
  dark: "深色",
};

const state = {
  feed: null,
  filter: "meme",
  sort: "latest",
  query: "",
  favoritesOnly: false,
  visible: PAGE_SIZE,
  loading: true,
  fromCache: false,
  error: null,
  favorites: new Set(),
  theme: "auto",
  toastTimer: 0,
  searchTimer: 0,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const els = {
  feed: $("#feed"),
  empty: $("#empty"),
  emptyTitle: $("#emptyTitle"),
  emptyText: $("#emptyText"),
  emptyAction: $("#emptyAction"),
  loadMoreWrap: $("#loadMoreWrap"),
  loadMore: $("#loadMore"),
  resultMeta: $("#resultMeta"),
  notice: $("#notice"),
  dataStatus: $("#dataStatus"),
  heroMeta: $("#heroMeta"),
  statMeme: $("#statMeme"),
  statReply: $("#statReply"),
  statComment: $("#statComment"),
  countMeme: $("#countMeme"),
  countReply: $("#countReply"),
  countComment: $("#countComment"),
  countHot: $("#countHot"),
  searchInput: $("#searchInput"),
  clearSearch: $("#clearSearch"),
  rankHint: $("#rankHint"),
  sourcePanel: $("#sourcePanel"),
  sourceSummary: $("#sourceSummary"),
  sourceList: $("#sourceList"),
  favToggle: $("#favToggle"),
  favCount: $("#favCount"),
  themeToggle: $("#themeToggle"),
  toast: $("#toast"),
  template: $("#cardTemplate"),
};

function safeStorageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_error) {
    return null;
  }
}

function safeStorageSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_error) {
    /* Private mode or a full quota should not break reading. */
  }
}

function initTheme() {
  const saved = safeStorageGet(THEME_KEY);
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
  safeStorageSet(THEME_KEY, state.theme);
  applyTheme();
  showToast(`主题已切换为：${THEME_LABELS[state.theme]}`);
}

function loadFavorites() {
  const raw = safeStorageGet(FAV_KEY);
  if (!raw) return;
  try {
    const values = JSON.parse(raw);
    if (Array.isArray(values)) {
      state.favorites = new Set(values.filter((value) => typeof value === "string"));
    }
  } catch (_error) {
    state.favorites = new Set();
  }
}

function saveFavorites() {
  safeStorageSet(FAV_KEY, JSON.stringify(Array.from(state.favorites)));
  const count = state.favorites.size;
  els.favCount.textContent = String(count);
  els.favCount.hidden = count === 0;
}

function toggleFavorite(id) {
  if (state.favorites.has(id)) {
    state.favorites.delete(id);
    showToast("已取消收藏");
  } else {
    state.favorites.add(id);
    showToast("已收藏，仅保存在这台设备");
  }
  saveFavorites();
  updateBookmarkButtons();
  if (state.favoritesOnly) {
    state.visible = PAGE_SIZE;
    renderFeed();
  }
}

function updateBookmarkButtons() {
  $$(".bookmark", els.feed).forEach((button) => {
    const active = state.favorites.has(button.dataset.id);
    button.setAttribute("aria-pressed", String(active));
    button.setAttribute("aria-label", active ? "取消收藏" : "收藏");
  });
}

function isRecent(item, hours) {
  const value = item.collected_at || item.published_at;
  const timestamp = Date.parse(value || "");
  if (!Number.isFinite(timestamp)) return true;
  return Date.now() - timestamp <= hours * 3600 * 1000;
}

function todayHours() {
  return Number(state.feed?.settings?.today_hours || 24);
}

function counts() {
  const items = state.feed?.items || [];
  return {
    meme: items.filter((item) => item.category === "meme" && isRecent(item, todayHours())).length,
    reply: items.filter((item) => item.category === "reply").length,
    comment: items.filter((item) => item.category === "comment").length,
    hot: items.filter((item) => item.category === "hot").length,
  };
}

function normalizeSearch(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("zh-CN")
    .replace(/\s+/g, "");
}

function searchText(item) {
  return normalizeSearch(
    [
      item.title,
      item.summary,
      item.context,
      item.source_name,
      item.author,
      ...(item.tags || []),
      ...(item.related || []).map((related) => related.title),
    ]
      .filter(Boolean)
      .join(" ")
  );
}

function compareLatest(a, b) {
  const at = Date.parse(a.published_at || a.collected_at || "") || 0;
  const bt = Date.parse(b.published_at || b.collected_at || "") || 0;
  if (bt !== at) return bt - at;
  return (a.rank || 1) - (b.rank || 1);
}

function compareRank(a, b) {
  const ar = Number(a.rank) || 1;
  const br = Number(b.rank) || 1;
  if (ar !== br) return ar - br;
  return String(a.source_name || "").localeCompare(String(b.source_name || ""), "zh-CN");
}

function filteredItems() {
  let items = (state.feed?.items || []).slice();
  if (state.favoritesOnly) {
    items = items.filter((item) => state.favorites.has(item.id));
  } else if (state.filter === "meme") {
    items = items.filter((item) => item.category === "meme" && isRecent(item, todayHours()));
  } else if (state.filter === "reply" || state.filter === "comment" || state.filter === "hot") {
    items = items.filter((item) => item.category === state.filter);
  }
  const query = normalizeSearch(state.query);
  if (query) {
    items = items.filter((item) => searchText(item).includes(query));
  }
  items.sort(state.sort === "rank" ? compareRank : compareLatest);
  return items;
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

function formatWhen(iso, precision = "datetime") {
  const parts = formatParts(iso);
  if (!parts) return "时间未知";
  const now = formatParts(new Date().toISOString());
  const sameDay = now && now.year === parts.year && now.month === parts.month && now.day === parts.day;
  if (precision === "date") {
    if (now && now.year === parts.year) return `${Number(parts.month)}月${Number(parts.day)}日`;
    return `${parts.year}年${Number(parts.month)}月${Number(parts.day)}日`;
  }
  const clock = `${parts.hour}:${parts.minute}`;
  if (sameDay) return `今天 ${clock}`;
  if (now && now.year === parts.year) {
    return `${Number(parts.month)}月${Number(parts.day)}日 ${clock}`;
  }
  return `${parts.year}年${Number(parts.month)}月${Number(parts.day)}日 ${clock}`;
}

function formatAge(iso) {
  const timestamp = Date.parse(iso || "");
  if (!Number.isFinite(timestamp)) return "时间未知";
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} 小时前`;
  return formatWhen(iso);
}

function formatItemTime(item) {
  if (item.published_at) {
    return formatWhen(item.published_at, item.published_precision || "datetime");
  }
  if (item.collected_at) {
    return `采集于 ${formatWhen(item.collected_at)}`;
  }
  return "时间未知";
}

function itemHeatText(item) {
  if (item.heat && item.heat.display) {
    return `${item.heat.label} ${item.heat.display} · 榜位 ${item.rank}`;
  }
  if (item.rank) return `榜位 ${item.rank}`;
  return "";
}

function setStatus(text, kind) {
  els.dataStatus.textContent = text;
  els.dataStatus.className = `status-pill ${kind || ""}`.trim();
}

function makeActionButton(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

function showNotice(message, kind, actionLabel, action) {
  els.notice.replaceChildren();
  els.notice.className = `notice ${kind || ""}`.trim();
  els.notice.hidden = false;
  els.notice.append(document.createTextNode(message));
  if (actionLabel && action) {
    els.notice.append(makeActionButton(actionLabel, action));
  }
}

function hideNotice() {
  els.notice.hidden = true;
  els.notice.replaceChildren();
}

function openSourcePanel() {
  if (els.sourcePanel.hidden) return;
  const details = $("details", els.sourcePanel);
  if (details) details.open = true;
  els.sourcePanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderHero() {
  const feed = state.feed;
  const values = counts();
  els.statMeme.textContent = feed ? values.meme : "—";
  els.statReply.textContent = feed ? values.reply : "—";
  els.statComment.textContent = feed ? values.comment : "—";
  els.countMeme.textContent = feed ? values.meme : "";
  els.countReply.textContent = feed ? values.reply : "";
  els.countComment.textContent = feed ? values.comment : "";
  els.countHot.textContent = feed ? values.hot : "";

  if (state.loading) {
    setStatus("连接中", "is-loading");
    els.heroMeta.textContent = "正在接收公开热榜与评论区信号…";
    return;
  }
  if (state.error) {
    setStatus("连接失败", "is-error");
    els.heroMeta.textContent = "没有读到数据文件，请检查部署或稍后重试。";
    return;
  }
  if (!feed) {
    setStatus("无信号", "is-error");
    return;
  }
  const run = feed.run || {};
  const generated = feed.generated_at ? formatAge(feed.generated_at) : "尚未成功采集";
  const sourceText =
    typeof run.sources_total === "number"
      ? `${run.sources_ok || 0}/${run.sources_total} 个数据源正常`
      : "";
  const parts = [`最后更新 ${generated}`, sourceText, `共 ${(feed.items || []).length} 条`].filter(Boolean);
  if (state.fromCache) parts.push("本机缓存");
  els.heroMeta.textContent = parts.join(" · ");

  if (feed.stale) setStatus("数据过期", "is-warn");
  else if (run.partial) setStatus("部分更新", "is-warn");
  else if (state.fromCache) setStatus("缓存阅读", "is-warn");
  else setStatus("已更新", "is-live");
}

function renderNotice() {
  hideNotice();
  if (state.loading) return;
  if (state.error) {
    showNotice(`加载失败：${state.error.message || "未知错误"}。`, "is-error", "重新加载", () =>
      loadFeed(true)
    );
    return;
  }
  const feed = state.feed;
  if (!feed) return;
  if (state.fromCache) {
    showNotice(
      "网络请求失败，正在显示本机上次缓存的内容；缓存可能是旧的。",
      "is-warn",
      "重试",
      () => loadFeed(true)
    );
    return;
  }
  if (feed.stale) {
    showNotice(
      `${feed.stale_reason || "本次采集全部失败，页面展示上次成功数据。"} 最后成功更新：${
        feed.generated_at ? formatWhen(feed.generated_at) : "暂无"
      }。`,
      "is-error",
      "查看数据源",
      openSourcePanel
    );
    return;
  }
  if (feed.run?.partial) {
    showNotice(
      "部分数据源本次未更新，页面保留了它们的上次成功数据。",
      "is-warn",
      "查看数据源",
      openSourcePanel
    );
    return;
  }
  const timestamp = Date.parse(feed.generated_at || "");
  if (Number.isFinite(timestamp) && Date.now() - timestamp > 12 * 3600 * 1000) {
    showNotice(
      `距上次更新已超过 12 小时（${formatWhen(feed.generated_at)}），定时任务可能被平台延迟。`,
      "is-warn",
      "查看数据源",
      openSourcePanel
    );
  }
}

function renderSourcePanel() {
  const sources = state.feed?.sources || [];
  if (!sources.length) {
    els.sourcePanel.hidden = true;
    return;
  }
  const run = state.feed.run || {};
  const ok = sources.filter((source) => source.status === "ok").length;
  const total = sources.filter((source) => source.status !== "disabled").length;
  els.sourceSummary.textContent = `${ok}/${total} 正常 · ${
    state.feed.generated_at ? formatWhen(state.feed.generated_at) : "尚未成功采集"
  }`;
  els.sourceList.replaceChildren();
  for (const source of sources) {
    const row = document.createElement("div");
    row.className = "source-row";

    const dot = document.createElement("span");
    dot.className = `source-dot ${source.status || ""}`;
    dot.setAttribute("aria-hidden", "true");

    const text = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = source.name || source.id;
    const detail = document.createElement("small");
    let statusText = "";
    if (source.status === "ok") statusText = `成功 · ${source.accepted || 0} 条`;
    else if (source.status === "failed") {
      statusText = `失败${source.retained ? ` · 保留 ${source.retained} 条旧数据` : ""}`;
    } else if (source.status === "skipped") statusText = "跳过";
    else if (source.status === "disabled") statusText = "未启用";
    else statusText = source.status || "未知";
    detail.textContent = source.error
      ? `${statusText} · ${String(source.error).slice(0, 180)}`
      : statusText;
    text.append(name, detail);

    const count = document.createElement("span");
    count.className = "source-count";
    count.textContent = source.status === "ok" ? `${source.accepted || 0} 条` : "";

    row.append(dot, text, count);
    els.sourceList.append(row);
  }
  els.sourcePanel.hidden = false;
  // Keep the testable count in the summary line useful even if run metadata is absent.
  if (!run.sources_total) els.sourceSummary.textContent = `${ok}/${total} 正常`;
}

function createSkeletonCard() {
  const card = document.createElement("article");
  card.className = "card skeleton-card";
  card.setAttribute("aria-hidden", "true");
  for (const className of ["skeleton-line short", "skeleton-line title", "skeleton-line", "skeleton-line medium"]) {
    const line = document.createElement("div");
    line.className = className;
    card.append(line);
  }
  return card;
}

function renderLoading() {
  els.feed.setAttribute("aria-busy", "true");
  els.feed.replaceChildren(createSkeletonCard(), createSkeletonCard(), createSkeletonCard());
  els.empty.hidden = true;
  els.loadMoreWrap.hidden = true;
  els.resultMeta.textContent = "正在整理信息流…";
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

function resetAndShowAll() {
  state.filter = "latest";
  state.query = "";
  state.favoritesOnly = false;
  state.visible = PAGE_SIZE;
  els.searchInput.value = "";
  els.clearSearch.hidden = true;
  els.favToggle.setAttribute("aria-pressed", "false");
  syncTabs();
  renderFeed();
}

function renderEmptyState(items) {
  if (state.error) {
    renderEmpty(
      "雷达暂时失联",
      "没有加载到 data/feed.json。若页面刚部署，请确认 Pages 已生成数据文件；也可以稍后重试。",
      "重新加载",
      () => loadFeed(true)
    );
    return;
  }
  if (!state.feed) {
    renderEmpty("还没有信号", "数据文件尚未准备好，稍后再来看看。", null, null);
    return;
  }
  if (!state.feed.items.length) {
    renderEmpty(
      "雷达还没有收到内容",
      "首次自动采集可能尚未完成；若数据源暂时不可用，页面会保留空状态而不是伪造热点。",
      "重新加载",
      () => loadFeed(true)
    );
    return;
  }
  if (state.favoritesOnly) {
    renderEmpty(
      "收藏夹还是空的",
      "在任意卡片右上角点书签，内容会保存在这台手机的浏览器里。",
      "回到信息流",
      () => {
        state.favoritesOnly = false;
        els.favToggle.setAttribute("aria-pressed", "false");
        state.visible = PAGE_SIZE;
        renderFeed();
      }
    );
    return;
  }
  if (state.query) {
    renderEmpty(
      "没有找到匹配内容",
      `当前分类里没有「${state.query}」。可以试试在全部内容中搜索，或换一个关键词。`,
      "搜索全部内容",
      resetAndShowAll
    );
    return;
  }
  if (state.filter === "meme") {
    renderEmpty(
      "今天还没有新的热梗",
      "本次采集没有发现符合关键词的新热梗。可以先去「综合热点」或「最新更新」看看。",
      "查看最新更新",
      () => {
        state.filter = "latest";
        state.visible = PAGE_SIZE;
        syncTabs();
        renderFeed();
      }
    );
    return;
  }
  renderEmpty(
    "这个分类还没有内容",
    "本次采集没有拿到这一类的数据，自动任务会在下一次运行时重试。",
    "查看最新更新",
    resetAndShowAll
  );
}

function createCard(item, index) {
  const card = els.template.content.firstElementChild.cloneNode(true);
  card.dataset.category = item.category || "hot";
  card.dataset.stale = item.source_stale ? "true" : "false";
  card.style.setProperty("--i", String(Math.min(index, 12)));

  $(".cat-badge", card).textContent = CATEGORY_LABELS[item.category] || "热点";

  const link = $(".card-link", card);
  link.href = item.url;
  link.setAttribute("aria-label", `${item.title}，在新标签页打开原文`);

  $(".card-title", card).textContent = item.title;
  const summary = $(".card-summary", card);
  summary.textContent = item.summary || "";

  const thumb = $(".card-thumb", card);
  if (item.image && (item.source_kind === "video" || item.source_kind === "article")) {
    thumb.src = item.image;
    thumb.alt = "";
    thumb.hidden = false;
    thumb.addEventListener("error", () => {
      thumb.hidden = true;
    });
  }

  const context = $(".card-context", card);
  if (item.context) {
    context.hidden = false;
    context.append(document.createTextNode("在「"));
    if (item.context_url) {
      const contextLink = document.createElement("a");
      contextLink.href = item.context_url;
      contextLink.target = "_blank";
      contextLink.rel = "noopener noreferrer nofollow";
      contextLink.textContent = item.context;
      context.append(contextLink);
    } else {
      context.append(document.createTextNode(item.context));
    }
    context.append(document.createTextNode("」下"));
  }

  const related = $(".card-related", card);
  if (item.group_size > 1 && Array.isArray(item.related) && item.related.length) {
    related.hidden = false;
    const label = document.createElement("span");
    label.className = "related-label";
    label.textContent = `同一事件还有 ${item.group_size - 1} 条相关来源`;
    related.append(label);
    item.related.slice(0, 4).forEach((entry) => {
      const anchor = document.createElement("a");
      anchor.className = "related-link";
      anchor.href = entry.url;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer nofollow";
      anchor.textContent = `${entry.source_name}：${String(entry.title || "").slice(0, 36)}`;
      related.append(anchor);
    });
  }

  $(".source-name", card).textContent = item.source_name || "未知来源";
  $(".item-time", card).textContent = formatItemTime(item);

  const heat = $(".heat-pill", card);
  const heatText = itemHeatText(item);
  if (heatText) {
    heat.textContent = heatText;
    heat.hidden = false;
  }

  if (item.source_stale) {
    const stale = document.createElement("span");
    stale.className = "stale-tag";
    stale.textContent = "上次数据";
    $(".card-meta", card).insertBefore(stale, heat);
  }

  const bookmark = $(".bookmark", card);
  bookmark.dataset.id = item.id;
  bookmark.setAttribute("aria-pressed", String(state.favorites.has(item.id)));
  bookmark.setAttribute("aria-label", state.favorites.has(item.id) ? "取消收藏" : "收藏");

  return card;
}

function updateResultMeta(items) {
  const shown = Math.min(items.length, state.visible);
  const bits = [];
  if (state.favoritesOnly) bits.push(`收藏 ${items.length} 条`);
  else if (state.query) bits.push(`匹配 ${items.length} 条`);
  else bits.push(`本类 ${items.length} 条`);
  if (items.length > shown) bits.push(`当前显示 ${shown} 条`);
  if (state.sort === "rank") bits.push("按来源榜位");
  els.resultMeta.textContent = bits.join(" · ");
  els.rankHint.hidden = state.sort !== "rank";
}

function renderFeed() {
  const items = filteredItems();
  els.feed.replaceChildren();
  els.feed.setAttribute("aria-busy", "false");
  els.empty.hidden = true;
  els.loadMoreWrap.hidden = true;
  updateResultMeta(items);

  if (state.error || !state.feed || !items.length) {
    renderEmptyState(items);
    return;
  }

  const fragment = document.createDocumentFragment();
  items.slice(0, state.visible).forEach((item, index) => {
    fragment.append(createCard(item, index));
  });
  els.feed.append(fragment);
  updateBookmarkButtons();
  els.loadMoreWrap.hidden = state.visible >= items.length;
}

function syncTabs() {
  $$(".tab").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.filter === state.filter));
  });
  $$(".sort-btn").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.sort === state.sort));
  });
  els.favToggle.setAttribute("aria-pressed", String(state.favoritesOnly));
}

function renderAll() {
  renderHero();
  renderNotice();
  renderSourcePanel();
  syncTabs();
  renderFeed();
}

function readCache() {
  const raw = safeStorageGet(CACHE_KEY);
  if (!raw) return null;
  try {
    const cached = JSON.parse(raw);
    if (!cached || !Array.isArray(cached.items)) return null;
    return cached;
  } catch (_error) {
    return null;
  }
}

async function loadFeed(force = false) {
  state.loading = true;
  state.error = null;
  renderLoading();
  renderHero();
  hideNotice();
  try {
    const response = await fetch(`${FEED_URL}?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data || !Array.isArray(data.items)) throw new Error("data/feed.json 格式不正确");
    state.feed = data;
    state.fromCache = false;
    state.loading = false;
    state.visible = PAGE_SIZE;
    safeStorageSet(CACHE_KEY, JSON.stringify(data));
    renderAll();
  } catch (error) {
    const cached = readCache();
    if (cached) {
      state.feed = cached;
      state.fromCache = true;
      state.loading = false;
      state.visible = PAGE_SIZE;
      renderAll();
    } else {
      state.feed = null;
      state.fromCache = false;
      state.loading = false;
      const message = error instanceof Error ? error.message : String(error);
      state.error = new Error(message === "Failed to fetch" ? "网络请求失败" : message);
      renderAll();
    }
  }
  if (force && state.fromCache) showToast("仍无法连接，继续显示本机缓存");
}

function showToast(message) {
  window.clearTimeout(state.toastTimer);
  els.toast.textContent = message;
  els.toast.classList.add("is-visible");
  state.toastTimer = window.setTimeout(() => {
    els.toast.classList.remove("is-visible");
  }, 1900);
}

function bindEvents() {
  els.themeToggle.addEventListener("click", cycleTheme);
  els.favToggle.addEventListener("click", () => {
    state.favoritesOnly = !state.favoritesOnly;
    state.visible = PAGE_SIZE;
    els.favToggle.setAttribute("aria-pressed", String(state.favoritesOnly));
    renderFeed();
    showToast(state.favoritesOnly ? `只看收藏（${state.favorites.size}）` : "已回到信息流");
  });

  $(".tabs").addEventListener("click", (event) => {
    const tab = event.target.closest(".tab");
    if (!tab) return;
    state.filter = tab.dataset.filter || "latest";
    state.favoritesOnly = false;
    state.visible = PAGE_SIZE;
    els.favToggle.setAttribute("aria-pressed", "false");
    syncTabs();
    renderFeed();
  });

  $$(".sort-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.sort = button.dataset.sort || "latest";
      state.visible = PAGE_SIZE;
      syncTabs();
      renderFeed();
    });
  });

  els.searchInput.addEventListener("input", () => {
    const value = els.searchInput.value;
    els.clearSearch.hidden = !value;
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      state.query = value.trim();
      state.visible = PAGE_SIZE;
      renderFeed();
    }, 120);
  });

  els.clearSearch.addEventListener("click", () => {
    els.searchInput.value = "";
    els.clearSearch.hidden = true;
    state.query = "";
    state.visible = PAGE_SIZE;
    renderFeed();
    els.searchInput.focus();
  });

  els.feed.addEventListener("click", (event) => {
    const button = event.target.closest(".bookmark");
    if (!button) return;
    event.preventDefault();
    toggleFavorite(button.dataset.id);
  });

  els.loadMore.addEventListener("click", () => {
    state.visible += PAGE_SIZE;
    renderFeed();
  });

  els.sourcePanel.addEventListener("click", () => {
    // Native details interaction is enough; this keeps the disclosure keyboard-friendly.
  });

  window.addEventListener("storage", (event) => {
    if (event.key === FAV_KEY) {
      loadFavorites();
      saveFavorites();
      renderFeed();
    }
  });
}

function init() {
  initTheme();
  loadFavorites();
  saveFavorites();
  bindEvents();
  loadFeed();
}

init();
