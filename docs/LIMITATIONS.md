# v0.1 limitations

## Supported target

Initial target: Microsoft Word 97–2003 binary `.doc` stored as CFB/OLE. The real damaged-file validation is CFB v3; the code handles CFB v4 sector geometry but that path is not yet validated against a real corpus.

The parser recognises a Word FIB and follows the Word 97-era `FibRgFcLcb97.fcClx/lcbClx` text-retrieval path.

## Not currently supported

### Pre-Word-97 binary formats

Older Word binary formats can have different structures. v0.1 does not claim support.

### Encryption and obfuscation

Detected and rejected. Password cracking/decryption is intentionally outside scope.

### Faithful formatting recovery

List numbering, styles, fonts, tabs/stops, indentation, sections and page layout are not reconstructed.

### Semantic tables

The text stream's table markers are reduced to separators. Rows/cells are not rebuilt as a table model.

### Images and embedded objects

Not extracted in v0.1.

### Code-page completeness

Compressed pieces use legacy code pages. v0.1 has a small language-ID map plus explicit `--codepage` override. Broader encoding inference needs corpus testing.

### Severe directory/FAT loss

If the CFB directory cannot be found or the required streams cannot be reconstructed, the structured recovery path fails. The optional raw scan may still find fragments but with low confidence.

### Malicious-file hardening

The implementation includes bounds and loop checks but has not undergone security review or fuzzing. Do not treat v0.1 as a hardened forensic library.

## Candidate next versions

The next work should be evidence-driven from additional damaged files, not implemented merely because MS-DOC contains the structure.

Likely high-value areas:

1. build a sanitised corpus of distinct corruption patterns;
2. fuzz CFB/FIB/CLX parsing and add resource limits;
3. improve code-page inference;
4. identify Word streams when the directory is partly damaged;
5. recover paragraph/list labels where reliable;
6. optionally recover tables into TSV/Markdown;
7. optionally extract embedded images without executing objects;
8. test Word 2000/2002/2003 variants and multiple-piece documents;
9. establish whether pre-97 support warrants a separate parser path.

