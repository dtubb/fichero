# Generated capability reference in the user manual

2026-08-29. How the generated workflow/tool reference sits inside the manuscript
flow, where screenshots would attach, and what still needs a decision.

## What exists now

`scripts/generate_capability_reference.py` reads the engine — the tool registry
(`list_executable_tools()`), the shipped presets in
`resources/default_workflows/*.json`, and the folder taxonomy in
`resources/workflow_folders.json` — and writes markdown under
`docs/user/reference/`: one page per tool (126), one per workflow (51), plus
three index pages. Every page states what the step reads and emits, every option
with its default, and the FULL prompt resolved through the tool's own
`prompt_builder` with the config that step actually runs. Workflow pages resolve
each node's prompt through the same builders, so a preset page and a tool page
can never disagree about what the model is asked.

The mkdocs `nav` entries are generated into `mkdocs.yml` between marker comments
by the same script, and `scripts/check_capability_reference_current.py`
regenerates into a temp dir and fails when the committed pages or that nav block
have drifted.

## How it feeds the .docx manuscript

The manuscript direction is docx → markdown → pages
(`scripts/sync_manuscript.py`: pandoc the edited `.docx`, split H2 chapters into
`docs/user/guide/NN-slug.md`). The reference runs the other way — engine →
markdown — so the two must not collide. They do not, because they own different
directories: the manuscript owns `docs/user/guide/`, the generator owns
`docs/user/reference/` and nothing else. Nobody hand-edits a reference page; the
banner at the top of each says so.

For the Word/PDF manual, the reference becomes a back-of-book appendix rather
than a chapter Daniel edits. The build is a pandoc concatenation in a fixed
order: the manuscript chapters first, then `docs/user/reference/index.md`,
`workflows/index.md` and the workflow pages, then `tools/index.md` and the tool
pages. Because the generated markdown is plain (headings, tables, fenced code)
it converts cleanly, and because the ordering is deterministic the appendix
diffs the same way the site does. That appendix build script does not exist yet
— it is the next small step, and it belongs beside `sync_manuscript.py`.

The prose voice question resolves the same way: the manuscript carries the
narrative ("here is how you transcribe a page"), the appendix carries the
specification ("here is exactly what Transcribe asks the model"). A reader who
wants to reason about a prompt turns to the back.

## Where annotated screenshots hook in (Mellel-style)

The aspiration is the Mellel guide: a numbered callout on a screenshot beside
the text explaining it. Screenshots are a later phase, but the hook is cheap to
leave open now:

- `sync_manuscript.py` already places extracted images into
  `docs/assets/users/` and rewrites references page-relative. Reference-page
  screenshots would use the same folder with a predictable name —
  `docs/assets/users/tool-<tool_name>.png`,
  `docs/assets/users/workflow-<slug>.png`.
- The generator can emit an image reference only when that file exists, so a
  screenshot appears in the manual the moment someone drops it in, and no page
  ever renders a broken image. That is a few lines in `tool_page()` /
  `workflow_page()`, deliberately not written yet.
- Annotations (numbered callouts) are baked into the PNG by whatever captures
  it, not layered in markdown — markdown callouts would not survive the docx
  conversion.

## Open questions for Daniel

1. **Site or appendix only?** 180 generated pages roughly triples the User
   Guide's nav. The alternative is publishing them on the site but keeping them
   out of the printed manual, or the reverse. Right now they are in both.
2. **Untested tools.** Only the HTR transcription chain is marked
   `tested=True`; every other tool's page says "Verified end to end: no". That
   is honest, and it is also 125 pages of "no" in a user manual. Keep it, soften
   the wording, or hide the row until more tools are verified?
3. **Prompt length.** Some prompts run to a page of text. In the printed manual
   that is a lot of monospace. Full text, first N lines with a link, or a
   smaller type size in the pandoc template?
4. **Tool naming.** Pages are keyed by the internal tool id (`clean_text`,
   `text_translate_review`) even though the heading uses the display name. Fine
   for stable URLs; slightly technical for a user manual. Keep ids, or slugify
   the display names and accept that a rename breaks a URL?
5. **The AI-draft badge.** Generated pages carry it, following the docs
   convention. But these pages are never going to be "reviewed into" prose —
   they are regenerated. A different marker ("generated from the app") may serve
   the reader better than the unreviewed badge.
6. **Appendix build.** Confirm the pandoc appendix order above before the script
   is written, and whether the appendix goes into the same `.docx` master or
   ships as a separate reference PDF.
