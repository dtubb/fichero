# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — Inspector V2 shipped (Phase 1 + 2). V1 inspector removed. Catalogue + Transcribe stable. Sidebar drag asymmetry filed as #711 for a focused follow-up session.

**Goal:** Land #711 (sidebar drag unification), then ship 0.0.2 (DMG, signing, release notes already in `CHANGELOG.md`).

## Open Issues (0.0.2 milestone)

| # | Title | Status |
|---|---|---|
| #711 | Sidebar drag: unify icon/text + row-body via `.draggable` Transferable | Diagnosed, ready to fix |
| #598 | Sidebar drop routes to selected row, not cursor target | Subsumed by #711 |
| #702 | Drop-target type matrix — reject folder→PDF, show insertion lines | Subsumed by #711 |
| #661 | Fichero download page on tubb.ca | Ready to do |
| #662 | tubb.ca/fichero release notes + download | Ready to do |
| #658 | fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build + sign + notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #665 | Dev blog post — 3 years AI coding | Content filing only |

## Open Issues (0.0.3 milestone — deferred test gaps from this session)

- **#707** per-page Artifact propagation test
- **#708** workflow stream `cached: true` field test
- **#709** AppDatabase RLock concurrency stress test
- **#710** ArtifactPanel RTF encode/decode round-trip test
- **#706** user-defined attribute schema (RTF/SVG/list/date payload types)

## Next Session — Start Here

1. **#711 — sidebar drag unification.** Use the prompt I wrote at the end of last session: read #711, #598, #702, the `feedback_list_selection_vs_tapgesture` and `feedback_dropdestination_stacking` memories. Migrate sidebar from `.onDrag(NSItemProvider)` to `.draggable(item.id)` + `.dropDestination(for: String.self)`. Verify #612 click reliability and #645 icon/text clicks still work. Test grab from icon, text, and row body all route to the cursor target.

2. **Smoke-test V2 inspector after #711 lands.** Daniel will reproduce the drop scenarios from #598 and #702 to confirm. Also re-test ruler / find-bar (⌃⌘R, ⌘F) end-to-end.

3. **Release pipeline** if #711 ships clean — start with #661/#662 (site content), then #658/#659 (DMG).

---

*Last updated: 2026-04-27* — session-end after Inspector V2 Phase 2 + ruler/find menu + V1 removal + sidebar drag diagnosis.
