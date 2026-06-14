"""X/Twitter content mining: topic search, following feed, tweet detail.

All functions take a Playwright `context` (typically the daemon's CDP context)
so the user can watch the crawl happen in the visible browser.
"""

import json
import random
import re
import time
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import Iterable
from urllib.parse import quote


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_count(s: str) -> int:
    """Parse '1.2K' / '3.4M' / '123,456' to int."""
    if not s:
        return 0
    s = s.strip().replace(",", "")
    m = re.search(r"([\d.]+)\s*([KMB]?)", s, re.I)
    if not m:
        return 0
    v = float(m.group(1))
    suf = (m.group(2) or "").upper()
    return int(v * {"K": 1e3, "M": 1e6, "B": 1e9}.get(suf, 1))


def _metric(tweet_el, testid: str) -> int:
    el = tweet_el.query_selector(f'[data-testid="{testid}"]')
    if not el:
        return 0
    label = el.get_attribute("aria-label") or el.inner_text() or ""
    return _parse_count(label)


def _views(tweet_el) -> int:
    vl = tweet_el.query_selector('a[href*="/analytics"]')
    if not vl:
        return 0
    return _parse_count(vl.get_attribute("aria-label") or "")


def _author_handle(tweet_el) -> tuple[str, str]:
    user_el = tweet_el.query_selector('[data-testid="User-Name"]')
    if not user_el:
        return "", ""
    parts = [s.strip() for s in user_el.inner_text().split("\n") if s.strip()]
    name = parts[0] if parts else ""
    handle = next((p for p in parts if p.startswith("@")), "")
    return name, handle


def _expand_show_more(tweet_el):
    """Click any 'Show more' / '显示更多' link inside the tweet so its full
    text is rendered before extraction. Silent if not present."""
    try:
        for sel in ('[data-testid="tweet-text-show-more-link"]',
                    'div[role="button"][data-testid$="show-more-link"]'):
            btn = tweet_el.query_selector(sel)
            if btn:
                btn.click()
                time.sleep(0.5)
                return
    except Exception:
        pass


def _tweet_text_robust(tweet_el) -> str:
    """Robust tweet body extraction with multiple fallbacks.

    Why: on long tweets, quote-tweets, or thread continuations the standard
    `[data-testid="tweetText"]` selector sometimes misses the body — usually
    because the text is split across multiple spans, or X has rolled out a
    DOM tweak. Falling through several strategies keeps text capture
    reliable across these variants.
    """
    _expand_show_more(tweet_el)

    # 0) X "Articles" long-form posts use a separate rich-text container
    # (twitterArticleRichTextView / twitterArticleReadView /
    # longformRichTextComponent) and do NOT expose `tweetText`. Check this
    # first so multi-thousand-char essays are captured intact.
    for sel in (
        '[data-testid="twitterArticleRichTextView"]',
        '[data-testid="longformRichTextComponent"]',
        '[data-testid="twitterArticleReadView"]',
    ):
        art = tweet_el.query_selector(sel)
        if art:
            # Article posts often have a separate title element.
            title_el = tweet_el.query_selector('[data-testid="twitter-article-title"]')
            title = (title_el.inner_text() or "").strip() if title_el else ""
            body = (art.inner_text() or "").strip()
            if body:
                return f"{title}\n\n{body}".strip() if title else body

    # 1) Standard selector
    el = tweet_el.query_selector('[data-testid="tweetText"]')
    if el:
        txt = (el.inner_text() or "").strip()
        if txt:
            return txt

    # 2) Sometimes split into multiple tweetText spans (quoted + own body)
    parts = tweet_el.query_selector_all('[data-testid="tweetText"]')
    if parts:
        joined = "\n\n".join(p.inner_text().strip() for p in parts if p.inner_text().strip())
        if joined:
            return joined

    # 3) Fallback: any [lang] block inside the article (X marks main text with lang attr)
    lang_blocks = tweet_el.query_selector_all('div[lang], span[lang]')
    if lang_blocks:
        cand = max((b.inner_text() or "" for b in lang_blocks), key=len, default="")
        if cand.strip():
            return cand.strip()

    return ""


def _tweet_to_dict(tweet_el, query: str = "") -> dict | None:
    """Extract a tweet card into a dict. Returns None if no parseable id."""
    text = _tweet_text_robust(tweet_el)

    link_el = tweet_el.query_selector('a[href*="/status/"]')
    href = link_el.get_attribute("href") if link_el else ""
    m = re.search(r"/status/(\d+)", href or "")
    tid = m.group(1) if m else None
    if not tid:
        return None

    name, handle = _author_handle(tweet_el)
    time_el = tweet_el.query_selector("time[datetime]")
    date_str = time_el.get_attribute("datetime") if time_el else ""

    likes = _metric(tweet_el, "like")
    rts = _metric(tweet_el, "retweet")
    reps = _metric(tweet_el, "reply")
    views = _views(tweet_el)

    # Media — collect images + video posters / src.
    # X serves images as `?format=jpg&name=small`; we rewrite to `name=large`
    # so saved assets are usable at higher resolution. Also dedupe on the
    # bare image id (the part before `?`).
    media = []
    seen_img_ids = set()
    for img in tweet_el.query_selector_all('img[src*="pbs.twimg.com/media"]'):
        src = img.get_attribute("src") or ""
        if not src:
            continue
        # Bump resolution
        src_hi = re.sub(r"(\?|&)name=\w+", lambda m: f"{m.group(1)}name=large", src)
        if "name=" not in src_hi:
            joiner = "&" if "?" in src_hi else "?"
            src_hi = f"{src_hi}{joiner}name=large"
        img_id = src_hi.split("?", 1)[0]
        if img_id in seen_img_ids:
            continue
        seen_img_ids.add(img_id)
        media.append({"type": "image", "url": src_hi})
    for vid in tweet_el.query_selector_all("video"):
        v_src = vid.get_attribute("src") or ""
        poster = vid.get_attribute("poster") or ""
        media.append({
            "type": "video",
            "url": v_src,
            "poster": poster,
        })

    return {
        "id": tid,
        "author": name,
        "handle": handle,
        "date": date_str,
        "text": text,
        "url": f"https://x.com{href}" if href and href.startswith("/") else href,
        "likes": likes,
        "retweets": rts,
        "replies": reps,
        "views": views,
        "engagement": likes + rts * 2 + reps,
        "media": media,
        "query": query,
    }


def _scroll_collect(page, max_scrolls: int, seen: dict, query: str = "",
                    date_filter=None, stop_when_no_new: int = 4) -> dict:
    """Scroll and collect tweets into `seen` (id -> dict). Mutates and returns it.

    `date_filter`: optional callable(date_str) -> bool. Tweets failing it are skipped.
    `stop_when_no_new`: stop early if N consecutive scrolls add nothing.
    """
    no_new_streak = 0
    for i in range(max_scrolls):
        added = 0
        for t in page.query_selector_all('[data-testid="tweet"]'):
            try:
                d = _tweet_to_dict(t, query=query)
                if not d:
                    continue
                if d["id"] in seen:
                    continue
                if date_filter and not date_filter(d["date"]):
                    continue
                seen[d["id"]] = d
                added += 1
            except Exception:
                pass
        if added == 0:
            no_new_streak += 1
            if no_new_streak >= stop_when_no_new:
                break
        else:
            no_new_streak = 0
        page.evaluate("window.scrollBy(0, 1800)")
        time.sleep(random.uniform(0.9, 1.5))
    return seen


# ---------------------------------------------------------------------------
# Public mining functions
# ---------------------------------------------------------------------------

def _date_range_filter(since: str | None, until: str | None):
    """Build a callable that accepts a tweet's ISO `date` string."""
    if not since and not until:
        return None

    def f(d: str) -> bool:
        if not d:
            return False
        day = d[:10]  # YYYY-MM-DD
        if since and day < since:
            return False
        if until and day > until:
            return False
        return True

    return f


def mine_topic(context, query: str, since: str | None = None,
               until: str | None = None, sort: str = "both",
               max_scrolls: int = 20, expand_queries: bool = False) -> list[dict]:
    """Search X for `query`, optionally filter by date in post-processing.

    `sort`: 'top' | 'latest' | 'both'. Date is NOT added to the search query;
    instead we just click X's Top/Latest tabs and filter client-side.
    `expand_queries`: also try a quoted-phrase variant for exact-match coverage.
    Returns list of tweet dicts sorted by engagement desc.
    """
    base_q = query.strip()

    if sort == "both":
        f_params = ["top", "live"]
    elif sort == "latest":
        f_params = ["live"]
    else:
        f_params = ["top"]

    queries = [base_q]
    if expand_queries and " " in base_q and not base_q.startswith('"'):
        queries.append(f'"{base_q}"')

    df = _date_range_filter(since, until)
    seen: dict[str, dict] = {}

    for q in queries:
        for f in f_params:
            tab_name = "Top" if f == "top" else "Latest"
            page = context.new_page()
            try:
                page.goto(f"https://x.com/search?q={quote(q)}&f={f}",
                          wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
                except Exception:
                    print(f"[mine_topic] no tweets for: {q} ({tab_name})")
                    continue
                time.sleep(2)
                before = len(seen)
                _scroll_collect(page, max_scrolls, seen, query=f"{q} ({tab_name})",
                                date_filter=df)
                print(f"[mine_topic] '{q}' [{tab_name}] → +{len(seen) - before} "
                      f"(total {len(seen)})")
            finally:
                page.close()

    items = sorted(seen.values(), key=lambda x: x["engagement"], reverse=True)
    return items


def mine_following(context, tab: str = "foryou", since: str | None = None,
                   until: str | None = None, max_scrolls: int = 30) -> list[dict]:
    """Mine the user's home timeline.

    `tab`: 'foryou' (recommended) or 'following' (only people you follow).
    """
    df = _date_range_filter(since, until)
    seen: dict[str, dict] = {}
    page = context.new_page()
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        except Exception:
            print("[mine_following] no tweets visible (login required?)")
            return []

        # Switch tab if requested
        if tab == "following":
            try:
                # Tab links: role=tab, text 'Following'
                tabs = page.query_selector_all('[role="tab"]')
                for t in tabs:
                    if "Following" in (t.inner_text() or "") or "关注" in (t.inner_text() or ""):
                        t.click()
                        break
                time.sleep(2)
            except Exception as e:
                print(f"[mine_following] tab switch failed: {e}")

        time.sleep(1)
        # When date_filter is set and tweets get older than `since`, stop early.
        early_stop_count = 0
        for i in range(max_scrolls):
            added = 0
            for tw in page.query_selector_all('[data-testid="tweet"]'):
                try:
                    d = _tweet_to_dict(tw, query=f"home:{tab}")
                    if not d or d["id"] in seen:
                        continue
                    if df and not df(d["date"]):
                        # Tweet outside date range — note but don't store
                        if d["date"] and since and d["date"][:10] < since:
                            early_stop_count += 1
                        continue
                    seen[d["id"]] = d
                    added += 1
                    early_stop_count = 0  # reset when we hit in-range
                except Exception:
                    pass
            if since and early_stop_count > 8:
                # Many consecutive too-old tweets — timeline has scrolled past `since`
                print(f"[mine_following] reached tweets older than {since}, stopping")
                break
            page.evaluate("window.scrollBy(0, 1800)")
            time.sleep(random.uniform(1.0, 1.5))
            print(f"[mine_following] scroll {i+1}/{max_scrolls}  collected={len(seen)}")
    finally:
        page.close()

    items = sorted(seen.values(), key=lambda x: x["engagement"], reverse=True)
    return items


# ---------------------------------------------------------------------------
# Tweet detail (click into a tweet)
# ---------------------------------------------------------------------------

def fetch_detail(context, tweet_url_or_id: str, max_replies: int = 30) -> dict:
    """Open a single tweet and capture main content + thread + top replies."""
    if tweet_url_or_id.isdigit():
        # Need a username — use /i/web/status which X accepts
        url = f"https://x.com/i/web/status/{tweet_url_or_id}"
    elif "/status/" in tweet_url_or_id:
        url = tweet_url_or_id if tweet_url_or_id.startswith("http") else f"https://x.com{tweet_url_or_id}"
    else:
        url = tweet_url_or_id

    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        except Exception:
            return {"url": url, "error": "tweet not found"}
        time.sleep(2)

        # Pre-scroll a bit so any "show more" / lazy-loaded thread tweets
        # by the same author render before we start parsing. Long-form
        # essays often need 2–3 scrolls before the full thread is in DOM.
        for _ in range(4):
            page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(random.uniform(0.8, 1.2))
        # Scroll back to top so the main tweet is the first article we see
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

        tweets = page.query_selector_all('[data-testid="tweet"]')
        if not tweets:
            return {"url": url, "error": "no tweet elements"}

        # First tweet on a status page is the main one (or thread root)
        main_dict = _tweet_to_dict(tweets[0], query="detail") or {}
        main_handle = main_dict.get("handle")

        # Walk subsequent tweets in DOM order. A same-author tweet is part of
        # the thread until we hit the first non-author tweet. After that,
        # everything goes into replies (even later same-author tweets, which
        # are usually self-replies in the conversation, not the original
        # thread continuation).
        thread = []
        replies = []
        in_thread = True
        for t in tweets[1:]:
            d = _tweet_to_dict(t, query="reply")
            if not d:
                continue
            same_author = main_handle and d.get("handle") == main_handle
            if in_thread and same_author:
                thread.append(d)
            else:
                in_thread = False
                replies.append(d)

        # Scroll to load more replies
        for _ in range(min(8, max(2, max_replies // 4))):
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(random.uniform(0.9, 1.3))
            seen_ids = {r["id"] for r in replies}
            for t in page.query_selector_all('[data-testid="tweet"]'):
                d = _tweet_to_dict(t, query="reply")
                if not d or d["id"] in seen_ids:
                    continue
                if d.get("id") == main_dict.get("id"):
                    continue
                if main_dict and d.get("handle") == main_dict.get("handle") and not [r for r in replies if r["id"] == d["id"]]:
                    if d not in thread:
                        thread.append(d)
                else:
                    replies.append(d)
            if len(replies) >= max_replies:
                break

        replies = sorted(replies[:max_replies], key=lambda x: x["engagement"], reverse=True)

        # Build a `full_text` field that joins main + same-author thread
        # continuations in DOM order. Long-form essays on X are usually split
        # across multiple tweets by the same author; downstream code (xhs
        # converter, summarizers) wants the whole essay as a single string.
        thread_in_order = list(thread)
        full_parts = [main_dict.get("text", "")] + [t.get("text", "") for t in thread_in_order]
        full_text = "\n\n".join(p for p in full_parts if p)

        return {
            "url": url,
            "main": main_dict,
            "thread": thread,
            "replies": replies,
            "reply_count": len(replies),
            "full_text": full_text,
        }
    finally:
        page.close()


# ---------------------------------------------------------------------------
# Media download helpers
# ---------------------------------------------------------------------------

_MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://x.com/",
    "Accept": "*/*",
}


def _ext_for_url(url: str, default: str = ".jpg") -> str:
    """Best-guess extension from a twimg URL."""
    bare = url.split("?", 1)[0].lower()
    for e in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".m3u8"):
        if bare.endswith(e):
            return e
    # twimg /media/<id>?format=jpg
    m = re.search(r"format=(\w+)", url)
    if m:
        return "." + m.group(1).lower()
    return default


def _safe_id(url: str) -> str:
    """Stable filename id from a media URL."""
    bare = url.split("?", 1)[0]
    name = bare.rsplit("/", 1)[-1]
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name) or "media"


def download_media(media_list, out_dir: str | Path,
                   prefix: str = "", timeout: int = 20) -> list[dict]:
    """Download media URLs to `out_dir` and return new dicts with `local_path`.

    - `prefix` is prepended to filenames (e.g. tweet id) for organization.
    - Failures are recorded in the returned dict (`error` key) but do not
      raise; we want best-effort capture even when X CDN serves 401/403.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, m in enumerate(media_list or []):
        url = m.get("url") or ""
        if not url:
            # Video without direct src — keep poster if any
            poster = m.get("poster")
            if poster:
                m2 = dict(m)
                local = _download_one(poster, out_dir, prefix, i, timeout, kind="poster")
                if local:
                    m2["poster_local"] = str(local)
                out.append(m2)
            else:
                out.append(dict(m))
            continue
        m2 = dict(m)
        local = _download_one(url, out_dir, prefix, i, timeout, kind=m.get("type", "image"))
        if local:
            m2["local_path"] = str(local)
        else:
            m2["error"] = "download failed"
        # Also try poster for videos
        if m.get("poster"):
            poster_local = _download_one(m["poster"], out_dir, prefix, i, timeout, kind="poster")
            if poster_local:
                m2["poster_local"] = str(poster_local)
        out.append(m2)
    return out


def _download_one(url: str, out_dir: Path, prefix: str, idx: int,
                  timeout: int, kind: str = "image") -> Path | None:
    try:
        ext = _ext_for_url(url, default=".mp4" if kind == "video" else ".jpg")
        suffix = "" if kind == "image" else f"-{kind}"
        fname = f"{prefix}{'-' if prefix else ''}{idx:02d}{suffix}{ext}"
        # If the URL has a more descriptive id, prefer it
        sid = _safe_id(url)
        if sid and sid != "media":
            fname = f"{prefix}{'-' if prefix else ''}{idx:02d}{suffix}-{sid}{ext}" \
                if not sid.endswith(ext) else f"{prefix}{'-' if prefix else ''}{idx:02d}{suffix}-{sid}"
        target = out_dir / fname
        if target.exists() and target.stat().st_size > 0:
            return target
        req = urllib.request.Request(url, headers=_MEDIA_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        target.write_bytes(data)
        return target
    except Exception as e:
        print(f"WARN: media download failed for {url[:100]}: {e}")
        return None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def items_to_markdown(items: Iterable[dict], title: str = "X Mining Results",
                      top_n: int | None = None) -> str:
    items = list(items)
    if top_n:
        items = items[:top_n]
    lines = [f"# {title}", "", f"_{len(items)} tweets_", ""]
    for i, t in enumerate(items, 1):
        date_short = t.get("date", "")[:16].replace("T", " ")
        lines.append(f"## [{i}] {t.get('author','')} {t.get('handle','')}")
        lines.append(f"_{date_short} UTC · ❤️ {t.get('likes',0):,} · 🔁 {t.get('retweets',0):,} · 💬 {t.get('replies',0):,} · 👁 {t.get('views',0):,}_")
        lines.append("")
        lines.append(t.get("text", ""))
        if t.get("url"):
            lines.append("")
            lines.append(f"<{t['url']}>")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def detail_to_markdown(detail: dict) -> str:
    if "error" in detail:
        return f"# Detail error\n\n{detail['error']} for {detail.get('url','')}"
    main = detail.get("main", {})
    lines = ["# Tweet detail", "", f"<{detail.get('url','')}>", ""]
    lines.append(f"## {main.get('author','')} {main.get('handle','')}")
    lines.append(f"_{main.get('date','')[:16].replace('T',' ')} UTC · ❤️ {main.get('likes',0):,} · 🔁 {main.get('retweets',0):,} · 💬 {main.get('replies',0):,} · 👁 {main.get('views',0):,}_")
    lines.append("")
    lines.append(main.get("text", ""))
    lines.append("")
    _append_media_md(lines, main.get("media", []))

    if detail.get("thread"):
        lines.append("## Thread continuation")
        lines.append("")
        for i, t in enumerate(detail["thread"], 1):
            lines.append(f"**{i}.** {t.get('text','')}")
            lines.append("")
            _append_media_md(lines, t.get("media", []))

    if detail.get("replies"):
        lines.append(f"## Top {len(detail['replies'])} replies")
        lines.append("")
        for i, r in enumerate(detail["replies"], 1):
            lines.append(f"**[{i}] {r.get('author','')} {r.get('handle','')}** "
                         f"❤️ {r.get('likes',0):,} 🔁 {r.get('retweets',0):,} 💬 {r.get('replies',0):,}")
            lines.append("")
            lines.append(r.get("text", ""))
            lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


def _append_media_md(lines: list, media: list) -> None:
    """Render media block in markdown.

    Prefers local paths when present (so the file works offline), and falls
    back to remote URLs. Videos use a link instead of `![ ]()` since
    markdown image syntax can't embed video.
    """
    if not media:
        return
    lines.append("### Media")
    lines.append("")
    for m in media:
        kind = m.get("type", "image")
        local = m.get("local_path")
        url = m.get("url") or ""
        poster_local = m.get("poster_local")
        poster = m.get("poster")
        if kind == "image":
            if local:
                lines.append(f"![image]({local})")
            elif url:
                lines.append(f"![image]({url})")
        else:  # video / other
            if poster_local or poster:
                lines.append(f"![poster]({poster_local or poster})")
            if local:
                lines.append(f"[video]({local})")
            elif url:
                lines.append(f"[video]({url})")
        lines.append("")
