"""Generic readability-style content extractor for arbitrary web pages."""

import re
from .base import BaseExtractor, ExtractedContent


class GenericExtractor(BaseExtractor):
    """Generic extractor using main content detection heuristics.

    Strategy:
    1. Try <article> element
    2. Try <main> or [role=main]
    3. Try #content, .content, .post, .entry selectors
    4. Fall back to <body> with nav/footer/script/style stripped
    """

    site_id = "generic"

    def can_handle(self, url: str) -> bool:
        return True

    def extract(self, page) -> ExtractedContent:
        url = page.url
        title = self._extract_title(page)
        author = self._extract_author(page)
        date = self._extract_date(page)

        main_html = self._extract_main_html(page)
        content_text = self._strip_html_tags(main_html)

        images = self._extract_images(page)
        links = self._extract_links(page)

        return ExtractedContent(
            title=title,
            author=author,
            date=date,
            url=url,
            site="generic",
            content_text=self._clean_text(content_text),
            raw_html=main_html,
            metadata=self._extract_metadata(page),
            images=images,
            links=links,
        )

    def _extract_title(self, page) -> str:
        selectors = [
            "h1",
            "[property='og:title']",
            "[name='twitter:title']",
            "title",
        ]
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                text = el.get_attribute("content") or el.inner_text()
                if text and text.strip():
                    return text.strip()
        return ""

    def _extract_author(self, page) -> str:
        selectors = [
            "[property='article:author']",
            "[name='author']",
            "[rel='author']",
            ".author",
            ".byline",
        ]
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                text = el.get_attribute("content") or el.inner_text()
                if text and text.strip():
                    return text.strip()
        return ""

    def _extract_date(self, page) -> str:
        selectors = [
            "time[datetime]",
            "[property='article:published_time']",
            "[name='date']",
            ".date",
            ".published",
        ]
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                text = el.get_attribute("datetime") or el.get_attribute("content") or el.inner_text()
                if text and text.strip():
                    return text.strip()
        return ""

    def _extract_main_html(self, page) -> str:
        # Strategy 1: <article>
        el = page.query_selector("article")
        if el:
            return el.inner_html()

        # Strategy 2: <main> or [role=main]
        for sel in ["main", "[role='main']"]:
            el = page.query_selector(sel)
            if el:
                return el.inner_html()

        # Strategy 3: Common content selectors
        for sel in ["#content", ".content", ".post", ".entry", ".article-body"]:
            el = page.query_selector(sel)
            if el:
                return el.inner_html()

        # Strategy 4: Fall back to body (stripped later)
        body = page.query_selector("body")
        if body:
            # Remove non-content elements before extracting
            page.evaluate("""() => {
                const remove = ['nav', 'footer', 'header', 'aside', 'script', 'style', 'noscript', 'iframe'];
                const body = document.body.cloneNode(true);
                remove.forEach(tag => {
                    body.querySelectorAll(tag).forEach(el => el.remove());
                });
                window._cleanedBody = body.innerHTML;
            }""")
            cleaned = page.evaluate("() => window._cleanedBody || document.body.innerHTML")
            return cleaned or ""

        return ""

    def _extract_images(self, page) -> list:
        images = []
        els = page.query_selector_all("img[src]")
        seen = set()
        for el in els:
            src = el.get_attribute("src") or ""
            if not src or src.startswith("data:") or src in seen:
                continue
            seen.add(src)
            alt = el.get_attribute("alt") or ""
            # Skip tiny images (icons, trackers)
            width = el.get_attribute("width")
            if width and width.isdigit() and int(width) < 50:
                continue
            images.append({"src": src, "alt": alt})
        return images

    def _extract_links(self, page) -> list:
        links = []
        els = page.query_selector_all("a[href]")
        seen = set()
        for el in els[:200]:  # Cap to avoid huge output
            href = el.get_attribute("href") or ""
            text = el.inner_text().strip()[:200]
            if not href or href.startswith("#") or href in seen:
                continue
            seen.add(href)
            links.append({"text": text, "href": href})
        return links

    def _extract_metadata(self, page) -> dict:
        meta = {}
        # Open Graph
        for prop in ["og:type", "og:site_name", "og:description", "og:image"]:
            el = page.query_selector(f"[property='{prop}']")
            if el:
                val = el.get_attribute("content")
                if val:
                    meta[prop] = val
        # Twitter Card
        for name in ["twitter:card", "twitter:site", "twitter:description"]:
            el = page.query_selector(f"[name='{name}']")
            if el:
                val = el.get_attribute("content")
                if val:
                    meta[name] = val
        # Description
        el = page.query_selector("[name='description']")
        if el:
            meta["description"] = el.get_attribute("content") or ""
        return meta

    def _strip_html_tags(self, html: str) -> str:
        """Remove HTML tags from a string."""
        clean = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"&nbsp;", " ", clean)
        clean = re.sub(r"&amp;", "&", clean)
        clean = re.sub(r"&lt;", "<", clean)
        clean = re.sub(r"&gt;", ">", clean)
        clean = re.sub(r"&quot;", '"', clean)
        clean = re.sub(r"&#\d+;", "", clean)
        return clean

    def _clean_text(self, text: str) -> str:
        """Clean up whitespace in extracted text."""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
        return text.strip()
