"""X/Twitter site-specific content extractor."""

import json
import re
from urllib.parse import urlparse

from .base import BaseExtractor, ExtractedContent


class XTwitterExtractor(BaseExtractor):
    """Extractor for X/Twitter tweets, profiles, and search results.

    Relies on data-testid attributes which are more stable than class names.
    """

    site_id = "x"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.hostname in ("x.com", "twitter.com", "www.x.com", "www.twitter.com")

    def wait_for_content(self, page, timeout: int = 15000) -> None:
        """Wait for tweet content to render."""
        try:
            page.wait_for_selector('[data-testid="tweet"]', timeout=timeout)
        except Exception:
            try:
                page.wait_for_selector('[data-testid="UserName"]', timeout=5000)
            except Exception:
                pass

    def extract(self, page) -> ExtractedContent:
        url = page.url

        if "/status/" in url:
            return self._extract_tweet(page)
        elif "/search" in url:
            return self._extract_search_results(page)
        elif self._is_profile_url(url):
            return self._extract_profile(page)
        else:
            return self._extract_timeline(page)

    def _is_profile_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        # Profile: /username (not /i/, /home, /explore, /search, etc.)
        if len(parts) == 1 and parts[0] and parts[0] not in (
            "home", "explore", "search", "i", "notifications", "messages",
            "settings", "compose", "lists", "bookmarks", "communities",
        ):
            return True
        if len(parts) == 2 and parts[1] in ("following", "followers", "verified_followers"):
            return True
        return False

    def _extract_tweet(self, page) -> ExtractedContent:
        """Extract a single tweet."""
        tweet_el = page.query_selector('[data-testid="tweet"]')
        if not tweet_el:
            return ExtractedContent(url=page.url, site="x", metadata={"error": "Tweet element not found"})

        # Tweet text
        text_el = tweet_el.query_selector('[data-testid="tweetText"]')
        text = text_el.inner_text() if text_el else ""

        # Author
        user_el = tweet_el.query_selector('[data-testid="User-Name"]')
        author = user_el.inner_text() if user_el else ""

        # Timestamp
        time_el = tweet_el.query_selector("time[datetime]")
        date = time_el.get_attribute("datetime") if time_el else ""

        # Metrics
        metrics = {}
        for key, testid in [("likes", "like"), ("retweets", "retweet"), ("replies", "reply")]:
            el = tweet_el.query_selector(f'[data-testid="{testid}"]')
            if el:
                val = el.get_attribute("aria-label") or el.inner_text()
                metrics[key] = val.strip()
        views_el = tweet_el.query_selector('a[href*="/analytics"] span')
        if views_el:
            metrics["views"] = views_el.inner_text().strip()

        # Media
        media = []
        img_els = tweet_el.query_selector_all('img[src*="pbs.twimg.com/media"]')
        for img in img_els:
            src = img.get_attribute("src") or ""
            if src:
                media.append({"type": "image", "url": src})
        video_el = tweet_el.query_selector("video")
        if video_el:
            poster = video_el.get_attribute("poster") or ""
            media.append({"type": "video", "thumbnail": poster})

        # Hashtags and mentions from text
        hashtags = re.findall(r"#(\w+)", text)
        mentions = re.findall(r"@(\w+)", text)

        # Tweet ID from URL
        tweet_id = ""
        match = re.search(r"/status/(\d+)", page.url)
        if match:
            tweet_id = match.group(1)

        return ExtractedContent(
            title=f"Tweet by {author}" if author else "Tweet",
            author=author,
            date=date,
            url=page.url,
            site="x",
            content_text=text,
            metadata={
                "tweet_id": tweet_id,
                "hashtags": hashtags,
                "mentions": mentions,
                "metrics": metrics,
                "media": media,
            },
            images=[m for m in media if m.get("type") == "image"],
        )

    def _extract_search_results(self, page) -> ExtractedContent:
        """Extract tweets from search results."""
        tweets = page.query_selector_all('[data-testid="tweet"]')
        results = []

        for tweet_el in tweets[:50]:
            text_el = tweet_el.query_selector('[data-testid="tweetText"]')
            text = text_el.inner_text() if text_el else ""

            user_el = tweet_el.query_selector('[data-testid="User-Name"]')
            author = user_el.inner_text() if user_el else ""

            time_el = tweet_el.query_selector("time[datetime]")
            date = time_el.get_attribute("datetime") if time_el else ""

            link_el = tweet_el.query_selector("time")
            tweet_url = link_el.evaluate("el => el.closest('a')?.href || ''") if link_el else ""

            results.append({
                "author": author,
                "text": text,
                "date": date,
                "url": tweet_url,
            })

        # Search query
        search_input = page.query_selector('[data-testid="SearchTextInput"]')
        query = search_input.input_value() if search_input else ""

        return ExtractedContent(
            title=f"Search: {query}",
            url=page.url,
            site="x",
            content_text="\n\n---\n\n".join(
                f"{r['author']}\n{r['text']}" for r in results if r["text"]
            ),
            metadata={
                "type": "search_results",
                "query": query,
                "result_count": len(results),
                "results": results,
            },
        )

    def _extract_profile(self, page) -> ExtractedContent:
        """Extract user profile information."""
        name_el = page.query_selector('[data-testid="UserName"]')
        display_name = ""
        handle = ""
        if name_el:
            spans = name_el.query_selector_all("span")
            parts = [s.inner_text().strip() for s in spans if s.inner_text().strip()]
            if parts:
                display_name = parts[0]
            handle = next((p for p in parts if p.startswith("@")), "")

        desc_el = page.query_selector('[data-testid="UserDescription"]')
        bio = desc_el.inner_text() if desc_el else ""

        # Follower/following counts
        stats = {}
        links_area = page.query_selector('[data-testid="UserName"] + div')
        if not links_area:
            links_area = page.query_selector("div")
        stat_links = page.query_selector_all('a[href*="/"]')
        for link in stat_links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "/verified_followers" in href or "/followers" in href:
                stats["followers"] = text
            elif "/following" in href:
                stats["following"] = text

        return ExtractedContent(
            title=f"{display_name} ({handle})" if handle else display_name,
            author=display_name,
            url=page.url,
            site="x",
            content_text=bio,
            metadata={
                "type": "profile",
                "handle": handle,
                "bio": bio,
                "stats": stats,
            },
        )

    def _extract_timeline(self, page) -> ExtractedContent:
        """Extract timeline / home feed tweets."""
        tweets = page.query_selector_all('[data-testid="tweet"]')
        results = []

        for tweet_el in tweets[:30]:
            text_el = tweet_el.query_selector('[data-testid="tweetText"]')
            text = text_el.inner_text() if text_el else ""

            user_el = tweet_el.query_selector('[data-testid="User-Name"]')
            author = user_el.inner_text() if user_el else ""

            time_el = tweet_el.query_selector("time[datetime]")
            date = time_el.get_attribute("datetime") if time_el else ""

            results.append({"author": author, "text": text, "date": date})

        return ExtractedContent(
            title="Timeline",
            url=page.url,
            site="x",
            content_text="\n\n---\n\n".join(
                f"{r['author']}\n{r['text']}" for r in results if r["text"]
            ),
            metadata={"type": "timeline", "tweet_count": len(results), "results": results},
        )
