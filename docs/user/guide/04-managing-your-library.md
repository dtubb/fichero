# Chapter 4. Managing Your Library


### About Libraries

A library is a `.fichero` package on disk. Each window works with one library. Current builds start with a ready-to-use local library: on first launch, onboarding surfaces that library and lets you continue straight into the app without creating anything first.

### Creating and Opening Libraries

You can create another library or open an existing `.fichero` package from the **File** menu at any time. Creating a new library uses a save panel and adds the `.fichero` suffix automatically if you do not type it. Opening a library uses a package picker.

### Importing Documents

You bring material into a library by dragging files and folders onto the window, or with the import commands in the toolbar’s add menu:

- 
- 
- 

**Link Files…** — keep the original file where it lives and add it to the library.**Copy Files…** — import a copy into library-managed storage.**Move Files…** — import the file into library-managed storage and remove the original. Use this when the library should take ownership of the file.You can also create a new folder first, then import into it. Imported files can be text-extracted and embedded for search as part of ingest.

#### Importing folders

If you import a folder, Fichero detects that and switches to the folder-import path. Folder imports run as background tasks, can recurse into subfolders, preserve the folder hierarchy, and report progress while running. This is why larger imports may continue in the background instead of appearing all at once.

#### Drag and drop

The library window accepts dropped files and folders. Dropping into the window starts an import; dropping onto a specific sidebar folder targets that folder. Fichero shows import progress and surfaces readable errors when an import fails. For day-to-day use, drag-and-drop is the fastest way to get a pile of scans or PDFs into the library.

### Supported File Types

Fichero recognizes 61 file extensions. In summary:

| Category | Examples |
|----|----|
| Images and scans (incl. RAW) | JPEG, PNG, TIFF, HEIC, JPEG 2000, DNG, CR2/CR3, NEF |
| PDF |  |
| Text and markup | TXT, Markdown, RTF, HTML, XML, subtitle files |
| Word processing | DOC, DOCX, ODT |
| Spreadsheets | CSV, XLS, XLSX, ODS |
| Presentations | PPT, PPTX, ODP |
| Ebooks | EPUB, MOBI |
| Audio | MP3, WAV, M4A, FLAC |
| Video | MP4, MOV, MKV, WebM |

Text extraction for search indexing is implemented for PDFs, word-processing files, text files, spreadsheets, presentations, and EPUBs. Files with unrecognized extensions can still be imported, but with limited functionality. The full extension list is in Appendix A.

### Moving Around

A few behaviors matter early:

- 
- 
- 
- 

### Changing the sidebar selection changes the document set in the browser.Changing the browser selection updates the Reader and the inspector.The app remembers window state such as visible panes, layout, and some sort settings.Search starts from the toolbar while you are in Library mode; results render into the Library view.Sharing a Library

A library can be shared with other people, each with their own user account. Sharing is off by default; when enabled, members are managed in Settings, and each member has a role that controls what they can see and change. Access can be granted at the library level and refined per folder. Remote access for another device or person runs over your private Tailscale network (see Chapter 9) — never over the open internet. Sharing is an early feature in active development.
