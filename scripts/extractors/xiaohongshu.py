"""Xiaohongshu (小红书) site-specific content extractor."""

import json
import re
from urllib.parse import urlparse

from .base import BaseExtractor, ExtractedContent


class XiaohongshuExtractor(BaseExtractor):
    """Extractor for 小红书 notes, search results, and user profiles."""

    site_id = "xiaohongshu"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return "xiaohongshu" in (parsed.hostname or "")

    def wait_for_content(self, page, timeout: int = 15000) -> None:
        """Wait for note content or search results to render."""
        selectors = [
            '#detail-desc',
            '.note-content',
            '[class*="noteDetail"]',
            '[class*="note-item"]',
            '[class*="feeds-container"]',
        ]
        for sel in selectors:
            try:
                page.wait_for_selector(sel, timeout=5000)
                return
            except Exception:
                continue
        # Final wait for any content
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

    def extract(self, page) -> ExtractedContent:
        url = page.url

        if "/explore/" in url or "/discovery/item/" in url:
            return self._extract_note(page)
        elif "/search_result/" in url or "/search" in url:
            return self._extract_search_results(page)
        elif "/user/profile/" in url:
            return self._extract_profile(page)
        else:
            return self._extract_note(page)

    def _extract_note(self, page) -> ExtractedContent:
        """Extract a single note (post)."""
        # Title
        title = ""
        title_el = page.query_selector('#detail-title') or page.query_selector('[class*="title"]')
        if title_el:
            title = title_el.inner_text().strip()

        # Content / description
        content = ""
        desc_el = page.query_selector('#detail-desc') or page.query_selector('[class*="desc"]')
        if desc_el:
            content = desc_el.inner_text().strip()

        # Author
        author = ""
        author_el = page.query_selector('[class*="author"] .name, [class*="username"], .user-nickname')
        if author_el:
            author = author_el.inner_text().strip()

        # Tags
        tags = re.findall(r"#(\S+)", content)
        tag_els = page.query_selector_all('[class*="tag"] a, [class*="hash-tag"]')
        for el in tag_els:
            tag_text = el.inner_text().strip().lstrip("#")
            if tag_text and tag_text not in tags:
                tags.append(tag_text)

        # Images
        images = []
        img_els = page.query_selector_all('.swiper-slide img, [class*="carousel"] img, [class*="slide"] img')
        seen = set()
        for img in img_els:
            src = img.get_attribute("src") or ""
            if not src or src.startswith("data:") or src in seen:
                continue
            seen.add(src)
            images.append({"src": src, "alt": ""})

        # Also grab the main image if no carousel
        if not images:
            main_img = page.query_selector('[class*="note-detail"] img[src*="sns-webpic"], img[src*="ci.xiaohongshu"]')
            if main_img:
                src = main_img.get_attribute("src") or ""
                if src:
                    images.append({"src": src, "alt": ""})

        # Metrics
        metrics = {}
        for key, selectors in [
            ("likes", ['[class*="like-wrapper"] .count', '[class*="like"] .count', '#likeCount']),
            ("collects", ['[class*="collect-wrapper"] .count', '[class*="collect"] .count', '#collectCount']),
            ("comments", ['[class*="comment-wrapper"] .count', '[class*="chat-wrapper"] .count', '#commentCount']),
        ]:
            for sel in selectors:
                el = page.query_selector(sel)
                if el:
                    val = el.inner_text().strip()
                    if val:
                        metrics[key] = val
                        break

        # Date
        date = ""
        date_el = page.query_selector('[class*="date"], [class*="bottom-container"] span')
        if date_el:
            date_text = date_el.inner_text().strip()
            if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d+天前|\d+小时前", date_text):
                date = date_text

        # Note ID from URL
        note_id = ""
        match = re.search(r"/explore/(\w+)|/discovery/item/(\w+)", page.url)
        if match:
            note_id = match.group(1) or match.group(2) or ""

        # Check if video
        is_video = bool(page.query_selector("video"))

        return ExtractedContent(
            title=title,
            author=author,
            date=date,
            url=page.url,
            site="xiaohongshu",
            content_text=f"{title}\n\n{content}" if title else content,
            metadata={
                "note_id": note_id,
                "note_type": "video" if is_video else "normal",
                "tags": tags,
                "metrics": metrics,
                "image_count": len(images),
                "is_video": is_video,
            },
            images=images,
        )

    def _extract_search_results(self, page) -> ExtractedContent:
        """Extract note cards from search results."""
        items = page.query_selector_all('[class*="note-item"], [class*="feeds"] section, [class*="card"]')
        results = []

        for item in items[:30]:
            title_el = item.query_selector('[class*="title"], [class*="desc"], a')
            title = title_el.inner_text().strip() if title_el else ""

            link_el = item.query_selector("a[href]")
            href = link_el.get_attribute("href") or "" if link_el else ""

            author_el = item.query_selector('[class*="author"], [class*="name"]')
            author = author_el.inner_text().strip() if author_el else ""

            likes_el = item.query_selector('[class*="like"] span, [class*="count"]')
            likes = likes_el.inner_text().strip() if likes_el else ""

            if title:
                results.append({
                    "title": title,
                    "author": author,
                    "likes": likes,
                    "url": href,
                })

        return ExtractedContent(
            title="Search Results",
            url=page.url,
            site="xiaohongshu",
            content_text="\n\n---\n\n".join(
                f"{r['author']}: {r['title']} (❤ {r['likes']})" for r in results
            ),
            metadata={
                "type": "search_results",
                "result_count": len(results),
                "results": results,
            },
        )

    def _extract_profile(self, page) -> ExtractedContent:
        """Extract user profile information."""
        nickname = ""
        name_el = page.query_selector('[class*="user-name"], [class*="nickname"], .nickname')
        if name_el:
            nickname = name_el.inner_text().strip()

        bio = ""
        desc_el = page.query_selector('[class*="user-desc"], [class*="desc"], .desc')
        if desc_el:
            bio = desc_el.inner_text().strip()

        stats = {}
        stat_els = page.query_selector_all('[class*="user-interaction"] .count, [class*="stats"] span')
        stat_labels = page.query_selector_all('[class*="user-interaction"] .label, [class*="stats"] .label')
        for label_el, count_el in zip(stat_labels, stat_els):
            label = label_el.inner_text().strip()
            count = count_el.inner_text().strip()
            if label and count:
                stats[label] = count

        # User ID from URL
        user_id = ""
        match = re.search(r"/user/profile/(\w+)", page.url)
        if match:
            user_id = match.group(1)

        return ExtractedContent(
            title=nickname,
            author=nickname,
            url=page.url,
            site="xiaohongshu",
            content_text=bio,
            metadata={
                "type": "profile",
                "user_id": user_id,
                "nickname": nickname,
                "bio": bio,
                "stats": stats,
            },
        )
