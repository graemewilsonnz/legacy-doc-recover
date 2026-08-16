from legacy_doc_recover.recover import recover_bytes
from .helpers import make_minimal_cfb, make_word_stream


def test_structured_integration_recovery():
    expected = "One\rTwo\rThree\r"
    word, table = make_word_stream(expected)
    blob = make_minimal_cfb(word, table, corrupt_unused_minifat=True)

    result = recover_bytes(blob, source_name="synthetic.doc")

    assert result.success is True
    assert result.mode == "piece_table"
    assert result.text == "One\nTwo\nThree\n"
    assert result.report["word"]["piece_count"] == 1
    assert result.report["word"]["ccpText"] == len(expected)
    assert result.report["recovery"]["method"] == "structured-piece-table"
    assert any("MiniFAT" in w for w in result.report["warnings"])


def test_raw_fallback_is_labelled():
    blob = b"not-a-cfb\x00" + b"A readable fallback sentence with enough letters and spaces to detect."
    result = recover_bytes(blob, source_name="broken.doc")

    assert result.success is True
    assert result.mode == "raw_scan"
    assert result.text.startswith("[LOW-CONFIDENCE RAW SCAN")
    assert result.report["recovery"]["confidence"] == "low"

