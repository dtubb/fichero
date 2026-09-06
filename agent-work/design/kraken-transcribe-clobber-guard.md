# Kraken transcribe clobbers good page_content — guard decision

**Date:** 2026-09-06
**Status:** PARKED — awaiting Daniel (design call). No code changed.
**For:** Daniel (return decision, alongside review-on-mlx-contract-fork.md)
**Owner context:** backend lane (owns the Kraken vision seam, 0e4f7dfb7).

---

## 0. One paragraph

Running "Transcribe (Kraken)" on a page that already has good text overwrites
that text in place with McCATMuS output. On the Istmina Demo the eval lane saw
it replace 2 pages of clean Spanish with near-noise (McCATMuS on Spanish court
hand is close to garbage); they restored the pages from source. McCATMuS being
low-quality here is not a bug to fix in the model — it is a reason the Kraken
path must not be allowed to destroy existing content. The guard that already
protects human edits does NOT cover machine-written content, so the clobber
ships in the DMG unless we add one. This violates "curation persists" and
"prefer raise over silent fallback".

## 1. Root cause (verified in the integration worktree)

- The Kraken recognition seam (`vision_base.py`, `vision_mode="kraken"` branch)
  sets `text = result.text` and persists through the shared
  `save_artifact` seam with `TOOL_CONFIG.update_page_content=True` (the
  `transcribe` tool's config).
- `save_artifact` / `_save_artifact_sync` (`llm_base.py` ~686–726) promotes the
  artifact content into `Document.page_content` whenever
  `update_page_content and not page_content_is_user_edited(doc)`.
- `page_content_is_user_edited` (`curation_guard.py:263`) returns True ONLY when
  `metadata[PAGE_CONTENT_USER_EDITED_KEY]` is set — i.e. a human saved an edit.
- **The gap:** a page whose good text came from a prior *machine* pass (an
  earlier LLM transcription, or ingest-extracted text) carries NO user-edited
  flag, so the guard returns False and the Kraken output overwrites it. Existing
  non-empty content is not considered — only human-edited content is protected.
- This is the SAME write path for both the old economy_htr Kraken preset and the
  new Option-A seam, so the new seam carries the identical clobber risk.

Note this is intentional for the *trusted* LLM `transcribe` path (re-running
transcription is meant to improve a page). The problem is specific to the
LOW-CONFIDENCE Kraken/McCATMuS recognizer using that same overwrite policy.

## 2. Options

- **A — artifact always, promote to page_content only when it is empty
  (recommended).** The Kraken run always saves a `transcription` artifact with
  the recognised text + the baseline-tied `ocr_geometry` (so it is discoverable
  on the Artifacts tab and the geometry work is preserved). It promotes into
  `page_content` only when the page has no content yet. An already-good page
  keeps its text; a fresh page gets the Kraken draft. Matches "curation
  persists"; no data loss; the user can still promote the artifact by hand.
- **B — explicit force flag.** Kraken node defaults to NOT overwriting existing
  `page_content`; a `force_overwrite` config (off by default) is required to
  replace it. Safe by default, but a page with content silently gets no
  page_content update unless the user knows to flip the flag.
- **C — skip-if-present with a message.** If `page_content` is non-empty, skip
  the promotion and report "page already has content; Kraken result saved as an
  artifact only." Effectively A without the promote-if-empty nicety (still saves
  the artifact); simplest, but a first-run empty page also would not auto-fill
  unless we special-case empty (which is just A).

## 3. Recommendation

**A.** It loses no existing text, still captures the Kraken transcript + the
per-line baseline geometry as an artifact, and auto-fills genuinely empty pages
so first-run HTR still "just works". A is the smallest policy that honours
curation-persists while keeping the demo's Kraken-baseline-and-text story.

## 4. What each option touches + test

- **A:** scope the promote-if-empty policy to the KRAKEN path (do NOT change the
  trusted LLM-transcribe overwrite behaviour). Two clean seams:
  - add an option to `save_artifact` / `_save_artifact_sync` (e.g.
    `promote_page_content_only_if_empty: bool`) that gates the
    `doc.page_content = cleaned` promotion on existing content being blank; OR
  - in the `vision_mode="kraken"` branch, read the page's current
    `page_content` and pass a per-call `update_page_content=False` when it is
    non-empty (the artifact still saves).
    The first is reusable and testable in isolation; the second keeps the
    knowledge local to the Kraken seam. Prefer the first.
  - Thread the flag from the Kraken seam only; the `transcribe` LLM path stays
    as-is.
- **B:** a `force_overwrite` key in the Kraken node config + a branch in the
  seam; default off.
- **C:** an emptiness check + a skip message in the seam.
- **Test (for A):** a page with existing non-empty `page_content` + a Kraken
  recognition run → `page_content` UNCHANGED, and a `transcription` artifact with
  the Kraken text + `ocr_geometry` exists; an empty page → `page_content` gets
  the Kraken transcript. (Pins "never clobber existing content, still fill empty
  pages".)

## 5. Live-risk note

This is LIVE until the embedded engine is rebuilt with the new preset AND a
guard lands. The OLD economy_htr Kraken preset is still in the running Dev
Embedded engine and already clobbered 2 Istmina pages (eval restored them). The
new Option-A seam (0e4f7dfb7) ships the same risk into the DMG unless one of the
above lands first. Until then, do not run Transcribe (Kraken) on pages that
already hold good text.
