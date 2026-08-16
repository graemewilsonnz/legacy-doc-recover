# legacy-doc-recover

**Experimental best-effort text recovery for damaged Microsoft Word 97–2003 binary `.doc` files.**

`legacy-doc-recover` is for the case where Word or another normal application refuses to open an old binary `.doc`, but useful document text may still survive inside the file.

> **Status: v0.1 alpha — one real damaged file tested so far.**
>
> The initial real-world test recovered the complete underlying text piece from one damaged Word 97-format `.doc` that Microsoft Word could not open or repair. The parser is based on Microsoft's published MS-CFB and MS-DOC specifications, but compatibility with other corruption patterns and other binary Word files has not yet been established.

## What it does

The structured recovery path:

```text
.doc bytes
   ↓
CFB/OLE header
   ↓
DIFAT/FAT + directory
   ↓
WordDocument + 0Table/1Table streams
   ↓
File Information Block (FIB)
   ↓
CLX / PlcPcd piece table
   ↓
compressed 8-bit or UTF-16LE text pieces
   ↓
UTF-8 recovered text + JSON diagnostic report
```

The CFB reader is intentionally **tolerant**. For example, damage in unused MiniFAT metadata does not prevent recovery of normal FAT streams if the `WordDocument` and Table streams remain accessible.

If structured recovery fails, v0.1 can perform a deliberately conservative **low-confidence raw text scan**. Raw-scan output is clearly labelled and must not be treated as authoritative.

## What it does not do

This is a **recovery tool, not a Word document repair tool**.

v0.1 does not attempt to reconstruct:

- list numbering or bullets generated from paragraph/list formatting;
- fonts, styles, colours or page layout;
- tables as tables;
- images, drawings or embedded OLE objects;
- comments, tracked changes or fields as semantic objects;
- macros;
- a repaired `.doc` file.

It extracts surviving logical text into a new UTF-8 text file.

## Safety model

The program reads the document as untrusted bytes. It does **not** launch Microsoft Word, LibreOffice, COM/OLE automation, VBA, embedded objects or macros.

Keep the original file unchanged. Recovery output should be treated as a derivative copy.

## Installation

Python 3.10+ is required. The core tool has no third-party runtime dependencies.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -e .
```

## Usage

```bash
legacy-doc-recover "damaged.doc"
```

This creates:

```text
damaged.recovered.txt
damaged.recovery.json
```

To keep generated files in one obvious place, use the repository's `output/`
directory:

```bash
legacy-doc-recover damaged.doc -o output/damaged.recovered.txt --report output/damaged.recovery.json
```

Specify paths explicitly:

```bash
legacy-doc-recover damaged.doc -o recovered.txt --report recovery.json
```

Print the recovered text:

```bash
legacy-doc-recover damaged.doc --stdout
```

Disable the low-confidence fallback:

```bash
legacy-doc-recover damaged.doc --no-raw-fallback
```

Override the compressed-text code page if auto-selection is wrong:

```bash
legacy-doc-recover damaged.doc --codepage cp1251
```

Recover the complete logical piece-table range rather than just the main-document story:

```bash
legacy-doc-recover damaged.doc --all-stories
```

## Diagnostic report

The JSON report records evidence useful for understanding whether the result can be trusted, including:

- SHA-256 and file size;
- CFB version and sector geometry;
- declared and usable FAT information;
- recovered stream directory entries;
- container anomalies/warnings;
- Word FIB version and selected Table stream;
- encryption/obfuscation flags;
- CLX location;
- each recovered text piece's CP range, physical offset and encoding mode;
- recovery method and confidence statement.

## Known real-world test case

The first damaged test file was a 19,968-byte CFB v3 / Word 97 binary document. Its important `WordDocument` and `1Table` streams were intact, but the CFB header contained inconsistent MiniFAT metadata: it declared zero MiniFAT sectors while pointing the MiniFAT start at a sector immediately beyond the physical end of the file.

The file's Word FIB and CLX were still usable. The CLX described one compressed text piece of 1,807 characters beginning at byte offset `0x400` in `WordDocument`. Structured extraction recovered that text even though strict CFB handling rejected the container.

See [`docs/KNOWN_TEST_CASE.md`](docs/KNOWN_TEST_CASE.md).

## Testing

Install the optional test dependency:

```bash
python -m pip install pytest
pytest
```

The repository tests use synthetic files and streams so no private real-world document needs to be published.

For a private damaged sample:

```bash
legacy-doc-recover input/bad.doc -o output/bad.recovered.txt --report output/bad.recovery.json
```

Do not commit private samples. Document files under `input/` and generated files
under `output/` are ignored by Git.

## Format documentation

- [`docs/DOC_BINARY_FORMAT.md`](docs/DOC_BINARY_FORMAT.md) — only the parts of CFB/MS-DOC needed by this project.
- [`docs/RECOVERY_PROCESS.md`](docs/RECOVERY_PROCESS.md) — recovery algorithm and confidence model.
- [`docs/KNOWN_TEST_CASE.md`](docs/KNOWN_TEST_CASE.md) — anonymised first damaged-file case.
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — explicit v0.1 boundaries and likely next work.

## Primary specifications

The implementation is derived from Microsoft's Open Specifications, especially:

- MS-CFB — Compound File Binary File Format: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/
- MS-DOC — Word (.doc) Binary File Format: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/ccd7b486-7881-484c-a137-51170af7cc22
- MS-DOC text retrieval: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/01d5d8c4-cf9c-4ef9-80fd-439e763cfe01

## Contributing

The most valuable contribution at this stage is **additional damaged-file test coverage** with a clear description of:

1. what applications/parsers fail on the file;
2. the observed corruption pattern;
3. what text should be recoverable;
4. whether v0.1 succeeds, partially succeeds or fails;
5. a sanitised/minimal fixture where redistribution is legally and ethically safe.

Do not submit confidential documents.

## License

This project is licensed under the [Zero-Clause BSD licence (0BSD)](LICENSE).
