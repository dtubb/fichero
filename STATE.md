# STATE.md — Fichero

Last updated: 2026-03-25

## Current Branch

`main` — clean. All direct commits pushed.

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5

## Completed This Session (2026-03-25)

- Merged PRs #329, #331, #333, #336 to main
- Fixed dangling FolderContentsGrid.swift pbxproj reference (build fix)
- Wired typography settings (@AppStorage) to inspector text editor (#324)
- Fixed Apple Vision OCR for PDFs (renders pages to CGImage via CGPDFDocument)
- Added thinking mode (off/short/medium/long) to workflow BASE_CONFIG_SCHEMA
- Enabled describe + rewrite workflow tools for 0.0.1 (release profile v21)
- Fixed icon view default scale 3.0 → 1.0
- Created FolderContentsGrid for folder preview in EditorView (#327)
- Fixed batch execute SSE content type mismatch (raw URLRequest bypass)
- Mounted settings router — AI Defaults endpoint now accessible
- Created issues #339-#344 for new features

## Blocked

- Developer ID Application certificate (notarization)
- Notarytool credentials
- Sparkle key pair

## Open 0.0.1 Issues

- **#326** — Keyboard shortcuts
- **#330** — Icon view: remember column width, fix first-run jump
- **#340** — Prompt preview panel (workflow node editor)
- **#341** — CLI agent provider (Claude, Codex, Gemini)
- **#344** — Thinking mode selector UI in workflow node config
- **#313** — Connection/API error state UI (PR #334 created but not merged)

## Next Session — Start Here

1. **Merge remaining PRs** — #334 (connection banner), #335 (image centering), #337, #338 may have conflicts from direct main commits. Rebase or recreate.
2. **#330** — Icon view still jumps on first click / view switch. Debug the `iconViewScale` reset.
3. **#326** — Keyboard shortcuts verification (needs running app).
4. **#344** — Add thinking mode Picker to workflow node config UI.
5. **#313** — Merge connection banner PR or rebase it.
