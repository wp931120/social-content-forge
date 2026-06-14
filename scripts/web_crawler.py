#!/usr/bin/env python3
"""Web crawler CLI with persistent login state and long-lived browser daemon.

Usage:
    web_crawler.py daemon                 # Start a long-lived headed browser (foreground)
    web_crawler.py stop                   # Stop the running daemon
    web_crawler.py login <site>           # Open browser for manual login
    web_crawler.py scrape <url>           # Scrape a URL (reuses daemon if running)
    web_crawler.py screenshot <url>       # Take a screenshot of a URL
    web_crawler.py states                 # List saved browser states

When the daemon is running, scrape/screenshot/login open a new tab in the
already-visible browser so the user can watch the crawl in real time.
"""

import argparse
import json
import os
import random
import signal
import sys
import time
import urllib.request
from pathlib import Path

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from playwright.sync_api import sync_playwright

from browser_state import (
    resolve_site,
    save_state,
    get_state_for_context,
    list_saved_states,
    validate_state,
)
from extractors import get_extractor
from converters.html_to_markdown import convert as html_to_markdown
from converters.html_to_json import convert as html_to_json


# Chrome path — preferred to avoid bot detection.
# Auto-detect by platform; override via env CHROME_PATH if needed.
import platform as _platform
_default_chrome_paths = {
    "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Linux": "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "Windows": "C:/Program Files/Google/Chrome/Application/chrome.exe",
}
WIN_CHROME_PATH = os.environ.get("CHROME_PATH") or _default_chrome_paths.get(
    _platform.system(), "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

DAEMON_FILE_NAME = ".daemon.json"
DAEMON_PROFILE_DIR = ".profile"
DEFAULT_DAEMON_PORT = 9222


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def apply_stealth(page):
    """Apply stealth patches to avoid bot detection."""
    try:
        from playwright_stealth import stealth as stealth_module
        stealth_obj = stealth_module.Stealth()
        stealth_obj.apply_stealth_sync(page)
    except Exception:
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.navigator.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
        """)


# ---------------------------------------------------------------------------
# Daemon (long-lived headed browser) helpers
# ---------------------------------------------------------------------------

def daemon_file_path(state_dir: str) -> Path:
    return Path(state_dir) / DAEMON_FILE_NAME


def daemon_profile_path(state_dir: str) -> Path:
    return Path(state_dir) / DAEMON_PROFILE_DIR


def read_daemon_info(state_dir: str) -> dict | None:
    f = daemon_file_path(state_dir)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def daemon_is_running(state_dir: str) -> bool:
    info = read_daemon_info(state_dir)
    if not info:
        return False
    if not is_pid_alive(info.get("pid", 0)):
        return False
    # Probe CDP endpoint
    port = info.get("port", DEFAULT_DAEMON_PORT)
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2):
            return True
    except Exception:
        return False


def connect_daemon(playwright, state_dir: str):
    """Try to connect to a running daemon. Returns (browser, context) or (None, None)."""
    if not daemon_is_running(state_dir):
        return None, None
    info = read_daemon_info(state_dir)
    port = info.get("port", DEFAULT_DAEMON_PORT)
    try:
        # Resolve websocket URL ourselves to avoid Playwright's trailing-slash
        # quirk on some Chrome versions where /json/version/ returns 400.
        try:
            with urllib.request.urlopen(
                f"http://localhost:{port}/json/version", timeout=3
            ) as resp:
                ws_url = json.loads(resp.read()).get("webSocketDebuggerUrl")
        except Exception:
            ws_url = None
        endpoint = ws_url or f"http://localhost:{port}"
        browser = playwright.chromium.connect_over_cdp(endpoint)
        if browser.contexts:
            return browser, browser.contexts[0]
        return browser, browser.new_context(viewport={"width": 1920, "height": 1080})
    except Exception as e:
        print(f"WARN: failed to connect to daemon: {e}")
        return None, None


def inject_saved_cookies(context, site_id: str, state_dir: str) -> int:
    """Inject cookies from saved storage_state JSON into daemon context.

    Skips cookies whose domain already has cookies in the context.
    Returns number of cookies added.
    """
    state_path = get_state_for_context(site_id, state_dir)
    if not state_path:
        return 0
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved = data.get("cookies", [])
        if not saved:
            return 0

        # Check if any cookie for this site already exists in context
        existing = context.cookies()
        existing_domains = {c.get("domain", "").lstrip(".") for c in existing}
        # Determine target domain root from saved cookies
        target_roots = {c.get("domain", "").lstrip(".").lstrip("www.") for c in saved}
        if existing_domains & target_roots:
            return 0  # Already have cookies, don't overwrite

        context.add_cookies(saved)
        return len(saved)
    except Exception as e:
        print(f"WARN: cookie injection failed: {e}")
        return 0


def cmd_daemon(state_dir: str = ".browser-state", port: int = DEFAULT_DAEMON_PORT,
               url: str = None):
    """Start a long-lived headed browser via subprocess + CDP port.

    We spawn Chrome directly (not via Playwright) because launch_persistent_context
    forces --remote-debugging-pipe which conflicts with --remote-debugging-port.
    """
    import subprocess

    Path(state_dir).mkdir(parents=True, exist_ok=True)

    if daemon_is_running(state_dir):
        info = read_daemon_info(state_dir)
        print(f"ERROR: daemon already running (pid={info.get('pid')}, port={info.get('port')})")
        print(f"HINT: run 'web_crawler.py stop' first")
        return 2

    profile_dir = daemon_profile_path(state_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    daemon_file = daemon_file_path(state_dir)

    if not Path(WIN_CHROME_PATH).exists():
        print(f"ERROR: Chrome not found at {WIN_CHROME_PATH}")
        print("HINT: install Chrome on Windows or edit WIN_CHROME_PATH in web_crawler.py")
        return 3

    # Convert WSL path -> Windows path so Chrome.exe accepts the user-data-dir.
    # Without this, Chrome silently joins an existing user instance and exits.
    try:
        win_profile_dir = subprocess.check_output(
            ["wslpath", "-w", str(profile_dir)], text=True
        ).strip()
    except Exception:
        win_profile_dir = str(profile_dir)

    chrome_cmd = [
        WIN_CHROME_PATH,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={win_profile_dir}",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-popup-blocking",
        url or "https://x.com/home",
    ]

    print(f"Starting Chrome on CDP port {port}...")
    print(f"Profile dir: {profile_dir}")

    chrome_proc = subprocess.Popen(
        chrome_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for CDP endpoint
    cdp_ready = False
    for _ in range(30):
        time.sleep(1)
        if chrome_proc.poll() is not None:
            print(f"ERROR: Chrome exited prematurely (code={chrome_proc.returncode})")
            return 4
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2):
                cdp_ready = True
                break
        except Exception:
            continue

    if not cdp_ready:
        print("ERROR: CDP endpoint did not become ready in 30s")
        chrome_proc.terminate()
        return 5

    daemon_file.write_text(json.dumps({
        "pid": chrome_proc.pid,
        "port": port,
        "profile_dir": str(profile_dir),
        "started_at": time.time(),
    }, indent=2), encoding="utf-8")

    print(f"Daemon ready (chrome pid={chrome_proc.pid}, supervisor pid={os.getpid()}).")
    print(f"Browser visible. CDP at http://localhost:{port}")
    print("Use 'scrape', 'login', 'screenshot' from another terminal.")
    print("Press Ctrl+C or run 'web_crawler.py stop' to exit.")

    stop_requested = {"flag": False}

    def handle_signal(signum, frame):
        stop_requested["flag"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while not stop_requested["flag"]:
            if chrome_proc.poll() is not None:
                print("Chrome exited.")
                break
            time.sleep(0.5)
    finally:
        if chrome_proc.poll() is None:
            print("Stopping Chrome...")
            chrome_proc.terminate()
            try:
                chrome_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                chrome_proc.kill()
        daemon_file.unlink(missing_ok=True)

    print("Daemon stopped.")
    return 0


def cmd_stop(state_dir: str = ".browser-state"):
    """Stop a running daemon by PID."""
    info = read_daemon_info(state_dir)
    if not info:
        print("No daemon record found.")
        return 0
    pid = info.get("pid", 0)
    if not is_pid_alive(pid):
        print(f"Daemon record exists but pid {pid} is not alive — cleaning up.")
        daemon_file_path(state_dir).unlink(missing_ok=True)
        return 0

    print(f"Stopping daemon (pid={pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"ERROR: kill failed: {e}")
        return 1

    # Wait up to 10s
    for _ in range(20):
        time.sleep(0.5)
        if not is_pid_alive(pid):
            break
    if is_pid_alive(pid):
        print("WARN: daemon did not exit in time, sending SIGKILL")
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    daemon_file_path(state_dir).unlink(missing_ok=True)
    print("Daemon stopped.")
    return 0


# ---------------------------------------------------------------------------
# Standalone (non-daemon) browser context
# ---------------------------------------------------------------------------

def create_browser_context(playwright, headless: bool = True, state_path: str = None,
                           viewport: dict = None) -> tuple:
    """Create a browser+context for one-shot use."""
    launch_opts = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    }
    if Path(WIN_CHROME_PATH).exists():
        launch_opts["executable_path"] = WIN_CHROME_PATH

    browser = playwright.chromium.launch(**launch_opts)

    context_options = {
        "viewport": viewport or {"width": 1920, "height": 1080},
        "user_agent": get_random_user_agent(),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }
    if state_path and Path(state_path).exists():
        context_options["storage_state"] = state_path

    context = browser.new_context(**context_options)
    return browser, context


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_login(site: str, state_dir: str = ".browser-state", timeout: int = 300):
    """Manual login. Reuses the daemon's browser if it is running."""
    site_info = resolve_site(site)
    site_id = site_info["id"]

    with sync_playwright() as p:
        daemon_browser, daemon_context = connect_daemon(p, state_dir)

        if daemon_context is not None:
            print(f"Daemon detected — opening login tab inside the running browser.")
            print(f"Cookies will persist automatically in the daemon's profile.")
            page = daemon_context.new_page()
            apply_stealth(page)
            page.goto(site_info["url"], wait_until="domcontentloaded", timeout=60000)
            print(f"Please log in manually. Tab will stay open for {timeout}s "
                  "(or close the tab to finish).")

            start = time.time()
            try:
                while time.time() - start < timeout:
                    time.sleep(1)
                    if page.is_closed():
                        break
            except KeyboardInterrupt:
                pass

            # Daemon's user_data_dir already persists cookies. Also dump a
            # storage_state JSON so non-daemon scrape calls still work.
            try:
                state_path = save_state(daemon_context, site_id, state_dir)
                meta = validate_state(state_path)
                print(f"\n✓ Snapshot saved to {state_path} "
                      f"({meta['cookie_count']} cookies, {meta['origin_count']} origins)")
            except Exception as e:
                print(f"WARN: could not export storage_state: {e}")

            if not page.is_closed():
                page.close()
            return 0

        # No daemon — fall back to a one-shot headed browser
        print(f"Opening one-shot browser for {site_info['url']}...")
        print(f"Log in manually. Closes after {timeout}s or on Ctrl+C.")
        launch_opts = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        }
        if Path(WIN_CHROME_PATH).exists():
            launch_opts["executable_path"] = WIN_CHROME_PATH
        browser = p.chromium.launch(**launch_opts)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=get_random_user_agent(),
        )
        page = context.new_page()
        apply_stealth(page)
        page.goto(site_info["url"], wait_until="domcontentloaded", timeout=60000)

        start = time.time()
        try:
            while time.time() - start < timeout:
                time.sleep(1)
                if not browser.is_connected():
                    break
        except KeyboardInterrupt:
            print("\nClosing browser and saving state...")

        state_path = save_state(context, site_id, state_dir)
        print(f"State saved to: {state_path}")
        browser.close()

    meta = validate_state(state_path)
    if meta["valid"]:
        print(f"✓ Saved {meta['cookie_count']} cookies, {meta['origin_count']} origins")
    else:
        print(f"⚠ Warning: {meta['error']}")
    return 0


def cmd_scrape(url: str, format: str = "markdown", state_dir: str = ".browser-state",
               output: str = None, site: str = None, headless: bool = True,
               wait_for: str = "domcontentloaded", scroll: bool = False,
               scroll_count: int = 5, stealth: bool = True, keep_tab: bool = False):
    """Scrape a URL. Reuses the daemon's browser when available."""
    from urllib.parse import urlparse

    site_info = resolve_site(url if "://" in url else f"https://{url}")
    site_id = site_info["id"]

    try:
        with sync_playwright() as p:
            daemon_browser, daemon_context = connect_daemon(p, state_dir)
            using_daemon = daemon_context is not None

            if using_daemon:
                print(f"Reusing daemon browser (visible) for {site_id}")
                injected = inject_saved_cookies(daemon_context, site_id, state_dir)
                if injected:
                    print(f"Injected {injected} saved cookies for {site_id}")
                context = daemon_context
                browser = daemon_browser
            else:
                state_path = get_state_for_context(site_id, state_dir)
                if state_path:
                    print(f"Using saved state for {site_id}")
                else:
                    print(f"No saved state for {site_id}, proceeding without auth")
                browser, context = create_browser_context(
                    p, headless=headless, state_path=state_path
                )

            page = context.new_page()
            if stealth:
                apply_stealth(page)

            print(f"Loading: {url}")
            try:
                page.goto(url, wait_until=wait_for, timeout=60000)
            except Exception as e:
                print(f"Error loading page: {e}")
                if not using_daemon:
                    browser.close()
                else:
                    page.close()
                return 10

            current_url = page.url
            parsed = urlparse(current_url)
            if "/login" in parsed.path or "/signin" in parsed.path:
                print("ERROR [AUTH]: Redirected to login page")
                print(f"HINT: Run: web_crawler.py login {site_id}")
                if not using_daemon:
                    browser.close()
                else:
                    page.close()
                return 14

            if scroll:
                print(f"Scrolling {scroll_count} times...")
                for _ in range(scroll_count):
                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(random.uniform(0.8, 1.5))

            extractor = get_extractor(url, site)
            extractor.wait_for_content(page)
            time.sleep(random.uniform(0.3, 0.8))

            content = extractor.extract(page)

            # Cleanup: only close the tab when reusing daemon, full close otherwise
            if using_daemon:
                if not keep_tab:
                    page.close()
            else:
                browser.close()

            if format == "markdown":
                result = html_to_markdown(content.raw_html or f"# {content.title}\n\n{content.content_text}")
            else:
                result = html_to_json(content)

            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                with open(output, "w", encoding="utf-8") as f:
                    f.write(result)
                print(f"Output saved to: {output}")
            else:
                print(result)
            return 0

    except Exception as e:
        print(f"ERROR [GENERAL]: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_screenshot(url: str, output: str = None, state_dir: str = ".browser-state",
                   full_page: bool = True, site: str = None, keep_tab: bool = False):
    """Take a screenshot of a URL."""
    site_info = resolve_site(url if "://" in url else f"https://{url}")
    site_id = site_info["id"]

    if not output:
        output = f"/tmp/screenshot_{site_id}_{int(time.time())}.png"

    try:
        with sync_playwright() as p:
            daemon_browser, daemon_context = connect_daemon(p, state_dir)
            using_daemon = daemon_context is not None

            if using_daemon:
                print(f"Reusing daemon browser (visible)")
                context = daemon_context
                browser = daemon_browser
            else:
                state_path = get_state_for_context(site_id, state_dir)
                browser, context = create_browser_context(p, headless=True, state_path=state_path)

            page = context.new_page()
            apply_stealth(page)

            print(f"Loading: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            page.screenshot(path=output, full_page=full_page)
            print(f"Screenshot saved to: {output}")

            if using_daemon:
                if not keep_tab:
                    page.close()
            else:
                browser.close()
            return 0

    except Exception as e:
        print(f"ERROR [GENERAL]: {e}")
        return 1


def _require_daemon(playwright, state_dir: str):
    """Connect to daemon or print a friendly error. Returns (browser, context) or (None, None)."""
    browser, context = connect_daemon(playwright, state_dir)
    if context is None:
        print("ERROR: this command needs the daemon to be running.")
        print("HINT: in another terminal run:")
        print("      python web_crawler.py daemon")
        return None, None
    return browser, context


def cmd_mine_topic(query: str, since: str = None, until: str = None,
                   sort: str = "top", max_scrolls: int = 20, top_n: int = 20,
                   detail: int = 0, fmt: str = "markdown",
                   output: str = None, state_dir: str = ".browser-state",
                   no_expand: bool = False):
    """Mine X for a topic in a date range."""
    import x_mine

    try:
        with sync_playwright() as p:
            browser, context = _require_daemon(p, state_dir)
            if context is None:
                return 2

            print(f"Mining X for '{query}' "
                  f"(since={since or '-'}, until={until or '-'}, sort={sort})")
            inject_saved_cookies(context, "x", state_dir)

            items = x_mine.mine_topic(
                context, query, since=since, until=until, sort=sort,
                max_scrolls=max_scrolls, expand_queries=not no_expand,
            )
            print(f"Collected {len(items)} tweets")

            details = []
            if detail > 0 and items:
                print(f"Opening top {detail} tweets for detail...")
                for i, t in enumerate(items[:detail], 1):
                    print(f"  [{i}/{detail}] {t['url']}")
                    try:
                        d = x_mine.fetch_detail(context, t["url"], max_replies=20)
                        details.append(d)
                    except Exception as e:
                        print(f"  WARN: detail failed: {e}")

            payload = {
                "query": query, "since": since, "until": until, "sort": sort,
                "items": items[:top_n] if top_n else items,
                "all_count": len(items),
                "details": details,
            }

            if fmt == "json":
                result = json.dumps(payload, ensure_ascii=False, indent=2)
            else:
                title = f"X topic: {query}"
                if since or until:
                    title += f" ({since or '*'} → {until or '*'})"
                md = x_mine.items_to_markdown(items, title=title, top_n=top_n)
                if details:
                    md += "\n\n# Detail expansions\n\n"
                    for d in details:
                        md += x_mine.detail_to_markdown(d) + "\n\n"
                result = md

            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(result, encoding="utf-8")
                print(f"Output saved to: {output}")
            else:
                print(result)
            return 0

    except Exception as e:
        print(f"ERROR [GENERAL]: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_mine_following(tab: str = "foryou", since: str = None, until: str = None,
                       max_scrolls: int = 30, top_n: int = 30, detail: int = 0,
                       fmt: str = "markdown", output: str = None,
                       state_dir: str = ".browser-state"):
    """Mine the user's home timeline (For You or Following)."""
    import x_mine

    try:
        with sync_playwright() as p:
            browser, context = _require_daemon(p, state_dir)
            if context is None:
                return 2

            inject_saved_cookies(context, "x", state_dir)
            print(f"Mining home timeline tab='{tab}' "
                  f"since={since or '-'} until={until or '-'}")

            items = x_mine.mine_following(
                context, tab=tab, since=since, until=until, max_scrolls=max_scrolls,
            )
            print(f"Collected {len(items)} tweets")

            details = []
            if detail > 0 and items:
                print(f"Opening top {detail} tweets for detail...")
                for i, t in enumerate(items[:detail], 1):
                    print(f"  [{i}/{detail}] {t['url']}")
                    try:
                        d = x_mine.fetch_detail(context, t["url"], max_replies=20)
                        details.append(d)
                    except Exception as e:
                        print(f"  WARN: detail failed: {e}")

            payload = {
                "tab": tab, "since": since, "until": until,
                "items": items[:top_n] if top_n else items,
                "all_count": len(items),
                "details": details,
            }

            if fmt == "json":
                result = json.dumps(payload, ensure_ascii=False, indent=2)
            else:
                title = f"X home ({tab})"
                if since or until:
                    title += f" {since or '*'} → {until or '*'}"
                md = x_mine.items_to_markdown(items, title=title, top_n=top_n)
                if details:
                    md += "\n\n# Detail expansions\n\n"
                    for d in details:
                        md += x_mine.detail_to_markdown(d) + "\n\n"
                result = md

            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(result, encoding="utf-8")
                print(f"Output saved to: {output}")
            else:
                print(result)
            return 0

    except Exception as e:
        print(f"ERROR [GENERAL]: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_detail(target: str, max_replies: int = 30, fmt: str = "markdown",
               output: str = None, state_dir: str = ".browser-state"):
    """Open one tweet and capture its main content + thread + replies."""
    import x_mine

    try:
        with sync_playwright() as p:
            browser, context = _require_daemon(p, state_dir)
            if context is None:
                return 2
            inject_saved_cookies(context, "x", state_dir)

            print(f"Opening detail for: {target}")
            d = x_mine.fetch_detail(context, target, max_replies=max_replies)

            if fmt == "json":
                result = json.dumps(d, ensure_ascii=False, indent=2)
            else:
                result = x_mine.detail_to_markdown(d)

            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(result, encoding="utf-8")
                print(f"Output saved to: {output}")
            else:
                print(result)
            return 0
    except Exception as e:
        print(f"ERROR [GENERAL]: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_xhs(mode: str, args, state_dir: str = ".browser-state"):
    """Convert crawled content into Xiaohongshu image+text drafts."""
    import x_mine
    import xhs_converter as xhs

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser, context = _require_daemon(p, state_dir)
            if context is None:
                return 2
            inject_saved_cookies(context, "x", state_dir)

            picks_data: list[dict] = []
            source_meta = {"mode": mode}

            if mode == "from-topic":
                source_meta.update({
                    "query": args.query, "since": args.since, "until": args.until,
                    "sort": args.sort,
                })
                print(f"[xhs] mining topic '{args.query}' "
                      f"(since={args.since or '-'}, until={args.until or '-'}, sort={args.sort})")
                items = x_mine.mine_topic(
                    context, args.query, since=args.since, until=args.until,
                    sort=args.sort, max_scrolls=args.max_scrolls,
                )
                picks_data = items[:args.pick]

            elif mode == "from-following":
                source_meta.update({"tab": args.tab, "since": args.since, "until": args.until})
                print(f"[xhs] mining following tab='{args.tab}' since={args.since or '-'}")
                items = x_mine.mine_following(
                    context, tab=args.tab, since=args.since, until=args.until,
                    max_scrolls=args.max_scrolls,
                )
                picks_data = items[:args.pick]

            elif mode == "from-url":
                source_meta["urls"] = args.urls
                # For each URL: if X tweet, fetch detail (with thread merge); else generic scrape
                for u in args.urls:
                    if "x.com/" in u or "twitter.com/" in u:
                        try:
                            d = x_mine.fetch_detail(context, u, max_replies=0)
                            main = dict(d.get("main") or {})
                            thread = d.get("thread") or []
                            # Merge same-author thread continuations into the main
                            # tweet so long-form essays come back complete. Also
                            # collect media across all thread tweets.
                            if thread:
                                main_text = main.get("text", "") or ""
                                extra = "\n\n".join(t.get("text", "") for t in thread if t.get("text"))
                                if extra:
                                    main["text"] = (main_text + ("\n\n" if main_text else "") + extra).strip()
                                merged_media = list(main.get("media") or [])
                                seen_urls = {m.get("url") for m in merged_media if m.get("url")}
                                for t in thread:
                                    for m in (t.get("media") or []):
                                        url_ = m.get("url")
                                        if url_ and url_ not in seen_urls:
                                            merged_media.append(m)
                                            seen_urls.add(url_)
                                main["media"] = merged_media
                                main["thread_tweet_count"] = 1 + len(thread)
                            if not main.get("text"):
                                print(f"[xhs] WARNING: empty text captured for {u} — "
                                      f"draft body may be sparse")
                            picks_data.append(main)
                        except Exception as e:
                            print(f"[xhs] tweet fetch failed: {e}")
                    else:
                        # Generic scrape via the existing extractor pipeline
                        page = context.new_page()
                        try:
                            page.goto(u, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(2)
                            ext = get_extractor(u, None)
                            ext.wait_for_content(page)
                            content = ext.extract(page)
                            picks_data.append({
                                "title": content.title,
                                "author": content.author,
                                "url": content.url,
                                "content_text": content.content_text,
                                "images": content.images or [],
                                "site": content.site,
                            })
                        except Exception as e:
                            print(f"[xhs] page scrape failed for {u}: {e}")
                        finally:
                            page.close()
            else:
                print(f"ERROR: unknown xhs mode {mode}")
                return 2

            if not picks_data:
                print("No content available to convert.")
                return 3

            print(f"[xhs] preparing {len(picks_data)} picks → {output_dir}")
            picks = []
            for i, item in enumerate(picks_data, 1):
                print(f"  [{i}/{len(picks_data)}] {item.get('author','')} {item.get('handle','')} "
                      f"{(item.get('text') or item.get('title') or '')[:60]}")
                if "text" in item or "handle" in item:
                    pick = xhs.prepare_pick_from_tweet(
                        item, output_dir, idx=i,
                        screenshot=args.screenshot, context=context,
                        style=args.style,
                    )
                else:
                    pick = xhs.prepare_pick_from_page(
                        item, output_dir, idx=i,
                        screenshot=args.screenshot, context=context,
                        style=args.style,
                    )
                picks.append(pick)

            manifest = xhs.write_manifest(output_dir, source_meta, picks)
            print()
            print(f"✓ Done. Manifest: {manifest}")
            print()
            for p in picks:
                print(f"  pick-{p['idx']:02d}: {p['draft']['title']}")
                print(f"    dir: {p['pick_dir']}")
                print(f"    cover: {p.get('cover')}")
                print(f"    images: {len(p.get('images') or [])}")
                print()
            return 0

    except Exception as e:
        print(f"ERROR [GENERAL]: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_states(state_dir: str = ".browser-state"):
    """List all saved browser states and daemon status."""
    if daemon_is_running(state_dir):
        info = read_daemon_info(state_dir)
        print(f"● Daemon: RUNNING (pid={info.get('pid')}, port={info.get('port')})\n")
    else:
        print("○ Daemon: not running\n")

    states = list_saved_states(state_dir)
    if not states:
        print("No saved browser states found.")
        print(f"Run 'web_crawler.py login <site>' to create one.")
        return 0

    print(f"Browser states in '{state_dir}/':\n")
    for s in states:
        status = "✓" if s["valid"] else "✗"
        print(f"  {status} {s['site_id']}")
        print(f"      Cookies: {s['cookie_count']}, Origins: {s['origin_count']}")
        print(f"      Size: {s['file_size_bytes'] / 1024:.1f} KB, Modified: {s['last_modified'][:19]}")
        if s["error"]:
            print(f"      ⚠ {s['error']}")
        print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Web crawler with persistent login state and long-lived browser daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Typical workflow:
  # Terminal A — keep browser visible
  python web_crawler.py daemon

  # Terminal B — login + scrape inside the visible browser
  python web_crawler.py login x
  python web_crawler.py scrape "https://x.com/user/status/123" --format markdown

  # Stop when done
  python web_crawler.py stop
        """,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("daemon", help="Start a long-lived visible browser (foreground)")
    d.add_argument("--state-dir", default=".browser-state")
    d.add_argument("--port", type=int, default=DEFAULT_DAEMON_PORT)
    d.add_argument("--url", help="Optional URL to open on start")

    s = sub.add_parser("stop", help="Stop the running daemon")
    s.add_argument("--state-dir", default=".browser-state")

    lg = sub.add_parser("login", help="Open browser for manual login")
    lg.add_argument("site", help="Site name or URL (e.g. x, xiaohongshu)")
    lg.add_argument("--state-dir", default=".browser-state")
    lg.add_argument("--timeout", type=int, default=300)

    sc = sub.add_parser("scrape", help="Scrape a URL")
    sc.add_argument("url")
    sc.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sc.add_argument("--output", "-o")
    sc.add_argument("--site")
    sc.add_argument("--state-dir", default=".browser-state")
    sc.add_argument("--headless", action="store_true", default=True,
                    help="(no-op when daemon is running) Run standalone browser headless")
    sc.add_argument("--headed", dest="headless", action="store_false")
    sc.add_argument("--wait-for", default="domcontentloaded",
                    choices=["load", "domcontentloaded", "networkidle"])
    sc.add_argument("--scroll", action="store_true")
    sc.add_argument("--scroll-count", type=int, default=5)
    sc.add_argument("--no-stealth", dest="stealth", action="store_false", default=True)
    sc.add_argument("--keep-tab", action="store_true",
                    help="When using daemon, leave the tab open after scrape")

    sh = sub.add_parser("screenshot", help="Take a screenshot")
    sh.add_argument("url")
    sh.add_argument("--output", "-o")
    sh.add_argument("--state-dir", default=".browser-state")
    sh.add_argument("--no-full", dest="full_page", action="store_false", default=True)
    sh.add_argument("--site")
    sh.add_argument("--keep-tab", action="store_true")

    st = sub.add_parser("states", help="List saved browser states and daemon status")
    st.add_argument("--state-dir", default=".browser-state")

    # mine: topic / following
    mine = sub.add_parser("mine", help="X-specific content mining (needs daemon)")
    mine_sub = mine.add_subparsers(dest="mine_cmd", required=True)

    mt = mine_sub.add_parser("topic", help="Search X by topic + date range")
    mt.add_argument("query", help='Search query, e.g. "AI agent" or "AI agent OR agentic"')
    mt.add_argument("--since", help="YYYY-MM-DD inclusive")
    mt.add_argument("--until", help="YYYY-MM-DD inclusive")
    mt.add_argument("--sort", choices=["top", "latest", "both"], default="both",
                    help="Which X tab to crawl. 'both' = Top + Latest (default)")
    mt.add_argument("--max-scrolls", type=int, default=20)
    mt.add_argument("--top-n", type=int, default=20, help="Show top N in output (0=all)")
    mt.add_argument("--detail", type=int, default=0,
                    help="Click into top-N tweets to capture replies")
    mt.add_argument("--expand", action="store_true",
                    help="Also try a quoted-phrase variant of the query")
    mt.add_argument("--format", choices=["markdown", "json"], default="markdown")
    mt.add_argument("--output", "-o")
    mt.add_argument("--state-dir", default=".browser-state")

    mf = mine_sub.add_parser("following",
                              help="Mine your home timeline (For You / Following)")
    mf.add_argument("--tab", choices=["foryou", "following"], default="foryou")
    mf.add_argument("--since", help="YYYY-MM-DD inclusive")
    mf.add_argument("--until", help="YYYY-MM-DD inclusive")
    mf.add_argument("--max-scrolls", type=int, default=30)
    mf.add_argument("--top-n", type=int, default=30)
    mf.add_argument("--detail", type=int, default=0)
    mf.add_argument("--format", choices=["markdown", "json"], default="markdown")
    mf.add_argument("--output", "-o")
    mf.add_argument("--state-dir", default=".browser-state")

    # detail
    dt = sub.add_parser("detail", help="Open a single tweet and grab its replies")
    dt.add_argument("target", help="Tweet URL, /username/status/123 path, or numeric ID")
    dt.add_argument("--max-replies", type=int, default=30)
    dt.add_argument("--format", choices=["markdown", "json"], default="markdown")
    dt.add_argument("--output", "-o")
    dt.add_argument("--state-dir", default=".browser-state")

    # xhs: convert content into Xiaohongshu drafts
    xhs_p = sub.add_parser("xhs", help="Convert crawled content into Xiaohongshu drafts")
    xhs_sub = xhs_p.add_subparsers(dest="xhs_cmd", required=True)

    def _xhs_common(p):
        p.add_argument("--pick", type=int, default=3, help="How many picks to convert")
        p.add_argument("--max-scrolls", type=int, default=20)
        p.add_argument("--output-dir", "-o", default="./xhs_drafts")
        p.add_argument("--no-screenshot", dest="screenshot", action="store_false", default=True,
                       help="Skip screenshot of the source card/page")
        p.add_argument("--state-dir", default=".browser-state")
        p.add_argument("--style", choices=["aida", "scqa", "pass", "hook"], default="hook",
                       help="Viral body framework: aida (种草) / scqa (观点) / pass (解决方案) / hook (资讯, default)")

    xt = xhs_sub.add_parser("from-topic", help="Search X by topic, convert top picks")
    xt.add_argument("query")
    xt.add_argument("--since")
    xt.add_argument("--until")
    xt.add_argument("--sort", choices=["top", "latest", "both"], default="both")
    _xhs_common(xt)

    xf = xhs_sub.add_parser("from-following", help="Convert top picks from your home timeline")
    xf.add_argument("--tab", choices=["foryou", "following"], default="following")
    xf.add_argument("--since")
    xf.add_argument("--until")
    _xhs_common(xf)

    xu = xhs_sub.add_parser("from-url", help="Convert a list of URLs (tweets or web pages)")
    xu.add_argument("urls", nargs="+", help="One or more tweet/page URLs")
    _xhs_common(xu)

    args = parser.parse_args()

    if args.command == "daemon":
        return cmd_daemon(args.state_dir, args.port, args.url)
    if args.command == "stop":
        return cmd_stop(args.state_dir)
    if args.command == "login":
        return cmd_login(args.site, args.state_dir, args.timeout)
    if args.command == "scrape":
        return cmd_scrape(args.url, args.format, args.state_dir, args.output, args.site,
                          args.headless, args.wait_for, args.scroll, args.scroll_count,
                          args.stealth, args.keep_tab)
    if args.command == "screenshot":
        return cmd_screenshot(args.url, args.output, args.state_dir, args.full_page,
                              args.site, args.keep_tab)
    if args.command == "states":
        return cmd_states(args.state_dir)
    if args.command == "mine":
        if args.mine_cmd == "topic":
            return cmd_mine_topic(
                args.query, args.since, args.until, args.sort,
                args.max_scrolls, args.top_n, args.detail,
                args.format, args.output, args.state_dir, not args.expand,
            )
        if args.mine_cmd == "following":
            return cmd_mine_following(
                args.tab, args.since, args.until, args.max_scrolls,
                args.top_n, args.detail, args.format, args.output, args.state_dir,
            )
    if args.command == "detail":
        return cmd_detail(args.target, args.max_replies, args.format,
                          args.output, args.state_dir)
    if args.command == "xhs":
        return cmd_xhs(args.xhs_cmd, args, args.state_dir)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
