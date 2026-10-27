# 热梗雷达 · Meme Radar

把中文互联网的搞笑帖子、抽象热梗、神回复和评论区金句，收进一个可以直接用安卓手机浏览器打开的轻量信息流。

- **不登录、不注册**
- **不接入付费 AI API**
- **不使用 VPS、域名或持续运行的服务器**
- **不伪造点赞、评论、排名或“模拟采集”数据**
- 采集与页面均为静态文件，靠 GitHub Actions 定时更新、GitHub Pages 托管

> 当前状态：代码、采集器、移动端页面与本地真实采集已完成；GitHub 仓库和 Pages 地址在首次部署后写入此处。源码地址：`https://github.com/Yezhen0205/meme-radar`；阅读器：`https://yezhen0205.github.io/meme-radar/`（首次 Actions 部署完成后生效）。

---

## 1. 它采集什么

第一版只使用**公开、匿名可访问**的 JSON 接口，不绕过登录、验证码、访问控制或反爬措施。

| 数据源 | 实际内容 | 热度口径 | 本地实测（2026-10-27） |
| --- | --- | --- | --- |
| 哔哩哔哩热门 | 公开热门视频（标题、简介、UP 主、封面） | 播放量，来源内榜位 | 50 条 |
| 哔哩哔哩评论区 | 热门视频下的公开热评；对高讨论热评再取一层公开回复 | 点赞数，来源内榜位 | 59 条（12 条热评 + 47 条回复） |
| 微博热搜 | 热搜词与热搜指数 | 微博提供的热搜指数，来源内榜位 | 50 条 |
| 百度热搜 | 热搜词 | 接口未提供数值热度，只展示榜位 | 50 条 |
| 贴吧热榜 | 热门话题、摘要、讨论数 | 讨论数，来源内榜位 | 30 条 |
| 头条热榜 | 热榜标题、热度、分类标签 | 头条热度，来源内榜位 | 50 条 |
| 抖音热榜 | 热榜词、热度 | 抖音热度，来源内榜位 | 50 条 |
| 知乎日报 | 日报编辑精选文章（不是知乎热榜） | 无热度，只展示日报顺序 | 4 条 |

一次完整本地采集得到 **343 条原始条目**，经同日事件归类和上限控制后保留 **327 条**：热梗 17、神回复 47、评论金句 12、综合热点 251。当前快照没有完全重复的 URL；有 13 组同一事件的多来源报道被合并展示。

### 实际测试后跳过的源

| 源 | 结果 | 处理 |
| --- | --- | --- |
| 知乎热榜 `api/v3/feed/topstory/hot-lists` | HTTP 401，要求登录身份 | 跳过，不伪造知乎热榜；只用无需登录的知乎日报 |
| 煎蛋 RSS | HTTP 403 | 跳过 |
| V2EX 热门 API | 连接超时 | 跳过 |
| 抖音、微博的完整帖子/评论 | 需要登录态或额外签名，未稳定匿名可得 | 第一版只取公开热榜，不抓完整帖子/评论 |

> 热榜接口给的是**榜单快照**，不是完整帖子，更不是完整评论树。B 站评论区采集的是公开热评和其下的一层公开回复；不递归抓取整棵树，也不登录。

---

## 2. 为什么没有直接复用候选项目

| 项目 | 结论 | 原因 |
| --- | --- | --- |
| [TrendRadar](https://github.com/sansan0/TrendRadar) | 参考数据源思路，不复制代码 | GPL-3.0；功能偏新闻热榜聚合、通知和 AI 分析，直接嵌入会让本项目的许可证和依赖变重 |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 不采用 | `NON-COMMERCIAL LEARNING LICENSE 1.1`；依赖 Playwright、数据库、Redis、登录态和代理，不适合免费、无服务器的 GitHub Actions，也不符合“不绕过访问控制”的约束 |

本项目为独立实现，运行期只依赖 **Python 3.12 标准库**。没有把上述项目的代码复制进来，因此本仓库使用 MIT 许可证；聚合内容的版权仍归原作者和平台。

---

## 3. 工作原理

```text
GitHub Actions (cron: 每 6 小时 / 手动)
        │
        ├─ python -m collector.collect
        │    ├─ 公开 JSON 接口（超时 / 重试 / 限速）
        │    ├─ 归一化：标题、摘要、来源、原文、时间、热度
        │    ├─ 分类：热梗 / 神回复 / 评论金句 / 综合热点
        │    ├─ 去重：规范化 URL + 内容指纹
        │    ├─ 归类：同一事件的多来源标题相似度
        │    └─ 合并：失败源保留上次成功条目
        │
        ├─ data/feed.json（提交进仓库的唯一数据源）
        │
        ├─ scripts/build_feed.py --check --stage
        │    └─ 校验并生成 site/data/feed.json（压缩 JSON）
        │
        └─ GitHub Pages
             └─ site/index.html + app.css + app.js
                  └─ 安卓手机浏览器信息流
```

### 目录结构

```text
meme-radar/
├── README.md
├── LICENSE
├── requirements.txt          # 仅注释；运行期无第三方依赖
├── .gitignore
├── config/
│   └── sources.json          # 源开关、超时、限量、评论采集参数
├── collector/
│   ├── http.py               # 标准库 HTTP、超时、重试、按域限速
│   ├── sources.py            # 8 个公开源适配器
│   ├── normalize.py          # 清洗、时间、URL、指纹、个人联系方式脱敏
│   ├── classify.py           # 可解释的关键词/分区分类
│   ├── deduplicate.py        # URL + 指纹去重、事件归类
│   └── collect.py            # 编排、失败保留、原子写入
├── data/
│   └── feed.json             # 已提交的真实采集结果
├── site/
│   ├── index.html
│   ├── app.css
│   ├── app.js
│   ├── favicon.svg
│   └── .nojekyll
├── scripts/
│   └── build_feed.py         # 校验 + 生成 Pages 用压缩 JSON
├── tests/
│   ├── test_normalize.py
│   ├── test_classify.py
│   ├── test_deduplicate.py
│   └── test_collect.py
└── .github/workflows/collect.yml
```

---

## 4. 本地运行

要求 Python 3.12+，不需要 `pip install`。

```bash
# 1. 真实采集一次（会写 data/feed.json）
python -m collector.collect

# 2. 校验 JSON 并生成 site/data/feed.json
python scripts/build_feed.py --check --stage --summary

# 3. 本地预览
python -m http.server 8765 --directory site
# 浏览器打开 http://127.0.0.1:8765/
```

测试：

```bash
python -m unittest discover -s tests -t . -v
```

测试覆盖：URL 规范化、联系方式脱敏、热度格式、标题摘要切分、分类规则、URL/指纹去重、同一事件归类、评论跨视频不误合并、失败保留旧数据、首次全失败空状态、部分失败合并、无实质变化时复用上一份 feed、JSON 校验。

### 配置

`config/sources.json` 可单独关闭数据源或调整限量。关键参数：

- `request.timeout_seconds`：单请求超时，默认 15 秒；
- `request.retries`：最多重试 1 次，指数退避；
- `request.min_interval_seconds`：同一域名请求间隔，默认 1.2 秒；
- `feed.max_items`：最多保留条目数；
- `feed.retention_hours`：失败源旧数据最长保留 7 天；
- `bilibili_comments.videos`：最多读取 4 个热门视频的评论区；
- `bilibili_comments.comments_per_video` / `subreplies_per_video`：每视频热评/回复上限。

---

## 5. 数据格式

`data/feed.json` 的关键字段：

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-27T12:51:19Z",
  "checked_at": "2026-10-27T12:51:19Z",
  "stale": false,
  "run": {
    "ok": true,
    "partial": false,
    "sources_ok": 8,
    "sources_failed": 0,
    "items_raw": 343,
    "items_final": 327
  },
  "sources": [
    {
      "id": "bilibili",
      "name": "哔哩哔哩热门",
      "status": "ok",
      "accepted": 50,
      "retained": 0,
      "error": null,
      "using_previous": false
    }
  ],
  "items": [
    {
      "id": "bilibili:…",
      "fingerprint": "…",
      "title": "…",
      "summary": "…",
      "source_id": "bilibili",
      "source_name": "哔哩哔哩热门",
      "source_kind": "video",
      "url": "https://www.bilibili.com/video/…",
      "published_at": "2026-10-27T07:45:29Z",
      "published_precision": "datetime",
      "collected_at": "2026-10-27T12:51:19Z",
      "category": "meme",
      "tags": ["B站热门", "短片", "热梗"],
      "heat": {
        "label": "播放",
        "value": 640976,
        "display": "64.1万",
        "rank": 10
      },
      "rank": 10,
      "context": null,
      "context_url": null,
      "author": "…",
      "image": "https://…",
      "group_id": "…",
      "group_size": 1,
      "related": []
    }
  ]
}
```

### 热度与排序的边界

不同平台的热度不可直接等价比较。因此：

- 每条只保存来源**确实提供**的指标；百度热搜没有数值热度就保持 `heat: null`；
- 卡片展示“播放 / 点赞 / 讨论 / 热搜指数 / 热度 + 来源内榜位”；
- 页面的「榜位」排序是**来源内排名的跨源排列**，不是统一的跨平台热度分；
- 页面在「榜位」模式下明确提示“不同来源的热度值不可直接比较”。

### 去重与事件归类

1. 规范化 URL：统一 `https`、去掉 `www.` 和 `utm_*` / `spm_*` / 分享参数，保留评论锚点；
2. 同一来源内按规范化 URL 与内容指纹去重；
3. 跨来源按标题字符 bigram 的 Jaccard/包含度归类；只有视频/文章/热榜条目参与，评论和回复不会跨视频误合并；
4. 保留质量更高的一条作为代表，其余放入 `related`，并显示“同一事件还有 N 条相关来源”；
5. `group_size` 是真实相关条目数，不代表互动量。

---

## 6. 失败、过期与保留策略

- 单个源失败不会中断其他源；
- 失败源的旧条目在 7 天内保留，卡片标记「上次数据」，页面顶部提示“部分数据源未更新”；
- 所有源都失败时，`stale: true`，页面保留上次成功数据并显示最后成功时间；
- 首次采集全部失败且没有旧数据时，页面显示空状态，不展示任何虚构内容；
- 页面加载不到 JSON 时先尝试浏览器本地缓存；缓存也没有则显示“雷达暂时失联”；
- 数据超过 12 小时未更新会显示延迟提示；
- 采集写入使用临时文件 + 原子替换，进程中断不会写坏 `data/feed.json`。

### “只在数据变化时提交”

采集器会为每条内容计算内容签名；如果两次运行的内容、来源状态都没有实质变化，会直接保留上一份 `data/feed.json` 的字节，不更新时间戳。因此定时任务不会每 6 小时制造一个空提交。

---

## 7. GitHub Actions 与 Pages

工作流：`.github/workflows/collect.yml`

- 定时：`0 */6 * * *`（UTC），约对应北京时间 02:00 / 08:00 / 14:00 / 20:00；
- 手动：Actions → Collect and deploy Meme Radar → Run workflow；
- 并发组 `meme-radar-collect`，`cancel-in-progress: false`，避免上一轮未结束时重复执行；
- 单任务超时 15 分钟；
- 只授予 `contents: write`、`pages: write`、`id-token: write`；
- 采集前跑单元测试，采集后校验 JSON；
- `git diff --quiet -- data/feed.json` 为真时跳过提交；
- 通过 `actions/upload-pages-artifact` + `actions/deploy-pages` 发布 `site/`；
- 不使用任何仓库密钥、Cookie 或账号凭证。

### 启用步骤（仓库创建后）

1. 仓库设为 **Public**（免费 Pages 和标准 Actions 的前提）；
2. Settings → Actions → General → Workflow permissions：允许 **Read and write permissions**；
3. Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**；
4. Actions 里手动运行一次 `Collect and deploy Meme Radar`；
5. 等待 `deploy` job 完成，打开 `https://<owner>.github.io/meme-radar/`。

> GitHub 的定时任务**不保证准点**：可能因平台负载、额度、仓库状态延迟数分钟到数十分钟，极端情况下会跳过某次。页面以 `generated_at` 和“最后更新”显示真实数据时间，不会把计划时间伪装成采集时间。

---

## 8. 免费额度与限制

- **GitHub Actions**：公开仓库使用 GitHub 托管的标准 runner 通常不消耗私有仓库分钟数；私有仓库 Free 计划有每月 2,000 分钟额度。以 GitHub 当前账单页面为准。
- **GitHub Pages**：公开仓库可免费使用；常见软限制为站点不超过 1 GB、每月约 100 GB 流量、每小时约 10 次构建。以 [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) 为准。
- **不使用**：付费 AI API、VPS、域名、数据库、Redis、代理池、付费云资源。
- **运行时间**：本地完整采集约 20–30 秒；Actions 还包含 checkout、测试和 Pages 部署，通常 1–4 分钟。

### 已知限制

1. 热榜接口只返回榜单快照，不返回完整帖子正文；B 站评论只取公开热评和一层回复，不是完整评论树。
2. 微博/百度/头条/抖音的条目链接是热榜搜索或榜单详情链接，不保证直达原帖；页面标注来源并在新标签页打开。微博搜索在部分网络会先跳到访客验证页，百度搜索也可能触发验证码；这是平台侧访问策略，本项目不会绕过，必要时可在平台 App 内搜索标题。
3. 知乎热榜、煎蛋、V2EX 当前不可匿名稳定获取，已跳过；知乎只保留无需登录的知乎日报。
4. B 站接口在部分云机房 IP 上会返回 `-352` 风控；采集器使用官方网页同款的匿名 `buvid` 标识和浏览器 UA，仍失败时记录状态并保留旧数据，不绕过验证码。
5. “热梗/神回复”分类是可解释的关键词和 B 站分区规则，不是语义模型；可能误判，后续可继续调参。
6. 热度只在同一来源、同一类型内可比；页面不生成跨平台统一热度分。
7. 数据源随时可能改接口或封禁云 IP；失败会在页面“数据源状态”中显示。
8. B 站视频/知乎日报封面图来自原平台 CDN，弱网或防盗链环境下可能不显示；正文与链接不受影响。

---

## 9. 合规与安全

- 只请求公开、无需登录的接口；
- 不提交 Cookie、Token、密码、`.env` 或账号信息；
- 不绕过登录、验证码、付费墙、访问控制或反爬；
- 请求有超时、重试上限和按域限速；不递归抓取完整评论树；
- 评论展示前脱敏手机号和邮箱，移除 URL、推广/加群等明显垃圾内容；
- 页面不跟踪用户、不接第三方统计、不要求注册；
- 收藏只存在浏览器 `localStorage`，不会上传；
- 内容版权归原作者和平台，页面只展示标题、摘要、必要上下文与原文链接；
- 如需删除某条内容，请通过仓库 Issues 联系，附上原始链接。

---

## 10. 后续可扩展

- 更多稳定公开源（在实测通过后加入 `config/sources.json` + 适配器）；
- 更细的“抽象/沙雕/社会趣闻”标签；
- 同一事件的时间线视图；
- 可选的 RSS 输出；
- 更丰富的来源内热度趋势（不跨源比较）。

## License

代码采用 [MIT](LICENSE)。聚合内容版权归原平台与原作者；本项目不主张对聚合内容的所有权。
