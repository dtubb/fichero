# 9. Ingest


The ingest module (`fichero_server.importers.ingest`) handles file import, metadata extraction, and storage — the unified path for bringing external files into a library.

### Modes

- **LINK** (default) — creates a macOS bookmark referencing the original file; no copy; the original must remain accessible.
- **COPY** — imports the file into library storage, using APFS cloning for near-instant same-volume copies; files are organized in a sharded directory structure.
- **MOVE** — imports into library storage, then deletes the original; the library owns the only copy afterwards.

File-type detection is extension-based (`_FILE_TYPE_MAP`, 50+ extensions → document/image/audio/video) with MIME detection. Metadata extraction covers size, checksums, MIME types, image dimensions/EXIF, and watch-folder provenance for camera intake (`source_path`, `source_folder`, `source_mtime`). Text extraction uses the unified loader system (PDF, DOCX, EPUB, text) and stores results on `document.page_content`; checksum-based deduplication prevents duplicate imports.

### Core functions

Both functions also accept internal `db` and `package_path` arguments; omit them for normal use — they default to the active library.

    from fichero_server.importers.ingest import ingest_file, ingest_folder, IngestMode

    # Single file — LINK is the default mode
    doc = ingest_file(Path("/path/to/file.pdf"))

    # COPY with text extraction and embeddings
    doc = ingest_file(
        Path("/path/to/document.docx"),
        mode=IngestMode.COPY,
        extract_text=True,
        auto_embed=True,
    )

    # Recursive folder ingest with progress
    docs = ingest_folder(
        Path("/path/to/folder"),
        mode=IngestMode.COPY,
        recursive=True,
        on_progress=lambda current, total: print(f"{current}/{total}"),
    )

`ingest_file(path, mode=LINK, parent_id=None, extract_metadata=True, extract_text=True, auto_embed=True, save=True)` returns a `Document`; it raises `FileNotFoundError` if the file doesn’t exist and `ValueError` if the path is not a file. `extract_text` and `auto_embed` default to `True` (#881) so dropped `.md`/`.txt`/`.docx`/text-bearing PDFs are searchable immediately; image-only files still skip the loader.

`ingest_folder(folder, mode=LINK, parent_id=None, recursive=True, create_collection=True, extract_text=True, auto_embed=True, on_progress=None)` returns a list of `Document`s, creating a collection for the folder by default (pass `create_collection=False` with an explicit `parent_id` to file into an existing collection).

Utility functions in the same module: `detect_file_type(path)` → `FileType`; `discover_files(folder, extensions=None, recursive=True)` yields matching paths; `count_files(folder, extensions=None, recursive=True)` → int; `find_duplicates(documents)` → `dict[checksum, list[Document]]`.

Note that the HTTP ingest routes wrap these implementations in the audited `import.file` / `import.folder` actions (chapter 5) — API-level imports get audit rows and change events. For camera/DSLR watched-folder intake, pair folder ingest with the built-in `Rotate / Auto-Orient Images` capture preset; it keeps source provenance in metadata and leaves the originals untouched.

------------------------------------------------------------------------
