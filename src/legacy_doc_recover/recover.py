"""Top-level recovery orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .cfb import CompoundFile
from .doc import parse_fib, parse_piece_table
from .errors import RecoveryError
from .rawscan import scan_raw_text
from .text import extract_text


@dataclass(slots=True)
class RecoveryResult:
    text: str
    report: dict[str, Any]
    success: bool
    mode: str


def recover_file(
    path: str | Path,
    *,
    codepage: str | None = None,
    all_stories: bool = False,
    allow_raw_fallback: bool = True,
) -> RecoveryResult:
    source = Path(path)
    data = source.read_bytes()
    result = recover_bytes(
        data,
        source_name=source.name,
        codepage=codepage,
        all_stories=all_stories,
        allow_raw_fallback=allow_raw_fallback,
    )
    result.report["source"]["path"] = str(source)
    return result


def recover_bytes(
    data: bytes,
    *,
    source_name: str = "<bytes>",
    codepage: str | None = None,
    all_stories: bool = False,
    allow_raw_fallback: bool = True,
) -> RecoveryResult:
    report: dict[str, Any] = {
        "tool": {"name": "legacy-doc-recover", "version": "0.1.0"},
        "source": {
            "name": source_name,
            "size_bytes": len(data),
            "sha256": sha256(data).hexdigest(),
        },
        "success": False,
        "mode": None,
        "warnings": [],
        "errors": [],
    }

    try:
        cfb = CompoundFile.parse(data)
        report["cfb"] = {
            "major_version": cfb.header.major_version,
            "minor_version": cfb.header.minor_version,
            "sector_size": cfb.header.sector_size,
            "physical_sector_count": cfb.physical_sector_count,
            "num_fat_sectors_declared": cfb.header.num_fat_sectors,
            "fat_sector_ids_used": cfb.fat_sector_ids,
            "first_directory_sector": cfb.header.first_directory_sector,
            "mini_stream_cutoff": cfb.header.mini_stream_cutoff,
            "first_minifat_sector": cfb.header.first_minifat_sector,
            "num_minifat_sectors": cfb.header.num_minifat_sectors,
            "streams": [
                {
                    "name": entry.name,
                    "start_sector": entry.start_sector,
                    "size_bytes": entry.stream_size,
                }
                for entry in cfb.directory_entries
                if entry.is_stream
            ],
        }
        report["warnings"].extend(cfb.warnings)

        word_document = cfb.read_stream("WordDocument")
        fib = parse_fib(word_document)
        table_stream = cfb.read_stream(fib.table_stream)
        pieces = parse_piece_table(table_stream, fib)
        text, selected_codepage, text_warnings = extract_text(
            word_document,
            fib,
            pieces,
            codepage=codepage,
            main_story_only=not all_stories,
        )
        report["warnings"].extend(text_warnings)
        # read_stream can add warnings, so capture them again without duplicates
        report["warnings"] = list(dict.fromkeys(report["warnings"] + cfb.warnings))
        report["word"] = {
            "wIdent": f"0x{fib.w_ident:04X}",
            "nFib": f"0x{fib.n_fib:04X}",
            "language_id": f"0x{fib.lid:04X}",
            "table_stream": fib.table_stream,
            "encrypted": fib.encrypted,
            "obfuscated": fib.obfuscated,
            "fcMin": fib.fc_min,
            "fcMac": fib.fc_mac,
            "ccpText": fib.ccp_text,
            "fcClx": fib.fc_clx,
            "lcbClx": fib.lcb_clx,
            "selected_codepage_for_compressed_text": selected_codepage,
            "main_story_only": not all_stories,
            "piece_count": len(pieces),
            "pieces": [asdict(piece) for piece in pieces],
        }
        report["recovery"] = {
            "character_count": len(text),
            "method": "structured-piece-table",
            "confidence": "high for logical text; formatting/list numbering not reconstructed",
        }
        report["success"] = True
        report["mode"] = "piece_table"
        return RecoveryResult(text=text, report=report, success=True, mode="piece_table")

    except (RecoveryError, ValueError, IndexError) as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        if allow_raw_fallback:
            try:
                raw = scan_raw_text(data, codepage=codepage or "cp1252")
            except LookupError as codec_exc:
                report["errors"].append(f"LookupError: {codec_exc}")
                raw = ""
            if raw:
                report["warnings"].append(
                    "structured recovery failed; output was produced by low-confidence raw scanning"
                )
                report["recovery"] = {
                    "character_count": len(raw),
                    "method": "raw-scan",
                    "confidence": "low",
                }
                report["success"] = True
                report["mode"] = "raw_scan"
                return RecoveryResult(text=raw, report=report, success=True, mode="raw_scan")
        return RecoveryResult(text="", report=report, success=False, mode="failed")

