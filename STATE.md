# STATE.md — Fichero

Last updated: 2026-03-23

## Current Branch

`main` — 14 uncommitted files (UI fixes + feature enablement, not yet committed)

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5

## Completed This Session

- **#319** — Workflows + Activity sidebar enabled; transcribe, catalogue, extract_entities tools wired
- **#318** — Inspector: ruler visible by default, checksum/mime type hidden, file size in MB
- **#317** — Image viewer: fit-to-window default, lighter background, overlay scrollbars, centering (in progress)
- Inspector sidebar toggle fixed (no longer hides left sidebar)
- Icon view defaults to 1 column wide (scale 3.0)
- Focus bars fade out after 2s (Tinderbox-style)
- Tab title shows current sidebar mode name (Library, Search, Workflows, etc.)
- Search bar only shows in search mode (not always centered in toolbar)
- Inspector minimum width increased to 250 (matches sidebar)
- Backend routes added: workflow-execution, batch, activity
- Batches, providers/models settings enabled for 0.0.1
- Feature profile bumped to v20
- Peekaboo MCP configured with local Homebrew binary
- GitHub issues created: #322-#327

## Blocked

- Developer ID Application certificate (notarization)
- Notarytool credentials
- Sparkle key pair
- **#322** — Image centering still not fully working (contentInsets approach, needs visual verification)

## Next Session — Start Here

1. **Commit changes** — 14 dirty files on main. Review diff and commit in logical chunks.
2. **#322** — Image centering: verify current contentInsets approach works. If not, try NSClipView centering or wrap image in a container view.
3. **#324** — Settings: default font, font size, margins with reset button.
4. **#327** — Folder preview: show folder contents grid instead of file preview.
5. **#326** — Keyboard shortcuts: verify all navigation shortcuts work end-to-end.
