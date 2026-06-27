# Worker Report — `lane/archdocs`

**Worker:** Claude (opus) · **Date:** 2026-06-27 · **Branch:** `lane/archdocs`
**Task:** Review the architecture + audit docs (SwiftUI + API) for accuracy vs code,
audit-incorporation, consolidation, and placement. Execute safe placement moves; flag
ambiguous/cross-lane ones; file issues for untracked findings.

## What I did

1. **Read & classified all 22 docs** in `docs/architecture/swiftui/` + `docs/architecture/api/`
   plus the 2 sibling top-level audits (`api_consistency_audit`, `search_audit`).
2. **Verified claims against current code** via jcodemunch (`local/fichero-29aa4eed`) and
   issue/milestone state via `gh`. Key confirmations:
   - `observable_data_layer.md` is **implemented** (EntityStore/ClaimStore/LibraryChangeStream/
     change_stream.py/emit_change all exist; #1863 + #1851 CLOSED).
   - `reform_masterplan` spot-checks hold (`_DEV_ROUTE_SPECS == []`, `.inspector()` adopted,
     #2031/#2032/#2033 CLOSED).
   - `api_consistency_audit` recommendations all CLOSED (#1412–#1417, #1710).
   - `notes_annotations_audit` shipped (#1759 CLOSED).
3. **Filed 1 issue** — **#2709** (search index canonicalization), the only finding not
   already covered by an open issue.
4. **Executed 3 archive moves** (`git mv` into existing `docs/archive/`) for fully-historical
   audits with zero inbound links, each with an `ARCHIVED` provenance banner.
5. **Flagged 3 cross-lane / ambiguous decisions** for Daniel (see ARCHDOCS-REVIEW.md):
   promoting durable principles to the public site (lane/docs territory), archiving
   `mac_shell_design_proposal` (needs ROADMAP edit — lane/review), and the canonical
   docs-vs-site-mirror split.
6. **Wrote** `ARCHDOCS-REVIEW.md` (full per-doc table + analysis) + this report.

## Why so few moves / issues (ponytail + coordination)

- Sibling lanes are actively restructuring docs: **lane/docs** owns `site/docs/**`
  (`developer→contributor` rename), **lane/review** owns governance/structure. Writing into
  `site/docs/` or editing `ROADMAP.md` from here would collide. I confined moves to
  unambiguous, zero-link, in-lane archives and **flagged** the cross-lane ones.
- Most audit findings are already implemented or tracked; filing more issues would just be
  duplicate noise. Verified net-new before filing (only #2709 qualified).

## Outputs
- `ARCHDOCS-REVIEW.md` — per-doc review table, issues, moves, flags, overall recommendation.
- `WORKER-REPORT.md` — this file.
- Issue **#2709** filed on the `Search` milestone.
- 3 docs archived under `docs/archive/`.

## Verification
- `mkdocs build --strict` **not run** — no `site/docs/` files were touched (moves stayed in
  internal `docs/`, which is never published).
- jcodemunch lookups used the canonical indexed repo (worktree itself unindexed); code is
  unchanged on this branch, so symbol existence is authoritative.

## Handoff / next
- Daniel decides the 3 flagged items (esp. promoting PRINCIPLES/standards to the public site
  — highest value, but lane/docs' to execute).
- When #1859 (mac-assed) and the ROADMAP link for `mac_shell_design_proposal` resolve, those
  two follow into `docs/archive/`.
- Commit authored as Claude, **not pushed** (per brief).
