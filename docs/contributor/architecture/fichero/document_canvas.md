(AI generated. Not reviewed.)

# Document Canvas — unified viewer + editor (image AND PDF)

> Status: **design / wireframe approved** (Daniel, 2026-05-31). Supersedes the
> three parallel zoom wrappers. Drives the re-scope of #1402, #1383, #1420.

## Problem

There are **three parallel zoom/viewer wrappers**, and the editor diverged from
the viewer instead of building on it:

| Wrapper | File | Used by |
|---|---|---|
| `ZoomableImagePreview` | `Views/Library/ImageViewerComponents.swift` | the real image viewer (has loupe + magnifier) |
| `ZoomableImageView` | `Views/Library/EditorView.swift` | older editor |
| `ZoomableNSImageView` | `Views/Library/ImageViewer/ZoomableNSImageView.swift` (branch) | new editor (#1383 attempt) |

Result (the bug behind #1383/#1420): in the **editor**, the viewer's
magnifier / loupe / scroll-zoom appear "gone" — because the editor doesn't use
them. Nothing was deleted; the editor just went its own way.

PDFs are a *fourth* world: `PDFLoupeOverlay` + `PDFView`, separate from images.

## Principle

**Augment the existing viewer stack with editing — do not replace it.** One
canvas serves plain preview, the folder page view, AND editing, for BOTH images
and PDFs. Zoom / loupe / magnifier are always present (view and edit). Editing
is a set of **overlays on the same canvas** plus an **inspector edit tab**.

## Target architecture

```
                    DocumentCanvas      ← ONE entry point (folds the 3+ wrappers in)
   ┌──────────────────────────┬───────────────────────────┬────────────────────────┐
   │ FOUNDATION (reused as-is) │ CONTENT (per type)         │ EDIT LAYER (overlays)  │
   │ • ZoomableImagePreview    │ • image → TrackingImageView│ • CropOverlay          │
   │   (NSScrollView magnify)  │ • pdf   → PDFView page      │ • RotateHandle         │
   │ • MagnifierPanelView      │   both share the same       │ • EditChainModel (#469)│
   │ • PDFLoupeOverlay         │   zoom / loupe / magnifier  │ • EditsInspectorTab    │
   │ • ScrollWheelZoom         │                             │ • ImageEditingService  │
   │ • ImageZoomToolbar        │                             │                        │
   └──────────────────────────┴───────────────────────────┴────────────────────────┘
```

- **Retire** `ZoomableImageView` (EditorView) and `ZoomableNSImageView` into the
  one `DocumentCanvas`. The viewer's `ZoomableImagePreview` is the foundation.
- The plain preview, the folder-page reading surface, and the editor are the
  **same** `DocumentCanvas` with the edit layer toggled off/on.

## Two toolbar levels — each owns its own back/forward

There are **two** toolbars, scoped differently. This is the key structural rule.

### 1. Window toolbar (native macOS titlebar, spans the window)

- **Left, Safari order:** **sidebar toggle first**, *then* browser-style
  **Back / Forward** (`sidebar.left` → `chevron.backward` / `chevron.forward`).
  Back/forward walk the user's **navigation history** — every selection visited
  (doc → folder → other doc → back). Window-scoped, always present.
- **Right:** search + inspector toggle, the `＋` add menu, etc.
- Driven by a `NavigationHistoryStore` (stack of visited selections: doc id,
  folder id, view mode, restorable scroll/zoom). Safari/Finder semantics:
  visiting a new item truncates the forward stack; back/forward don't push new
  entries.

### 2. Document toolbar (owned by the open document / canvas)

Appears because a document is open; scoped to *that* document.

- **Page Back / Forward** `◀ N/M ▶` — navigate **within the current document**
  (page-to-page). NOT history; distinct from the window back/forward.
- Undo / Redo, Original ⇄ Edited compare, and the **edit-tool glyphs**
  (crop/rotate/enhance/remove-bg/split).

> Never conflate the two: window back/forward = *where you've been across the
> library*; document `◀ ▶` = *which page of this document*.

## Iconography — SF Symbols, not words

**All toolbar controls are icon-only SF Symbols**; the text label is the
tooltip/hover help and the accessibility label, never inline text.

| Action | SF Symbol (candidate) |
|---|---|
| Back / Forward | `chevron.backward` / `chevron.forward` |
| Undo / Redo | `arrow.uturn.backward` / `arrow.uturn.forward` |
| Original ⇄ Edited | segmented, or `rectangle.righthalf.inset.filled.arrow.right` |
| Crop | `crop` |
| Rotate | `rotate.right` / `rotate.left` |
| Enhance | `wand.and.stars` |
| Remove background | `person.and.background.dotted` (or `rectangle.dashed`) |
| Split / Segment | `square.split.2x1` / `square.split.bottomrightquarter` |
| Loupe | `magnifyingglass` |
| Magnifier panel | `rectangle.and.text.magnifyingglass` |
| Zoom in / out | `plus.magnifyingglass` / `minus.magnifyingglass` |

## Interaction model

- **Both entry points, one model** (approved): the **top toolbar** AND the
  inspector **✎ Edits** tab both invoke tools; both drive a single
  `EditChainModel`. Toolbar = quick start; inspector = the chain (reorder,
  toggle each step ●/○, adjust each step's settings).
- **Bidirectional overlay ⇄ inspector**: selecting an edit step in the inspector
  activates/selects its overlay on the canvas for in-place adjustment, and
  selecting an overlay on the canvas highlights its step in the inspector. Same
  selection, two surfaces.
- **Original ⇄ Edited** toggle stays.

## Tool applicability (image vs PDF — be honest)

| Tool | Image | PDF |
|---|---|---|
| Rotate | ✅ raster transform | ✅ page transform |
| Crop | ✅ | ✅ (cropbox) |
| Enhance (contrast/denoise/sharpen) | ✅ | ⚠️ raster-only → applies to a rasterized page render / page-image |
| Remove background | ✅ | ⚠️ raster-only → same |
| Despeckle (`fuzzy_clean` op) | ✅ raster despeckle | ⚠️ raster-only |
| Split / Segment / Recombine | ✅ | ✅ (page ops) |

Universal tools (Rotate, Crop, Split) act on both natively. Raster tools on a
PDF operate on a rasterized render of the page (or its stored page-image), not
vector text — surface this in the UI so the user knows what an edit produces.

> **Despeckle ≠ Clean Up Text.** The image **Despeckle** step (backend op
> `fuzzy_clean`, `workflows/tools/fuzzy_clean_images.apply_fuzzy_clean`) is a
> raster noise/speckle filter. It is unrelated to the text/OCR `clean_text`
> tool (#1462/#284), which operates on transcribed text, not pixels. The image
> op is surfaced in the UI as "Despeckle" to avoid that confusion (#1534).

## Re-scope of the issues

- **#1402** — becomes "introduce `DocumentCanvas`: one canvas for image + PDF,
  built on the existing viewer stack; retire the duplicate wrappers." The
  foundational refactor; everything else builds on it.
- **#1383** — "editor reuses the existing magnifier/loupe/zoom via
  `DocumentCanvas`" (not a new wrapper). Falls out of #1402 for free.
- **#1420** — "Photos-style edit layer: toolbar + inspector both drive one
  `EditChainModel`; bidirectional overlay⇄inspector; adjustable, chainable
  steps." Sits on top of #1402.

Build order: **#1402 (canvas) → #1383 (loupe/zoom in editor, now free) →
#1420 (edit layer + chain)**.
