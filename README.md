# Social Content Forge — 社媒内容锻造

从互联网收集热门信息，生成可直接发布的社媒爆款文案。

---

## 前置要求

### 1. 环境安装

```bash
# 安装 Python 3.10+（推荐 conda/venv）
pip install -r requirements.txt
playwright install chromium
```

### 2. 工作目录

```
skill 根目录/
├── workspace/                  # 内容生产输出目录
│   ├── drafts/
│   │   ├── xhs/
│   │   └── wechat/
│   ├── published/
│   └── assets/
└── ...
```

---

## 快速开始

```bash
# 启动浏览器
python scripts/web_crawler.py daemon

# 登录（仅首次）
python scripts/web_crawler.py login x

# 抓取内容
python scripts/web_crawler.py scrape "https://x.com/search?q=AI&f=top"
python scripts/web_crawler.py mine topic "AI" --since 2026-06-13
```

---

## 工作流

```
抓取内容 → Agent 参考 playbook 生成��稿 → 用 de_ai_playbook 去 AI 味 → 保存到 workspace/
```

---

## Playbooks

| 文件 | 用途 |
|------|------|
| `references/xhs_viral_playbook.md` | 小红书爆款文案 |
| `references/wechat_viral_playbook.md` | 微信公众号爆款文案 |
| `references/de_ai_playbook.md` | 去 AI 味道 |

---

## 环境

- Python 3.10+
- WSL2 + X 服务器（或 Linux + X）

---

## License

MIT