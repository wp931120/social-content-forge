---
name: social-content-forge
description: "社媒内容锻造 skill：从互联网（X/Twitter、网页、小红书）收集热门信息，生成可直接发布的社媒爆款文案。主 Agent 参考 playbook 直接生成文案。触发词：社媒内容、热点转图文、内容整理、社媒文案、小红书草稿、爆款笔记、xhs、内容采集、信息收集、爬虫抓取、内容forge、convert to social、daemon、browser state。"
---

# Social Content Forge — 社媒内容锻造

使用 Playwright 从互联网收集热门内容，**主 Agent 直接参考爆款方法论文档生成高质量社媒文案**。

**默认推荐 daemon 模式**：让浏览器进程一直存在，用户可以全程看到爬取过程，每次抓取只新开/关闭 tab，不重启浏览器。

## 爆款方法论文档（Agent 生成文案时参考）

> 生成文案时，Agent 必须先读取对应的 playbook 文件，按其规则生成内容。

| 平台 | Playbook 文件 | 核心内容 |
|------|--------------|----------|
| 小红书 | [`references/xhs_viral_playbook.md`](references/xhs_viral_playbook.md) | 标题 5 大公式 / 正文 4 框架 / CES 互动 / 标签金字塔 / 发布时间 / 封面三色法则 |
| 微信公众号 | [`references/wechat_viral_playbook.md`](references/wechat_viral_playbook.md) | 标题 6 大公式 / 开头 12 种技巧 / 正文 4 框架 / 结尾互动 / 发布时间 / 格式硬指标 |
| 去 AI 味 | [`references/de_ai_playbook.md`](references/de_ai_playbook.md) | AI 文字特征检测 / 去过渡词 / 破句式 / 加个人痕迹 / 添细节 |

### 小红书爆款速查

- **算法**：阶梯式流量池（200→5k→50k→爆款）。CES = `点赞×1 + 收藏×1 + 评论×4 + 转发×4 + 关注×8`。正文末尾**必须**有开放问题 + 关注/收藏引导。
- **标题公式**（按内容线索选 1）：
  1. `数字+痛点+方案`（"3 个 X，让你 Y"）
  2. `反常识+悬念`（"不是 X，而是 Y"）
  3. `实测+结果`（"亲测 N 天 ___"）
  4. `对比+反差`（"从 X 到 Y"）
  5. `人群标签+解决`（"打工人必看｜___"）
- **正文框架**：AIDA / SCQA / PASS / hook（根据内容类型选）
- **标签金字塔**：1 核心 + 2-3 长尾 + 3-5 广义 = 6-9 个
- **发布时间**：AI/职场 7:30-9:00 / 12:00-13:30；美食 11-12 / 17-19；学习 19-22
- **格式**：标题 18-22 字 / 段落 ≤3 行 / 段间空行 / 总字数 300-800 / 末尾 emoji + 开放问题

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

# 终端 B —— 在 daemon 浏览器中登录，登录态持久保存到 daemon profile
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py login x

# 终端 B —— 抓取（复用 daemon 浏览器，用户全程可见）
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py scrape "https://x.com/user/status/123" --format markdown

# 完成后关闭 daemon
/mnt/d/wsl/miniconda3/bin/python .claude/skills/social-content-forge/scripts/web_crawler.py stop
```

`scrape` / `login` / `screenshot` 会自动检测 daemon 是否运行：
- **daemon 运行中**：在已可见的浏览器中开新 tab 执行任务，结束后只关闭 tab，浏览器进程保留
- **daemon 未运行**：回退到一次性 headless 浏览器

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

### login - 手动登录

```bash
web_crawler.py login <site> [--timeout 300]
```

- `<site>`: `x`、`xiaohongshu`、`twitter` 或完整 URL
- 登录态自动持久化到 daemon profile

### scrape - 抓取网页

```bash
web_crawler.py scrape <url> [options]
```

主要选项：
- `--format markdown|json`: 输出格式
- `--output <file>`: 保存到文件
- `--scroll`: 滚动加载更多
- `--keep-tab`: daemon 模式下保留 tab

### screenshot - 截图

```bash
web_crawler.py screenshot <url> [--output <path>]
```

### states - 查看 daemon 状态与登录状态

```bash
web_crawler.py states
```

### mine - X 内容挖掘

```bash
# 按主题挖掘
web_crawler.py mine topic "AI agent" --since 2026-06-13 --top-n 10 --detail 3

# 挖掘关注流
web_crawler.py mine following --tab following --since 2026-06-13 --top-n 20
```

### detail - 单条推文展开

```bash
web_crawler.py detail <url-or-id> [--max-replies 30]
```

### extract - 抓取并提取内容（推荐工作流）

```bash
# 抓取 X 推文并提取正文
web_crawler.py extract "https://x.com/user/status/123456" --format json -o tweet.json

# 抓取网页并提取正文
web_crawler.py extract "https://example.com/article" --format markdown -o article.md
```

> 抓取内容后，**由主 Agent 参考 playbook 直接生成社媒文案**，不再使用 converter 脚本。

## 支持的网站

### X/Twitter
- 自动提取：推文内容、作者、时间戳、互动数据、媒体
- 长推文/线程自动合并全文

### 小红书
- 自动提取：笔记标题、正文、图片、标签、互动数据

### 通用网站
- readability 风格主内容检测

## 常见问题

1. **看不到爬取过程**：先运行 `daemon`，再在另一个终端运行 scrape

2. **登录态失效**：删除 `.browser-state/<site>.json`，重新 login

3. **daemon 端口冲突**：使用 `--port 9333` 换端口

4. **WSL2 无可视化**：需要 X 服务器（VcXsrv 或 WSLg）

## 参考资料

- [小红书爆款方法论](references/xhs_viral_playbook.md)
- [微信公众号爆款方法论](references/wechat_viral_playbook.md)
- [去 AI 味写作指南](references/de_ai_playbook.md)
- [网站选择器](references/site_selectors.md)
- [反检测策略](references/anti_detection.md)
- [输出格式](references/output_formats.md)