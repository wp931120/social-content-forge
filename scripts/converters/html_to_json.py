"""Convert ExtractedContent to structured JSON."""

import json
import sys
from pathlib import Path
from typing import Optional

# Handle imports when run as script
if __name__ == "__main__" or len(sys.path) < 3:
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from extractors.base import ExtractedContent
except ImportError:
    from .extractors.base import ExtractedContent


def convert(extracted: ExtractedContent, include_raw: bool = False,
            include_images: bool = True, include_links: bool = False) -> str:
    """Convert ExtractedContent to a structured JSON string.

    Args:
        extracted: ExtractedContent instance from an extractor.
        include_raw: Include raw HTML in output.
        include_images: Include image references.
        include_links: Include link references (can be very large).
    """
    data = {
        "url": extracted.url,
        "site": extracted.site,
        "title": extracted.title,
        "author": extracted.author,
        "date": extracted.date,
        "content": extracted.content_text,
        "metadata": extracted.metadata,
    }

    if include_images and extracted.images:
        data["images"] = extracted.images

    if include_links and extracted.links:
        data["links"] = extracted.links[:100]  # Cap links to avoid huge output

    if include_raw and extracted.raw_html:
        data["raw_html"] = extracted.raw_html

    return json.dumps(data, ensure_ascii=False, indent=2)


def to_dict(extracted: ExtractedContent, include_raw: bool = False,
            include_images: bool = True, include_links: bool = False) -> dict:
    """Convert ExtractedContent to a dict (for programmatic use)."""
    data = {
        "url": extracted.url,
        "site": extracted.site,
        "title": extracted.title,
        "author": extracted.author,
        "date": extracted.date,
        "content": extracted.content_text,
        "metadata": extracted.metadata,
    }

    if include_images and extracted.images:
        data["images"] = extracted.images

    if include_links and extracted.links:
        data["links"] = extracted.links[:100]

    if include_raw and extracted.raw_html:
        data["raw_html"] = extracted.raw_html

    return data