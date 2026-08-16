"""Minimal, recovery-oriented Compound File Binary (CFB/OLE) reader.

This is intentionally not a complete MS-CFB implementation. It reads enough of
CFB version 3/4 to locate and extract streams while tolerating some damaged
metadata that does not affect the requested stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Iterable

from .errors import CFBError

CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF
MAXREGSECT = 0xFFFFFFFA


@dataclass(slots=True)
class CFBHeader:
    major_version: int
    minor_version: int
    sector_shift: int
    mini_sector_shift: int
    sector_size: int
    mini_sector_size: int
    num_directory_sectors: int
    num_fat_sectors: int
    first_directory_sector: int
    mini_stream_cutoff: int
    first_minifat_sector: int
    num_minifat_sectors: int
    first_difat_sector: int
    num_difat_sectors: int
    header_difat: list[int]


@dataclass(slots=True)
class DirectoryEntry:
    index: int
    name: str
    object_type: int
    start_sector: int
    stream_size: int
    child_id: int
    left_sibling_id: int
    right_sibling_id: int

    @property
    def is_stream(self) -> bool:
        return self.object_type == 2

    @property
    def is_root(self) -> bool:
        return self.object_type == 5


@dataclass
class CompoundFile:
    data: bytes
    header: CFBHeader
    fat_sector_ids: list[int]
    fat: list[int]
    directory_entries: list[DirectoryEntry]
    warnings: list[str] = field(default_factory=list)
    _minifat: list[int] | None = None
    _mini_stream: bytes | None = None

    @classmethod
    def parse(cls, data: bytes) -> "CompoundFile":
        warnings: list[str] = []
        header = parse_header(data, warnings)
        temp = cls(data, header, [], [], [], warnings)
        fat_sector_ids = temp._collect_fat_sector_ids()
        fat = temp._read_fat(fat_sector_ids)
        temp.fat_sector_ids = fat_sector_ids
        temp.fat = fat
        temp.directory_entries = temp._read_directory()
        temp._validate_nonessential_metadata()
        return temp

    @property
    def sector_size(self) -> int:
        return self.header.sector_size

    @property
    def physical_sector_count(self) -> int:
        # In CFB v3 the header occupies one 512-byte sector. In v4 the
        # meaningful header is still 512 bytes, but it is padded to the 4096-byte
        # sector boundary; regular sector 0 starts at offset sector_size.
        first_sector_offset = self.sector_size
        if len(self.data) <= first_sector_offset:
            return 0
        return (len(self.data) - first_sector_offset) // self.sector_size

    def sector_bytes(self, sector_id: int) -> bytes:
        if sector_id < 0 or sector_id >= self.physical_sector_count:
            raise CFBError(
                f"sector {sector_id} is outside physical sector range "
                f"0..{max(self.physical_sector_count - 1, 0)}"
            )
        start = self.sector_size + sector_id * self.sector_size
        end = start + self.sector_size
        return self.data[start:end]

    def _collect_fat_sector_ids(self) -> list[int]:
        ids = [
            sid
            for sid in self.header.header_difat
            if sid not in (FREESECT, ENDOFCHAIN)
        ]

        next_difat = self.header.first_difat_sector
        seen: set[int] = set()
        entries_per_difat = self.sector_size // 4 - 1
        for _ in range(self.header.num_difat_sectors):
            if next_difat in (ENDOFCHAIN, FREESECT):
                self.warnings.append("DIFAT chain ended before declared DIFAT sector count")
                break
            if not self._is_physical_sector(next_difat):
                self.warnings.append(
                    f"DIFAT sector {next_difat} is outside the physical file; ignoring remaining DIFAT chain"
                )
                break
            if next_difat in seen:
                self.warnings.append(f"loop detected in DIFAT chain at sector {next_difat}")
                break
            seen.add(next_difat)
            raw = self.sector_bytes(next_difat)
            values = list(struct.unpack("<" + "I" * (self.sector_size // 4), raw))
            ids.extend(v for v in values[:entries_per_difat] if v != FREESECT)
            next_difat = values[-1]

        # Header declarations can be corrupt. Keep valid unique FAT sector ids,
        # preferring the declared count but never following an out-of-file sector.
        valid: list[int] = []
        seen.clear()
        for sid in ids:
            if sid in seen:
                continue
            seen.add(sid)
            if self._is_physical_sector(sid):
                valid.append(sid)
            else:
                self.warnings.append(f"declared FAT sector {sid} is outside the physical file")

        if self.header.num_fat_sectors and len(valid) < self.header.num_fat_sectors:
            self.warnings.append(
                f"header declares {self.header.num_fat_sectors} FAT sector(s), but only {len(valid)} valid FAT sector(s) were found"
            )
        if self.header.num_fat_sectors:
            valid = valid[: self.header.num_fat_sectors]
        if not valid:
            raise CFBError("no usable FAT sectors found")
        return valid

    def _read_fat(self, fat_sector_ids: Iterable[int]) -> list[int]:
        fat: list[int] = []
        words_per_sector = self.sector_size // 4
        fmt = "<" + "I" * words_per_sector
        for sid in fat_sector_ids:
            fat.extend(struct.unpack(fmt, self.sector_bytes(sid)))
        return fat

    def _follow_chain(
        self,
        start_sector: int,
        table: list[int],
        *,
        label: str,
        max_steps: int | None = None,
    ) -> tuple[list[int], bool]:
        if start_sector in (ENDOFCHAIN, FREESECT):
            return [], True

        chain: list[int] = []
        seen: set[int] = set()
        sid = start_sector
        hard_limit = max_steps or max(len(table), self.physical_sector_count + 1)
        complete = False

        for _ in range(hard_limit):
            if sid == ENDOFCHAIN:
                complete = True
                break
            if sid in (FREESECT, FATSECT, DIFSECT) or sid > MAXREGSECT:
                self.warnings.append(f"{label} chain encountered invalid marker 0x{sid:08X}")
                break
            if sid in seen:
                self.warnings.append(f"loop detected in {label} chain at sector {sid}")
                break
            if sid >= len(table):
                self.warnings.append(f"{label} chain references FAT index {sid} beyond available FAT")
                break
            if not self._is_physical_sector(sid):
                self.warnings.append(f"{label} chain references sector {sid} outside the physical file")
                break
            seen.add(sid)
            chain.append(sid)
            sid = table[sid]
        else:
            self.warnings.append(f"{label} chain exceeded safety limit")

        return chain, complete

    def _read_directory(self) -> list[DirectoryEntry]:
        chain, _ = self._follow_chain(
            self.header.first_directory_sector, self.fat, label="directory"
        )
        if not chain:
            raise CFBError("directory stream could not be recovered")
        raw = b"".join(self.sector_bytes(sid) for sid in chain)
        entries: list[DirectoryEntry] = []
        for index in range(0, len(raw) // 128):
            block = raw[index * 128 : (index + 1) * 128]
            obj_type = block[66]
            if obj_type == 0:
                continue
            name_len = struct.unpack_from("<H", block, 64)[0]
            if name_len < 2 or name_len > 64 or name_len % 2:
                name = f"<invalid-name-{index}>"
                self.warnings.append(f"directory entry {index} has invalid UTF-16 name length {name_len}")
            else:
                name_bytes = block[: name_len - 2]
                name = name_bytes.decode("utf-16le", errors="replace")
            start_sector = struct.unpack_from("<I", block, 116)[0]
            stream_size = struct.unpack_from("<Q", block, 120)[0]
            if self.header.major_version == 3:
                stream_size &= 0xFFFFFFFF
            entries.append(
                DirectoryEntry(
                    index=index,
                    name=name,
                    object_type=obj_type,
                    start_sector=start_sector,
                    stream_size=stream_size,
                    child_id=struct.unpack_from("<I", block, 76)[0],
                    left_sibling_id=struct.unpack_from("<I", block, 68)[0],
                    right_sibling_id=struct.unpack_from("<I", block, 72)[0],
                )
            )
        return entries

    def _validate_nonessential_metadata(self) -> None:
        h = self.header
        if h.num_minifat_sectors == 0 and h.first_minifat_sector not in (ENDOFCHAIN, FREESECT):
            if not self._is_physical_sector(h.first_minifat_sector):
                self.warnings.append(
                    "MiniFAT start sector is outside the physical file while MiniFAT sector count is zero; "
                    "treating MiniFAT metadata as nonessential corruption"
                )
            else:
                self.warnings.append(
                    "MiniFAT start sector is set while MiniFAT sector count is zero; ignoring MiniFAT unless required"
                )

    def _is_physical_sector(self, sid: int) -> bool:
        return 0 <= sid < self.physical_sector_count

    def find_entry(self, name: str) -> DirectoryEntry | None:
        wanted = name.casefold()
        for entry in self.directory_entries:
            if entry.name.casefold() == wanted:
                return entry
        return None

    def root_entry(self) -> DirectoryEntry | None:
        for entry in self.directory_entries:
            if entry.is_root:
                return entry
        return None

    def read_stream(self, name: str) -> bytes:
        entry = self.find_entry(name)
        if entry is None or not entry.is_stream:
            raise CFBError(f"stream {name!r} not found")
        return self.read_entry(entry)

    def read_entry(self, entry: DirectoryEntry) -> bytes:
        if entry.stream_size == 0:
            return b""
        if entry.stream_size < self.header.mini_stream_cutoff:
            return self._read_mini_stream_entry(entry)
        return self._read_regular_stream_entry(entry)

    def _read_regular_stream_entry(self, entry: DirectoryEntry) -> bytes:
        expected = (entry.stream_size + self.sector_size - 1) // self.sector_size
        chain, complete = self._follow_chain(
            entry.start_sector,
            self.fat,
            label=f"stream {entry.name!r}",
            max_steps=max(expected + 8, expected * 2),
        )
        if len(chain) < expected:
            self.warnings.append(
                f"stream {entry.name!r} FAT chain produced {len(chain)} of {expected} expected sector(s)"
            )
            contiguous = self._contiguous_fallback(entry.start_sector, expected)
            if len(contiguous) > len(chain):
                self.warnings.append(
                    f"stream {entry.name!r} recovered using contiguous-sector fallback; ordering confidence is reduced"
                )
                chain = contiguous
        elif not complete:
            self.warnings.append(f"stream {entry.name!r} chain did not terminate cleanly after usable data")
        raw = b"".join(self.sector_bytes(sid) for sid in chain[:expected])
        if len(raw) < entry.stream_size:
            raise CFBError(
                f"stream {entry.name!r} is truncated: recovered {len(raw)} of {entry.stream_size} bytes"
            )
        return raw[: entry.stream_size]

    def _contiguous_fallback(self, start_sector: int, count: int) -> list[int]:
        if start_sector < 0 or count <= 0:
            return []
        end = min(start_sector + count, self.physical_sector_count)
        return list(range(start_sector, end))

    def _load_minifat(self) -> list[int]:
        if self._minifat is not None:
            return self._minifat
        h = self.header
        if h.num_minifat_sectors == 0:
            raise CFBError("MiniFAT is required for this stream but the header declares zero MiniFAT sectors")
        if not self._is_physical_sector(h.first_minifat_sector):
            raise CFBError("MiniFAT start sector is outside the physical file")
        chain, _ = self._follow_chain(h.first_minifat_sector, self.fat, label="MiniFAT")
        chain = chain[: h.num_minifat_sectors]
        if not chain:
            raise CFBError("MiniFAT chain could not be read")
        raw = b"".join(self.sector_bytes(sid) for sid in chain)
        count = len(raw) // 4
        self._minifat = list(struct.unpack("<" + "I" * count, raw[: count * 4]))
        return self._minifat

    def _load_mini_stream(self) -> bytes:
        if self._mini_stream is not None:
            return self._mini_stream
        root = self.root_entry()
        if root is None:
            raise CFBError("root storage entry not found; cannot read mini stream")
        if root.stream_size == 0:
            raise CFBError("root mini stream is empty")
        # Root mini stream itself is always stored in regular FAT sectors.
        expected = (root.stream_size + self.sector_size - 1) // self.sector_size
        chain, _ = self._follow_chain(root.start_sector, self.fat, label="root mini stream")
        raw = b"".join(self.sector_bytes(sid) for sid in chain[:expected])
        if len(raw) < root.stream_size:
            raise CFBError("root mini stream is truncated")
        self._mini_stream = raw[: root.stream_size]
        return self._mini_stream

    def _read_mini_stream_entry(self, entry: DirectoryEntry) -> bytes:
        minifat = self._load_minifat()
        mini_stream = self._load_mini_stream()
        expected = (entry.stream_size + self.header.mini_sector_size - 1) // self.header.mini_sector_size
        chain: list[int] = []
        seen: set[int] = set()
        sid = entry.start_sector
        for _ in range(max(expected + 8, expected * 2)):
            if sid == ENDOFCHAIN:
                break
            if sid in seen or sid >= len(minifat) or sid > MAXREGSECT:
                self.warnings.append(f"mini-stream {entry.name!r} chain is damaged at mini-sector {sid}")
                break
            seen.add(sid)
            chain.append(sid)
            sid = minifat[sid]
        if len(chain) < expected:
            raise CFBError(
                f"mini-stream {entry.name!r} is truncated: recovered {len(chain)} of {expected} mini-sector(s)"
            )
        out = bytearray()
        mini_size = self.header.mini_sector_size
        for mini_sid in chain[:expected]:
            start = mini_sid * mini_size
            end = start + mini_size
            if end > len(mini_stream):
                raise CFBError(f"mini-sector {mini_sid} lies beyond root mini stream")
            out.extend(mini_stream[start:end])
        return bytes(out[: entry.stream_size])


def parse_header(data: bytes, warnings: list[str] | None = None) -> CFBHeader:
    warnings = warnings if warnings is not None else []
    if len(data) < 512:
        raise CFBError("file is shorter than the 512-byte CFB header")
    if data[:8] != CFB_SIGNATURE:
        raise CFBError("not a Compound File Binary file: signature mismatch")

    minor = struct.unpack_from("<H", data, 24)[0]
    major = struct.unpack_from("<H", data, 26)[0]
    byte_order = struct.unpack_from("<H", data, 28)[0]
    sector_shift = struct.unpack_from("<H", data, 30)[0]
    mini_sector_shift = struct.unpack_from("<H", data, 32)[0]
    if byte_order != 0xFFFE:
        raise CFBError(f"unsupported CFB byte order 0x{byte_order:04X}")
    if major not in (3, 4):
        raise CFBError(f"unsupported CFB major version {major}")
    expected_shift = 9 if major == 3 else 12
    if sector_shift != expected_shift:
        warnings.append(
            f"CFB major version {major} normally uses sector shift {expected_shift}, found {sector_shift}"
        )
    sector_size = 1 << sector_shift
    mini_sector_size = 1 << mini_sector_shift
    if sector_size not in (512, 4096):
        raise CFBError(f"unsupported sector size {sector_size}")
    if mini_sector_size != 64:
        warnings.append(f"unusual mini-sector size {mini_sector_size}")

    num_dir = struct.unpack_from("<I", data, 40)[0]
    num_fat = struct.unpack_from("<I", data, 44)[0]
    first_dir = struct.unpack_from("<I", data, 48)[0]
    cutoff = struct.unpack_from("<I", data, 56)[0]
    first_minifat = struct.unpack_from("<I", data, 60)[0]
    num_minifat = struct.unpack_from("<I", data, 64)[0]
    first_difat = struct.unpack_from("<I", data, 68)[0]
    num_difat = struct.unpack_from("<I", data, 72)[0]
    header_difat = list(struct.unpack_from("<109I", data, 76))

    if major == 3 and num_dir != 0:
        warnings.append(f"CFB v3 header has non-zero directory-sector count {num_dir}")
    if cutoff != 4096:
        warnings.append(f"unusual mini-stream cutoff {cutoff}; standard value is 4096")

    return CFBHeader(
        major_version=major,
        minor_version=minor,
        sector_shift=sector_shift,
        mini_sector_shift=mini_sector_shift,
        sector_size=sector_size,
        mini_sector_size=mini_sector_size,
        num_directory_sectors=num_dir,
        num_fat_sectors=num_fat,
        first_directory_sector=first_dir,
        mini_stream_cutoff=cutoff,
        first_minifat_sector=first_minifat,
        num_minifat_sectors=num_minifat,
        first_difat_sector=first_difat,
        num_difat_sectors=num_difat,
        header_difat=header_difat,
    )

