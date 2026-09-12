# Writing the Guides

Fichero has three manuals, owned differently. Who writes each one is the rule
that matters — see AGENTS.md "Authorship model" for the canonical statement.

## The three manuals

- **User Guide — `docs/user_manual/`.** The maintainer's. Authored in
  **Tinderbox** and exported to this folder. An agent **never edits the prose**
  here. It contributes two things only: **facts** (so the guide can't disagree
  with the software) and **deterministic screenshots** (below).
- **Contributor Guide — `docs/contributor_manual/*.md`.** AI-authored markdown —
  agents draft and revise these pages directly. This file lives here.
- **Reference — `docs/reference_manual/`.** Code-generated, never hand-edited:
  - `scripts/generate_capability_reference.py` → `docs/reference_manual/tool_references/`
  - `scripts/gen_feature_tiers.py` → `docs/reference_manual/features.md`
  Each generated page carries a banner saying so. Fix the generator, not the page.

## Screenshots

Screenshots are captured **deterministically** — Xcode `RenderPreview` or the
`.xctestplan` screenshot capture from a UI-test run (capture, not pixel-diff).
Store them under `docs/assets/<milestone>/` (subfolder named for the
spec feature / milestone) and reference them page-relative, e.g.
`![The library window](../../assets/<milestone>/library-window.png)`.

## Building the site

`mkdocs build --strict`, gated by `scripts/check_docs_publication.py`. A new
page needs a `mkdocs.yml` nav line.
