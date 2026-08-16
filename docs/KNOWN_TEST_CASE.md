# Known damaged-file test case — anonymised

## Status

This is the only real damaged `.doc` used to validate v0.1 before initial handover. The original document is private and is **not included in the repository**.

## External symptom

Microsoft Word could not open the document and its normal repair path also failed.

A strict CFB parser reported damage associated with the short-sector allocation structures.

## Container observations

```text
File size                  19,968 bytes
CFB major version          3
Sector size                512 bytes
Physical sectors           0..37
WordDocument size          5,150 bytes
1Table size                4,096 bytes
```

A notable header inconsistency was:

```text
Number of MiniFAT sectors  0
First MiniFAT sector       38
Highest physical sector    37
```

The MiniFAT start therefore pointed immediately beyond end-of-file despite the header declaring that no MiniFAT sectors existed.

The two streams required for text recovery were not mini streams, so this inconsistency did not need to prevent recovery.

## Word observations

The recovered FIB identified a Word 97-era binary format and selected `1Table`.

The FIB located a valid CLX in `1Table`:

```text
fcClx                      0x03DB
lcbClx                     0x0015
```

The CLX contained one text piece:

```text
Logical CP range           0..1807
Character count            1,807
Compressed                 yes
Physical text offset       0x0400 in WordDocument
```

The raw `FcCompressed` value was `0x40000800`; masking the compression flag and dividing the remaining value by two gives `0x400`.

## Result

The structured piece-table path recovered the entire underlying 1,807-character text piece.

Displayed list numbers/letters were not part of that text piece; they were generated through Word formatting structures. v0.1 therefore intentionally does not claim visual-format recovery.

## What this test establishes

It demonstrates that:

1. strict rejection of damaged CFB metadata can discard a document whose important streams remain usable;
2. a recovery reader can ignore corruption in structures that are not dependencies of the requested streams;
3. the Word FIB → CLX → PlcPcd path can recover logical text from such a file.

## What this test does not establish

One file is not a corpus. It does not demonstrate support for:

- other CFB corruption patterns;
- fragmented damaged streams;
- MiniFAT-dependent Word streams;
- multiple text pieces;
- mixed compressed/Unicode pieces in a real damaged document;
- non-Western compressed encodings;
- encrypted files;
- pre-Word-97 binary formats;
- formatting reconstruction.

