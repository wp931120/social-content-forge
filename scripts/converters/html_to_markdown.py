"""Convert HTML to Markdown."""

import html2text


def convert(html: str, body_width: int = 0, protect_links: bool = True,
            wrap_links: bool = False, images_to_alt: bool = False) -> str:
    """Convert HTML to Markdown using html2text.

    Args:
        html: Raw HTML string.
        body_width: Line wrap width (0 = no wrapping).
        protect_links: Keep link URLs intact without wrapping.
        wrap_links: Whether to wrap link text.
        images_to_alt: Replace images with alt text only (no URL).
    """
    h2t = html2text.HTML2Text()
    h2t.body_width = body_width
    h2t.ignore_links = False
    h2t.ignore_images = images_to_alt
    h2t.ignore_emphasis = False
    h2t.ignore_tables = False
    h2t.single_line_break = False
    h2t.wrap_links = wrap_links
    h2t.wrap_lists = True
    h2t.ul_item_mark = "- "

    markdown = h2t.handle(html)

    # Post-process: clean up excessive whitespace
    lines = markdown.split("\n")
    cleaned_lines = []
    prev_empty = False

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if not prev_empty:
                cleaned_lines.append("")
            prev_empty = True
        else:
            cleaned_lines.append(stripped)
            prev_empty = False

    # Remove leading/trailing whitespace
    while cleaned_lines and not cleaned_lines[0]:
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()

    return "\n".join(cleaned_lines)