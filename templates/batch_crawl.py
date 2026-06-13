#!/usr/bin/env python3
"""Batch crawl multiple URLs.

Usage:
    python batch_crawl.py urls.txt --output-dir ./output --format json

The input file should contain one URL per line.
Lines starting with # are treated as comments.
"""

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from browser_state import resolve_site, get_state_for_context
from extractors import get_extractor
from converters.html_to_markdown import convert as html_to_markdown
from converters.html_to_json import convert as html_to_json


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


def load_urls(file_path: str) -> list[str]:
    """Load URLs from a file, ignoring comments and empty lines."""
    urls = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def create_browser_context(playwright, state_path: str = None):
    """Create a browser context."""
    browser = playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    context_options = {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": random.choice(USER_AGENTS),
    }

    if state_path and Path(state_path).exists():
        context_options["storage_state"] = state_path

    return browser, browser.new_context(**context_options)


def apply_stealth(page):
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")


def crawl_url(playwright, url: str, state_dir: str = ".browser-state") -> dict:
    """Crawl a single URL and return result dict."""
    site_info = resolve_site(url)
    site_id = site_info["id"]
    state_path = get_state_for_context(site_id, state_dir)

    browser, context = create_browser_context(playwright, state_path)
    page = context.new_page()
    apply_stealth(page)

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)

        # Random delay
        time.sleep(random.uniform(0.5, 1.5))

        extractor = get_extractor(url)
        content = extractor.extract(page)

        return {
            "url": url,
            "success": True,
            "title": content.title,
            "author": content.author,
            "content_text": content.content_text[:500],  # Truncate for summary
            "metadata": content.metadata,
        }

    except Exception as e:
        return {
            "url": url,
            "success": False,
            "error": str(e),
        }

    finally:
        browser.close()


def batch_crawl(urls: list[str], output_dir: str, format: str = "json",
                state_dir: str = ".browser-state", delay: float = 2.0):
    """Batch crawl multiple URLs."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(urls)

    print(f"Starting batch crawl of {total} URLs...")

    with sync_playwright() as p:
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{total}] {url}")

            result = crawl_url(p, url, state_dir)
            results.append(result)

            # Save incrementally
            if format == "json":
                output_file = output_path / "results.json"
                import json as json_module
                with open(output_file, "w", encoding="utf-8") as f:
                    json_module.dump(results, f, ensure_ascii=False, indent=2)
            else:
                output_file = output_path / "results.md"
                with open(output_file, "w", encoding="utf-8") as f:
                    for r in results:
                        status = "✓" if r["success"] else "✗"
                        f.write(f"## {status} {r['url']}\n\n")
                        if r["success"]:
                            f.write(f"**Title**: {r.get('title', '')}\n\n")
                            f.write(f"**Author**: {r.get('author', '')}\n\n")
                            f.write(f"{r.get('content_text', '')}\n\n")
                        else:
                            f.write(f"**Error**: {r.get('error', 'Unknown')}\n\n")
                        f.write("---\n\n")

            # Delay between requests
            if i < total:
                time.sleep(delay + random.uniform(-0.5, 0.5))

    # Summary
    success_count = sum(1 for r in results if r["success"])
    print(f"\nCompleted: {success_count}/{total} successful")

    return results


def main():
    parser = argparse.ArgumentParser(description="Batch crawl multiple URLs")
    parser.add_argument("input", help="Input file with URLs (one per line)")
    parser.add_argument("--output-dir", "-o", default="./crawl_output", help="Output directory")
    parser.add_argument("--format", choices=["markdown", "json"], default="json")
    parser.add_argument("--state-dir", default=".browser-state")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")

    args = parser.parse_args()

    urls = load_urls(args.input)
    if not urls:
        print("No URLs found in input file")
        return 1

    batch_crawl(urls, args.output_dir, args.format, args.state_dir, args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())