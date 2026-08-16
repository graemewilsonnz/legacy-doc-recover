# Recovery process

## Objective

Recover surviving document text without executing any active content and without requiring Word to accept the file as structurally valid.

The key principle is:

> Failure of the container or application parser does not necessarily mean failure of the underlying data.

## Structured recovery

### Stage 1 — Validate enough CFB to proceed

1. Check the CFB signature.
2. Read sector geometry.
3. Collect usable FAT sectors from the DIFAT.
4. Follow the directory sector chain.
5. Read directory entries.
6. Record anomalies rather than rejecting every nonessential inconsistency.

The implementation remains bounded: invalid sector references, loops and impossible sizes are detected rather than followed indefinitely.

### Stage 2 — Recover the Word streams

Locate:

- `WordDocument`;
- the Table stream selected by the Word FIB (`0Table` or `1Table`).

Streams at or above the mini-stream cutoff use normal FAT sectors. Smaller streams use the MiniFAT/root mini stream when those structures are usable.

If a normal FAT stream's chain is damaged, the reader can try a contiguous-sector fallback. A warning reduces confidence because physical adjacency is not guaranteed by CFB.

### Stage 3 — Parse the Word FIB

From `WordDocument`:

1. verify `wIdent == 0xA5EC`;
2. record `nFib`;
3. reject encrypted/obfuscated documents in v0.1;
4. select `0Table` or `1Table`;
5. walk the variable FIB sections;
6. locate `fcClx/lcbClx`;
7. record `ccpText` for main-story extraction.

### Stage 4 — Parse CLX / PlcPcd

1. Skip any `Prc` records.
2. locate the `Pcdt`;
3. validate `PlcPcd` length;
4. read logical CP boundaries;
5. read each PCD;
6. derive each physical offset and compression mode.

### Stage 5 — Decode pieces

For each piece in logical order:

- compressed piece → decode as the selected Windows code page;
- uncompressed piece → decode as UTF-16LE.

By default extraction stops at `ccpText`, so v0.1 returns the main document story. `--all-stories` disables that boundary.

### Stage 6 — Normalise only basic text controls

The output normalises obvious paragraph/line separators and removes a small number of non-text structural markers. It deliberately does not infer missing formatting or list labels.

## Low-confidence fallback

If the structured path fails, the default CLI tries a conservative raw scan for plausible single-byte and simple UTF-16LE text runs.

Raw scan output begins with an explicit warning and includes byte offsets. It can contain:

- strings unrelated to document body text;
- incorrect ordering;
- duplicates;
- missing non-Latin text;
- text from metadata or embedded content.

Use `--no-raw-fallback` when only high-confidence structured recovery is acceptable.

## Confidence levels

### Structured piece-table recovery

High confidence for the recovered **logical character sequence**, subject to:

- correct code-page selection for compressed pieces;
- undamaged relevant piece-table structures;
- v0.1's intentional formatting exclusions.

### Contiguous FAT fallback

Reduced confidence in stream reconstruction because CFB streams are allowed to be fragmented.

### Raw scan

Low confidence. It is evidence discovery, not document reconstruction.

## Security considerations

The parser should continue to follow these rules as it evolves:

- never execute VBA/macros;
- never instantiate embedded OLE objects;
- never launch Word/LibreOffice as part of core recovery;
- bound all sector-chain traversal;
- detect cycles;
- validate offsets and lengths before slicing;
- treat document bytes as adversarial input;
- reject unsupported encryption rather than guessing.

