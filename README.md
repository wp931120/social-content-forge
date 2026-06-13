# Social Content Forge — 社媒内容锻造

从互联网收集热门信息，自动整理成小红书 / 微博 / 公众号爆款图文草稿。

[English](#english) | 中文

---

## ✨ 核心能力

| 能力 | 说明 |
|------|------|
| **信息采集** | 从 X/Twitter、小红书、任意网页抓取热门内容 |
| **Daemon 模式** | 浏览器进程常驻，整个会话期间可见，登录态自动复用 |
| **爆款文案生成** | 自动套用 AIDA/SCQA/PASS/hook 正文框架 |
| **标题公式** | 自动从 5 大爆款标题公式中选取最匹配的 |
| **标签金字塔** | 自动生成 1 核心 + 2-3 长尾 + 3-5 广义标签（6-9 个） |
| **CES 互动优化** | 结尾强制开放问题 + 关注/收藏引导（权重×4/×8） |
| **推荐发布时间** | 按内容品类自动给出黄金发布时段 |

> **完整爆款方法论** 见 [`references/xhs_viral_playbook.md`](references/xhs_viral_playbook.md)

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# Python 环境（推荐 miniconda）
/mnt/d/wsl/miniconda3/bin/python -m pip install -r requirements.txt
/mnt/d/wsl/miniconda3/bin/python -m playwright install chromium
```

### 2. 启动 Daemon 浏览器

```bash
# 终端 A：启动可视浏览器（前台运行）
/mnt/d/wsl/miniconda3/bin/python scripts/web_crawler.py daemon
```

### 3. 登录账号（仅首次）

```bash
# 终端 B：在 daemon 浏览器中手动登录
/mnt/d/wsl/miniconda3/bin/python scripts/web_crawler.py login x
```

### 4. 开始采集 + 生成小红书草稿

```bash
# 按主题搜索 X，生成 3 篇小红书草稿
/mnt/d/wsl/miniconda3/bin/python scripts/web_crawler.py xhs from-topic "AI Agent" \
  --since 2026-06-13 --pick 3 --style hook --output-dir ./xhs_drafts

# 从你的关注流采集
/mnt/d/wsl/miniconda3/bin/python scripts/web_crawler.py xhs from-following \
  --tab following --pick 2 --output-dir ./xhs_drafts

# 直接把推文/网页转成小红书
/mnt/d/wsl/miniconda3/bin/python scripts/web_crawler.py xhs from-url \
  "https://x.com/username/status/123456789" \
  --style scqa --output-dir ./xhs_drafts
```

---

## 📖 命令参考

### 核心命令

| 命令 | 说明 |
|------|------|
| `daemon` | 启动长驻可视浏览器 |
| `stop` | 停止 daemon |
| `login <site>` | 手动登录（x / xiaohongshu / twitter） |
| `scrape <url>` | 抓取网页内容 |
| `states` | 查看 daemon 和登录状态 |

### 内容挖掘（X）

| 命令 | 说明 |
|------|------|
| `mine topic <query>` | 按主题挖掘，指定日期范围 |
| `mine following` | 挖掘关注流 / For You 流 |
| `detail <url-or-id>` | 点进单条推文，捕获全文 + 回复 |

### 小红书生成

```bash
# xhs from-topic    — 按主题搜索 X，转小红书
# xhs from-following — 从关注流转小红书
# xhs from-url      — 直接把 URL 转小红书
```

**通用参数**：
- `--pick N` — 转换前 N 条（按互动量降序）
- `--style {aida,scqa,pass,hook}` — 正文框架
- `--since YYYY-MM-DD` / `--until YYYY-MM-DD` — 日期过滤
- `--max-scrolls N` — 滚动次数
- `--output-dir <dir>` — 输出目录
- `--no-screenshot` — 跳过截图

---

## 📂 输出结构

```
xhs_drafts/
├── manifest.json              # 全部 picks 元信息
├── pick-01-<slug>/
│   ├── source.json            # 原始数据（推文/网页）
│   ├── draft.md               # 小红书草稿（已套爆款公式）
│   └── images/
│       ├── img-01.jpg         # 原图
│       └── tweet-card.png     # 推文截图（封面）
├── pick-02-...
└── pick-03-...
```

`draft.md` 包含：
- 爆款标题（5 选 1）
- 框架化正文（AIDA/SCQA/PASS/hook）
- 标签金字塔（6-9 个）
- 推荐发布时间
- CES 互动引导
- 图集顺序建议

---

## 🔧 环境要求

- **Python**: 3.10+
- **依赖**: 见 `requirements.txt`
- **浏览器**: Chrome/Chromium（daemon 模式推荐 Windows Chrome + WSL2）
- **WSL2**: 需要 X 服务器（VcXsrv 或 WSLg）才能显示可视浏览器

---

## 📦 项目结构

```
social-content-forge/
├── SKILL.md                    # Skill 定义（触发词 + 完整文档）
├── README.md                   # 本文件
├── requirements.txt            # Python 依赖
├── scripts/
│   ├── web_crawler.py          # CLI 入口
│   ├── x_mine.py               # X 内容挖掘模块
│   ├── xhs_converter.py        # 小红书草稿生成器
│   └── browser_state.py        # 浏览器状态管理
├── references/
│   ├── xhs_viral_playbook.md   # 小红书爆款方法论完整版
│   ├── site_selectors.md       # 网站 CSS 选择器
│   ├── anti_detection.md       # 反检测策略
│   └── output_formats.md       # 输出格式说明
├── configs/
│   └── sites.json              # 站点配置
└── templates/
    ├── batch_crawl.py          # 批量抓取模板
    ├── crawl_task.py           # 任务模板
    └── monitor_changes.py      # 变更监控模板
```

---

## 🐛 常见问题

**Q: 看不到爬取过程**
> 先运行 `daemon` 启动可视浏览器，再在另一个终端运行 scrape

**Q: 登录态失效**
> 删除 `.browser-state/<site>.json`，重新运行 `login <site>`

**Q: daemon 端口冲突**
> 使用 `daemon --port 9333` 换端口

**Q: WSL2 无可视化**
> 需要安装 X 服务器（VcXsrv 或启用 WSLg）

---

## 📜 License

MIT License — 可免费商用，欢迎 Star ⭐

---

## English

**Social Content Forge** collects trending content from the web (X/Twitter, Xiaohongshu, any website) and automatically transforms it into viral social media posts (Xiaohongshu, Weibo, etc.).

**Key Features**:
- Playwright-based crawler with persistent daemon browser
- Auto-applies viral writing frameworks (AIDA/SCQA/PASS/hook)
- 5 title formulas + tag pyramid + CES interaction optimization
- Works on WSL2 + Windows Chrome or Linux/WSL with X server

**Quick Start**:
```bash
# Install
pip install -r requirements.txt
playwright install chromium

# Run daemon
python scripts/web_crawler.py daemon

# Login (once)
python scripts/web_crawler.py login x

# Generate Xiaohongshu drafts
python scripts/web_crawler.py xhs from-topic "AI Agent" --pick 3 --style hook
```

See `SKILL.md` for complete documentation.