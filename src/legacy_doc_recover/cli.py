from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .recover import recover_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="legacy-doc-recover",
        description="Best-effort text recovery from damaged Word 97-2003 binary .doc files.",
    )
    parser.add_argument("input", type=Path, help="input .doc file")
    parser.add_argument("-o", "--output", type=Path, help="recovered text output path")
    parser.add_argument("--report", type=Path, help="JSON diagnostic report path")
    parser.add_argument(
        "--codepage",
        help="override code page for compressed text (for example cp1252, cp1251, cp932)",
    )
    parser.add_argument(
        "--all-stories",
        action="store_true",
        help="recover the complete logical piece-table range rather than only the main-document story",
    )
    parser.add_argument(
        "--no-raw-fallback",
        action="store_true",
        help="fail instead of attempting low-confidence raw text scanning when structured recovery fails",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="write recovered text to stdout instead of a .recovered.txt file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    result = recover_file(
        args.input,
        codepage=args.codepage,
        all_stories=args.all_stories,
        allow_raw_fallback=not args.no_raw_fallback,
    )

    output = args.output or args.input.with_suffix(".recovered.txt")
    report_path = args.report or args.input.with_suffix(".recovery.json")

    report_path.write_text(json.dumps(result.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if result.success:
        if args.stdout:
            sys.stdout.write(result.text)
        else:
            output.write_text(result.text, encoding="utf-8")
            print(f"Recovered text: {output}")
        print(f"Diagnostic report: {report_path}", file=sys.stderr if args.stdout else sys.stdout)
        print(f"Recovery mode: {result.mode}", file=sys.stderr if args.stdout else sys.stdout)
        return 0 if result.mode == "piece_table" else 1

    print("recovery failed; see diagnostic report", file=sys.stderr)
    print(f"Diagnostic report: {report_path}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

