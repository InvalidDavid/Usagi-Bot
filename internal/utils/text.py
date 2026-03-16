from __future__ import annotations

import re


def strip_html(text: str | None) -> str:
    if not text:
        return "No description available."

    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?i>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned.strip()


def truncate_words(text: str, max_words: int, link: str | None = None) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text

    short_text = " ".join(words[:max_words])
    if link:
        return f"{short_text}... [(more)]({link})"
    return f"{short_text}..."
