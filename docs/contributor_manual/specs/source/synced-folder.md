# Source Model — The synced folder — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Keeping a folder in step" section: tying a project to a folder, what Fichero
> writes there and when, what happens to files that arrive or change there, and how conflicts
> are shown.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model (split out of
> `models-chains-and-projects.md` on 2026-09-19, because it is a programme of its own): read
> `source-model.md` first. Behaviour ids below have **no tags yet**; nothing here is built.
>
> **Owners, and do not duplicate.** Writing a project's outputs to disk as the work goes on
> is already the exporter's planned continuous export (`export/exporter.md`,
> `export.exporter-manager-continuous-sync`, #4640): the **out** half of this file states what
> the source model needs from that, and is not a second exporter. Taking files **in** is a new
> *trigger* for the one import path (`importer/importer.md`), not a second importer; re-import
> of an unchanged file is the importer's content-hash skip (#739).

## Intent

A project can be tied to a folder. Its outputs (the XML and the rest) are written there and
kept up to date as the work goes on, and files that arrive or change there come into the
project. Ruled 2026-09-19: the folder has a **fixed layout that Fichero chooses**; taking files
in is switched on for each project, and asks before its first run.

## The design (proposed)

A project can be tied to a folder on the machine where the engine runs. This is more than
export: the folder is a **new way to start an import**, and it needs real engine and app work
(watching the folder; matching files to sources; bringing outside edits in as passes; showing
conflicts). It is a new *trigger* for the one import path that `importer/importer.md` owns,
not a second importer. Taking files **in** from the folder is switched on for each project,
and the first time it shows what it is about to bring in and waits for a yes (a folder of
fifty thousand images must not start work by surprise).

- **Out, as you go.** For each source, Fichero keeps chosen outputs up to date in the folder.
  It writes the **working pass and the chosen readings**. Where a reading nobody has chosen
  is written, the file and its loss report say it is machine-made. Outputs:
  the page's PageXML or ALTO, a TEI file for the source, plain text, the training set, and the
  rest of `formats-and-training.md`. When a segment or reading changes, the affected files are
  rewritten soon after, not at some later export. Each file says which pass, reading order and
  kind of reading it holds, and carries its loss report beside it.
- **In, as they arrive.** New images dropped into the folder become sources in the project and
  go through its default chain. An XML file that appears or changes there (edited in another
  tool) comes in as **a new pass with its own provenance**, the same as any import. It never
  overwrites work in the project.
- **Conflicts are shown, not settled silently.** If the project and the file both changed,
  Fichero keeps both, as two passes, and says so.
- **Restricted material stays out** of the folder unless deliberately included.
- The folder is a **projection**: it can be deleted and made again from the project. The
  project remains the record.
- The engine may be on another machine, so the folder is named on the engine's side; the app
  never assumes it can see the same disk.
- Writing is throttled like all background work, so a large project never pegs the machine.
- **The layout is fixed** (ruled): Fichero chooses where each kind of file goes and what it is
  called, so two projects' folders look alike and a file can always be matched to its source.
- **Fichero never overwrites a file it did not write.** It records a checksum of everything it
  writes; a file in its way that it does not recognise is left alone and reported.

## Behaviors (ids proposed; untagged until approval)

- `source.sync.writes-the-record-or-says-so` — the folder holds the working pass and chosen
  readings; an unchosen machine reading written there is marked machine-made in the file and
  its loss report.
- `source.sync.intake-is-opt-in` — taking files in from the folder is switched on for each
  project and shows what it will bring in before its first run.
- `source.sync.outputs-follow-edits` — chosen outputs in the project's folder are rewritten
  soon after the segments or readings they hold change.
- `source.sync.files-say-what-they-hold` — each file names its pass, reading order and reading
  kind, with its loss report beside it.
- `source.sync.new-images-come-in` — images added to the folder become sources and run the
  project's default chain.
- `source.sync.outside-edits-are-passes` — a changed or new XML file comes in as a new pass
  with provenance and overwrites nothing.
- `source.sync.conflicts-kept-both` — when project and file both changed, both are kept and
  the conflict is shown.
- `source.sync.restricted-stays-out` — restricted material is left out of the folder unless
  deliberately included.
- `source.sync.folder-is-a-projection` — the folder can be deleted and remade from the project.
- `source.sync.one-import-path` — files arriving through the synced folder go through the same
  import path as any other import.
- `source.sync.engine-side-and-throttled` — the folder is named where the engine runs, and
  syncing is throttled background work.
- `source.sync.fixed-layout` — the folder's layout is chosen by Fichero and is the same for
  every project.
- `source.sync.never-overwrites-a-stranger` — Fichero overwrites only files it wrote itself,
  known by a checksum it recorded; any other file in the way is left and reported.
- `source.sync.out-is-the-exporters` — writing outputs as the work goes on is the exporter's
  continuous export (#4640), fed by this model; no second export path exists.

## Test matrix

To be filled at approval.

## Open questions

See `source-model.md`.
