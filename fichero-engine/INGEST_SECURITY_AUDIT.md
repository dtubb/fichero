# Ingest Security Audit

Scope reviewed on 2026-07-05:

- `fichero-engine/src/fichero/importers/ingest.py`
- `fichero-engine/src/fichero/importers/*`
- `fichero-engine/src/fichero/bookmarks.py`
- `fichero-engine/src/fichero/loaders/*`

## Findings

1. `fichero-engine/src/fichero/importers/ingest.py:245`, `:998-1010`, `fichero-engine/src/fichero/bookmarks.py:96`
   - Attack: symlink escape during single-file or folder ingest. `ingest_file()` resolves the caller-supplied path before any policy check, so a symlinked file inside an ingest folder can target a file outside the chosen tree. `ingest_folder()` also accepts symlinked files because it filters on `f.is_file()` but never rejects `f.is_symlink()`. In LINK mode, `create_bookmark(path.resolve())` then bookmarks the out-of-tree target; in COPY/MOVE mode the engine copies or deletes the target, not the link.
   - Fix: reject symlink sources before `resolve()` in `ingest_file()`, and skip or fail symlinked entries in `ingest_folder()` before they reach `ingest_file()`. Keep the check in the shared ingest path, not only in routes.

2. `fichero-engine/src/fichero/loaders/xlsx_reader.py:18-32`
   - Attack: zip-bomb / oversized workbook resource exhaustion. The loader caps each individual member at 20 MiB, but it does not cap total uncompressed size or member count. A workbook with many members each under 20 MiB can still drive high memory/CPU use during XML parsing.
   - Fix: add a total-uncompressed-bytes cap and a member-count cap in `_validate_zip_members()`, then reject the archive before parsing any XML.

3. `fichero-engine/src/fichero/loaders/image_loader.py:89-137` and `fichero-engine/src/fichero/importers/ingest.py:707-731`
   - Attack: decompression-bomb / oversized image resource exhaustion. PIL is opened directly for metadata extraction and full image load, and helper conversions (`heif-convert`, `djxl`) materialize PNGs without an explicit pixel ceiling. That is not a write-outside bug, but a crafted image can still cause large memory use.
   - Fix: enforce a hard pixel cap (or turn Pillow's decompression-bomb warning into a hard failure for ingest paths), and reject converted outputs whose dimensions exceed the cap before copying them into memory.

## Notes

- I did not find a current write-outside bug in `_copy_to_library()`: destination filenames are derived from `source.name`, so path separators do not survive into the destination path.
- I did not find archive path-traversal extraction in the reviewed code: the `.xlsx` reader parses members in-place with `zipfile.ZipFile.open()` and does not call `extract()` / `extractall()`.
- The clearest safe fix is finding #1: symlink rejection in the shared ingest path.
