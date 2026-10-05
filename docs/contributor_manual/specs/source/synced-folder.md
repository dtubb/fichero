# Source Model — The synced folder — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Keeping a folder in step" section: tying a project or a folder of it to a
> folder on disk, what Fichero writes there and when, which files it reads back, what happens to
> files that arrive, change or disappear there, how an existing folder of TEI, ALTO or PAGE XML is
> adopted, and how conflicts are shown.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model (split out of
> `models-chains-and-projects.md` on 2026-09-19, because it is a programme of its own): read
> `source-model.md` first. Behaviours are tagged with their issue; the write half of a made folder is
> built (2026-10-04), the rest is not. Reorganised on 2026-10-01; no behaviour id was removed or renamed.
>
> **Owners, and do not duplicate.** Writing a project's outputs to disk as the work goes on is the
> exporter's planned continuous export (`export/exporter.md`, its continuous-sync behaviour,
> #4640): the **out** half of this file states what the source model needs from that, and is not
> a second exporter. Taking files **in** is a new *trigger* for the one import path
> (`importer/importer.md`), not a second importer; re-import of an unchanged file is the
> importer's content-hash skip (#739). Running work on what comes in is the activity system's
> (`ui/activity-and-automatic-work.md`, #5352). Which formats exist is `formats-and-training.md`'s.

## Intent

A project, or a folder inside it, can be tied to a folder on disk. Its outputs (TEI, PAGE, ALTO,
Markdown, a spreadsheet, a static site) are written there and kept current as the work goes on,
so the folder always matches the library without anyone exporting again. Files that arrive or
change there come into the project as new work, never over a person's. A folder someone already
keeps (TEI they edit in Oxygen, ALTO from a digitisation project) can be adopted as it is.

Ruled 2026-09-19: a folder Fichero makes has a **fixed layout that Fichero chooses**; taking files
in is switched on for each project and asks before its first run. Ruled 2026-10-01: the folder
works **both ways**, and an existing folder of TEI, ALTO or PAGE XML can be **adopted**, keeping
its own layout.

## The words

| Word | Means |
|---|---|
| **synced folder** | a folder on the engine's disk tied to a project or a folder of it, written by an export step of its recipe and, where the formats allow, read back |
| **made folder** | a synced folder Fichero created: Fichero's fixed layout |
| **adopted folder** | an existing folder brought in by import and then kept in step in its own layout |
| **read-back format** | a format Fichero can import (PAGE, ALTO, TEI): edits to such files come back. Every other format is **out only** |
| **intake** | new images or files arriving in the folder becoming sources |

**The four ways sources come in** (ruled by the maintainer, 2026-10-03). Setup asks this once per
project, and each import can choose again:

| Way | What happens to the originals |
|---|---|
| **Link** (the default) | read where they are; Fichero never changes them |
| **Copy** | Fichero makes its own copy in the project; the originals are never touched |
| **Move** | moved into the project and kept by the app; the originals are removed from where they were (setup says so plainly) |
| **Index** | Fichero works on the folder in place and writes its changes back into the original files, keeping that folder up to date: an adopted folder, both ways |

Link, Copy, Move and Index are the folder ingest `mode` (`link`, `copy`, `move`, `index`). Index
is this spec's adopted folder: the files are linked, and the folder is kept in step in place.

## What exists today

- The exporter writes PAGE, ALTO, TEI, plain text and more on request (`export/exporter.md`);
  continuous export is planned there (#4640), not built.
- Folder watching exists for automation triggers (`workflows/file_watcher.py`, on `watchdog`,
  with debouncing), starting workflow runs; it is the base intake grows from, not a second
  watcher.
- The importer skips a file whose content hash it has seen (#739).
- Nothing records which files Fichero wrote, or their checksums.

## The design (proposed)

### What a synced folder is

A synced folder is the **destination of an output step** in the recipe (`export` with `to:
synced-folder`, `models-chains-and-projects.md`). The step names the formats; the project binds
the step to a folder on the engine's disk. A project can have **several**: TEI and PAGE for the
edition, Markdown for an Obsidian vault, a spreadsheet for a collaborator, an Eleventy site. All
are the same mechanism. A folder of the project can have its own (a folder of maps writes its own
georeferenced outputs).

The folder is named **on the engine's side**: the engine may be on another machine, and the app
never assumes it can see the same disk.

### Out, as you go

- For each source, Fichero keeps the chosen outputs current. It writes the **working pass and
  the chosen readings**. Where a reading nobody has chosen is written (a relaxed project, or before
  review), the file and its loss report say it is machine-made.
- When a segment or reading changes, the files that hold it are rewritten **after a short quiet
  period**, as an export job in Activity, not at some later export. Only what the change touched is
  rewritten.
- A file is written **whole**: to a temporary file beside it, then renamed into place, so another
  program never reads half a file.
- Each file says which pass, reading order and kind of reading it holds, carries the source's
  **lasting id** (in the format's own place for an identifier), and has its loss report beside it.
- Writing is **background work**: throttled like all of it, stopped by *Pause Background Work*,
  and caught up after.
- **Restricted material stays out** unless deliberately included.

### In, as they arrive

- **Intake** is switched on for each project. The first time, it shows what it is about to bring
  in (how many files, of which kinds) and waits for a yes: a folder of fifty thousand images must
  not start work by surprise.
- New images become sources and go through the recipe of the folder they land in, as the
  project's automatic work.
- A **read-back file** (PAGE, ALTO, TEI) that appears or changes, edited in another tool, comes in
  as **a new pass with its own provenance** (who: "edited outside Fichero"; when: the file's
  time), the same as any import. It never overwrites work in the project. In a strict project it
  waits for a person to make it the working pass; in a relaxed one it counts as a person's work
  only if the person says the edit was theirs (it is never assumed).
- An edit to an **out-only file** (a spreadsheet, Markdown, the site) is not read back: the folder's
  status lists it as "changed outside; not read back", and the next rewrite of that file asks
  before replacing it.
- A **renamed or moved** file is still matched, by the lasting id it carries.
- A file **deleted** in the folder deletes nothing in the project. The status lists it; it is
  written again on the next change to its source or on **Rebuild Folder**.
- **After downtime.** Watchers miss events while the engine is off, so on start the folder is
  compared with the checksums Fichero recorded, and anything changed, added or removed meanwhile is
  handled as though it had been seen live.

### Conflicts are shown, not settled silently

If the project and a read-back file both changed since Fichero last wrote it, Fichero keeps both,
as two passes, and says so: the source's Inspector shows "two versions: edited in the folder on 3
May, and in Fichero on 4 May", with the passes side by side. Nothing is merged by itself.

### Fichero never overwrites a file it did not write

Fichero records a checksum of every file it writes. Before writing, it checks the file on disk:
if the checksum matches, it writes; if the file has changed, it is a read-back edit or an
out-only change (above); if the file is not one Fichero wrote at all, it is **left alone and
reported**.

### Adopting an existing folder (2026-10-01)

A folder someone already keeps (TEI files, ALTO, PAGE XML) can be **made the synced folder by
importing it**: its files come in through the one import path, and from then on the folder
**keeps its own layout**. Each file is matched to the source it made (by the image it names, or by
file name where it names none, and the match is shown for correction). Work done in Fichero is
written back into **the same file, in the same format**; edits made in the folder come in as
passes, as above. A made folder uses Fichero's fixed layout; an adopted one keeps the one it had
(this refines the fixed-layout ruling of 2026-09-19 for adopted folders only). Adopting is the
person's explicit permission for Fichero to write those files: it records each file's checksum
when it reads it, and writes back only if the file is unchanged since; a file edited meanwhile is
a conflict, and both are kept. Adopting turns intake on for that folder, because that is what
adopting means; the first run still shows what it will bring in.

### The fixed layout of a made folder

Fichero chooses where each kind of file goes and what it is called (one subfolder per format; one
file per source, or per page where the format is per page; names from the source's title and
lasting id), so two projects' folders look alike and a file can always be matched to its source.

### A projection, with a status

- The folder is a **projection**: it can be deleted and made again from the project with
  **Rebuild Folder**. The project remains the record.
- **Untying** a folder stops writing and intake; the files are left on disk.
- The folder's **status**, in the Inspector when the folder (or the library) is selected: where it
  is, its formats, when it was last written, how many files wait to be written, conflicts, files
  changed outside and not read back, files deleted outside, and files in the way that Fichero did
  not write.

## Behaviors (each cites its issue on milestone `source-model`, 322; the write half of a made folder is built)

Out
- `source.sync.out-is-the-exporters` — **[OK]** (#4952) *Built 2026-10-04: each file is the exporter's own output, byte for byte (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* writing outputs as the work goes on is the
  exporter's continuous export (→ #4640), fed by this model; no second export path exists.
- `source.sync.one-mechanism-many-folders` — **[PARTIAL]** (#4952, #4640) *Built: several folders, each naming its formats, one mechanism; a folder of part of a project is not built (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* a project or one of its
  folders can have several synced folders, each the destination of an export step naming its
  formats, all through the same mechanism.
- `source.sync.writes-the-record-or-says-so` — **[OK]** (#4952) *Built: the working pass is written, each line with its counted reading; the lines whose reading a machine made and nobody chose are counted in the file (`fichero-machine-made-lines`), in its loss report and in the export's choices (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* the folder holds the working pass
  and chosen readings; an unchosen machine reading written there is marked machine-made in the
  file and its loss report.
- `source.sync.outputs-follow-edits` — **[OK]** (#4952) *Built: a change queues its pages' rewrite in the change's own transaction, after a quiet period that each new change pushes later, as a `write-to-folder` job in Activity (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* the files holding a changed segment or
  reading are rewritten after a short quiet period, as an export job in Activity; files the change
  did not touch are not rewritten.
- `source.sync.atomic-writes` — **[OK]** (#4640) *Built: a temporary file beside it, renamed into place (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* every file is written to a temporary file and
  renamed into place, so no other program can read a half-written file.
- `source.sync.files-say-what-they-hold` — **[OK]** (#4952) *Built: `fichero-pass`, `fichero-reading-order`, `fichero-reading-kind` in the file, `<file>.loss.json` beside it (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* each file names its pass, reading
  order and reading kind, with its loss report beside it.
- `source.sync.files-carry-ids` — **[OK]** (#4952) *Built: `fichero-source` in PAGE's MetadataItem, ALTO's fileIdentifier, TEI's idno, and read back by each format's reader; a renamed or moved file is matched to its source by it (`fichero-server/tests/unit/jobs/test_synced_folder.py`, `fichero-server/tests/unit/jobs/test_synced_folder_arrivals.py`).* each written file carries its source's lasting
  id, so a renamed or moved file is still matched to its source.
- `source.sync.restricted-stays-out` — **[GAP]** (#4952) restricted material is left out of the
  folder unless deliberately included.
- `source.sync.engine-side-and-throttled` — **[OK]** (#4952) *Built: a full path on the engine's disk, written by jobs on the background database lane (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* the folder is named where the engine
  runs, and syncing is throttled background work.
- `source.sync.paused-with-background-work` — **[PARTIAL]** (#4952) *Built for writing; intake is not built (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* writing and intake stop under Pause
  Background Work and catch up when it is resumed.

In
- `source.sync.intake-is-opt-in` — **[PARTIAL]** (#4952) *Built in the engine: intake is off for a made folder until `PUT /api/sync-folders/{id}/intake`, after `GET` of the same gives what it would bring in, by kind (images, and files by format); an adopted folder has it on. The app's preview and switch are not built (`fichero-server/tests/unit/jobs/test_synced_folder_intake.py`).* taking files in from the folder is switched on
  for each project and shows what it will bring in (counts by kind) before its first run.
- `source.sync.one-import-path` — **[OK]** (#4952) *Built: files arriving in a folder with intake on are imported as one set through `import_file_set`, the path a drop of files takes (`POST /api/ingest/files`), so a layout file beside its image becomes its pass (`fichero-server/tests/unit/jobs/test_synced_folder_arrivals.py`).* files arriving through the synced folder go
  through the same import path as any other import.
- `source.sync.new-images-come-in` — **[PARTIAL]** (#4952) *Built: with intake on, the folder is watched while the engine runs, and an image put in it becomes a source, linked where it was put, with the project's automatic work as any import has it; the recipe of the subfolder it lands in is not built (`fichero-server/tests/unit/jobs/test_synced_folder_arrivals.py`).* images added to the folder become sources and
  run the recipe of the folder they land in.
- `source.sync.read-back-formats` — **[PARTIAL]** (#4952) *Built: a file that arrives in another format is listed (`not_read_back`) and not taken in; a synced folder writes no out-only format yet, so "the next rewrite asks first" has nothing to ask about (`fichero-server/tests/unit/jobs/test_synced_folder_arrivals.py`).* only files in a format Fichero can import
  (PAGE, ALTO, TEI) are read back; a change to any other file is listed as "changed outside; not
  read back", and the next rewrite of it asks first.
- `source.sync.outside-edits-are-passes` — **[PARTIAL]** (#4952) *Built for files Fichero wrote or adopted: a changed one comes in through `format.import` as a new pass made by "edited outside Fichero", named with the file's time, which the working-pass ladder passes over until a person chooses it. The folder is watched while the engine runs, and read when the library opens, when intake is switched on, and when a write finds a file changed (`fichero-server/tests/unit/jobs/test_synced_folder_intake.py`).* a changed or new read-back file comes
  in as a new pass with provenance ("edited outside Fichero", the file's time) and overwrites
  nothing.
- `source.sync.conflicts-kept-both` — **[PARTIAL]** (#4952) *Built: both changed since the last write is found by two checksums (the file's and the exporter's output); the file's version comes in as a pass beside the project's, the file is no longer written, and `GET /api/sync-folders` lists it under `conflicts`. The Inspector and settling a conflict are not built (`fichero-server/tests/unit/jobs/test_synced_folder_intake.py`).* when project and file both changed since
  Fichero last wrote it, both are kept as passes and the conflict is shown in the source's
  Inspector.
- `source.sync.deleted-outside` — **[PARTIAL]** (#4952) *Built: a deleted file deletes nothing, is listed, and is written again on the next change to its source; Rebuild Folder is not built (`fichero-server/tests/unit/jobs/test_synced_folder_intake.py`).* a file deleted in the folder deletes nothing in
  the project; it is listed, and written again on the next change to its source or on Rebuild
  Folder.
- `source.sync.rescan-after-downtime` — **[PARTIAL]** (#4952) *Built: on library open, files changed or deleted while the engine was off are found and reported; with intake on they are handled as though seen live (an edit comes in as a pass); files added meanwhile are not taken in (`fichero-server/tests/unit/jobs/test_synced_folder.py`, `fichero-server/tests/unit/jobs/test_synced_folder_intake.py`).* on engine start the folder is compared
  with the recorded checksums, and changes made while the engine was off are handled as though
  seen live.

Ownership and layout
- `source.sync.never-overwrites-a-stranger` — **[OK]** (#4952) *Built: a file Fichero did not write, or one changed since, is left and reported (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* Fichero overwrites only files it
  wrote itself, known by a checksum it recorded; any other file in the way is left and reported.
- `source.sync.fixed-layout` — **[OK]** (#4952) *Built: one subfolder per format, `<title>--<lasting id><extension>` (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* a made folder's layout is chosen by Fichero and is
  the same for every project.
- `source.sync.four-ways-in` — **[PARTIAL]** (#4952) *Built: the engine's folder import takes `mode: index`, which leaves the originals in place, changes no file and adopts the folder (`fichero-server/tests/unit/jobs/test_adopted_folder.py`). Built 2026-10-04 (app): setup's Your Material screen asks the way in (Link, Copy, Move, Index, each saying what it does to the originals; Link the default), saves it with the project's answers, and its Add a Folder… imports with it, `index` sent as `index` (`IngestMode.index`, `RecipeSetupStore.addFolder`; `fichero/Tests/Unit/general/Models/RecipeSetupFlowTests.swift`). Default taken 2026-10-04 (design lead), awaiting the maintainer's ruling: Index is a folder way in; loose files chosen with Index are linked. Not built: the import menus and drops still offer Link, Copy and Move only, and do not start from the project's saved choice.* setup and import offer Link, Copy, Move and Index with what each does to the originals; Link, Copy and Move are built (ingest `mode`). A fifth way, **Keep arranged** (ruled 2026-10-05, #5480), and setup's use of `/api/sync-folders` for Index are specified once in `models-chains-and-projects.md` section 7b (`source.onboard.five-ways-in`, `source.onboard.index-ties-the-folder`, `source.onboard.keep-arranged`).
- `source.sync.adopt-existing-folder` — **[PARTIAL]** (#4952) *Built: an Index import of PAGE or ALTO files paired with their images adopts the folder in its own layout and records each file's checksum at read; a change to the page is written back into the same file in the same format, only while it is unchanged since; a file changed meanwhile is left and reported. Adopting turns intake on: edits made in the folder come in as passes, and a conflict keeps both. Not built: the match shown for correction, and a TEI file spanning several images (`fichero-server/tests/unit/jobs/test_adopted_folder.py`, `fichero-server/tests/unit/jobs/test_synced_folder_intake.py`).* importing a folder of TEI, ALTO or PAGE XML
  can make it the synced folder: it keeps its own layout, each file is matched to its source (the
  match shown for correction), work in Fichero is written back into the same file in the same
  format, edits made in the folder come in as passes, and a file changed since it was read is a
  conflict with both kept.
- `source.sync.folder-is-a-projection` — **[GAP]** (#4952) the folder can be deleted and remade from
  the project with Rebuild Folder.
- `source.sync.untie-leaves-files` — **[PARTIAL]** (#4952) *Built: untying stops writing and leaves the files; intake is not built (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* untying a folder stops writing and intake and
  leaves its files on disk.
- `source.sync.status-in-inspector` — **[PARTIAL]** (#4952) *Built: `GET /api/sync-folders` gives place, formats, last write, pending, and files written, in the way, changed and deleted outside, conflicts, and whether intake is on; the Inspector is not built (`fichero-server/tests/unit/jobs/test_synced_folder.py`).* the Inspector shows each synced folder's
  place, formats, last write, pending files, conflicts, files changed or deleted outside, and files
  in the way that Fichero did not write.

## Test matrix

To be filled at approval. The legs it will need: backend tests on a temporary folder (write, edit
outside, conflict, delete, rename, stranger file, restart with changes made while stopped,
adoption of a TEI folder written by another tool); a load test on a folder of thousands of files
(bounded writing, no CPU peg).

## Open questions (with recommendations)

1. **Markdown both ways?** An Obsidian vault is edited by hand, and people will expect edits to
   come back. *Recommend:* out only until `formats-and-training.md` defines how Markdown maps to
   readings; then it joins the read-back formats with no change here.
2. **Who made an outside edit, in a relaxed project?** A file's edit carries no author.
   *Recommend:* "edited outside Fichero", counted as a person's only when the person says it was
   theirs (as written); never assumed.
3. **Answered** (design lead 2026-10-04, applying the spec's lean): The same quiet period Activity uses after a correction. **How long is the quiet period before a rewrite?** *Recommend:* the same quiet period the
   activity system uses for re-extraction after a correction, so a run of corrections makes one
   write.

Older questions: see `source-model.md`.

## Future (ideas, not scheduled)
- (#4463) Future section: a fifth file mode MANAGED (Fichero owns layout in an iCloud Drive folder, which becomes the sync channel); product vision.
