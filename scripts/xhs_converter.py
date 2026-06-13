"""Convert crawled content (tweets / web pages) into Xiaohongshu image+text drafts.

Each "pick" produces a directory:
    pick-NN/
      source.json      — original metadata
      draft.md         — XHS-style title/body/tags draft (viral-formula applied)
      images/          — downloaded media + optional screenshot

Viral methodology codified here is sourced from
`references/xhs_viral_playbook.md`. Keep this file aligned with the playbook.
"""

import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str, maxlen: int = 60) -> str:
    if not text:
        return "pick"
    text = re.sub(r"\s+", "-", text).strip("-")
    text = re.sub(r"[^\w一-鿿-]", "", text)
    return text[:maxlen] or "pick"


def normalize_twimg_url(url: str) -> str:
    """Force original-quality variant of a pbs.twimg.com media URL."""
    if "pbs.twimg.com/media" not in url:
        return url
    parsed = urlparse(url)
    qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    qs["name"] = "orig"
    qs.setdefault("format", "jpg")
    return parsed._replace(query=urlencode(qs)).geturl()


def download_url(url: str, dest: Path, timeout: int = 20) -> Path | None:
    """Download a URL to dest with browser-like headers. None on failure."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://x.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest
    except Exception as e:
        print(f"[download] FAIL {url}: {e}")
        return None


def screenshot_tweet_card(context, tweet_url: str, dest: Path) -> Path | None:
    """Open a tweet URL in the daemon and screenshot the article card."""
    page = context.new_page()
    try:
        page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        time.sleep(2)
        article = page.query_selector('article[data-testid="tweet"]')
        dest.parent.mkdir(parents=True, exist_ok=True)
        if article:
            article.screenshot(path=str(dest))
        else:
            page.screenshot(path=str(dest))
        return dest
    except Exception as e:
        print(f"[screenshot tweet] FAIL: {e}")
        return None
    finally:
        page.close()


def screenshot_page(context, url: str, dest: Path, full_page: bool = False) -> Path | None:
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        dest.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest), full_page=full_page)
        return dest
    except Exception as e:
        print(f"[screenshot page] FAIL: {e}")
        return None
    finally:
        page.close()


# ---------------------------------------------------------------------------
# Topic / emoji classification (also drives recommended posting time + tags)
# ---------------------------------------------------------------------------

# Each entry: (regex, emoji, category-key). category-key feeds tag pyramid &
# posting-time table below.
TOPIC_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"(NBA|篮球|总决赛|绝杀|comeback|knicks|spurs|世界杯|football)", re.I), "🏀", "sports"),
    (re.compile(r"\b(AI|agent|Agent|GPT|Claude|LLM|大模型|智能体|AGI)\b"), "🤖", "ai"),
    (re.compile(r"(rocket|SpaceX|Starship|Starlink|火箭|卫星|航天)", re.I), "🚀", "tech"),
    (re.compile(r"(crypto|web3|币|defi|NFT|金融|股票|投资|理财)", re.I), "💰", "finance"),
    (re.compile(r"(医疗|medical|healthcare|医生|健康|养生)", re.I), "🩺", "health"),
    (re.compile(r"(GitHub|开源|开发|coding|工具|tool|程序员)", re.I), "🛠️", "dev"),
    (re.compile(r"(美食|food|餐厅|料理|烘焙|探店)", re.I), "🍜", "food"),
    (re.compile(r"(穿搭|时尚|fashion|outfit|OOTD)", re.I), "👗", "fashion"),
    (re.compile(r"(旅行|旅游|travel|攻略)", re.I), "✈️", "travel"),
    (re.compile(r"(电影|movie|剧|film|追剧)", re.I), "🎬", "entertainment"),
    (re.compile(r"(职场|打工|加班|跳槽|副业|career)", re.I), "💼", "career"),
    (re.compile(r"(学习|考研|考试|学生|study)", re.I), "📚", "study"),
]

# Tag pyramid: (1 core, 2-3 long-tail, 3-5 broad). Joined into final tag list
# of 6-9 tags as the playbook prescribes.
TAG_PYRAMID: dict[str, dict] = {
    "sports":        {"core": "NBA",      "long": ["篮球分享", "今日体育", "赛事解读"],         "broad": ["热点", "干货分享", "运动"]},
    "ai":            {"core": "AI",       "long": ["AI Agent", "AI工具推荐", "效率工具"],      "broad": ["科技前沿", "打工人神器", "干货分享", "成长"]},
    "tech":          {"core": "硬核科技",  "long": ["SpaceX", "航天科技", "前沿科技"],          "broad": ["科技", "马斯克", "干货分享"]},
    "finance":       {"core": "投资",      "long": ["财经观察", "理财干货", "副业增收"],         "broad": ["搞钱", "成长", "干货分享"]},
    "health":        {"core": "健康科技",  "long": ["医疗AI", "养生日记", "自律生活"],          "broad": ["健康", "干货", "成长"]},
    "dev":           {"core": "GitHub",   "long": ["开源项目", "效率工具", "程序员日常"],        "broad": ["干货分享", "工具控", "AI工具"]},
    "food":          {"core": "美食分享",  "long": ["今日美食", "探店日记", "家常菜"],           "broad": ["生活", "种草", "好物分享"]},
    "fashion":       {"core": "穿搭",      "long": ["OOTD", "穿搭灵感", "时尚分享"],            "broad": ["种草", "生活方式", "好物分享"]},
    "travel":        {"core": "旅行攻略",  "long": ["小众旅行", "周末去哪儿", "旅行vlog"],       "broad": ["生活记录", "种草", "周末"]},
    "entertainment": {"core": "影视分享",  "long": ["追剧日记", "电影推荐", "剧荒"],             "broad": ["娱乐", "生活", "周末"]},
    "career":        {"core": "职场",      "long": ["打工人日常", "副业搞钱", "职场成长"],        "broad": ["干货分享", "成长", "搞钱"]},
    "study":         {"core": "学习方法",  "long": ["考试干货", "学生党必备", "高效学习"],        "broad": ["干货分享", "成长", "自律"]},
    "default":       {"core": "今日热点",  "long": ["每日分享", "热点观察", "好物推荐"],          "broad": ["分享", "生活记录", "成长"]},
}

# Recommended posting windows per the playbook (品类×时段表).
POSTING_TIMES: dict[str, str] = {
    "sports":        "赛事结束后 1-2 小时 / 工作日 22:00",
    "ai":            "工作日 07:30-09:00, 12:00-13:30, 周日晚 20:00-22:00",
    "tech":          "工作日 07:30-09:00, 12:00-13:30, 周日晚 20:00-22:00",
    "finance":       "工作日 07:30-09:00, 21:00-23:00",
    "health":        "工作日 09:30-11:00, 14:00-16:00",
    "dev":           "工作日 12:00-13:30, 21:00-23:00",
    "food":          "11:00-12:00, 17:00-19:00, 周末全天",
    "fashion":       "12:00-14:00, 21:00-23:00, 周五晚",
    "travel":        "周四 21:00-23:00, 周末上午",
    "entertainment": "20:00-23:00, 周末全天",
    "career":        "工作日 07:30-09:00, 12:00-13:30",
    "study":         "工作日 19:00-22:00, 周日晚",
    "default":       "工作日 12:00-13:30, 21:00-23:00",
}


def classify_topic(text: str) -> tuple[str, str]:
    """Return (emoji, category-key) based on keyword match."""
    for pat, emoji, key in TOPIC_RULES:
        if pat.search(text or ""):
            return emoji, key
    return "✨", "default"


# ---------------------------------------------------------------------------
# Title formulas — five viral templates from the playbook
# ---------------------------------------------------------------------------

def _truncate(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _first_meaningful_line(text: str, maxlen: int = 18) -> str:
    parts = re.split(r"[。！？.!?\n]", text or "", maxsplit=1)
    return _truncate(parts[0].strip(), maxlen)


def make_title(text: str, author: str = "", category: str = "default",
               emoji: str = "✨") -> str:
    """Pick a viral-formula title from 5 templates based on cues in `text`.

    Order of preference (each gated by a content cue):
      1. 数字+痛点+方案     — text 中含数字
      2. 反常识+悬念        — text 含 "其实/原来/反而/不是" 等转折词
      3. 实测+结果         — text 含 "亲测/实测/试了/用了 N 天"
      4. 对比+反差         — text 含 "从...到..." 或大量数字对比
      5. 人群标签+解决（兜底）
    """
    src = text or ""
    head = _first_meaningful_line(src, maxlen=16)

    # 1) 数字+痛点+方案
    m = re.search(r"(\d{1,3})\s*(?:个|条|招|步|天|小时|倍|%)", src)
    if m:
        head_short = _truncate(head, 14) if head else "技巧"
        return f"{emoji} {m.group(1)} 个{head_short}，看完直接收藏"

    # 2) 反常识 / 悬念
    if re.search(r"(其实|原来|反而|不是.*而是|没想到|99%)", src):
        return f"{emoji} 不是你想的那样，{_truncate(head, 14)}"

    # 3) 实测 / 结果
    if re.search(r"(亲测|实测|试了|用了|测试)", src):
        return f"{emoji} 亲测有效｜{_truncate(head, 16)}"

    # 4) 对比 / 反差
    if re.search(r"从.{1,8}到.{1,8}", src) or src.count("→") + src.count("->") >= 1:
        return f"{emoji} {_truncate(head, 18)}，反差太大了"

    # 5) 人群标签+解决（按 category 选人群词）
    AUDIENCE = {
        "ai": "打工人", "dev": "程序员", "tech": "科技党", "finance": "搞钱党",
        "career": "打工人", "study": "学生党", "health": "自律党",
        "food": "吃货", "fashion": "时尚党", "travel": "旅行党",
        "entertainment": "追剧党", "sports": "球迷",
    }
    audience = AUDIENCE.get(category, "i人")
    if head:
        return f"{emoji} {audience}必看｜{_truncate(head, 16)}"
    return f"{emoji} {audience}必看的今日热点"


# ---------------------------------------------------------------------------
# Body frameworks — AIDA / SCQA / PASS / hook
# ---------------------------------------------------------------------------

def _split_paragraphs(text: str, maxlen_per_para: int = 90) -> list[str]:
    """Split text into XHS-friendly short paragraphs (≤3 lines each)."""
    raw = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out: list[str] = []
    for p in raw:
        # If a single paragraph is too long, soft-split on sentence boundaries.
        if len(p) <= maxlen_per_para:
            out.append(p)
            continue
        sentences = re.split(r"(?<=[。！？.!?])\s*", p)
        buf = ""
        for s in sentences:
            if not s:
                continue
            if len(buf) + len(s) > maxlen_per_para and buf:
                out.append(buf.strip())
                buf = s
            else:
                buf += s
        if buf.strip():
            out.append(buf.strip())
    return out


def _comment_hook(category: str) -> str:
    HOOKS = {
        "ai":      "💬 你最近在用哪个 AI 工具？评论区分享一下～",
        "dev":     "💬 你的常用工具栈是什么？评论区交流",
        "tech":    "💬 你怎么看？评论区留下你的观点",
        "finance": "💬 你最近在关注哪个赛道？评论区聊聊",
        "career":  "💬 你遇到过类似的职场问题吗？评论区抱团",
        "study":   "💬 你的学习方法是什么？评论区互相借鉴",
        "health":  "💬 你的自律习惯有哪些？评论区分享",
        "food":    "💬 最近吃到的最爱是什么？评论区种草",
        "fashion": "💬 你最爱的穿搭风格是？评论区聊聊",
        "travel":  "💬 你最想去的地方是？评论区写下来",
        "entertainment": "💬 最近追的剧/电影是？评论区互相安利",
        "sports":  "💬 你怎么看这场？评论区开聊",
        "default": "💬 你怎么看？评论区聊聊～",
    }
    return HOOKS.get(category, HOOKS["default"])


def _action_call(category: str) -> str:
    """Closing line that drives follows + saves (CES weights: 关注×8 收藏×1)."""
    return ("👉 持续更新这个系列，关注不迷路 ✨\n"
            "🔖 觉得有用的话，先收藏再看，别让算法把它从你信息流冲走")


def _build_body(style: str, source_text: str, source_label: str,
                metrics: list[str], url: str, category: str, emoji: str,
                title_hint: str = "") -> str:
    paras = _split_paragraphs(source_text, maxlen_per_para=100)[:6]
    style = (style or "hook").lower()

    if style == "aida":
        lines = [
            f"{emoji} 看到这条内容的瞬间，我愣了 3 秒",
            "",
            "因为它戳中了我最近一直在思考的事情👇",
            "",
        ]
        for p in paras:
            lines += [p, ""]
        lines += [
            "—",
            "",
            f"我的几点收获：",
            "",
            "1️⃣ 这件事比想象中更值得关注",
            "2️⃣ 普通人也能用得上",
            "3️⃣ 越早知道越好",
            "",
        ]
    elif style == "scqa":
        lines = [
            f"{emoji} 现在大家都在聊这个话题",
            "",
            "但仔细看完原文，我发现一个被忽略的关键点👇",
            "",
        ]
        for p in paras:
            lines += [p, ""]
        lines += [
            "—",
            "",
            "那应该怎么看？我的解读是：",
            "",
            "→ 表层是热点，里层其实是趋势",
            "→ 与其追新闻，不如盯方向",
            "",
        ]
    elif style == "pass":
        lines = [
            f"{emoji} 你是不是也有过这种感觉？",
            "",
            "信息太多、变化太快，每天都在被推着走😮‍💨",
            "",
            "下面这条内容，可能是这周最值得花 1 分钟看的👇",
            "",
        ]
        for p in paras:
            lines += [p, ""]
        lines += [
            "—",
            "",
            "我的解法很简单：",
            "",
            "✅ 用 5 分钟搞清楚事情本身",
            "✅ 用 5 分钟想清楚和我有什么关系",
            "✅ 用 5 分钟决定要不要 follow up",
            "",
        ]
    else:  # hook  (default — best for 资讯/转发型)
        lines = [
            f"{emoji} 刚刷到一条让我停下手指的内容",
            "",
            "看完之后越想越有意思，所以决定搬过来分享👇",
            "",
        ]
        for p in paras:
            lines += [p, ""]
        lines += ["—", ""]

    # Common footer (source + metrics + CTA + comment hook)
    lines.append(f"📍 来源：{source_label}")
    if metrics:
        lines.append(f"📊 互动数据：{' · '.join(metrics)}")
    if url:
        lines.append(f"🔗 {url}")
    lines += [
        "",
        _action_call(category),
        "",
        _comment_hook(category),
    ]
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Tags + posting time
# ---------------------------------------------------------------------------

def build_tag_pyramid(text: str, category: str) -> list[str]:
    """1 core + 2-3 long-tail + 3-5 broad, dedup, total 6-9.

    Inline `#话题` from source text takes priority for the core slot.
    """
    explicit = list(dict.fromkeys(re.findall(r"#([\w一-鿿]+)", text or "")))
    pyramid = TAG_PYRAMID.get(category, TAG_PYRAMID["default"])
    tags: list[str] = []

    # Core: prefer explicit topic word from source, else pyramid core.
    if explicit:
        tags.append(explicit[0])
    else:
        tags.append(pyramid["core"])

    # Long-tail: up to 3, mix explicit (skip first, already used) + pyramid long
    for t in (explicit[1:4] + pyramid["long"]):
        if t not in tags:
            tags.append(t)
        if len(tags) >= 4:  # 1 core + 3 long
            break

    # Broad: top up to 8 total
    for t in pyramid["broad"]:
        if t not in tags:
            tags.append(t)
        if len(tags) >= 8:
            break

    return tags[:9]


def recommended_posting_time(category: str) -> str:
    return POSTING_TIMES.get(category, POSTING_TIMES["default"])


# ---------------------------------------------------------------------------
# Draft assembly
# ---------------------------------------------------------------------------

def _format_metrics(item: dict) -> list[str]:
    metrics = []
    if item.get("likes"):
        metrics.append(f"❤️ {item['likes']:,}")
    if item.get("retweets"):
        metrics.append(f"🔁 {item['retweets']:,}")
    if item.get("replies"):
        metrics.append(f"💬 {item['replies']:,}")
    if item.get("views"):
        metrics.append(f"👁 {item['views']:,}")
    return metrics


def make_xhs_draft_from_tweet(tweet: dict, style: str = "hook") -> dict:
    text = (tweet.get("text") or "").strip()
    author = tweet.get("author") or ""
    handle = tweet.get("handle") or ""
    url = tweet.get("url") or ""

    emoji, category = classify_topic(f"{text} {author}")
    title = make_title(text, author=author, category=category, emoji=emoji)
    metrics = _format_metrics(tweet)
    source_label = f"X / {author} {handle}".strip()
    body = _build_body(style, text, source_label, metrics, url, category, emoji,
                       title_hint=title)
    tags = build_tag_pyramid(text, category)
    return {
        "title": title,
        "body": body,
        "tags": tags,
        "emoji": emoji,
        "category": category,
        "style": style,
        "post_time": recommended_posting_time(category),
    }


def make_xhs_draft_from_page(page_data: dict, style: str = "hook") -> dict:
    title_raw = page_data.get("title") or ""
    text = page_data.get("content_text") or ""
    author = page_data.get("author") or ""
    url = page_data.get("url") or ""

    emoji, category = classify_topic(f"{title_raw} {text}")
    # Feed both title and body intro into title selector so cues like
    # "其实/原来/N 倍/亲测" in the body still trigger the right formula.
    title_seed = f"{title_raw}\n\n{text[:200]}" if text else title_raw
    title = make_title(title_seed, author=author, category=category, emoji=emoji)
    source_label = author or (urlparse(url).hostname or "网络文章")
    # Trim long body to the AIDA/SCQA/PASS-friendly length (3-6 paragraphs).
    body_text = "\n\n".join(_split_paragraphs(text, maxlen_per_para=120)[:6])
    body = _build_body(style, body_text, source_label, [], url, category, emoji,
                       title_hint=title)
    tags = build_tag_pyramid(f"{title_raw} {text}", category)
    return {
        "title": title,
        "body": body,
        "tags": tags,
        "emoji": emoji,
        "category": category,
        "style": style,
        "post_time": recommended_posting_time(category),
    }


# ---------------------------------------------------------------------------
# Pick assembly
# ---------------------------------------------------------------------------

def _write_draft_md(pick_dir: Path, draft: dict, cover: str | None,
                    images: list[str], source_label: str) -> None:
    lines = [
        f"# {draft['title']}",
        "",
        f"> 小红书图文草稿（{source_label}）— 框架: **{draft.get('style','hook').upper()}** · 品类: **{draft.get('category','default')}**",
        f"> 发布前请人工润色；爆款方法论参考 `references/xhs_viral_playbook.md`",
        "",
    ]
    if cover:
        lines += [f"**封面图**：`{cover}`", "", f"![cover]({cover})", ""]

    lines += ["## 正文", "", draft["body"], ""]
    lines += ["## 标签（金字塔：1 核心 + 长尾 + 广义）", ""]
    lines.append(" ".join(f"#{t}" for t in draft["tags"]))
    lines += ["", "## 推荐发布时间", "", f"⏰ {draft.get('post_time','')}", ""]

    if images:
        lines += ["## 图集顺序建议", ""]
        for i, p in enumerate(images, 1):
            lines.append(f"{i}. `{p}`")
        lines += [
            "",
            "> 第 1 张是封面，遵守三色法则（主色 70% / 辅色 25% / 点缀 5%），核心信息放中心或右上。",
        ]

    (pick_dir / "draft.md").write_text("\n".join(lines), encoding="utf-8")


def prepare_pick_from_tweet(tweet: dict, output_dir: Path, idx: int = 1,
                            screenshot: bool = False, context=None,
                            style: str = "hook") -> dict:
    pick_dir = output_dir / f"pick-{idx:02d}-{slugify(tweet.get('handle','') or tweet.get('id',''), 20)}"
    img_dir = pick_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    (pick_dir / "source.json").write_text(
        json.dumps(tweet, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    downloaded: list[str] = []
    for i, m in enumerate((tweet.get("media") or []), 1):
        if m.get("type") != "image" or not m.get("url"):
            continue
        dest = img_dir / f"img-{i:02d}.jpg"
        if download_url(normalize_twimg_url(m["url"]), dest):
            downloaded.append(str(dest.relative_to(pick_dir)))

    screenshot_rel = None
    if screenshot and context and tweet.get("url"):
        dest = img_dir / "tweet-card.png"
        if screenshot_tweet_card(context, tweet["url"], dest):
            screenshot_rel = str(dest.relative_to(pick_dir))

    draft = make_xhs_draft_from_tweet(tweet, style=style)
    images = list(dict.fromkeys(downloaded + ([screenshot_rel] if screenshot_rel else [])))
    cover = images[0] if images else None

    _write_draft_md(pick_dir, draft, cover, images,
                    source_label=f"X / @{tweet.get('handle','').lstrip('@')}")

    return {
        "idx": idx, "pick_dir": str(pick_dir), "source": tweet,
        "draft": draft, "images": images, "cover": cover,
    }


def prepare_pick_from_page(page_data: dict, output_dir: Path, idx: int = 1,
                           screenshot: bool = True, context=None,
                           style: str = "hook") -> dict:
    pick_dir = output_dir / f"pick-{idx:02d}-{slugify(page_data.get('title',''), 30)}"
    img_dir = pick_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    (pick_dir / "source.json").write_text(
        json.dumps(page_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    downloaded: list[str] = []
    for i, m in enumerate((page_data.get("images") or []), 1):
        url = m.get("url") if isinstance(m, dict) else m
        if not url:
            continue
        ext = ".jpg"
        if any(url.lower().endswith(e) for e in (".png", ".webp", ".gif", ".jpeg", ".jpg")):
            ext = "." + url.rsplit(".", 1)[-1].split("?")[0].lower()
            if ext == ".jpeg":
                ext = ".jpg"
        dest = img_dir / f"img-{i:02d}{ext}"
        if download_url(url, dest):
            downloaded.append(str(dest.relative_to(pick_dir)))
        if i >= 9:
            break

    screenshot_rel = None
    if screenshot and context and page_data.get("url"):
        dest = img_dir / "page.png"
        if screenshot_page(context, page_data["url"], dest, full_page=False):
            screenshot_rel = str(dest.relative_to(pick_dir))

    draft = make_xhs_draft_from_page(page_data, style=style)
    images = list(dict.fromkeys(downloaded + ([screenshot_rel] if screenshot_rel else [])))
    cover = images[0] if images else None

    _write_draft_md(pick_dir, draft, cover, images,
                    source_label=urlparse(page_data.get("url","")).hostname or "web")

    return {
        "idx": idx, "pick_dir": str(pick_dir), "source": page_data,
        "draft": draft, "images": images, "cover": cover,
    }


def write_manifest(output_dir: Path, source_meta: dict, picks: list[dict]) -> Path:
    payload = {
        **source_meta,
        "created_at": time.time(),
        "picks": [
            {
                "idx": p["idx"],
                "pick_dir": p["pick_dir"],
                "title": p["draft"]["title"],
                "tags": p["draft"]["tags"],
                "style": p["draft"].get("style"),
                "category": p["draft"].get("category"),
                "post_time": p["draft"].get("post_time"),
                "cover": p.get("cover"),
                "image_count": len(p.get("images") or []),
            }
            for p in picks
        ],
    }
    path = output_dir / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
