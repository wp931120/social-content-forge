"""Browser state management for Playwright storage_state persistence."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

SITE_ALIASES = {
    "x": {"id": "x", "domain": "x.com", "url": "https://x.com"},
    "twitter": {"id": "x", "domain": "x.com", "url": "https://x.com"},
    "xiaohongshu": {"id": "xiaohongshu", "domain": "xiaohongshu.com", "url": "https://www.xiaohongshu.com"},
    "xhs": {"id": "xiaohongshu", "domain": "xiaohongshu.com", "url": "https://www.xiaohongshu.com"},
}


def resolve_site(site: str) -> dict:
    """Resolve a site name/alias or URL to a site config dict.

    Returns: {"id": str, "domain": str, "url": str, "state_file": str}
    """
    site_lower = site.lower().strip()

    if site_lower in SITE_ALIASES:
        info = SITE_ALIASES[site_lower]
        return {**info, "state_file": f"{info['id']}.json"}

    # Try to match by domain from URL
    from urllib.parse import urlparse
    parsed = urlparse(site if "://" in site else f"https://{site}")
    hostname = parsed.hostname or site_lower

    # Check if hostname matches any known alias domain
    for alias, info in SITE_ALIASES.items():
        if info["domain"] in hostname:
            return {**info, "state_file": f"{info['id']}.json"}

    # Unknown site: derive id from domain
    domain_parts = hostname.replace("www.", "").split(".")
    site_id = domain_parts[0] if domain_parts else hostname
    return {
        "id": site_id,
        "domain": hostname,
        "url": f"https://{hostname}",
        "state_file": f"{site_id}.json",
    }


def get_state_path(site_id: str, state_dir: str = ".browser-state") -> Path:
    """Get the path to a site's state file."""
    return Path(state_dir) / f"{site_id}.json"


def state_exists(site_id: str, state_dir: str = ".browser-state") -> bool:
    """Check if a saved state file exists for the given site."""
    return get_state_path(site_id, state_dir).exists()


def save_state(context, site_id: str, state_dir: str = ".browser-state") -> Path:
    """Save browser context state to a JSON file using Playwright's storage_state API.

    Args:
        context: Playwright BrowserContext instance.
        site_id: Site identifier (e.g. 'x', 'xiaohongshu').
        state_dir: Directory to save state files.

    Returns:
        Path to the saved state file.
    """
    state_path = get_state_path(site_id, state_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(state_path))
    return state_path


def get_state_for_context(site_id: str, state_dir: str = ".browser-state") -> Optional[str]:
    """Get the state file path for creating a new context with storage_state.

    Returns the path string if state exists, None otherwise.
    """
    state_path = get_state_path(site_id, state_dir)
    if state_path.exists():
        return str(state_path)
    return None


def validate_state(state_path: Path) -> dict:
    """Validate a state file and return its metadata.

    Returns: {"valid": bool, "cookie_count": int, "origin_count": int,
              "last_modified": str, "file_size_bytes": int, "error": str|None}
    """
    if not state_path.exists():
        return {
            "valid": False,
            "cookie_count": 0,
            "origin_count": 0,
            "last_modified": "",
            "file_size_bytes": 0,
            "error": "State file not found",
        }

    try:
        stat = state_path.stat()
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cookies = data.get("cookies", [])
        origins = data.get("origins", [])

        valid = len(cookies) > 0

        return {
            "valid": valid,
            "cookie_count": len(cookies),
            "origin_count": len(origins),
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "file_size_bytes": stat.st_size,
            "error": None if valid else "State contains no cookies (session likely expired)",
        }
    except (json.JSONDecodeError, KeyError) as e:
        return {
            "valid": False,
            "cookie_count": 0,
            "origin_count": 0,
            "last_modified": "",
            "file_size_bytes": state_path.stat().st_size if state_path.exists() else 0,
            "error": f"Invalid state file: {e}",
        }


def list_saved_states(state_dir: str = ".browser-state") -> list[dict]:
    """List all saved browser states with their metadata."""
    state_path = Path(state_dir)
    if not state_path.exists():
        return []

    results = []
    for f in sorted(state_path.glob("*.json")):
        site_id = f.stem
        meta = validate_state(f)
        results.append({"site_id": site_id, **meta})
    return results
