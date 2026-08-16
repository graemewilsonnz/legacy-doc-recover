# Binary format notes for recovery

This document describes only the subset of Microsoft Word 97–2003 binary `.doc` required by `legacy-doc-recover`. It is not a replacement for MS-CFB or MS-DOC.

## 1. Two layers matter

A classic Word `.doc` is normally a **Compound File Binary (CFB/OLE) container**. Conceptually it is a small filesystem inside one file.

For text recovery we need to move through two layers:

```text
CFB container
  ├─ WordDocument stream
  ├─ 0Table OR 1Table stream
  └─ other streams (usually irrelevant to v0.1 text extraction)

Word binary structures
  WordDocument
     └─ File Information Block (FIB)
          ├─ which Table stream to use
          ├─ document story character counts
          └─ fcClx/lcbClx → CLX in Table stream

  Table stream
     └─ CLX
          └─ Pcdt
               └─ PlcPcd piece table
                    └─ CP ranges + PCD physical locations
```

## 2. CFB essentials

A CFB file begins with the signature:

```text
D0 CF 11 E0 A1 B1 1A E1
```

The 512-byte header describes sector geometry and points at the structures needed to locate streams.

Important v0.1 fields include:

- major version;
- sector shift / sector size;
- FAT sector count;
- first directory sector;
- MiniFAT metadata;
- DIFAT entries locating FAT sectors.

The FAT is an array of sector-to-next-sector links. A directory entry gives a named stream's starting sector and declared byte length.

`WordDocument` and the selected Table stream can therefore be reconstructed by following their FAT chains.

### Mini streams

CFB usually stores streams smaller than 4,096 bytes in 64-byte mini sectors. These use the MiniFAT and a root mini stream. v0.1 implements this path because some legitimate Word streams can be small.

However, recovery is deliberately dependency-sensitive: broken MiniFAT metadata should not block a needed stream stored in normal FAT sectors.

## 3. File Information Block (FIB)

`WordDocument` begins with a File Information Block.

For Word 97+ files the first 16-bit value (`wIdent`) is expected to be `0xA5EC`. `nFib` describes the Word binary format version.

The `FibBase` flags include:

- encryption;
- `fWhichTblStm`, selecting `0Table` or `1Table`;
- obfuscation.

v0.1 rejects encrypted/obfuscated documents rather than attempting password recovery or decryption.

The FIB is partly variable-length. The parser walks:

```text
FibBase (32 bytes)
csw + FibRgW
cslw + FibRgLw
cbRgFcLcb + FC/LCB pairs
```

In `FibRgFcLcb97`, pair index 33 contains `fcClx` and `lcbClx`, locating the CLX in the selected Table stream.

`FibRgLw97.ccpText` provides the length of the main-document story. By default v0.1 uses this to avoid silently mixing headers, footnotes or other stories into the main recovered text.

## 4. CLX and the piece table

The CLX can contain zero or more `Prc` records followed by a `Pcdt`.

The `Pcdt` contains a `PlcPcd`, which can be viewed as:

```text
CP[0]
CP[1]
...
CP[n]
PCD[0]
PCD[1]
...
PCD[n-1]
```

There is one more CP than PCD. Each PCD maps the corresponding logical character range to bytes in `WordDocument`.

For a `PlcPcd` of byte length `L`:

```text
L = 4*(n+1) + 8*n
  = 12*n + 4

n = (L - 4) / 12
```

## 5. Compressed vs Unicode pieces

The PCD contains `FcCompressed`.

For recovery purposes:

- bit `0x40000000` set → compressed/single-byte piece;
- otherwise → UTF-16LE piece.

For a compressed piece, the actual byte position is derived by masking the flag bits and dividing the stored value by two:

```text
file_offset = (FcCompressed & 0x3FFFFFFF) / 2
```

and one logical character consumes one byte.

For an uncompressed piece:

```text
file_offset = FcCompressed & 0x3FFFFFFF
```

and one logical character consumes two bytes (UTF-16LE).

This is why naive `strings` extraction is weaker than piece-table recovery: the piece table provides **logical order, physical location and encoding mode**.

## 6. Compressed-text code pages

A single-byte piece is not inherently UTF-8. Legacy Word documents can use Windows code pages.

v0.1 maps a small set of common FIB language IDs to code pages and provides `--codepage` for explicit override. Unknown language IDs fall back to `cp1252` with a warning.

This area requires broader corpus testing.

## 7. Word text control characters

Some bytes/characters in a text piece are structural markers rather than printable text. v0.1 conservatively maps or removes a small subset:

- paragraph mark → newline;
- manual line break → newline;
- page/section break → blank-line separation;
- table cell/row marker → tab separator;
- field begin/separator/end → removed;
- embedded-object placeholder → removed.

This does not recreate Word formatting.

## 8. Why list numbering can disappear

A displayed list such as:

```text
1) First item
2) Second item
```

can store only:

```text
First item
Second item
```

in the text piece. The visible `1)` and `2)` can be generated from paragraph/list-formatting structures elsewhere in the document.

Therefore v0.1 promises **surviving logical text**, not faithful visual reconstruction.

## Primary references

- MS-CFB: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/
- MS-DOC: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/ccd7b486-7881-484c-a137-51170af7cc22
- MS-DOC, Retrieving Text: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/01d5d8c4-cf9c-4ef9-80fd-439e763cfe01
- MS-DOC, Example of a Clx: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/a30a9a42-cf78-4974-b99f-d559639ee383

