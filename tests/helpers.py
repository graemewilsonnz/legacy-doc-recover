from __future__ import annotations

import struct

from legacy_doc_recover.cfb import ENDOFCHAIN, FATSECT, FREESECT

SECTOR_SIZE = 512


def make_word_stream(text: str, *, compressed: bool = True) -> tuple[bytes, bytes]:
    """Create synthetic WordDocument and 1Table streams for parser tests."""
    if compressed:
        encoded = text.encode("cp1252")
        char_count = len(text)
    else:
        encoded = text.encode("utf-16le")
        char_count = len(text)

    word = bytearray(4608)  # >= cutoff, easy regular-FAT integration fixture
    struct.pack_into("<H", word, 0, 0xA5EC)  # wIdent
    struct.pack_into("<H", word, 2, 0x00C1)  # nFib Word 97
    struct.pack_into("<H", word, 6, 0x0409)  # lid en-US
    flags = 0x0200  # fWhichTblStm = 1Table
    struct.pack_into("<H", word, 10, flags)
    text_offset = 0x400
    struct.pack_into("<I", word, 24, text_offset)
    struct.pack_into("<I", word, 28, text_offset + len(encoded))

    # FIB variable sections: csw=14, cslw=22, cbRgFcLcb=93.
    struct.pack_into("<H", word, 0x20, 14)
    cslw_offset = 0x22 + 14 * 2
    struct.pack_into("<H", word, cslw_offset, 22)
    lw_offset = cslw_offset + 2
    lw = [0] * 22
    lw[0] = len(word)
    lw[3] = char_count
    struct.pack_into("<22I", word, lw_offset, *lw)
    fc_lcb_count_offset = lw_offset + 22 * 4
    struct.pack_into("<H", word, fc_lcb_count_offset, 93)
    pairs_offset = fc_lcb_count_offset + 2

    table = bytearray(4096)
    fc_clx = 0x100
    plc_len = 16  # two CPs + one 8-byte PCD
    clx = bytearray(5 + plc_len)
    clx[0] = 0x02
    struct.pack_into("<I", clx, 1, plc_len)
    struct.pack_into("<II", clx, 5, 0, char_count)
    pcd_offset = 5 + 8
    struct.pack_into("<H", clx, pcd_offset, 0)
    if compressed:
        fc_raw = 0x40000000 | (text_offset * 2)
    else:
        fc_raw = text_offset
    struct.pack_into("<I", clx, pcd_offset + 2, fc_raw)
    struct.pack_into("<H", clx, pcd_offset + 6, 0)
    table[fc_clx : fc_clx + len(clx)] = clx

    pair33 = pairs_offset + 33 * 8
    struct.pack_into("<II", word, pair33, fc_clx, len(clx))
    word[text_offset : text_offset + len(encoded)] = encoded
    return bytes(word), bytes(table)


def make_minimal_cfb(word: bytes, table: bytes, *, corrupt_unused_minifat: bool = False) -> bytes:
    assert len(word) >= 4096 and len(table) >= 4096
    word_sectors = _split_and_pad(word)
    table_sectors = _split_and_pad(table)
    directory_sid = len(word_sectors) + len(table_sectors)
    fat_sid = directory_sid + 1
    sector_count = fat_sid + 1
    assert sector_count <= 128  # one FAT sector covers all sectors in this fixture

    sectors = [bytearray(s) for s in word_sectors + table_sectors]
    directory = bytearray(SECTOR_SIZE)
    _write_dir_entry(directory, 0, "Root Entry", 5, ENDOFCHAIN, 0, child=1)
    _write_dir_entry(directory, 1, "WordDocument", 2, 0, len(word), right=2)
    _write_dir_entry(directory, 2, "1Table", 2, len(word_sectors), len(table))
    sectors.append(directory)

    fat = [FREESECT] * 128
    for start, count in ((0, len(word_sectors)), (len(word_sectors), len(table_sectors))):
        for sid in range(start, start + count - 1):
            fat[sid] = sid + 1
        fat[start + count - 1] = ENDOFCHAIN
    fat[directory_sid] = ENDOFCHAIN
    fat[fat_sid] = FATSECT
    sectors.append(bytearray(struct.pack("<128I", *fat)))

    header = bytearray(512)
    header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<H", header, 24, 0x003E)  # minor
    struct.pack_into("<H", header, 26, 3)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 9)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 40, 0)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, directory_sid)
    struct.pack_into("<I", header, 56, 4096)
    if corrupt_unused_minifat:
        struct.pack_into("<I", header, 60, sector_count)  # one beyond last physical sector
    else:
        struct.pack_into("<I", header, 60, ENDOFCHAIN)
    struct.pack_into("<I", header, 64, 0)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)
    struct.pack_into("<I", header, 72, 0)
    difat = [FREESECT] * 109
    difat[0] = fat_sid
    struct.pack_into("<109I", header, 76, *difat)
    return bytes(header) + b"".join(bytes(s) for s in sectors)


def _split_and_pad(data: bytes) -> list[bytes]:
    chunks = []
    for i in range(0, len(data), SECTOR_SIZE):
        chunk = data[i : i + SECTOR_SIZE]
        chunks.append(chunk + b"\x00" * (SECTOR_SIZE - len(chunk)))
    return chunks


def _write_dir_entry(
    directory: bytearray,
    index: int,
    name: str,
    obj_type: int,
    start_sector: int,
    size: int,
    *,
    child: int = 0xFFFFFFFF,
    left: int = 0xFFFFFFFF,
    right: int = 0xFFFFFFFF,
) -> None:
    off = index * 128
    encoded = (name + "\x00").encode("utf-16le")
    directory[off : off + len(encoded)] = encoded
    struct.pack_into("<H", directory, off + 64, len(encoded))
    directory[off + 66] = obj_type
    directory[off + 67] = 1
    struct.pack_into("<I", directory, off + 68, left)
    struct.pack_into("<I", directory, off + 72, right)
    struct.pack_into("<I", directory, off + 76, child)
    struct.pack_into("<I", directory, off + 116, start_sector)
    struct.pack_into("<Q", directory, off + 120, size)

