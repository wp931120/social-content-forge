---
name: social-content-forge
description: "社媒内容锻造 skill：从互联网（X/Twitter、网页、小红书）收集热门信息，自动整理成小红书 / 微博 / 公众号爆款图文草稿。支持爬虫 daemon 模式保持浏览器长驻，内容抓取后自动套用爆款方法论（标题公式 + AIDA/SCQA/PASS/hook 正文框架 + 标签金字塔 + 推荐发布时间 + CES 互动优化）。触发词：社媒内容、热点转图文、内容整理、社媒文案、小红书草稿、爆款笔记、xhs、内容采集、信息收集、爬虫抓取、内容forge、convert to social、AIDA、SCQA、PASS、daemon、browser state。"
---

# Social Content Forge — 社媒内容锻造

使用 Playwright 从互联网收集热门内容，**并把信息一键转成社交媒体爆款图文草稿**。

**默认推荐 daemon 模式**：让浏览器进程一直存在，用户可以全程看到爬取过程，每���抓取只新开/关闭 tab，不重启浏览器。

## 小红书爆款方法论速查（生成草稿时遵循）

> 完整研究文档见 [`references/xhs_viral_playbook.md`](references/xhs_viral_playbook.md)。`xhs_converter.py` 已把以下规则硬编码到生成的 `draft.md` 里。

- **算法**：阶梯式流量池（200→5k→50k→爆款）。CES 评分 = `点赞×1 + 收藏×1 + 评论×4 + 转发×4 + 关注×8`。**评论/转发/关注权重最高**，所以正文末尾**必须**有开放问题 + 关注/收藏引导。
- **标题公式**（converter 自动按内容线索选 1）：
  1. `数字+痛点+方案`（"3 个 X，让你 Y"）— 内容含数字时优先
  2. `反常识+悬念`（"不是 X，而是 Y"）— 内容含转折词
  3. `实测+结果`（"亲测 N 天 ___"）
  4. `对比+反差`（"从 X 到 Y"）
  5. `人群标签+解决`（"打工人必看｜___"）— 兜底
- **正文框架**（用 `--style` 选）：
  - `--style aida`：Attention→Interest→Desire→Action（产品/工具种草）
  - `--style scqa`：Situation→Complication→Question→Answer（观点/深度）
  - `--style pass`：Problem→Agitate→Solution→Story（解决方案/教程）
  - `--style hook`（默认）：开篇钩子 + 短段落 + 金句（资讯/转发型）
- **标签金字塔**：1 个核心词 + 2-3 个长��词 + 3-5 个广义词 = 总 6-9 个。converter 自动按品类生成。
- **发布时间**（converter 自动写入 draft.md）：AI/职场/干货 7:30-9:00 / 12:00-13:30；体育 赛后 1-2h；美食 11-12 / 17-19；穿搭 12-14 / 21-23；学习 19-22。
- **格式硬指标**：标题 18-22 字 / 段落 ≤3 行 / 段间空行 / 总字数 300-800 / 末尾必有 emoji + 开放问题。

→ 任何"把这条内容/这篇文章/这条推文做成小红书"的需求，都直接走 `xhs from-url`、`xhs from-topic` 或 `xhs from-following`，不要手动写 markdown。

## Python 路径

所有命令使用绝对路径 `/mnt/d/wsl/miniconda3/bin/python` 执行。

## 依赖安装

```bash
/mnt/d/wsl/miniconda3/bin/python -m pip install playwright playwright-stealth html2text readability-lxml
/mnt/d/wsl/miniconda3/bin/python -m playwright install chromium
```

## 推荐工作流（daemon 模式）

爬虫过程对用户可见，浏览器进程在整个会话期间一直存在。

```bash
# 终端 A —— 启动长驻可视浏览器（前台运行，一直占用终端）
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py daemon

# 终端 B —— 在 daemon 浏览器��登录，登录态持久保存到 daemon profile
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py login x

# 终端 B —— 抓取（复用 daemon 浏览器，用户全程可见）
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py scrape "https://x.com/user/status/123" --format markdown

# 完成后关闭 daemon
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py stop
```

`scrape` / `login` / `screenshot` 会自动检测 daemon 是否运行：
- **daemon 运行中**：在已可见的浏览器中开新 tab 执行任务，结束后只关闭 tab，浏览器进程保留
- **daemon 未运行**：回退到一次性 headless 浏览器（旧行为）

## 命令说明

### daemon - 启动长驻可视浏览器

```bash
web_crawler.py daemon [--port 9222] [--url <初始页>]
```

- 前台运行，占用终端，浏览器窗口一直可见
- 监听 CDP 端口（默认 9222），其他子命令通过此端口连接
- profile 持久化在 `.browser-state/.profile/`，cookies/localStorage 自动复用
- `Ctrl+C` 或 `web_crawler.py stop` 退出

### stop - 停止 daemon

```bash
web_crawler.py stop
```

向 daemon 进程发送 SIGTERM，10s 内未退出则 SIGKILL。

### login - 手动登录

```bash
web_crawler.py login <site> [--timeout 300]
```

- `<site>`: `x`、`xiaohongshu`、`twitter` 或完整 URL
- **daemon 运行时**：在 daemon 浏览器中开新 tab，登录态自动持久化到 daemon profile，并导出 storage_state JSON 以兼容非 daemon 模式
- **daemon 未运行**：开一次性有头浏览器，关闭后保存 cookies/localStorage 到 `.browser-state/<site>.json`

### scrape - 抓取网页

```bash
web_crawler.py scrape <url> [options]
```

主要选项：
- `--format markdown|json`: 输出格式，默认 markdown
- `--output <file>`: 保存到文件
- `--site <site>`: 强制使用特定网站提取器
- `--scroll`: 滚动加载更多（无限滚动页面）
- `--scroll-count <n>`: 滚动次数，默认 5
- `--keep-tab`: daemon 模式下保留 tab 不关闭（便于调试）
- `--headed`: 非 daemon 模式下显示浏览器窗口（daemon 模式下无意义）

示例：
```bash
# Markdown 输出（daemon 运行时全程可见）
web_crawler.py scrape "https://x.com/user/status/123" --format markdown

# JSON 保存到文件
web_crawler.py scrape "https://www.xiaohongshu.com/explore/abc123" --format json --output result.json

# 滚动抓取搜索结果，保留 tab 便于查看
web_crawler.py scrape "https://x.com/search?q=AI" --scroll --scroll-count 10 --keep-tab
```

### screenshot - 截图

```bash
web_crawler.py screenshot <url> [--output <path>] [--keep-tab]
```

### states - 查看 daemon 状态与登录状态

```bash
web_crawler.py states
```

输出示例：
```
● Daemon: RUNNING (pid=12345, port=9222)

Browser states in '.browser-state/':
  ✓ x
      Cookies: 42, Origins: 3
      Size: 18.5 KB, Modified: 2026-06-13T10:00:00
```

### mine - X 内容挖掘（需 daemon 在运行）

X 站特化的两个挖掘子命令。所有挖掘都在可见的 daemon 浏览器里发生，时间过滤在客户端做（**不会**把 `since:`/`until:` 写进 X 搜索框，避免触发 X 极严的日期搜索导致 0 结果）。

#### `mine topic` — 按主题 + 时间段挖掘

```bash
web_crawler.py mine topic <query> [options]
```

主要选项：
- `--since YYYY-MM-DD` / `--until YYYY-MM-DD`：客户端日期过滤（包含端点）
- `--sort top|latest|both`：抓哪个 tab。默认 `both`，会依次打开 X 的 **Top** 和 **Latest** 两个 tab 滚动收集
- `--max-scrolls N`：每个 tab 滚动次数，默认 20
- `--top-n N`：输出前 N 条（按互动量降序），默认 20
- `--detail N`：**点进互动量 Top N 推文，捕获正文 + 同作者楼层 + 回复**
- `--expand`：额外尝试加引号的精确查询变体
- `--format markdown|json`，`--output <file>`

示例：
```bash
# 抓 "AI agent" 今天的内容，对热度 Top 3 点进去看回复
web_crawler.py mine topic "AI agent" \
  --since 2026-06-13 --until 2026-06-13 \
  --top-n 10 --detail 3 \
  --output /tmp/aiagent.md

# 只看最新（不要 Top）
web_crawler.py mine topic "agentic" --sort latest --max-scrolls 30
```

#### `mine following` — 挖掘关注流 / 推荐流

```bash
web_crawler.py mine following [--tab foryou|following] [options]
```

- `--tab foryou`（默认）：For You 推荐流；`following`：仅关注的人
- 其他参数与 `mine topic` 同（`--since/--until/--top-n/--detail/--max-scrolls`）
- 当 `--since` 指定后，连续滚到 8 条以上"早于 since"的推文会自动停止

示例：
```bash
# 看今天关注的人发了什么，按互动量排序，点进 Top 5 看详情
web_crawler.py mine following --tab following \
  --since 2026-06-13 --top-n 20 --detail 5 \
  --output /tmp/following_today.md
```

### detail - 单条推文展开

```bash
web_crawler.py detail <url-or-id> [--max-replies 30]
```

`<url-or-id>` 可以是完整 URL、`/user/status/123` 路径或纯数字 ID。捕获：主推文、同作者楼层（thread）、按互动量排序的 Top 回复。

```bash
web_crawler.py detail "https://x.com/freeCodeCamp/status/2065585204450775439"
web_crawler.py detail 2065585204450775439 --format json -o /tmp/detail.json
```

### xhs - 一键转小红书图文草稿（爆款公式自动套用）

抓取互联网内容 → 选 Top N 热门 → 下载媒体 + 截图 → 输出**小红书爆款图文草稿包**（已套用标题公式 + 正文框架 + 标签金字塔 + 推荐发布时间）。三种入口：

```bash
# 1) 按主题搜索 X
web_crawler.py xhs from-topic "AI agent" \
  --since 2026-06-13 --pick 3 --style aida --output-dir ./xhs_drafts

# 2) 从你的 Following / For You 流挑热帖
web_crawler.py xhs from-following --tab following \
  --since 2026-06-13 --pick 3 --style hook --output-dir ./xhs_drafts

# 3) 直接给若干 URL（X 推文或普通网页都支持）
web_crawler.py xhs from-url \
  "https://x.com/NBA/status/2065593744490172859" \
  "https://www.example.com/article" \
  --style scqa --output-dir ./xhs_drafts
```

通用参数：
- `--pick N`：转换前 N 条（按互动量降序）
- `--style {aida,scqa,pass,hook}`：正文框架，默认 `hook`
  - `aida` — Attention/Interest/Desire/Action，**适合产品 / 工具种草**
  - `scqa` — Situation/Complication/Question/Answer，**适合观点 / 深度内容**
  - `pass` — Problem/Agitate/Solution/Story，**适合解决方案 / 教程**
  - `hook` — 开篇钩子 + 短段落 + 金句收束，**适合资讯 / 热点搬运**（默认）
- `--max-scrolls N`：抓取阶段每个 tab 滚动次数
- `--output-dir <dir>`：输出根目录
- `--no-screenshot`：跳过推文卡片/页面截图（默认会截）

> **方法论参考**：完整爆款写作研究见 [`references/xhs_viral_playbook.md`](references/xhs_viral_playbook.md)（标题 5 大公式 / 4 种正文框架 / 三色封面法则 / CES 计算 / 品类×时段表 / 反漏斗选题）。

#### 输出结构

```
xhs_drafts/
├── manifest.json              # 全部 picks 元信息（title/tags/style/post_time/cover/...）
├── pick-01-<slug>/
│   ├── source.json            # 原始推文 / 网页数据
│   ├── draft.md               # 小红书风格草稿（标题+框架化正文+金字塔标签+推荐发布时间+图集说明）
│   └── images/
│       ├── img-01.jpg         # 原图（X 推文：自动取 name=orig 高清版）
│       ├── img-02.jpg
│       └── tweet-card.png     # 推文卡片截图（��作图集/封面）
├── pick-02-<slug>/...
└── pick-03-<slug>/...
```

`draft.md` 自动包含：
- **爆款公式标题**（按内容线索从 5 公式里选 1，含品类 emoji）
- **框架化正文**（按 `--style` 套 AIDA/SCQA/PASS/hook，段落 ≤3 行 + 空行分隔）
- **关注/收藏引导**（CES 关注权重 ×8，最高 ROI）
- **结尾开放问题**（CES 评论权重 ×4）
- **标签金字塔**（1 核心 + 2-3 长尾 + 3-5 广义，共 6-9 个）
- **推荐发布时间**（按品类查表）
- **图集顺序建议**（含三色法则提示）

**典型工作流**：daemon 已运行 → 跑 `xhs from-topic` 或 `from-following` → 看 `manifest.json` 选你最想发的那一篇 → 进 `pick-XX/` 目录润色 `draft.md`（人工微调标题字数/段落表达） → 拷贝标题/正文到小红书 + 上传图片，按草稿建议的时间发布。

## 状态持久化机制

两套并存的状态：

1. **daemon profile**（`.browser-state/.profile/`）：
   - Chrome 用户数据目录，cookies/localStorage/缓存自动持久
   - daemon 运行期间所有 tab 共享，自动复用
   - 跨 daemon 重启依然有效

2. **storage_state JSON**（`.browser-state/<site>.json`）：
   - Playwright 标准格式，仅 cookies + localStorage
   - 非 daemon 模式下用 `storage_state=` 加载
   - `login` 命令在 daemon 模式下也会同时导出一份，确保非 daemon 模式可用

### 重新登录

状态过期时，重新运行 login（推荐先启动 daemon）：
```bash
web_crawler.py login x
```

## 支持的网站

### X/Twitter
- URL 模式：`x.com`, `twitter.com`
- 自动提取：推文内容、作者、时间戳、互动数据、媒体
- 长推文/线程自动合并全文到 `full_text` 字段

### 小红书 (Xiaohongshu)
- URL 模式：`xiaohongshu.com`
- 自动提取：笔记标题、正文、图片、标签、互动数据

### 通用网站
- readability 风格主内容检测，自动提取标题/作者/日期/正文/图片/链接

## 决策流程

```
用户请求抓取
    │
    ├─ daemon 运行中? ── 是 ──> 复用浏览器开新 tab，用户可见
    │                  └─ 否 ──> 一次性 headless 浏览器（兼容模式）
    │
    └─ 需要登录?
         ├─ 有保存状态 ──> 加载状态抓取
         └─ 无         ──> 提示先 login
```

## 常见问题

1. **看不到爬取过程**：先在终端 A 运行 `web_crawler.py daemon`，再在终端 B 运��� scrape。daemon 未启动时 scrape 默认 headless。

2. **登录状态失效**：删除 `.browser-state/<site>.json`（如有需要也清空 `.browser-state/.profile/`），重新 login。

3. **daemon 启动失败 / 端口冲突**：换端口 `web_crawler.py daemon --port 9333`，scrape 会自动从 `.daemon.json` 读取端口。

4. **daemon 残留**：浏览器异常退出时，运行 `web_crawler.py stop` 清理状态文件。

5. **WSL2 环境**：daemon 模式需要 X 服务器（VcXsrv 或 WSLg）才能显示 Chrome 窗口。

6. **被网站检测**：daemon 模式下使用 Windows Chrome（非 Playwright Chromium），结合长驻 profile，反检测效果更好。

## 参考资料

- [网站选择器](references/site_selectors.md) - 各网站 CSS 选择器
- [反检测策略](references/anti_detection.md) - 防止被识别为机器人
- [输出格式](references/output_formats.md) - JSON/Markdown 格式详解
- [小红书爆款方法论](references/xhs_viral_playbook.md) - 完整的爆款写作指南