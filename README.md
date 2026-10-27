# 梗图雷达 · Meme Radar

一个免费优先、无需 VPS 的中文互联网梗图与热梗混合阅读器。

- **网站：** [https://yezhen0205.github.io/meme-radar/](https://yezhen0205.github.io/meme-radar/)
- **仓库：** [https://github.com/Yezhen0205/meme-radar](https://github.com/Yezhen0205/meme-radar)
- **最新 Actions：** [40525473295](https://github.com/Yezhen0205/meme-radar/actions/runs/40525473295)（成功）
- Android 浏览器可直接使用，支持添加到主屏幕。

> 这是现有 `meme-radar` 项目的整合升级，不是新项目。旧的纯图片前端已替换为图片 + 文字混合前端；旧的 `collector/` 代码被修复并接回，`data/feed.json` 仅作为历史数据保留，当前文字数据为 `data/text.json`。

---

## 1. 当前真实内容

最近一次真实 Actions 运行（2026-10-27 22:54 CST）：

| 指标 | 实际结果 |
|---|---:|
| 综合内容 | **382 条** |
| 梗图 | **60 张** |
| 文字内容 | **322 条** |
| 真实采集 | **382 条** |
| 原创改写 | **0 条** |
| AI 原创 | **0 条** |

### 七个分类及真实数量

| 分类 | 数量 | 数据来源 |
|---|---:|---|
| 综合发现 | **382** | 图片 + 文字混合，默认首页 |
| 梗图 | **60** | Reddit 32、百度贴吧 28 |
| 热梗 | **15** | B站热门/贴吧热榜/知乎日报等真实标题 |
| 抽象段子 | **4** | 关键词规则筛出的真实标题/摘要；没有用普通热点或 AI 文本填充 |
| 神回复 | **40** | B站公开评论区的回复 |
| 评论金句 | **12** | B站公开评论区的高赞评论 |
| 热点 | **251** | 微博、百度、头条、抖音、贴吧热榜、知乎日报等 |

> 分类规则在 `collector/classify.py`，只使用标题/平台分区关键词，不调用 AI；“抽象段子”不是把普通热点直接改标签。当前 4 条可能偏少，但都是真实来源；页面没有用假数据凑数。

### 真实性

所有当前内容均为 `authenticity: "real"`。数据结构支持 `rewrite` 和 `ai`，页面会分别显示“原创改写”“AI 原创”，但本次没有生成或混入任何 AI/原创改写内容。

---

## 2. 数据来源与状态

### 图片

| 来源 | 状态 | 实际结果 |
|---|---|---|
| Reddit | **ok** | 32 张；官方多社区 Atom/RSS；标题、社区、原帖、发布时间、图片 URL、帖子 ID；RSS 不提供点赞/评论数，字段保持 `null` |
| 百度贴吧 | **degraded** | 28 张；公开热点话题页的帖子标题、`/p/` 原帖链接、吧名、评论数、图片；帖子详情页自动请求 403 |

### 文字

| 来源 | 状态 | 实际结果 |
|---|---|---|
| B站热门 | ok | 50 条 |
| B站评论区 | ok | 52 条（40 神回复 + 12 评论金句） |
| 微博热搜 | ok | 50 条 |
| 百度热搜 | ok | 50 条 |
| 贴吧热榜 | ok | 30 条 |
| 头条热榜 | ok | 50 条 |
| 抖音热榜 | ok | 50 条 |
| 知乎日报 | ok | 4 条 |

文字八个来源全部成功；最终文字 322 条（原始 336，事件归类 12 组）。

### 已实测不可用

| 来源 | 结果 | 处理 |
|---|---|---|
| 知乎热榜 | HTTP 401，要求登录身份 | 不绕过，不使用 |
| 煎蛋 RSS | HTTP 403 | 不重试，不使用 |
| V2EX 热门 API | 连接超时 | 有限超时后跳过 |
| 贴吧帖子详情页 | HTTP 403 | 降级为热点页摘要 + 原帖入口 |

这些不可用来源会显示在页面“数据源健康”区域，不会被伪装成正常数据源。X、B站图片、微博图片仍为 `planned`，没有空壳采集器冒充运行中。

---

## 3. 页面功能

- **综合发现默认首页**：图片卡片与文字卡片按类型均衡交错，首屏至少能看到两种内容（实测首屏 12 图 + 12 文字）。
- 七个分类导航：综合发现、梗图、热梗、抽象段子、神回复、评论金句、热点。
- 图片瀑布流、大图浏览、来源标记、原帖入口、图片失败占位；
- 文字卡片、文字详情、复制文字、收藏、已看、隐藏已看；
- 来源筛选：全部/Reddit/贴吧/B站/微博/百度/头条/抖音/知乎；
- 内容类型筛选：全部/图片/文字；
- 关键词搜索、热点候选词标签；
- 最新/热门/随机发现排序；随机模式“换一批”；
- 加载更多（首屏 24 条）；
- 空状态、加载失败、缓存回退、部分来源降级/过期提示；
- 深色模式；
- PWA manifest、192/512 图标、Service Worker（v4），可添加到 Android 主屏幕。

### 分类验收

线上页面实际点击验证：

| 分类 | 页面结果 |
|---|---|
| 综合发现 | 382 条总数据，首屏 12 图 + 12 文字 |
| 梗图 | 60 张，图片加载/大图正常（Reddit 图片受网络限制时占位） |
| 热梗 | 15 条 |
| 抽象段子 | 4 条 |
| 神回复 | 40 条，首屏 24 条 |
| 评论金句 | 12 条 |
| 热点 | 251 条，首屏 24 条 |

所有分类都有实际数据读取逻辑；若未来某类为 0，会显示明确空状态和原因，不会填充假内容。

---

## 4. 图片与文字独立存储

```text
data/gallery.json   图片：60 条；来源、图片 URL、图片校验状态、dHash
data/health.json    图片来源健康/连续失败/历史
data/text.json      文字：322 条；分类、真实性、原帖、上下文
data/feed.json      旧文字版历史快照（legacy，不再被新工作流使用）
```

前端分别请求 `site/data/gallery.json` 和 `site/data/text.json`，合并为一个内存信息流；任何一类缺失/失败时，另一类仍然展示。

### 文字字段

```json
{
  "id": "bilibili_comments:…",
  "content_type": "text",
  "authenticity": "real",
  "category": "reply",
  "title": "…",
  "summary": "回复 @…",
  "url": "https://www.bilibili.com/video/…#reply…",
  "source_id": "bilibili_comments",
  "source_name": "哔哩哔哩评论区",
  "source_kind": "reply",
  "published_at": "…",
  "collected_at": "…",
  "heat": {"label": "点赞", "value": 176, "display": "176", "rank": 23},
  "tags": ["B站评论区", "神回复"],
  "context": "视频标题"
}
```

- `content_type` 区分 `text` / `image`；
- `authenticity` 区分 `real` / `rewrite` / `ai`；
- `ai` 数据必须带 `ai_generated=true`，否则 `scripts/build_text.py` 拒绝；
- 空互动字段保持 `null`；
- 文字卡片展示上下文，避免把评论脱离视频语境。

### 图片字段

图片条目额外包含 `image_url`、`thumbnail_url`、`images`、`image_status`、`image_http_status`、`image_checked_at`、`image_error`、`image_width/height`、`image_hash`（dHash）、`post_url`。

- `image_status=ok` 表示 Actions 侧 HTTP Range/图片魔数校验通过；
- 浏览器所在网络可能无法访问 Reddit 图片域，页面会明确显示占位和原帖入口；
- 不把占位图当成采集成功；
- 不下载/镜像整站图片。

### 去重

- 图片：帖子 ID、规范化原帖 URL、图片 URL、dHash ≤ 6 同图归并；
- 文字：来源 ID、规范化 URL、内容指纹；同标题但不同来源且有不同正文时**不合并**；
- 同图多来源保留 `related` 链接；
- 失败来源保留历史，单次空结果不会清空。

---

## 5. 自动更新

工作流：[collect.yml](https://github.com/Yezhen0205/meme-radar/blob/main/.github/workflows/collect.yml)

- 定时：`0 */6 * * *`（UTC），约北京时间 **02:00 / 08:00 / 14:00 / 20:00**；
- 手动：Actions → Collect images and text, deploy → Run workflow；
- 并发组 `meme-radar-all`，不取消正在运行的任务；
- 超时 25 分钟；
- 文字和图片各自 `continue-on-error`，独立写入 `data/text.json` / `data/gallery.json`；
- 一个采集器失败不会阻止另一个数据文件和旧页面部署；
- 仅在 `data/text.json`、`data/gallery.json`、`data/health.json` 有实质变化时提交；
- 失败保留历史；健康 warning 输出到 Actions；
- Pages 使用 `upload-pages-artifact` + `deploy-pages`；
- 不使用 VPS、付费 API、数据库、Cookie、Token 或用户账号。

**最新运行：** run 40525473295，`collect` / `deploy` 均 success（手动触发）。  
**自然定时运行：** 尚未观察到；不能把手动运行写成“定时任务已验证”。

GitHub cron 是 UTC 且不保证准点，可能延迟或跳过。

---

## 6. 实测报告

### PASS

- 文字 8 个来源真实采集：全部成功；
- 图片 Reddit 官方 RSS、贴吧公开热点页：真实条目；
- 图片 URL / 文字 URL 校验：本轮 51 张图片检查，0 张来源侧失效；
- 图片 dHash、帖子/URL/同图去重：通过；
- 文字/图片独立文件、失败保留：通过；
- 同标题不同正文不合并：通过；
- 7 个分类都有真实数据并可点击；
- 综合首页首屏 12 图 + 12 文字；
- 搜索、来源筛选、类型筛选、收藏、已看、隐藏已看、文字复制、原帖跳转：通过；
- 390×844、320×720：0 横向溢出、0 JavaScript 异常；
- PWA manifest、图标、Service Worker v4：通过；
- Actions 手动运行、Pages 部署：通过；
- 仓库密钥扫描：无 Token/Cookie/密码。

### BLOCKED / 部分限制

- **Reddit 图片域在当前网络不可达**：图片占位和页级提示已验证；采集器服务端校验图片 URL 正常。原因在读者网络，不是数据造假。
- **贴吧详情页 403**：来源降级为热点页，无法取完整楼层。
- **知乎热榜 401 / 煎蛋 403 / V2EX 超时**：不绕过，页面健康面板记录。
- **Reddit RSS 无互动数**：字段为 `null`，不伪造。

### NOT_TESTED

- 6 小时自然定时触发（尚未到自然触发点）；
- 实体 Android 主屏幕安装弹窗（PWA 技术项已验证，安装步骤见下）；
- X / B站图片 / 微博图片（planned，未实现）。

**本地测试：45 项全部通过。**  
**线上页面：HTTP 200；`data/gallery.json` 200；`data/text.json` 200；manifest/sw 200；Service Worker 已接管。**

---

## 7. 仍然存在的问题

1. **Reddit 图片在部分网络被重置**。页面显示占位、原帖入口和页级提示；没有擅自引入第三方代理或大规模镜像。
2. **贴吧详情页 403**，只能拿到热点页的帖子摘要、原帖链接、吧名、评论数和图片。
3. **抽象段子只有 4 条**，因为当前规则严格且没有用普通热点/AI 内容填充；后续可继续调关键词或增加合规来源。
4. **B站评论来自少数热门视频**，不是全站评论；评论上下文保留在卡片/详情中。
5. **小红书、X、B站图片、微博图片**未接入，标记 planned。
6. **自然定时任务未观察**；GitHub cron 可能延迟。
7. 图片和文章版权归原作者/平台；如需删除请通过仓库 Issues 提供原帖链接。

---

## 8. 本地运行

```bash
python -m pip install -r requirements.txt

# 独立采集文字（不会覆盖图片）
python -m collector.collect --output data/text.json

# 独立采集图片（不会覆盖文字）
python -m gallery.collect

# 校验并生成两份 Pages 数据
python scripts/build_text.py --check --stage
python scripts/build_gallery.py --check --stage

# 测试
python -m unittest discover -s tests -t . -v

# 预览
python -m http.server 8765 --directory site
```

---

## 9. Android 添加到主屏幕

1. Chrome 打开 [https://yezhen0205.github.io/meme-radar/](https://yezhen0205.github.io/meme-radar/)。
2. 点右上角三个点。
3. 选“添加到主屏幕”/“安装应用”。
4. 确认后从桌面启动，standalone 模式显示。
5. Service Worker v4 缓存应用外壳；JSON 采用 network-first，避免长期显示过期数据。

---

## 10. 费用与安全

- GitHub 公开仓库 + GitHub Pages，未使用付费 API、VPS、域名、数据库或云资源。
- 没有提交 Token、Cookie、密码、`.env` 或用户隐私数据。
- 收藏/已看只存浏览器 `localStorage`。
- 不绕过登录、验证码、403 或访问控制。
- 免费额度以 GitHub 当前账单和 [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) 为准。

## License

代码采用 MIT；图片、帖子、评论版权归原作者与平台。
