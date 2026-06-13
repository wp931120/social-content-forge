#!/usr/bin/env python3
"""Monitor a page for changes and notify when content changes.

Usage:
    python monitor_changes.py <url> --check-interval 3600 --state-dir ./monitor_state

This script checks a URL at regular intervals, compares content hashes,
and reports when changes are detected.
"""

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from browser_state import resolve_site, get_state_for_context
from extractors import get_extractor


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_previous_state(monitor_file: Path) -> dict:
    """Load previous monitoring state."""
    if monitor_file.exists():
        with open(monitor_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_current_state(monitor_file: Path, url: str, content_hash: str,
                       content_text: str, timestamp: str):
    """Save current monitoring state."""
    state = {
        "url": url,
        "content_hash": content_hash,
        "content_text": content_text[:2000],  # Save snippet for reference
        "last_check": timestamp,
    }
    with open(monitor_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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


def check_page(url: str, state_dir: str = ".browser-state") -> dict:
    """Check a page and return status."""
    site_info = resolve_site(url)
    site_id = site_info["id"]
    state_path = get_state_for_context(site_id, state_dir)

    with sync_playwright() as p:
        browser, context = create_browser_context(p, state_path)
        page = context.new_page()
        apply_stealth(page)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(random.uniform(0.5, 1.0))

            extractor = get_extractor(url)
            content = extractor.extract(page)

            content_hash = compute_hash(content.content_text)

            return {
                "success": True,
                "content_hash": content_hash,
                "content_text": content.content_text,
                "title": content.title,
                "author": content.author,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

        finally:
            browser.close()


def monitor_page(url: str, check_interval: int = 3600, state_dir: str = ".browser-state",
                 output_dir: str = "./monitor_output"):
    """Monitor a page for changes at regular intervals."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    monitor_file = output_path / f"monitor_{Path(url).stem}.json"
    log_file = output_path / "monitor.log"

    print(f"Monitoring: {url}")
    print(f"Check interval: {check_interval} seconds")
    print(f"State file: {monitor_file}")
    print("Press Ctrl+C to stop\n")

    # Load previous state
    prev_state = load_previous_state(monitor_file)
    prev_hash = prev_state.get("content_hash", "")

    if prev_hash:
        print(f"Previous content hash: {prev_hash[:16]}...")

    while True:
        timestamp = datetime.now().isoformat()
        print(f"[{timestamp}] Checking page...")

        result = check_page(url, state_dir)

        if not result["success"]:
            msg = f"Error: {result.get('error', 'Unknown')}"
            print(f"  ✗ {msg}")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} - ERROR: {result.get('error')}\n")
        else:
            curr_hash = result["content_hash"]
            print(f"  Content hash: {curr_hash[:16]}...")

            if curr_hash != prev_hash:
                if prev_hash:
                    print("  ⚠ CHANGE DETECTED!")
                    change_msg = f"Page changed! Hash: {prev_hash[:16]}... -> {curr_hash[:16]}..."
                    print(f"  {change_msg}")

                    # Save change notification
                    change_file = output_path / f"change_{int(time.time())}.json"
                    with open(change_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "url": url,
                            "timestamp": timestamp,
                            "previous_hash": prev_hash,
                            "current_hash": curr_hash,
                            "previous_content": prev_state.get("content_text", ""),
                            "current_content": result["content_text"],
                        }, f, ensure_ascii=False, indent=2)

                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"{timestamp} - CHANGE DETECTED: {curr_hash}\n")
                else:
                    print("  ✓ First run, no previous state")

                # Update state
                save_current_state(monitor_file, url, curr_hash,
                                   result["content_text"], timestamp)
                prev_hash = curr_hash
            else:
                print("  ✓ No change")

        # Wait for next check
        print(f"  Waiting {check_interval} seconds...")
        time.sleep(check_interval)


def main():
    parser = argparse.ArgumentParser(description="Monitor a page for changes")
    parser.add_argument("url", help="URL to monitor")
    parser.add_argument("--check-interval", type=int, default=3600,
                       help="Seconds between checks (default: 3600 = 1 hour)")
    parser.add_argument("--state-dir", default=".browser-state")
    parser.add_argument("--output-dir", default="./monitor_output")

    args = parser.parse_args()

    try:
        monitor_page(args.url, args.check_interval, args.state_dir, args.output_dir)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())