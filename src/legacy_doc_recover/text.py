"""Text decoding and conservative Word control-character normalisation."""

from __future__ import annotations

from .doc import FIBInfo, TextPiece
from .errors import DocFormatError

# A deliberately small language-ID to Windows code page map for common legacy
# compressed text. --codepage can override this when a document uses another
# locale or charset. Unknown LIDs intentionally fall back to cp1252 with a warning.
_LID_CODEPAGES = {
    0x0401: "cp1256",  # Arabic (Saudi Arabia)
    0x0404: "cp950",   # Chinese (Traditional, Taiwan)
    0x0405: "cp1250",  # Czech
    0x0408: "cp1253",  # Greek
    0x0409: "cp1252",  # English (United States)
    0x040A: "cp1252",  # Spanish (Traditional Sort)
    0x040D: "cp1255",  # Hebrew
    0x040E: "cp1250",  # Hungarian
    0x0411: "cp932",   # Japanese
    0x0412: "cp949",   # Korean
    0x0415: "cp1250",  # Polish
    0x0419: "cp1251",  # Russian
    0x041F: "cp1254",  # Turkish
    0x0422: "cp1251",  # Ukrainian
    0x0425: "cp1257",  # Estonian
    0x0426: "cp1257",  # Latvian
    0x0427: "cp1257",  # Lithuanian
    0x0804: "cp936",   # Chinese (Simplified, PRC)
    0x0809: "cp1252",  # English (United Kingdom)
    0x0C09: "cp1252",  # English (Australia)
    0x1409: "cp1252",  # English (New Zealand)
}


def choose_codepage(lid: int, override: str | None = None) -> tuple[str, str | None]:
    if override:
        # Let Python's codec lookup validate the codec during decode.
        return override, None
    if lid in _LID_CODEPAGES:
        return _LID_CODEPAGES[lid], None
    return "cp1252", f"no code-page mapping for language ID 0x{lid:04X}; using cp1252 fallback"


def extract_text(
    word_document: bytes,
    fib: FIBInfo,
    pieces: list[TextPiece],
    *,
    codepage: str | None = None,
    main_story_only: bool = True,
    normalise_controls: bool = True,
) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    selected_codepage, warning = choose_codepage(fib.lid, codepage)
    if warning:
        warnings.append(warning)

    logical_end = fib.ccp_text if main_story_only and fib.ccp_text is not None else None
    chunks: list[str] = []

    for piece in pieces:
        cp_start = piece.cp_start
        cp_end = piece.cp_end
        if logical_end is not None:
            if cp_start >= logical_end:
                break
            cp_end = min(cp_end, logical_end)
        char_count = cp_end - cp_start
        if char_count <= 0:
            continue

        bytes_per_char = 1 if piece.compressed else 2
        byte_count = char_count * bytes_per_char
        start = piece.file_offset
        end = start + byte_count
        if start < 0 or end > len(word_document):
            raise DocFormatError(
                f"text piece {piece.index} references WordDocument bytes {start}:{end}, outside stream length {len(word_document)}"
            )
        raw = word_document[start:end]
        try:
            decoded = raw.decode(selected_codepage if piece.compressed else "utf-16le", errors="strict")
        except (UnicodeDecodeError, LookupError) as exc:
            if isinstance(exc, LookupError):
                raise DocFormatError(f"unknown Python codec {selected_codepage!r}") from exc
            codec = selected_codepage if piece.compressed else "utf-16le"
            warnings.append(
                f"piece {piece.index} contains invalid {codec} byte sequence; replacement characters were inserted"
            )
            decoded = raw.decode(codec, errors="replace")
        chunks.append(decoded)

    text = "".join(chunks)
    if normalise_controls:
        text = normalise_word_controls(text)
    return text, selected_codepage, warnings


def normalise_word_controls(text: str) -> str:
    # Word's binary text uses CR as the paragraph mark. Preserve useful layout
    # separators without claiming to reconstruct formatting.
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\x0b", "\n")      # manual line break
    text = text.replace("\x0c", "\n\n")   # page/section break, conservatively separated
    text = text.replace("\x07", "\t")      # table cell/row marker: retain separation only

    # Field markers and embedded-object placeholders are structural, not text.
    for marker in ("\x01", "\x13", "\x14", "\x15"):
        text = text.replace(marker, "")

    # Remove remaining C0 controls except tab/newline.
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 0x20)
    return text

