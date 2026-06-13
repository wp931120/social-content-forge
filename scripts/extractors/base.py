"""Base extractor classes for web content extraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedContent:
    """Unified output structure for all extractors."""

    title: str = ""
    author: str = ""
    date: str = ""
    url: str = ""
    site: str = ""
    content_markdown: str = ""
    content_text: str = ""
    metadata: dict = field(default_factory=dict)
    raw_html: str = ""
    images: list = field(default_factory=list)
    links: list = field(default_factory=list)


class BaseExtractor(ABC):
    """Abstract base class for site-specific content extractors."""

    @property
    @abstractmethod
    def site_id(self) -> str:
        """Unique identifier for this extractor's site."""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this extractor can handle the given URL."""

    @abstractmethod
    def extract(self, page) -> ExtractedContent:
        """Extract content from a fully loaded Playwright page."""

    def wait_for_content(self, page, timeout: int = 15000) -> None:
        """Wait for site-specific dynamic content to load. Override as needed."""
        pass
