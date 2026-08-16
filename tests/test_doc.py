from legacy_doc_recover.doc import parse_fib, parse_piece_table
from legacy_doc_recover.text import extract_text
from .helpers import make_word_stream


def test_compressed_piece_round_trip():
    expected = "First paragraph\rSecond paragraph with smart quote: ‘yes’.\r"
    word, table = make_word_stream(expected, compressed=True)
    fib = parse_fib(word)
    pieces = parse_piece_table(table, fib)
    text, codepage, warnings = extract_text(word, fib, pieces)

    assert fib.table_stream == "1Table"
    assert fib.ccp_text == len(expected)
    assert len(pieces) == 1
    assert pieces[0].compressed is True
    assert pieces[0].file_offset == 0x400
    assert codepage == "cp1252"
    assert warnings == []
    assert text == expected.replace("\r", "\n")


def test_unicode_piece_round_trip():
    expected = "Unicode: café Ελληνικά 日本語\r"
    word, table = make_word_stream(expected, compressed=False)
    fib = parse_fib(word)
    pieces = parse_piece_table(table, fib)
    text, _, _ = extract_text(word, fib, pieces)

    assert pieces[0].compressed is False
    assert pieces[0].file_offset == 0x400
    assert text == expected.replace("\r", "\n")

