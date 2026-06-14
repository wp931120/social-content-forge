---
name: social-content-forge
description: "社媒内容锻造 skill：从互联网（X/Twitter、网页、小红书）收集热门信息，生成可直接发布的社媒爆款文案。触发词：社媒内容、热点转图文、小红书草稿、爆款笔记、内容采集、信息收集、爬虫抓取、daemon。"
---

# Social Content Forge — 社媒内容锻造

从互联网收集热门信息，生成可直接发布的社媒爆款文案。

## 前置要求

### 1. 环境安装

```bash
# 安装 Python 3.10+（推荐 conda/venv）
# 安装依赖
pip install playwright playwright-stealth html2text readability-lxml
playwright install chromium
```

### 2. 工作目录

```
skill 根目录/
├── workspace/                  # 内容生产输出目录
│   ├── drafts/                 # 草稿
│   │   ├── xhs/                # 小红书草稿
│   │   └── wechat/             # 微信公众号草稿
│   ├── published/              # 已发布内容
│   └── assets/                 # 图片等素材
└── ...
```

**约束**：所有抓取输出必须保存到 `workspace/` 目录，禁止输出到 skill 外部。

## 核心命令

> **本机 Python 环境**：使用 skill 目录下的 venv `.venv/bin/python`（已预装 playwright + chromium）。

```bash
cd ~/.agents/skills/social-content-forge

# 启动浏览器（推荐 daemon 模式）
.venv/bin/python scripts/web_crawler.py daemon

# 登录（仅首次）
.venv/bin/python scripts/web_crawler.py login x

# 抓取
.venv/bin/python scripts/web_crawler.py scrape <url>
.venv/bin/python scripts/web_crawler.py mine topic "关键词" --since 2026-06-13
.venv/bin/python scripts/web_crawler.py detail <tweet_url>
```

## 工作流

```
抓取内容 → Agent 参考 playbook 生成初稿 → 用 de_ai_playbook 去 AI 味 → 保存到 workspace/
```

## Playbooks

| 文件 | 用途 |
|------|------|
| `references/xhs_viral_playbook.md` | 小红书爆款文案 |
| `references/wechat_viral_playbook.md` | 微信公众号爆款文案 |
| `references/de_ai_playbook.md` | 去 AI 味道 |

---

## 常见问题

1. **看不到爬取过程**：先运行 `daemon`，再运行抓取命令
2. **登录态失效**：删除 `.browser-state/<site>.json`，重新 `login`
3. **daemon 端口冲突**：使用 `--port 9333` 换端口
4. **WSL2 无可视化**：需要 X 服务器（VcXsrv 或 WSLg）