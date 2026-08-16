"""Recovery-oriented parser for the Word 97-2003 binary .doc text path."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .errors import DocFormatError, UnsupportedDocError

WORD_FIB_IDENT = 0xA5EC
FC_LCB_CLX_INDEX = 33  # FibRgFcLcb97.fcClx / lcbClx pair


@dataclass(slots=True)
class FIBInfo:
    w_ident: int
    n_fib: int
    lid: int
    flags: int
    encrypted: bool
    obfuscated: bool
    table_stream: str
    fc_min: int
    fc_mac: int
    ccp_text: int | None
    ccp_ftn: int | None
    ccp_hdd: int | None
    ccp_atn: int | None
    ccp_edn: int | None
    ccp_txbx: int | None
    ccp_hdr_txbx: int | None
    fc_clx: int
    lcb_clx: int
    csw: int
    cslw: int
    cb_rg_fc_lcb: int


@dataclass(slots=True)
class TextPiece:
    index: int
    cp_start: int
    cp_end: int
    fc_raw: int
    file_offset: int
    compressed: bool
    byte_length: int

    @property
    def char_count(self) -> int:
        return self.cp_end - self.cp_start


@dataclass(slots=True)
class ParsedDoc:
    fib: FIBInfo
    pieces: list[TextPiece]


def parse_fib(word_document: bytes) -> FIBInfo:
    if len(word_document) < 32:
        raise DocFormatError("WordDocument stream is too short for FibBase")

    w_ident, n_fib = struct.unpack_from("<HH", word_document, 0)
    if w_ident != WORD_FIB_IDENT:
        raise DocFormatError(
            f"WordDocument does not begin with expected FIB identifier 0x{WORD_FIB_IDENT:04X}; found 0x{w_ident:04X}"
        )

    lid = struct.unpack_from("<H", word_document, 6)[0]
    flags = struct.unpack_from("<H", word_document, 10)[0]
    encrypted = bool(flags & 0x0100)
    table_stream = "1Table" if flags & 0x0200 else "0Table"
    obfuscated = bool(flags & 0x8000)
    fc_min = struct.unpack_from("<I", word_document, 24)[0]
    fc_mac = struct.unpack_from("<I", word_document, 28)[0]

    if encrypted or obfuscated:
        kind = "encrypted" if encrypted else "obfuscated"
        raise UnsupportedDocError(f"{kind} Word binary documents are not supported in v0.1")

    offset = 32
    csw = _u16(word_document, offset, "csw")
    offset += 2
    _ensure(word_document, offset, csw * 2, "FibRgW")
    offset += csw * 2

    cslw = _u16(word_document, offset, "cslw")
    offset += 2
    _ensure(word_document, offset, cslw * 4, "FibRgLw")
    lw_values = list(struct.unpack_from("<" + "I" * cslw, word_document, offset))
    offset += cslw * 4

    cb_rg_fc_lcb = _u16(word_document, offset, "cbRgFcLcb")
    offset += 2
    pair_bytes = cb_rg_fc_lcb * 8
    _ensure(word_document, offset, pair_bytes, "FibRgFcLcb")
    if cb_rg_fc_lcb <= FC_LCB_CLX_INDEX:
        raise UnsupportedDocError(
            "FIB does not contain the Word 97 fcClx/lcbClx pair; pre-Word-97 binary documents are outside v0.1 scope"
        )
    pair_offset = offset + FC_LCB_CLX_INDEX * 8
    fc_clx, lcb_clx = struct.unpack_from("<II", word_document, pair_offset)

    # FibRgLw97 positions. Values may be absent for unexpected/older layouts.
    ccp_text = lw_values[3] if len(lw_values) > 3 else None
    ccp_ftn = lw_values[4] if len(lw_values) > 4 else None
    ccp_hdd = lw_values[5] if len(lw_values) > 5 else None
    ccp_atn = lw_values[7] if len(lw_values) > 7 else None
    ccp_edn = lw_values[8] if len(lw_values) > 8 else None
    ccp_txbx = lw_values[9] if len(lw_values) > 9 else None
    ccp_hdr_txbx = lw_values[10] if len(lw_values) > 10 else None

    return FIBInfo(
        w_ident=w_ident,
        n_fib=n_fib,
        lid=lid,
        flags=flags,
        encrypted=encrypted,
        obfuscated=obfuscated,
        table_stream=table_stream,
        fc_min=fc_min,
        fc_mac=fc_mac,
        ccp_text=ccp_text,
        ccp_ftn=ccp_ftn,
        ccp_hdd=ccp_hdd,
        ccp_atn=ccp_atn,
        ccp_edn=ccp_edn,
        ccp_txbx=ccp_txbx,
        ccp_hdr_txbx=ccp_hdr_txbx,
        fc_clx=fc_clx,
        lcb_clx=lcb_clx,
        csw=csw,
        cslw=cslw,
        cb_rg_fc_lcb=cb_rg_fc_lcb,
    )


def parse_piece_table(table_stream: bytes, fib: FIBInfo) -> list[TextPiece]:
    if fib.lcb_clx == 0:
        raise DocFormatError("FIB reports an empty CLX")
    if fib.fc_clx + fib.lcb_clx > len(table_stream):
        raise DocFormatError(
            f"CLX range {fib.fc_clx}:{fib.fc_clx + fib.lcb_clx} lies outside {fib.table_stream} ({len(table_stream)} bytes)"
        )
    clx = table_stream[fib.fc_clx : fib.fc_clx + fib.lcb_clx]

    pos = 0
    plc: bytes | None = None
    while pos < len(clx):
        clxt = clx[pos]
        if clxt == 0x01:  # Prc: formatting grpprl preceding the piece table
            if pos + 3 > len(clx):
                raise DocFormatError("truncated Prc in CLX")
            cb_grpprl = struct.unpack_from("<H", clx, pos + 1)[0]
            pos += 3 + cb_grpprl
            if pos > len(clx):
                raise DocFormatError("Prc length extends beyond CLX")
        elif clxt == 0x02:  # Pcdt
            if pos + 5 > len(clx):
                raise DocFormatError("truncated Pcdt header in CLX")
            lcb = struct.unpack_from("<I", clx, pos + 1)[0]
            start = pos + 5
            end = start + lcb
            if end > len(clx):
                raise DocFormatError("PlcPcd length extends beyond CLX")
            plc = clx[start:end]
            break
        else:
            raise DocFormatError(f"unexpected CLX record type 0x{clxt:02X} at offset {pos}")

    if plc is None:
        raise DocFormatError("CLX does not contain a Pcdt/PlcPcd piece table")
    if len(plc) < 4 or (len(plc) - 4) % 12:
        raise DocFormatError(f"invalid PlcPcd size {len(plc)}")

    piece_count = (len(plc) - 4) // 12
    cp_count = piece_count + 1
    cp_bytes = cp_count * 4
    cps = list(struct.unpack_from("<" + "I" * cp_count, plc, 0))
    pieces: list[TextPiece] = []

    for i in range(piece_count):
        cp_start = cps[i]
        cp_end = cps[i + 1]
        if cp_end < cp_start:
            raise DocFormatError(f"piece {i} has descending CP range {cp_start}..{cp_end}")
        pcd_offset = cp_bytes + i * 8
        fc_raw = struct.unpack_from("<I", plc, pcd_offset + 2)[0]
        compressed = bool(fc_raw & 0x40000000)
        masked = fc_raw & 0x3FFFFFFF
        if compressed:
            if masked & 1:
                raise DocFormatError(f"piece {i} has odd compressed FcCompressed value 0x{fc_raw:08X}")
            file_offset = masked // 2
            byte_length = cp_end - cp_start
        else:
            file_offset = masked
            byte_length = (cp_end - cp_start) * 2
        pieces.append(
            TextPiece(
                index=i,
                cp_start=cp_start,
                cp_end=cp_end,
                fc_raw=fc_raw,
                file_offset=file_offset,
                compressed=compressed,
                byte_length=byte_length,
            )
        )
    return pieces


def parse_doc(word_document: bytes, table_stream: bytes) -> ParsedDoc:
    fib = parse_fib(word_document)
    pieces = parse_piece_table(table_stream, fib)
    return ParsedDoc(fib=fib, pieces=pieces)


def _ensure(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise DocFormatError(f"{label} lies outside WordDocument stream")


def _u16(data: bytes, offset: int, label: str) -> int:
    _ensure(data, offset, 2, label)
    return struct.unpack_from("<H", data, offset)[0]

