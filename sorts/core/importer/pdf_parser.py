"""
PDF club list parser.

Extracts club name + description pairs from a plain-text PDF.
Heuristic: a short capitalised line is treated as a club name; the
paragraphs that follow (until the next title) form the description.
"""

from __future__ import annotations
import re
from typing import Any


def parse_clubs_from_pdf(filepath: str) -> list[dict[str, Any]]:
    """Return a list of club dicts extracted from *filepath* (a PDF file).

    Each dict matches the shape expected by ImporterPipeline.run_import_from_list:
        name, summary, description, website, discord, instagram,
        email, image, meeting_frequency, commitment
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF import. "
            "Add 'pypdf>=4.0.0' to requirements.txt."
        ) from exc

    reader = PdfReader(filepath)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return _parse_clubs_from_text(full_text)


def _parse_clubs_from_text(text: str) -> list[dict[str, Any]]:
    """Heuristic block parser: title line followed by body paragraphs."""
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    clubs: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if _looks_like_title(lines[i]):
            name = _clean(lines[i])
            desc_lines: list[str] = []
            i += 1
            while i < len(lines) and not _looks_like_title(lines[i]):
                desc_lines.append(lines[i])
                i += 1
            description = _clean(" ".join(desc_lines))
            summary = description[:160] if description else ""
            if name:
                clubs.append({
                    "name": name,
                    "summary": summary,
                    "description": description,
                    "website": None,
                    "discord": None,
                    "instagram": None,
                    "email": None,
                    "image": None,
                    "meeting_frequency": None,
                    "commitment": None,
                })
        else:
            i += 1

    return clubs


def _looks_like_title(line: str) -> bool:
    """Return True when *line* looks like a club-name heading."""
    if not line:
        return False
    if len(line) > 80:
        return False
    if line[0] in ("*", "-", "•") or line[0].isdigit() or line[0].islower():
        return False
    if line.endswith(".") and len(line.split()) > 6:
        return False
    if re.fullmatch(r"[\d\s\-|/]+", line):
        return False
    return True


def _clean(text: str) -> str:
    """Collapse whitespace and strip typographic noise."""
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\u2014", "-").replace("\u2013", "-").replace("\u00a0", " ")
    return text.strip()
