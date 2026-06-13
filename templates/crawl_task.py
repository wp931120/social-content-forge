#!/usr/bin/env python3
"""Single page crawl task template.

Usage:
    python crawl_task.py <url> [--output OUTPUT] [--format FORMAT]

Copy this template and customize the extract_* functions for your specific needs.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from browser_state import resolve_site, get_state_for_context
from extractors import get_extractor, extract_from_page
from converters.html_to_markdown import convert as html_to_markdown
from converters.html_to_json import convert as html_to_json


def create_browser_context(playwright, headless: bool = True, state_path: str = None):
    """Create a browser context with stealth and optional saved state."""
    import random

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    ]

    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )

    context_options = {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": random.choice(USER_AGENTS),
    }

    if state_path:
        context_options["storage_state"] = state_path

    return browser, browser.new_context(**context_options)


def apply_stealth(page):
    """Apply stealth patches."""
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)


def crawl_url(url: str, format: str = "markdown", output: str = None,
              state_dir: str = ".browser-state", headless: bool = True):
    """Crawl a single URL and return extracted content."""
    from urllib.parse import urlparse

    # Determine site
    site_info = resolve_site(url)
    site_id = site_info["id"]

    # Try to load state
    state_path = get_state_for_context(site_id, state_dir)

    with sync_playwright() as p:
        browser, context = create_browser_context(p, headless, state_path)
        page = context.new_page()
        apply_stealth(page)

        page.goto(url, wait_until="networkidle", timeout=30000)

        # Optional: customize wait logic
        # page.wait_for_selector('.specific-content', timeout=10000)

        # Extract content
        extractor = get_extractor(url)
        content = extractor.extract(page)

        browser.close()

    # Output
    if format == "json":
        result = html_to_json(content)
    else:
        result = html_to_markdown(content.raw_html or f"# {content.title}\n\n{content.content_text}")

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Saved to: {output}")
    else:
        print(result)

    return content


def main():
    parser = argparse.ArgumentParser(description="Crawl a single URL")
    parser.add_argument("url", help="URL to crawl")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--state-dir", default=".browser-state")
    parser.add_argument("--headed", action="store_true", help="Show browser window")

    args = parser.parse_args()

    try:
        crawl_url(args.url, args.format, args.output, args.state_dir, not args.headed)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())