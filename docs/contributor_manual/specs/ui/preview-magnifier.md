# Preview Magnifier (Loupe) — Design Spec

> Milestone: preview-magnifier
> Manual: TBD — a "Magnifying a source" section for the reading/transcribing part: how to summon
> the loupe, park it, resize it, change magnification, and what ⌥ does.

> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass.
> Status: DRAFT.
> Tags: **[OK]** built · **[GAP]** intended, never built · **[BROKEN]** code contradicts the line.

## Intent (the design)

The magnifier is a **reading instrument on a source**, not a window feature. A palaeographer
working a hard hand needs to enlarge a patch of ink without losing their place in the page: the
loupe sits where you leave it, follows only when asked, and says what magnification it is at.

Split from `panes-workspaces` (creative-director, 2026-09-17): "magnifiers for preview image
editor… that's in preview, source. not really workspaces, other than they should sync." This spec
owns the instrument; [[panes-workspaces]] owns only how loupe state behaves across MORE THAN ONE
pane (`panes.magnifier.per-pane-open-state`, `panes.zoom.sync-across-panes`).

## Behaviors

- `magnifier.parks-where-left` **[PARTIAL]** (implemented, unpinned; #4806) — the loupe stays where you put it and does not ride the
  cursor; ⌥-click parks it at the click. (Daniel, 2026-09-01: "it should live where you leave it".)
  `TrackingImageView.swift`.
- `magnifier.option-summons-transient` **[PARTIAL]** (implemented, unpinned; #4806) — holding ⌥ alone summons a transient loupe while
  the toggled loupe is off; releasing dismisses it. ⌥ must be the SOLE modifier — a ⌘⌥ chord is a
  keyboard shortcut, not a loupe request (fixed 2026-09-16: ⌘⌥1 was popping the loupe).
  `ZoomableImagePreviewMac.installOptionLoupeMonitor`.
- `magnifier.follows-only-while-option` **[PARTIAL]** (implemented, unpinned; #4806) — a parked loupe follows the pointer only while
  ⌥ is held and it is unlocked; otherwise it holds position. `TrackingImageView.mouseMoved`.
- `magnifier.lockable` **[PARTIAL]** (implemented, unpinned; #4806) — the loupe can be locked so it ignores follow entirely, with a
  lock badge drawn on it. ⌘⌥M toggles the lock.
- `magnifier.scroll-adjusts-magnification` **[PARTIAL]** (implemented, unpinned; #4806) — scrolling OVER a parked loupe changes its
  magnification; scrolling anywhere else pans the page. Bounded by `MagnifierLimits`.
- `magnifier.edge-resize` **[PARTIAL]** (implemented, unpinned; #4806) — dragging the loupe's edge resizes it; dragging its middle
  moves what it looks at along with it.
- `magnifier.states-its-power` **[PARTIAL]** (implemented, unpinned; #4806) — the loupe shows a `N.Nx · NNNpx` badge so magnification
  is never guessed.
- `magnifier.right-click-dismiss` **[PARTIAL]** (implemented, unpinned; #4806) — right-clicking a placed loupe removes it.
- `magnifier.follow-mouse-bar` **[GAP]** (#4716) — a bottom magnifier BAR that tracks the pointer and
  magnifies the strip under it (distinct from the round loupe), for scanning a line of text.
- `magnifier.per-source-memory` **[GAP]** (#4717) — a source remembers its loupe size/magnification, so
  returning to a hand you were working resumes where you were.
- `magnifier.pdf-viewer-has-the-loupe-too` **[GAP]** (#2419, redirected from the legacy
  "Reader View - Page" milestone while folding `reader-view.md`'s pass 2) the PDF viewer
  should offer the same loupe the image viewer already has, with its summoning control at the
  BOTTOM of the PDF view — this spec's behaviors above are all read against the image-viewer
  loupe; not verified whether any apply to the PDF viewer already, or whether it has none at
  all.

## Test matrix

| Behavior | Test | State |
|---|---|---|
| option-summons-transient (⌥ sole modifier) | `MenuShortcutUniquenessTests` (chord uniqueness) | ⚠ partial — needs a direct modifier test |
| parks-where-left / follows-only-while-option | — | ❌ |
| lockable / scroll-adjusts / edge-resize | — | ❌ |
| states-its-power | — | ❌ |
| follow-mouse-bar | — | ❌ [GAP] |
| per-source-memory | — | ❌ [GAP] |

## Open questions

1. Does the magnifier belong to the **source** or to the **rendition**? A deskewed rendition and
   the base page are different pixels — does the loupe follow the source across renditions?
2. Is the bottom magnifier BAR (`follow-mouse-bar`) still wanted, given the parked loupe works?
3. Should magnification be absolute (3.0x) or relative to the page's current zoom?

## References

- `fichero/fichero/Views/Preview/ImageViewer/TrackingImageView.swift` (parking, follow, resize, badge)
- `fichero/fichero/Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift` (⌥ monitor, transient loupe)
- `fichero/fichero/App/Menus/ImagePreviewMenuCommands.swift` (⌘⌥L toggle, ⌘⌥M lock, zoom in/out)
- Cross-pane behavior: [[panes-workspaces]] §B
