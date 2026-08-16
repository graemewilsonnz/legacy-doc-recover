from legacy_doc_recover.cfb import CompoundFile
from .helpers import make_minimal_cfb, make_word_stream


def test_extracts_regular_word_streams():
    word, table = make_word_stream("Hello from a synthetic document.\r")
    blob = make_minimal_cfb(word, table)
    cfb = CompoundFile.parse(blob)

    assert cfb.read_stream("WordDocument") == word
    assert cfb.read_stream("1Table") == table
    assert cfb.header.major_version == 3


def test_unused_out_of_range_minifat_is_warning_not_fatal():
    word, table = make_word_stream("Recover me.\r")
    blob = make_minimal_cfb(word, table, corrupt_unused_minifat=True)
    cfb = CompoundFile.parse(blob)

    assert cfb.read_stream("WordDocument") == word
    assert any("MiniFAT" in warning and "outside" in warning for warning in cfb.warnings)

