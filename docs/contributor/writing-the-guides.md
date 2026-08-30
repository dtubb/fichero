# Writing the Guides

The user and contributor guides are written in **markdown, in this
repository** — the files are the master copies. The Word manual and the
documentation site are both built from them.

## Where the words live

- **User Guide chapters:** `docs/user/guide/NN-slug.md` — one chapter per
  file, ordered by the `NN-` prefix, each starting with a single `# Title`.
- **Contributor pages:** `docs/contributor/*.md`.
- **Images:** `docs/assets/users/` (user guide) and
  `docs/assets/contributor/`, referenced page-relative, e.g.
  `![The library window](../../assets/users/03-library-window.png)`.
- **Generated reference** (`docs/user/reference/`): built from the app by
  `scripts/generate_capability_reference.py`. Never hand-edited — the
  banner on each page says so.

## Editing in Scrivener

Point Scrivener's **Sync with External Folder** at `docs/user/guide/` with
plain-text/markdown sync. Scrivener edits land as changes to the same
files; commit them like any other change. Keep the sync set to markdown
(not RTF), keep one chapter per document, and let the `NN-` file names
carry the order.

## Editing anywhere else

The files are ordinary markdown — edit them in any editor, or let an agent
draft into them. Pages carrying the `> 🤖 *AI Drafted (Not reviewed)*`
badge have not been human-reviewed; delete the badge when a page has been
made your own.

## Building the outputs

- **Site:** `mkdocs build --strict` (gated by
  `scripts/check_docs_publication.py`; a new chapter needs a `mkdocs.yml`
  nav line).
- **Word manual:** `python3 scripts/build_manual_appendix.py` concatenates
  the guide chapters plus the generated reference (prompts in small type)
  into `Fichero User Guide with Reference.docx` in the Drive folder. The
  `.docx` is an output — never edit it expecting the words to survive.
