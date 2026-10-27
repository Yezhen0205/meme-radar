# 梗图雷达 · Meme Radar

一个免费优先、无需 VPS 的中外梗图发现系统。

- **阅读器：** [https://yezhen0205.github.io/meme-radar/](https://yezhen0205.github.io/meme-radar/)
- **源码：** [https://github.com/Yezhen0205/meme-radar](https://github.com/Yezhen0205/meme-radar)
- **最新 Actions：** [40521418470](https://github.com/Yezhen0205/meme-radar/actions/runs/40521418470)（成功）
- Android 手机可直接打开，支持添加到主屏幕。

> 本项目是在原有文字版「热梗雷达」上的扩展：保留旧 `collector/` 与 `data/feed.json` 作为历史/实验代码，新的主流程是 `gallery/` 图片采集器、`data/gallery.json` 和图片瀑布流页面。

---

## 1. 当前真实验收结果

最近一次 GitHub Actions 真实采集（2026-10-27 22:29 CST）：

| 指标 | 实际结果 |
|---|---:|
| 图库条目 | **55 张** |
| Reddit | **27 张**（图库实际数量，含历史保留） |
| 百度贴吧 | **28 张**（当前运行接受 29，重复图片归并） |
| 本轮新发现 | **4 张** |
| 本轮更新 | 3 张 |
| 同图合并组 | **2 组** |
| 来源端图片校验 | **52 张检查，0 张失效** |
| dHash 图片指纹 | 本轮新图 5 张计算，历史指纹保留 |
| 采集耗时 | 约 29 秒 |
| 健康状态 | **degraded**（贴吧详情页 403，使用公开热点页降级采集） |
| Actions `collect` / `deploy` | **均成功** |
| 页面 HTTP | **200** |
| 页面实测 | 390×844、320×720 Chromium，0 个 JavaScript 异常；Reddit 图片域连接重置按预期显示占位，0 横向溢出 |

**重要网络限制：** Reddit 的 JSON/API 对云 IP 返回 403，因此本项目使用 Reddit 官方 Atom/RSS；Reddit 图片直链（`i.redd.it` / `preview.redd.it`）在当前本机网络不可达，页面会明确显示“图片暂时无法加载 / 打开原帖”，不会伪装成功。贴吧图片可正常加载。

---

## 2. 数据源状态

| 来源 | 接入方式 | 状态 | 内容 |
|---|---|---|---|
| **Reddit** | 官方多社区 Atom/RSS：`/r/196+okbuddyretard+AnimalsBeingDerps/new/.rss` | **ok** | 标题、帖子 ID、社区、原帖 URL、发布时间、图片 URL；RSS 不提供点赞/评论数，字段为 `null` |
| **百度贴吧** | 公开热点话题列表 + 热点话题页 | **degraded** | 真实帖子标题、原帖链接、吧名、评论数、帖子图片；帖子详情页对自动请求 403 |
| **热点辅助** | 微博热搜、百度热搜、头条热榜的公开接口 | **ok** | 生成候选关键词，用于标签和轻量排序；不直接生成图片 |
| **X** | 未实现 | planned | 不显示为运行中 |
| **B站** | 未实现（旧文字采集器里的 B站逻辑不用于图库） | planned | 不显示为运行中 |
| **微博图片** | 未实现 | planned | 不显示为运行中 |

### Reddit 的分页、空结果和限速

- Reddit 多社区 RSS 一次请求返回约 25 条最新条目；已验证 200、25 条、图片直链 206。
- 使用 `new` feed，并按 72 小时时间窗过滤旧置顶通知。
- 连续请求单社区会被 429，因此生产路径只用**一次多社区请求**；失败会有限重试并标记 blocked/degraded。
- 不使用 OAuth、不伪造点赞数、不尝试绕过 Reddit 的访问限制。

### 贴吧为什么是 degraded

已验证：

- `topicList` 热点话题接口：200；
- 热点话题页：200，包含真实帖子标题、`/p/{id}` 原帖链接、吧名、评论数、`data-origin` 图片；
- 帖子图片直链：206，真实 JPEG；
- 帖子详情页：自动请求 **403**。

因此贴吧不使用详情页，也不声称拿到了完整帖子/评论；只展示热点页中真实存在的帖子摘要、原帖链接和图片，并把来源明确标为 degraded。

---

## 3. 页面功能

- 图片优先的 CSS 多列瀑布流：手机 2 列，平板 3 列，桌面 4–5 列；
- **最新 / 热门 / 随机发现** 三个入口；
- 来源筛选：全部 / Reddit / 贴吧；
- 关键词搜索、热点候选词标签筛选；
- 点击卡片打开大图：大图、标题、摘要、来源、社区、时间、评论数、标签、原帖链接；
- **收藏**：`localStorage`，不需要登录；
- **已看标记 / 隐藏已看**：打开大图自动标记，也可以手动切换；
- 加载更多（首屏 24 张，避免一次加载全部历史）；
- 图片加载失败显示明确占位与原帖入口；
- 空状态、网络错误、本机缓存回退、数据过期/来源降级提示；
- 数据源健康面板，展示 ok/degraded/blocked/planned；
- 深色模式、跟随系统；
- PWA：`manifest.webmanifest`、192/512 图标、Service Worker；可添加到 Android 主屏幕。

### 添加到 Android 主屏幕

1. 用 Chrome 打开 [https://yezhen0205.github.io/meme-radar/](https://yezhen0205.github.io/meme-radar/)。
2. 点浏览器右上角菜单（三个点）。
3. 选择 **“添加到主屏幕” / “安装应用”**。
4. 确认后从桌面图标打开，页面会以 standalone 模式显示。
5. 首次加载后 Service Worker 会缓存应用外壳；图库 JSON 使用 network-first，离线时回退到缓存。

---

## 4. 采集与数据模型

```text
GitHub Actions (每 6 小时 / 手动)
  → gallery.collect
      ├─ Reddit 官方多社区 RSS（一次请求）
      ├─ Tieba 公开热点话题页
      ├─ 微博/百度/头条公开热榜 → 候选关键词
      ├─ 图片 HTTP Range 校验 + Pillow dHash
      ├─ 去重：帖子 ID / URL / 图片 URL / dHash
      ├─ 历史合并：失败来源保留上次数据
      └─ health 连续失败计数
  → data/gallery.json + data/health.json
  → scripts/build_gallery.py --check --stage
  → GitHub Pages (site/)
```

### 条目字段

```json
{
  "id": "reddit:…",
  "source": "reddit",
  "source_id": "1xgtqsz",
  "source_name": "Reddit",
  "community": "r/196",
  "title": "I participated in the protest for housing in Madrid, AMA",
  "summary": "",
  "post_url": "https://www.reddit.com/r/196/comments/…",
  "image_url": "https://i.redd.it/….jpeg",
  "thumbnail_url": "https://preview.redd.it/…",
  "images": [{"url": "…", "thumbnail_url": "…"}],
  "created_at": "2026-10-27T14:16:42Z",
  "collected_at": "2026-10-27T14:19:24Z",
  "time_source": "source",
  "score": null,
  "comment_count": null,
  "tags": ["r/196", "reddit", "196"],
  "content_hash": "…",
  "image_hash": "34afeb7c5e1d368e",
  "image_id": "…",
  "status": "active",
  "image_status": "ok",
  "image_http_status": 206,
  "image_checked_at": "2026-10-27T14:19:24Z",
  "image_error": null,
  "image_width": 1200,
  "image_height": 675,
  "rank_score": 100.0,
  "rank_basis": "recency",
  "group_id": "…",
  "group_size": 1,
  "related": []
}
```

- `score` / `comment_count` 没有来源数据时必须是 `null`，不编造。
- 贴吧的 `created_at` 在热点页不可得，使用 `time_source: "collection"`；页面显示“收录于”。
- `rank_basis` 说明排序依据：`recency`、`recency+comments`、`recency+comments+trend` 或 `recency+trend`。
- `image_status` 为 `ok` 表示 Actions 侧 HTTP/Range 校验通过，并不保证每个读者所在网络都能访问 Reddit 图片域。
- 图片失效不删除记录，保留原帖入口；下次运行会重新校验新条目。

### 去重

1. 同一来源按帖子 ID 去重；
2. 同一来源按规范化原帖 URL 去重；
3. 完全相同的图片 URL 直接合并；
4. 有 dHash 时，汉明距离 ≤ 6 的图片合并为同一组，保留一个代表卡片和多个 `related` 原帖链接；
5. 不同来源的同一图片会保留来源链接，不丢失原帖入口。

### 关键词

- 从微博/百度/头条热榜真实标题提取；
- 优先使用 `jieba` 分词；未安装时使用精选词表和完整短词，不使用会产生“交部回应 / 应姆巴佩”这类碎片的滑动 n-gram；
- 候选词只用于标签、搜索提示和轻微排序加成，不声称是 AI 主题分析。

---

## 5. 测试结果

测试分为实际运行结果（PASS）、实际失败/外部限制（FAIL/BLOCKED）和未运行（NOT_TESTED）。

| 测试 | 结果 | 证据 |
|---|---|---|
| Reddit 官方多社区 RSS | **PASS** | GitHub Actions 200；一次返回约 25 条；图库实际 27 张（含历史） |
| Reddit 图片直链 | **PASS（Actions 侧）** | 206，0 张 collector 校验失效；本机/大陆网络可能被 Reddit 域阻断 |
| Reddit JSON/API | **BLOCKED** | 云 IP 403；不绕过，改用官方 RSS |
| 贴吧热点话题接口 | **PASS** | 200，返回 30 个话题 |
| 贴吧热点页帖子/图片 | **PASS** | 29 条帖子，真实 `/p/` 链接和 `tiebapic` 图片 |
| 贴吧详情页 | **BLOCKED / degraded** | 自动请求 403；不绕过，页面标注降级 |
| 单来源失败保留历史 | **PASS** | `tests/test_gallery_dedupe.py` |
| 空结果不清空历史 | **PASS** | 合并逻辑保留旧条目，页面显示空/过期状态 |
| 重复帖子/图片去重 | **PASS** | 55 条最终数据，0 重复帖子，2 个图片合并组 |
| 图片 URL 真实可访问 | **PASS（Actions）** | 52 张检查、0 失效，图片字节为真实 JPEG/PNG/WebP |
| 手机瀑布流 | **PASS** | 390×844、320×720，0 横向溢出，0 JS 异常；网络图片错误按预期占位 |
| 搜索/来源筛选/随机/收藏/已看 | **PASS** | Chromium 交互测试 |
| 图片加载失败占位 | **PASS** | 受限网络下 Reddit 卡片显示“图片暂时无法加载 / 打开原帖” |
| PWA manifest / Service Worker | **PASS** | manifest、图标、SW 已注册并接管 |
| GitHub Actions 手动运行 | **PASS** | run 40521418470，collect/deploy 均 success |
| GitHub Pages | **PASS** | 页面 HTTP 200；gallery.json HTTP 200 |
| 6 小时定时任务 | **NOT_TESTED（尚未到首个自然触发点）** | 已配置 `0 */6 * * *` |
| 密钥/隐私扫描 | **PASS** | 仓库无 Token/Cookie/.env；无用户隐私数据 |
| X / B站 / 微博图片 | **NOT_TESTED / planned** | 未实现，未显示为运行中 |

本地单元测试：**38 项全部通过**。

---

## 6. 自动更新与费用

工作流：`.github/workflows/collect.yml`

- 每 6 小时：`0 */6 * * *`（UTC），约北京时间 02:00 / 08:00 / 14:00 / 20:00；
- 手动触发：Actions → Collect gallery and deploy → Run workflow；
- 并发组 `meme-radar-gallery`，`cancel-in-progress: false`；
- 任务超时 20 分钟；
- 仅在 `data/gallery.json` 或 `data/health.json` 有实质变化时提交；
- 采集失败保留历史；连续失败会写入 health 并在 Actions 输出 `::warning::`；
- 只使用 `contents: write`、`pages: write`、`id-token: write`；
- 不保存 Token/Cookie/账号凭证，不需要任何 Secrets；
- 不使用 VPS、付费 API、域名、数据库或付费云资源。

### 免费额度

- 公开仓库使用 GitHub 托管 runner 通常不消耗私有仓库分钟额度；私有仓库 Free 计划约 2,000 分钟/月，以 GitHub 账单为准。
- GitHub Pages 公开仓库免费；常见软限制约 1 GB 站点、100 GB/月流量、10 次构建/小时，以 [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) 为准。
- **GitHub 的 cron 不保证准点**，可能延迟数分钟到数十分钟，极端情况下跳过某次；页面显示数据的真实生成时间，不把计划时间伪装成采集时间。

---

## 7. 已知问题与限制

1. **Reddit 图片在大陆网络可能不可达**：数据与 Actions 侧校验正常，但浏览器可能显示占位。没有使用第三方图片代理或镜像，以避免绕过网络限制、版权和隐私问题。
2. **Reddit RSS 不提供点赞/评论数**：字段保持 `null`，热门排序只使用时间/趋势，不会伪造互动量。
3. **贴吧详情页 403**：只使用公开热点页的帖子摘要与图片，标记 degraded，不能保证拿到完整楼层/评论。
4. **贴吧没有可靠发布时间**：按收录时间排序并明确标注。
5. **热点候选词是统计结果**：不是语义模型，可能包含泛词。
6. **图片版权**：页面只展示原帖链接和来源图片 URL，不批量镜像全部图片；版权归原作者/平台。
7. **X、B站、微博是 planned**：没有空壳采集器伪装成正常来源。
8. **定时任务尚未自然触发**：手动运行已验证；首次自然 cron 仍需观察。
9. GitHub Pages CDN 可能有缓存；页面请求带时间戳并优先网络，Service Worker 提供离线回退。

---

## 8. 本地运行

要求 Python 3.12+。

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
python -m gallery.collect
python scripts/build_gallery.py --check --stage --summary
python -m http.server 8765 --directory site
# 打开 http://127.0.0.1:8765/
```

无 Reddit 网络时可只验证贴吧：

```bash
python - <<'PY'
import json
from pathlib import Path
from gallery.collect import load_config, build_feed
from gallery.models import utc_now
cfg = load_config(Path("config/gallery.json"))
cfg["reddit"]["enabled"] = False
feed, health, code = build_feed(cfg, None, utc_now(), previous_health={}, image_enabled=True)
print(health["status"], len(feed["items"]))
PY
```

---

## 9. 目录

```text
meme-radar/
├── config/gallery.json        # Reddit 社区、贴吧话题、限制、planned 来源
├── gallery/
│   ├── collect.py             # 编排、图片校验、健康与输出
│   ├── http.py                # 超时/重试/限速、Range 图片校验
│   ├── models.py              # 统一数据模型
│   ├── images.py              # 图片魔数、尺寸、dHash
│   ├── dedupe.py              # 历史合并、去重、同图分组、排序
│   ├── health.py              # 连续失败与健康文件
│   └── collectors/
│       ├── reddit.py          # 官方多社区 RSS
│       ├── tieba.py           # 公开热点话题页
│       └── trends.py          # 热点候选词
├── data/gallery.json          # 线上图库数据
├── data/health.json           # 来源健康/历史
├── site/                      # 图片瀑布流 + PWA
├── scripts/build_gallery.py   # 校验与 Pages 压缩数据
├── tests/                     # 38 项单元/交互 fixture 测试
├── collector/                 # 旧文字版采集器（legacy）
└── data/feed.json             # 旧文字版数据（legacy）
```

## 10. 合规

- 只访问公开、无需登录的页面/接口；
- 不绕过登录、验证码、403、访问控制或反爬；
- 不提交任何 Token、Cookie、密码、`.env`；
- 不下载/传播违法、恶意或侵犯隐私的内容；
- 图片展示遵循来源平台条款；如需删除某条内容，请通过仓库 Issues 提供原帖链接；
- 用户收藏与已看记录只保存在浏览器 `localStorage`。

## License

代码采用 MIT；聚合内容版权归原作者与平台。
