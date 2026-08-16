"""Low-confidence raw text scanning used only when structured recovery fails."""

from __future__ import annotations

import re


def scan_raw_text(data: bytes, *, min_run: int = 24, codepage: str = "cp1252") -> str:
    """Return labelled low-confidence text runs from the raw file.

    This deliberately favours false negatives over binary garbage. It is not a
    substitute for the Word piece table and does not preserve document order
    reliably when storage is fragmented.
    """
    runs: list[tuple[int, str]] = []

    # Mostly printable single-byte runs, allowing normal whitespace and common
    # Windows-1252 bytes. Score after decoding to reject obvious binary noise.
    pattern = re.compile(rb"[\x09\x0A\x0D\x20-\x7E\x80-\xFF]{%d,}" % min_run)
    for match in pattern.finditer(data):
        text = match.group().decode(codepage, errors="replace")
        if _looks_textual(text):
            runs.append((match.start(), _clean_run(text)))

    # Basic Latin UTF-16LE runs are common enough to be worth a second pass.
    utf16_pattern = re.compile(rb"(?:[\x20-\x7E]\x00){%d,}" % max(8, min_run // 2))
    for match in utf16_pattern.finditer(data):
        text = match.group().decode("utf-16le", errors="replace")
        if _looks_textual(text):
            runs.append((match.start(), _clean_run(text)))

    runs.sort(key=lambda item: item[0])
    if not runs:
        return ""
    out = ["[LOW-CONFIDENCE RAW SCAN — ordering/contents may be incomplete or incorrect]", ""]
    for offset, text in runs:
        out.append(f"--- byte offset 0x{offset:X} ---")
        out.append(text)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _looks_textual(text: str) -> bool:
    if not text:
        return False
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
    alpha_space = sum(ch.isalpha() or ch.isspace() for ch in text)
    return printable / len(text) > 0.97 and alpha_space / len(text) > 0.55


def _clean_run(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 0x20).strip()

