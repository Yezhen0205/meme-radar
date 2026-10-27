"use strict";

const TZ = "Asia/Shanghai";
const GALLERY_URL = "data/gallery.json";
const TEXT_URL = "data/text.json";
const GALLERY_CACHE = "memeRadar:gallery:feed:v2";
const TEXT_CACHE = "memeRadar:text:feed:v1";
const FAV_KEY = "memeRadar:gallery:favorites:v1";
const SEEN_KEY = "memeRadar:gallery:seen:v1";
const THEME_KEY = "memeRadar:gallery:theme:v1";
const PAGE_SIZE = 24;
const THEMES = ["auto", "light", "dark"];
const THEME_LABELS = { auto: "跟随系统", light: "浅色", dark: "深色" };
const CATEGORY_LABELS = {
  discover: "综合发现",
  image: "梗图",
  meme: "热梗",
  abstract: "抽象段子",
  reply: "神回复",
  comment: "评论金句",
  hot: "热点",
};
const TEXT_CATEGORY_LABELS = {
  meme: "热梗",
  abstract: "抽象段子",
  reply: "神回复",
  comment: "评论金句",
  hot: "热点",
};
const SOURCE_GROUPS = {
  reddit: "Reddit",
  tieba: "贴吧",
  bilibili: "B站",
  weibo: "微博",
  baidu: "百度",
  toutiao: "头条",
  douyin: "抖音",
  zhihu: "知乎",
};
const TEXT_SOURCE_GROUPS = {
  bilibili: "bilibili",
  bilibili_comments: "bilibili",
  weibo_hot: "weibo",
  baidu_hot: "baidu",
  tieba_hot: "tieba",
  toutiao_hot: "toutiao",
  douyin_hot: "douyin",
  zhihu_daily: "zhihu",
};
const AUTH_LABELS = { real: "真实采集", rewrite: "原创改写", ai: "AI 原创" };
const KNOWN_UNAVAILABLE = [
  { name: "知乎热榜", status: "blocked", detail: "HTTP 401（2026-10-27 实测；不绕过登录）" },
  { name: "煎蛋 RSS", status: "blocked", detail: "HTTP 403（2026-10-27 实测）" },
  { name: "V2EX 热门", status: "blocked", detail: "连接超时（2026-10-27 实测，已停止重试）" },
];

const state = {
  galleryFeed: null,
  textFeed: null,
  items: [],
  category: "discover",
  type: "all",
  source: "all",
  mode: "latest",
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
  error: null,
  fromCacheGallery: false,
  fromCacheText: false,
  imageFailures: new Set(),
  currentItem: null,
  toastTimer: 0,
  searchTimer: 0,
  deferredPrompt: null,
  loadErrors: {},
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
  authLine: $("#authLine"),
  statusPill: $("#statusPill"),
  heroMeta: $("#heroMeta"),
  statTotal: $("#statTotal"),
  statImages: $("#statImages"),
  statText: $("#statText"),
  categoryTabs: $("#categoryTabs"),
  typeFilters: $("#typeFilters"),
  sourceFilters: $("#sourceFilters"),
  countTypeAll: $("#countTypeAll"),
  countTypeImage: $("#countTypeImage"),
  countTypeText: $("#countTypeText"),
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
  textModal: $("#textModal"),
  textClose: $("#textClose"),
  textBadges: $("#textBadges"),
  textModalTitle: $("#textModalTitle"),
  textBody: $("#textBody"),
  textContext: $("#textContext"),
  textTags: $("#textTags"),
  textStats: $("#textStats"),
  textCopy: $("#textCopy"),
  textFav: $("#textFav"),
  textSeen: $("#textSeen"),
  textPost: $("#textPost"),
  toast: $("#toast"),
  imageTemplate: $("#imageCardTemplate"),
  textTemplate: $("#textCardTemplate"),
};

function safeGet(key) {
  try { return window.localStorage.getItem(key); } catch (_error) { return null; }
}

function safeSet(key, value) {
  try { window.localStorage.setItem(key, value); } catch (_error) { /* private mode */ }
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
  updateFilterButtons();
}

function updateFilterButtons() {
  if (els.favCount) els.favCount.textContent = String(state.favorites.size);
  if (els.favOnly) els.favOnly.setAttribute("aria-pressed", String(state.favoritesOnly));
  if (els.hideSeen) els.hideSeen.setAttribute("aria-pressed", String(state.hideSeen));
}

function migrateLocalIds() {
  const imageIds = new Set(state.items.filter((item) => item.kind === "image").map((item) => item.id));
  let changed = false;
  for (const value of Array.from(state.favorites)) {
    if (imageIds.has(value)) {
      state.favorites.delete(value);
      state.favorites.add(`image:${value}`);
      changed = true;
    }
  }
  for (const value of Array.from(state.seen)) {
    if (imageIds.has(value)) {
      state.seen.delete(value);
      state.seen.add(`image:${value}`);
      changed = true;
    }
  }
  if (changed) {
    saveSet(FAV_KEY, state.favorites);
    saveSet(SEEN_KEY, state.seen);
  }
  updateFilterButtons();
}

function toggleFavorite(uid) {
  if (!uid) return;
  const active = state.favorites.has(uid);
  if (active) state.favorites.delete(uid);
  else state.favorites.add(uid);
  saveSet(FAV_KEY, state.favorites);
  updateFilterButtons();
  updateCardState(uid);
  if (state.currentItem?.uid === uid) {
    if (state.currentItem.kind === "image") syncImageFavorite();
    else syncTextFavorite();
  }
  showToast(active ? "已取消收藏" : "已收藏，仅保存在这台设备");
  if (state.favoritesOnly && active) renderGrid();
}

function markSeen(uid, silent = false) {
  if (!uid || state.seen.has(uid)) return;
  state.seen.add(uid);
  saveSet(SEEN_KEY, state.seen);
  updateCardState(uid);
  if (!silent) showToast("已标记为已看");
}

function updateCardState(uid) {
  const card = $(`.card[data-uid="${cssEscape(uid)}"]`, els.grid);
  if (!card) return;
  const fav = state.favorites.has(uid);
  const seen = state.seen.has(uid);
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
  return String(value || "").normalize("NFKC").toLocaleLowerCase("zh-CN").replace(/\s+/g, "");
}

function sourceGroupForText(sourceId) {
  return TEXT_SOURCE_GROUPS[sourceId] || "other";
}

function normalizeGalleryItem(item) {
  const sourceGroup = item.source || "other";
  const tags = Array.isArray(item.tags) ? item.tags : [];
  return {
    raw: item,
    kind: "image",
    id: item.id,
    uid: `image:${item.id}`,
    title: item.title || "",
    body: item.summary || "",
    context: item.context || "",
    contextUrl: item.context_url || "",
    postUrl: item.post_url || "",
    imageUrl: item.image_url || "",
    thumbUrl: item.thumbnail_url || item.image_url || "",
    imageStatus: item.image_status || "unchecked",
    imageWidth: item.image_width || null,
    imageHeight: item.image_height || null,
    createdAt: item.created_at || null,
    collectedAt: item.collected_at || null,
    category: "image",
    categoryLabel: "梗图",
    sourceGroup,
    sourceName: item.source_name || SOURCE_GROUPS[sourceGroup] || sourceGroup,
    community: item.community || "",
    heat: item.heat || null,
    comments: item.comment_count,
    score: item.score,
    tags,
    authenticity: item.authenticity || "real",
    rankScore: Number(item.rank_score) || 0,
    related: item.related || [],
    groupSize: item.group_size || 1,
    rankBasis: item.rank_basis || "recency",
    searchBlob: normalize([item.title, item.summary, item.community, item.source_name, ...tags].filter(Boolean).join(" ")),
  };
}

function rankText(item) {
  const heatValue = item.heat?.value;
  const heatScore = typeof heatValue === "number" ? Math.min(48, Math.log10(heatValue + 1) * 12) : 0;
  const date = Date.parse(item.published_at || item.collected_at || "") || Date.now();
  const age = Math.max(0, (Date.now() - date) / 3600000);
  const recency = Math.max(0, 100 - (age / 168) * 100);
  const categoryBoost = ["reply", "comment", "abstract"].includes(item.category) ? 6 : 0;
  return Math.round((recency + heatScore + categoryBoost) * 10) / 10;
}

function normalizeTextItem(item) {
  const category = TEXT_CATEGORY_LABELS[item.category] ? item.category : "hot";
  const sourceGroup = sourceGroupForText(item.source_id);
  const tags = Array.isArray(item.tags) ? item.tags : [];
  return {
    raw: item,
    kind: "text",
    id: item.id,
    uid: `text:${item.id}`,
    title: item.title || "",
    body: item.summary || "",
    context: item.context || "",
    contextUrl: item.context_url || "",
    postUrl: item.url || "",
    imageUrl: "",
    thumbUrl: "",
    imageStatus: null,
    createdAt: item.published_at || null,
    collectedAt: item.collected_at || null,
    category,
    categoryLabel: TEXT_CATEGORY_LABELS[category] || "热点",
    sourceGroup,
    sourceName: item.source_name || SOURCE_GROUPS[sourceGroup] || sourceGroup,
    community: item.context ? "评论区" : "",
    heat: item.heat || null,
    comments: null,
    score: null,
    tags,
    authenticity: item.authenticity || "real",
    rankScore: rankText(item),
    related: item.related || [],
    groupSize: item.group_size || 1,
    rankBasis: "recency+source-metric",
    searchBlob: normalize([item.title, item.summary, item.context, item.source_name, ...tags].filter(Boolean).join(" ")),
  };
}

function allItems() {
  return state.items;
}

function counts() {
  const images = state.items.filter((item) => item.kind === "image").length;
  const text = state.items.filter((item) => item.kind === "text").length;
  const byCategory = { discover: state.items.length, image: 0, meme: 0, abstract: 0, reply: 0, comment: 0, hot: 0 };
  const bySource = {};
  for (const item of state.items) {
    byCategory[item.category] = (byCategory[item.category] || 0) + 1;
    bySource[item.sourceGroup] = (bySource[item.sourceGroup] || 0) + 1;
  }
  return {
    all: state.items.length,
    image: images,
    text,
    byCategory,
    bySource,
    authenticity: {
      real: state.items.filter((item) => item.authenticity === "real").length,
      rewrite: state.items.filter((item) => item.authenticity === "rewrite").length,
      ai: state.items.filter((item) => item.authenticity === "ai").length,
    },
  };
}

function timestamp(item) {
  return Date.parse(item.createdAt || item.collectedAt || "") || 0;
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
  if (state.category === "image") items = items.filter((item) => item.kind === "image");
  else if (state.category !== "discover") {
    items = items.filter((item) => item.kind === "text" && item.category === state.category);
  }
  if (state.category === "discover" && state.type !== "all") {
    items = items.filter((item) => item.kind === state.type);
  }
  if (state.source !== "all") items = items.filter((item) => item.sourceGroup === state.source);
  if (state.favoritesOnly) items = items.filter((item) => state.favorites.has(item.uid));
  if (state.hideSeen) items = items.filter((item) => !state.seen.has(item.uid));
  const query = normalize(state.query);
  if (query) items = items.filter((item) => item.searchBlob.includes(query));
  if (state.tag) {
    const tag = normalize(state.tag);
    items = items.filter(
      (item) => item.tags.some((value) => normalize(value) === tag) || item.searchBlob.includes(tag)
    );
  }
  if (state.mode === "hot") {
    items.sort((a, b) => (b.rankScore || 0) - (a.rankScore || 0) || timestamp(b) - timestamp(a));
  } else if (state.mode === "random") {
    items.sort((a, b) => hashString(`${a.uid}:${state.randomSeed}`) - hashString(`${b.uid}:${state.randomSeed}`));
  } else {
    items.sort((a, b) => timestamp(b) - timestamp(a) || (b.rankScore || 0) - (a.rankScore || 0));
  }
  if (state.category === "discover" && state.type === "all") {
    items = interleaveKinds(items);
  }
  return items;
}

function interleaveKinds(items) {
  const images = items.filter((item) => item.kind === "image");
  const texts = items.filter((item) => item.kind === "text");
  if (!images.length || !texts.length) return items;
  const result = [];
  let imageIndex = 0;
  let textIndex = 0;
  let next = (timestamp(images[0]) || 0) >= (timestamp(texts[0]) || 0) ? "image" : "text";
  while (imageIndex < images.length || textIndex < texts.length) {
    if (next === "image" && imageIndex < images.length) {
      result.push(images[imageIndex]);
      imageIndex += 1;
      next = "text";
    } else if (next === "text" && textIndex < texts.length) {
      result.push(texts[textIndex]);
      textIndex += 1;
      next = "image";
    } else if (imageIndex < images.length) {
      result.push(images[imageIndex]);
      imageIndex += 1;
    } else if (textIndex < texts.length) {
      result.push(texts[textIndex]);
      textIndex += 1;
    }
  }
  return result;
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
  const parts = Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
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
  const value = Date.parse(iso || "");
  if (!Number.isFinite(value)) return "时间未知";
  const minutes = Math.max(0, Math.floor((Date.now() - value) / 60000));
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

function setStatus(text, kind) {
  els.statusPill.textContent = text;
  els.statusPill.className = `status-pill ${kind || ""}`.trim();
}

function renderHero() {
  const values = counts();
  els.statTotal.textContent = state.items.length ? String(values.all) : "—";
  els.statImages.textContent = state.items.length ? String(values.image) : "—";
  els.statText.textContent = state.items.length ? String(values.text) : "—";
  els.countTypeAll.textContent = String(values.all);
  els.countTypeImage.textContent = String(values.image);
  els.countTypeText.textContent = String(values.text);
  const updated = latestGeneratedAt();
  if (state.loading) {
    setStatus("连接中", "is-loading");
    els.heroMeta.textContent = "正在接收图片与文字内容…";
    return;
  }
  if (state.error) {
    setStatus("连接失败", "is-error");
    els.heroMeta.textContent = "两类数据都没有加载成功，请稍后重试。";
    els.authLine.hidden = true;
    return;
  }
  const bits = [
    updated ? `更新 ${formatAge(updated)}` : "等待首次采集",
    `${values.image} 张图 · ${values.text} 条文字`,
    `${Object.keys(values.bySource).length} 个来源`,
  ];
  if (state.fromCacheGallery || state.fromCacheText) bits.push("缓存");
  els.heroMeta.textContent = bits.join(" · ");
  els.authLine.hidden = false;
  els.authLine.textContent = `真实性：真实采集 ${values.authenticity.real} · 原创改写 ${values.authenticity.rewrite} · AI 原创 ${values.authenticity.ai}`;
  const textFailed = state.textFeed?.run?.sources_failed || 0;
  const galleryHealth = state.galleryFeed?.health?.status;
  if (state.loadErrors.gallery || state.loadErrors.text) setStatus("部分加载", "is-warn");
  else if (state.galleryFeed?.stale || state.textFeed?.stale) setStatus("数据过期", "is-warn");
  else if (galleryHealth === "blocked") setStatus("来源中断", "is-error");
  else if (galleryHealth === "degraded" || textFailed || state.textFeed?.run?.partial) setStatus("部分降级", "is-warn");
  else if (state.fromCacheGallery || state.fromCacheText) setStatus("缓存阅读", "is-warn");
  else setStatus("已更新", "is-live");
}

function latestGeneratedAt() {
  const values = [state.galleryFeed?.generated_at, state.textFeed?.generated_at].filter(Boolean).map((value) => Date.parse(value)).filter(Number.isFinite);
  if (!values.length) return null;
  return new Date(Math.max(...values)).toISOString();
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
    showBanner(`加载失败：${state.error.message || "网络错误"}。图片与文字数据都不可用。`, "is-error", "重新加载", () => loadAll(true));
    return;
  }
  const messages = [];
  let kind = "is-warn";
  if (state.loadErrors.gallery) messages.push("图片数据加载失败，正在显示可用的文字/缓存内容。");
  if (state.loadErrors.text) messages.push("文字数据加载失败，正在显示可用的图片/缓存内容。");
  if (state.fromCacheGallery || state.fromCacheText) messages.push("部分内容来自本机上次缓存。");
  if (state.galleryFeed?.stale) messages.push("图片图库本轮全部失败，已保留上次成功数据。");
  const galleryHealth = state.galleryFeed?.health?.status;
  if (galleryHealth === "degraded") messages.push("图片来源有降级：贴吧详情页 403，使用公开热点页。");
  if (galleryHealth === "blocked") { messages.push("图片主要来源中断。"); kind = "is-error"; }
  if (state.textFeed?.stale) messages.push("文字采集本轮失败，已保留上次成功数据。");
  if (state.textFeed?.run?.sources_failed) messages.push(`文字来源 ${state.textFeed.run.sources_failed} 个失败。`);
  if (messages.length) showBanner(messages.join(" "), kind, "数据源详情", openHealth);
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

function markImageFailure(uid) {
  if (!uid) return;
  state.imageFailures.add(uid);
  renderImageNote();
}

function renderCategoryCounts() {
  const values = counts();
  $$(".cat-btn", els.categoryTabs).forEach((button) => {
    const category = button.dataset.category;
    const count = values.byCategory[category] || 0;
    button.querySelector("span").textContent = String(count);
    button.setAttribute("aria-selected", String(state.category === category));
  });
}

function renderTypeFilters() {
  $$(".filter-btn", els.typeFilters).forEach((button) => {
    button.setAttribute("aria-pressed", String(state.type === button.dataset.type));
    button.disabled = state.category !== "discover";
    button.title = state.category !== "discover" ? "类型由当前分类自动决定" : "";
  });
}

function sourceOptions() {
  const values = counts().bySource;
  const keys = Object.keys(values).sort((a, b) => {
    const order = ["reddit", "tieba", "bilibili", "weibo", "baidu", "toutiao", "douyin", "zhihu", "other"];
    return order.indexOf(a) - order.indexOf(b);
  });
  return [{ key: "all", label: "全部来源", count: state.items.length }, ...keys.map((key) => ({
    key,
    label: SOURCE_GROUPS[key] || key,
    count: values[key] || 0,
  }))];
}

function renderSourceFilters() {
  els.sourceFilters.replaceChildren();
  for (const option of sourceOptions()) {
    const button = document.createElement("button");
    button.className = "filter-btn";
    button.type = "button";
    button.dataset.source = option.key;
    button.setAttribute("aria-pressed", String(state.source === option.key));
    button.append(document.createTextNode(`${option.label} `));
    const count = document.createElement("span");
    count.textContent = String(option.count);
    button.append(count);
    button.addEventListener("click", () => {
      state.source = option.key;
      state.visible = PAGE_SIZE;
      renderSourceFilters();
      renderGrid();
    });
    els.sourceFilters.append(button);
  }
}

function renderTrendChips() {
  const keywords = state.galleryFeed?.trends?.keywords || [];
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
      renderTrendChips();
      renderGrid();
    });
    els.trendChips.append(button);
  }
}

function combinedSources() {
  const rows = [];
  for (const source of state.galleryFeed?.sources || []) {
    if (source.source === "trends") continue;
    rows.push({
      name: source.name || SOURCE_GROUPS[source.source] || source.source,
      status: source.status || "unknown",
      count: source.item_count || 0,
      error: source.error || "",
      section: "图片",
    });
  }
  for (const source of state.textFeed?.sources || []) {
    rows.push({
      name: source.name || source.id,
      status: source.status || "unknown",
      count: source.accepted || 0,
      error: source.error || "",
      section: "文字",
    });
  }
  return rows;
}

function renderHealth() {
  const rows = combinedSources();
  if (!rows.length) {
    els.healthPanel.hidden = true;
    return;
  }
  const statusLabel = { ok: "正常", degraded: "降级", blocked: "失败", failed: "失败", skipped: "跳过", planned: "计划中", disabled: "未启用" };
  const galleryHealth = state.galleryFeed?.health?.status;
  const textFailed = state.textFeed?.run?.sources_failed || 0;
  const overall = state.error ? "blocked" : galleryHealth === "blocked" ? "degraded" : galleryHealth === "degraded" || textFailed ? "degraded" : "ok";
  els.healthSummary.textContent = `${statusLabel[overall] || overall} · ${latestGeneratedAt() ? formatWhen(latestGeneratedAt()) : "尚未成功"}`;
  els.healthList.replaceChildren();
  for (const source of rows) {
    const row = document.createElement("div");
    row.className = "health-row";
    const dot = document.createElement("span");
    dot.className = `health-dot ${source.status}`;
    dot.setAttribute("aria-hidden", "true");
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = `${source.section} · ${source.name}`;
    const detail = document.createElement("small");
    detail.textContent = [statusLabel[source.status] || source.status, source.error].filter(Boolean).join(" · ");
    copy.append(name, detail);
    const count = document.createElement("span");
    count.className = "health-count";
    count.textContent = source.count ? `${source.count} 条` : "";
    row.append(dot, copy, count);
    els.healthList.append(row);
  }
  for (const source of KNOWN_UNAVAILABLE) {
    const row = document.createElement("div");
    row.className = "health-row";
    const dot = document.createElement("span");
    dot.className = "health-dot blocked";
    dot.setAttribute("aria-hidden", "true");
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = `文字 · ${source.name}`;
    const detail = document.createElement("small");
    detail.textContent = source.detail;
    copy.append(name, detail);
    row.append(dot, copy);
    els.healthList.append(row);
  }
  els.healthPanel.hidden = false;
}

function renderFilterState() {
  $$(".mode-btn").forEach((button) => button.setAttribute("aria-selected", String(state.mode === button.dataset.mode)));
  renderCategoryCounts();
  renderTypeFilters();
  renderSourceFilters();
  els.favOnly.setAttribute("aria-pressed", String(state.favoritesOnly));
  els.hideSeen.setAttribute("aria-pressed", String(state.hideSeen));
  els.shuffleBtn.hidden = state.mode !== "random";
  els.clearSearch.hidden = !els.searchInput.value;
}

function createBadge(text, className) {
  const span = document.createElement("span");
  span.className = className;
  span.textContent = text;
  return span;
}

function makeActions(item) {
  const actions = document.createElement("div");
  actions.className = "text-actions";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "copy-btn";
  copy.textContent = "复制";
  copy.addEventListener("click", (event) => {
    event.stopPropagation();
    copyItem(item);
  });
  const original = document.createElement("a");
  original.className = "original-link";
  original.href = item.postUrl;
  original.target = "_blank";
  original.rel = "noopener noreferrer nofollow";
  original.textContent = "原帖 ↗";
  original.addEventListener("click", (event) => event.stopPropagation());
  actions.append(copy, original);
  return actions;
}

function createImageCard(item, index) {
  const card = els.imageTemplate.content.firstElementChild.cloneNode(true);
  card.dataset.uid = item.uid;
  card.dataset.kind = "image";
  card.classList.toggle("is-favorite", state.favorites.has(item.uid));
  card.classList.toggle("is-seen", state.seen.has(item.uid));
  card.style.setProperty("--i", String(Math.min(index, 12)));
  const badges = $(".card-badges", card);
  const source = $(".source-pill", card);
  source.textContent = item.sourceName;
  source.dataset.source = item.sourceGroup;
  const related = $(".related-pill", card);
  if (item.groupSize > 1) {
    related.hidden = false;
    related.textContent = `同图 +${item.groupSize - 1}`;
  }
  const image = $(".card-media img", card);
  image.alt = item.title;
  image.loading = "lazy";
  image.decoding = "async";
  image.referrerPolicy = "no-referrer";
  if (item.imageWidth && item.imageHeight) {
    image.width = item.imageWidth;
    image.height = item.imageHeight;
    image.style.aspectRatio = `${item.imageWidth} / ${item.imageHeight}`;
  }
  image.src = item.thumbUrl || item.imageUrl;
  image.addEventListener("error", () => {
    image.hidden = true;
    const fallback = $(".media-fallback", card);
    fallback.hidden = false;
    $("a", fallback).href = item.postUrl;
    markImageFailure(item.uid);
  });
  $(".card-title", card).textContent = item.title;
  const summary = $(".card-summary", card);
  summary.textContent = item.body || "";
  $(".community", card).textContent = item.community || item.sourceName;
  $(".time", card).textContent = item.createdAt ? formatWhen(item.createdAt) : `收录 ${formatWhen(item.collectedAt)}`;
  const comments = $(".comments", card);
  if (typeof item.comments === "number") comments.textContent = `${formatNumber(item.comments)} 评论`;
  else if (item.heat?.display) comments.textContent = `${item.heat.label} ${item.heat.display}`;
  else comments.hidden = true;
  const tags = $(".card-tags", card);
  item.tags.filter((tag) => !["reddit", "贴吧", item.community].includes(tag)).slice(0, 3).forEach((tag) => {
    tags.append(createBadge(tag, "tag"));
  });
  const fav = $(".fav-btn", card);
  fav.setAttribute("aria-pressed", String(state.favorites.has(item.uid)));
  fav.setAttribute("aria-label", state.favorites.has(item.uid) ? "取消收藏" : "收藏");
  fav.addEventListener("click", (event) => { event.stopPropagation(); toggleFavorite(item.uid); });
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `${item.title}，打开大图和原帖`);
  card.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) return;
    openImage(item);
  });
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openImage(item); }
  });
  return card;
}

function createTextCard(item, index) {
  const card = els.textTemplate.content.firstElementChild.cloneNode(true);
  card.dataset.uid = item.uid;
  card.dataset.kind = "text";
  card.dataset.category = item.category;
  card.classList.toggle("is-favorite", state.favorites.has(item.uid));
  card.classList.toggle("is-seen", state.seen.has(item.uid));
  card.style.setProperty("--i", String(Math.min(index, 12)));
  const badges = $(".badge-row", card);
  badges.append(createBadge(item.categoryLabel, "cat-pill"), createBadge(AUTH_LABELS[item.authenticity] || "真实采集", "auth-pill"));
  $(".text-title", card).textContent = item.title;
  const body = $(".text-body", card);
  body.textContent = item.body && item.body !== item.title ? item.body : "";
  if (!body.textContent) body.hidden = true;
  const context = $(".text-context", card);
  if (item.context) {
    context.hidden = false;
    context.textContent = `在「${item.context}」下`;
  }
  $(".source-name", card).textContent = item.sourceName;
  $(".time", card).textContent = item.createdAt ? formatWhen(item.createdAt) : `收录 ${formatWhen(item.collectedAt)}`;
  const comments = $(".comments", card);
  if (item.heat?.display) comments.textContent = `${item.heat.label} ${item.heat.display}`;
  else if (item.category === "reply" || item.category === "comment") comments.textContent = "评论区";
  else comments.hidden = true;
  const tags = $(".card-tags", card);
  item.tags.filter((tag) => !["热梗", "搞笑", "贴吧", item.context].includes(tag)).slice(0, 3).forEach((tag) => {
    tags.append(createBadge(tag, "tag"));
  });
  const fav = $(".text-fav", card);
  fav.setAttribute("aria-pressed", String(state.favorites.has(item.uid)));
  fav.setAttribute("aria-label", state.favorites.has(item.uid) ? "取消收藏" : "收藏");
  fav.addEventListener("click", (event) => { event.stopPropagation(); toggleFavorite(item.uid); });
  const copy = $(".copy-btn", card);
  copy.addEventListener("click", (event) => {
    event.stopPropagation();
    copyItem(item);
  });
  const original = $(".original-link", card);
  original.href = item.postUrl;
  original.addEventListener("click", (event) => event.stopPropagation());
  if (item.groupSize > 1) {
    const related = document.createElement("span");
    related.className = "related-small";
    related.textContent = `+${item.groupSize - 1} 条相关`;
    $(".card-meta", card).append(related);
  }
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `${item.title}，打开文字详情`);
  card.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) return;
    openText(item);
  });
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openText(item); }
  });
  return card;
}

function renderEmptyState(items) {
  if (state.error) {
    renderEmpty("页面暂时失联", "图片和文字数据都没有加载成功。请稍后重试。", "重新加载", () => loadAll(true));
    return;
  }
  if (!state.items.length) {
    renderEmpty("还没有可用内容", "首次采集可能尚未完成；没有真实数据时不会显示假内容。", "重新加载", () => loadAll(true));
    return;
  }
  if (state.category !== "discover" && !counts().byCategory[state.category]) {
    const reason = state.category === "abstract"
      ? "本轮真实来源中没有足够明确的抽象段子；不会用普通热点或 AI 文本冒充。"
      : "该分类本轮没有通过校验的真实内容，采集器会在下一次运行重试。";
    renderEmpty(`${CATEGORY_LABELS[state.category]}暂无内容`, reason, "看综合发现", () => {
      state.category = "discover"; state.visible = PAGE_SIZE; renderAll();
    });
    return;
  }
  if (state.favoritesOnly) {
    renderEmpty("收藏夹是空的", "点卡片上的爱心，内容会保存在这台手机上。", "回到内容流", resetFilters);
    return;
  }
  if (items.length === 0) {
    renderEmpty("没有匹配的内容", "当前筛选条件太窄，清除筛选再看看。", "清除筛选", resetFilters);
    return;
  }
  renderEmpty("暂时没有更多内容", "本轮没有新增内容，稍后会自动重试。", "重新加载", () => loadAll(true));
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
  state.type = "all";
  state.source = "all";
  state.query = "";
  state.tag = "";
  state.favoritesOnly = false;
  state.hideSeen = false;
  state.visible = PAGE_SIZE;
  els.searchInput.value = "";
  els.clearSearch.hidden = true;
  updateFilterButtons();
  renderTrendChips();
  renderAll();
}

function updateResultMeta(items, shown) {
  const bits = [];
  if (state.favoritesOnly) bits.push(`收藏 ${items.length} 条`);
  else bits.push(`${CATEGORY_LABELS[state.category]} ${items.length} 条`);
  if (state.type !== "all" && state.category === "discover") bits.push(state.type === "image" ? "图片" : "文字");
  if (state.source !== "all") bits.push(SOURCE_GROUPS[state.source] || state.source);
  if (state.query) bits.push(`搜索「${state.query}」`);
  if (state.tag) bits.push(`标签「${state.tag}」`);
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
  if (state.error || !state.items.length || !items.length) {
    updateResultMeta(items, 0);
    renderEmptyState(items);
    return;
  }
  const shown = Math.min(state.visible, items.length);
  updateResultMeta(items, shown);
  const fragment = document.createDocumentFragment();
  items.slice(0, shown).forEach((item, index) => {
    fragment.append(item.kind === "image" ? createImageCard(item, index) : createTextCard(item, index));
  });
  els.grid.append(fragment);
  els.loadMoreWrap.hidden = shown >= items.length;
}

function renderAll() {
  renderHero();
  renderBanner();
  renderImageNote();
  renderCategoryCounts();
  renderHealth();
  renderFilterState();
  renderTrendChips();
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
  els.resultMeta.textContent = "正在整理内容…";
}

function readCache(key) {
  const raw = safeGet(key);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    return value && Array.isArray(value.items) ? value : null;
  } catch (_error) { return null; }
}

async function fetchJson(url) {
  const response = await fetch(`${url}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (!data || !Array.isArray(data.items)) throw new Error(`${url} 格式不正确`);
  return data;
}

async function loadAll(force = false) {
  state.loading = true;
  state.error = null;
  state.loadErrors = {};
  renderLoading();
  renderHero();
  hideBanner();
  const results = await Promise.allSettled([fetchJson(GALLERY_URL), fetchJson(TEXT_URL)]);
  const [galleryResult, textResult] = results;
  if (galleryResult.status === "fulfilled") {
    state.galleryFeed = galleryResult.value;
    state.fromCacheGallery = false;
    safeSet(GALLERY_CACHE, JSON.stringify(galleryResult.value));
  } else {
    state.loadErrors.gallery = galleryResult.reason;
    const cached = readCache(GALLERY_CACHE);
    if (cached) { state.galleryFeed = cached; state.fromCacheGallery = true; }
    else state.galleryFeed = null;
  }
  if (textResult.status === "fulfilled") {
    state.textFeed = textResult.value;
    state.fromCacheText = false;
    safeSet(TEXT_CACHE, JSON.stringify(textResult.value));
  } else {
    state.loadErrors.text = textResult.reason;
    const cached = readCache(TEXT_CACHE);
    if (cached) { state.textFeed = cached; state.fromCacheText = true; }
    else state.textFeed = null;
  }
  if (!state.galleryFeed && !state.textFeed) {
    state.loading = false;
    state.items = [];
    state.error = new Error("图片和文字数据都加载失败");
    renderAll();
    return;
  }
  const images = (state.galleryFeed?.items || []).map(normalizeGalleryItem);
  const texts = (state.textFeed?.items || []).map(normalizeTextItem);
  state.items = [...images, ...texts];
  state.loading = false;
  state.imageFailures.clear();
  migrateLocalIds();
  renderAll();
  if (force && (state.fromCacheGallery || state.fromCacheText)) showToast("仍无法连接，继续显示本机缓存");
}

function openImage(item) {
  state.currentItem = item;
  markSeen(item.uid, true);
  els.lightbox.hidden = false;
  document.body.classList.add("is-locked");
  els.lightboxSource.textContent = item.sourceName;
  els.lightboxSource.dataset.source = item.sourceGroup;
  els.lightboxCommunity.textContent = item.community || "";
  els.lightboxTime.textContent = item.createdAt ? formatWhen(item.createdAt) : `收录 ${formatWhen(item.collectedAt)}`;
  els.lightboxTitle.textContent = item.title;
  els.lightboxSummary.textContent = item.body || "原帖没有额外正文摘要。";
  els.lightboxTags.replaceChildren();
  item.tags.slice(0, 8).forEach((tag) => els.lightboxTags.append(createBadge(tag, "tag")));
  els.lightboxPost.href = item.postUrl;
  els.lightboxFallbackLink.href = item.postUrl;
  els.lightboxFallback.hidden = true;
  els.lightboxImage.hidden = false;
  els.lightboxLoading.hidden = false;
  els.lightboxMedia.classList.remove("is-loaded");
  let triedThumbnail = false;
  els.lightboxImage.onload = () => {
    els.lightboxMedia.classList.add("is-loaded");
    els.lightboxLoading.hidden = true;
  };
  els.lightboxImage.onerror = () => {
    if (!triedThumbnail && item.thumbUrl && item.thumbUrl !== item.imageUrl) {
      triedThumbnail = true;
      els.lightboxImage.src = item.thumbUrl;
      return;
    }
    els.lightboxImage.hidden = true;
    els.lightboxLoading.hidden = true;
    els.lightboxFallback.hidden = false;
    markImageFailure(item.uid);
  };
  els.lightboxImage.src = item.imageUrl;
  els.lightboxImage.alt = item.title;
  const stats = [];
  if (typeof item.comments === "number") stats.push(`评论 ${formatNumber(item.comments)}`);
  if (item.heat?.display) stats.push(`${item.heat.label} ${item.heat.display}`);
  if (!stats.length) stats.push(item.sourceGroup === "reddit" ? "Reddit RSS 未提供互动数" : "来源未提供互动数");
  stats.push(`真实性 ${AUTH_LABELS[item.authenticity] || "真实采集"}`);
  els.lightboxStats.textContent = stats.join(" · ");
  els.lightboxRelated.replaceChildren();
  if (item.groupSize > 1 && item.related.length) {
    els.lightboxRelated.hidden = false;
    els.lightboxRelated.append(document.createTextNode(`同一图片还有 ${item.groupSize - 1} 条相关记录：`));
    item.related.forEach((entry, index) => {
      if (index) els.lightboxRelated.append(document.createTextNode(" · "));
      const link = document.createElement("a");
      link.href = entry.post_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer nofollow";
      link.textContent = `${entry.source_name || entry.source} ${entry.title || ""}`.slice(0, 60);
      els.lightboxRelated.append(link);
    });
  } else {
    els.lightboxRelated.hidden = true;
  }
  syncImageFavorite();
  updateLightboxSeen();
  els.lightboxClose.focus();
}

function openText(item) {
  state.currentItem = item;
  markSeen(item.uid, true);
  els.textModal.hidden = false;
  document.body.classList.add("is-locked");
  els.textBadges.replaceChildren(
    createBadge(item.categoryLabel, "cat-pill"),
    createBadge(AUTH_LABELS[item.authenticity] || "真实采集", "auth-pill"),
    createBadge(item.sourceName, "source-pill")
  );
  els.textModalTitle.textContent = item.title;
  els.textBody.textContent = item.body && item.body !== item.title ? item.body : "";
  els.textBody.hidden = !els.textBody.textContent;
  if (item.context) {
    els.textContext.hidden = false;
    els.textContext.textContent = `上下文：在「${item.context}」的评论区`;
  } else {
    els.textContext.hidden = true;
    els.textContext.textContent = "";
  }
  els.textTags.replaceChildren();
  item.tags.slice(0, 12).forEach((tag) => els.textTags.append(createBadge(tag, "tag")));
  const stats = [item.sourceName];
  stats.push(item.createdAt ? `发布 ${formatWhen(item.createdAt)}` : `收录 ${formatWhen(item.collectedAt)}`);
  if (item.heat?.display) stats.push(`${item.heat.label} ${item.heat.display}`);
  if (item.category === "reply" || item.category === "comment") stats.push("公开评论区");
  stats.push(`真实性 ${AUTH_LABELS[item.authenticity] || "真实采集"}`);
  els.textStats.textContent = stats.join(" · ");
  els.textPost.href = item.postUrl;
  syncTextFavorite();
  updateTextSeen();
  els.textClose.focus();
}

function copyItem(item) {
  const parts = [item.title];
  if (item.body && item.body !== item.title) parts.push(item.body);
  if (item.context) parts.push(`上下文：${item.context}`);
  if (item.postUrl) parts.push(item.postUrl);
  writeClipboard(parts.join("\n\n"), "文字已复制");
}

async function writeClipboard(text, message) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      showToast(message);
      return;
    }
  } catch (_error) { /* fall through */ }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.focus();
  area.select();
  try {
    document.execCommand("copy");
    showToast(message);
  } catch (_error) {
    showToast("复制失败，请手动选择文字");
  } finally {
    area.remove();
  }
}

function syncImageFavorite() {
  if (!state.currentItem) return;
  const active = state.favorites.has(state.currentItem.uid);
  els.lightboxFav.textContent = active ? "已收藏" : "收藏";
  els.lightboxFav.classList.toggle("is-active", active);
  els.lightboxFav.setAttribute("aria-pressed", String(active));
}

function updateLightboxSeen() {
  if (!state.currentItem) return;
  els.lightboxSeen.textContent = state.seen.has(state.currentItem.uid) ? "已看" : "标为已看";
  els.lightboxSeen.setAttribute("aria-pressed", String(state.seen.has(state.currentItem.uid)));
}

function syncTextFavorite() {
  if (!state.currentItem) return;
  const active = state.favorites.has(state.currentItem.uid);
  els.textFav.textContent = active ? "已收藏" : "收藏";
  els.textFav.classList.toggle("is-active", active);
  els.textFav.setAttribute("aria-pressed", String(active));
}

function updateTextSeen() {
  if (!state.currentItem) return;
  els.textSeen.textContent = state.seen.has(state.currentItem.uid) ? "已看" : "标为已看";
  els.textSeen.setAttribute("aria-pressed", String(state.seen.has(state.currentItem.uid)));
}

function closeImage() {
  els.lightbox.hidden = true;
  document.body.classList.remove("is-locked");
  els.lightboxImage.removeAttribute("src");
  els.lightboxMedia.classList.remove("is-loaded");
  state.currentItem = null;
  if (state.hideSeen) renderGrid();
}

function closeText() {
  els.textModal.hidden = true;
  document.body.classList.remove("is-locked");
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
  els.categoryTabs.addEventListener("click", (event) => {
    const button = event.target.closest(".cat-btn");
    if (!button) return;
    state.category = button.dataset.category || "discover";
    state.type = "all";
    state.visible = PAGE_SIZE;
    renderFilterState();
    renderGrid();
  });
  $$(".mode-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode || "latest";
      state.visible = PAGE_SIZE;
      renderFilterState();
      renderGrid();
    });
  });
  $$(".filter-btn", els.typeFilters).forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      state.type = button.dataset.type || "all";
      state.visible = PAGE_SIZE;
      renderFilterState();
      renderGrid();
    });
  });
  els.favOnly.addEventListener("click", () => {
    state.favoritesOnly = !state.favoritesOnly;
    state.visible = PAGE_SIZE;
    updateFilterButtons();
    renderFilterState();
    renderGrid();
  });
  els.hideSeen.addEventListener("click", () => {
    state.hideSeen = !state.hideSeen;
    state.visible = PAGE_SIZE;
    updateFilterButtons();
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
  els.lightboxClose.addEventListener("click", closeImage);
  els.lightbox.addEventListener("click", (event) => { if (event.target === els.lightbox) closeImage(); });
  els.lightboxFav.addEventListener("click", () => { if (state.currentItem) toggleFavorite(state.currentItem.uid); });
  els.lightboxSeen.addEventListener("click", () => {
    if (!state.currentItem) return;
    toggleSeen(state.currentItem.uid);
    updateLightboxSeen();
  });
  els.textClose.addEventListener("click", closeText);
  els.textModal.addEventListener("click", (event) => { if (event.target === els.textModal) closeText(); });
  els.textFav.addEventListener("click", () => { if (state.currentItem) toggleFavorite(state.currentItem.uid); });
  els.textSeen.addEventListener("click", () => {
    if (!state.currentItem) return;
    toggleSeen(state.currentItem.uid);
    updateTextSeen();
  });
  els.textCopy.addEventListener("click", () => { if (state.currentItem) copyItem(state.currentItem); });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!els.lightbox.hidden) closeImage();
    if (!els.textModal.hidden) closeText();
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

function toggleSeen(uid) {
  if (state.seen.has(uid)) state.seen.delete(uid);
  else state.seen.add(uid);
  saveSet(SEEN_KEY, state.seen);
  updateCardState(uid);
  showToast(state.seen.has(uid) ? "已标记为已看" : "已取消已看");
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  try { await navigator.serviceWorker.register("sw.js", { scope: "./" }); }
  catch (error) { console.warn("service worker registration failed", error); }
}

function init() {
  initTheme();
  loadLocalState();
  bindEvents();
  registerServiceWorker();
  loadAll();
}

init();
