"""Extractor registry and auto-detection."""

from typing import Optional
from .base import BaseExtractor, ExtractedContent
from .x_twitter import XTwitterExtractor
from .xiaohongshu import XiaohongshuExtractor
from .generic import GenericExtractor

EXTRACTORS: list[BaseExtractor] = [
    XTwitterExtractor(),
    XiaohongshuExtractor(),
    GenericExtractor(),  # Must be last — can_handle always returns True
]


def get_extractor(url: str, site: Optional[str] = None) -> BaseExtractor:
    """Get the appropriate extractor for a URL.

    If site is specified, force that extractor.
    Otherwise, iterate EXTRACTORS and return first can_handle match.
    """
    if site:
        for ext in EXTRACTORS:
            if ext.site_id == site:
                return ext
        raise ValueError(f"Unknown site extractor: {site}. Available: {[e.site_id for e in EXTRACTORS]}")

    for ext in EXTRACTORS:
        if ext.can_handle(url):
            return ext

    return EXTRACTORS[-1]  # Fallback to generic


def extract_from_page(page, url: str, site: Optional[str] = None) -> ExtractedContent:
    """Convenience: get extractor and extract in one call."""
    extractor = get_extractor(url, site)
    return extractor.extract(page)