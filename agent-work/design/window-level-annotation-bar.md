# The annotation bar is window-level, and annotates anything

**Status:** ruled by Daniel 2026-08-30 (lunchtime), first cut implemented.
**Model:** Preview.app — pencil in the toolbar (with the highlight-style
chevron), markup bar slides in BELOW the toolbar, ABOVE the workflow bar.

## The ruling (paraphrased)

Annotation is not a property of the preview image. You might annotate an
image, a PDF, the reader's text, an entity, an artifact, even a file — or
rows in library view or data-entry view. Star anything. Select, marquee —
marquee parts of an image and make new nodes from them. So the bar lives at
the WINDOW level: toolbar pencil toggles it on and off, exactly Preview.app's
grammar; the bar appears under the toolbar, over the workflow bar, and its
verbs act on whatever surface has focus.

## What exists after the first cut (2026-08-30)

- `AnnotationBar` (Views/Shell/Toolbar/): window-level bar hosting the
  markup verbs — select ⬚, draw-region ▭, line, highlight (split button,
  five colors + underline/strikethrough), text note, star, delete, combine.
  Mounted as a detail-column top safe-area inset above the workflow bar
  (`ContentView+RootLayout`), toggled by `@SceneStorage("showAnnotationBar")`.
- Toolbar pencil `ContentToolbarID.annotationBar`: pencil toggles the bar
  (accent while on); `PreviewHighlightStyleMenu` chevron picks the style,
  shared storage with the bar's split button.
- The preview PANE HEAD's tools slot is retired (the machinery in PaneHead
  stays for other panes); the two-row head fix (constant two-state height,
  explicit HStack) remains for any future tools row.
- Verbs travel as the existing notifications (`.previewAnnotateTool`,
  `.previewRegionVerb`). Consumers today: the image and PDF canvases
  (highlight, note, star→bookmark). `select`/`drawRegion` arm the
  preview-regions interactions; `line` awaits a drawing kind.

## The road it opens (not built yet)

- Reader text: highlight/underline/strikethrough over the WebKit
  transcript, persisting as span annotations (charStart/charEnd exist on
  addNote already).
- Rows and entities: star/note on a library row, a dataset row, an entity,
  an artifact — AnnotationScope already models document/page scopes; a
  node-scoped bookmark is the natural first.
- Marquee-anywhere: the marquee seam is per-window
  (`WindowState.previewMarquees`); "marquee parts of an image, then make
  new nodes" already works in preview — other surfaces adopt the same seam.
- The bar should eventually reflect the FOCUSED surface's capabilities
  (grey the verbs a surface cannot answer) — today it posts and surfaces
  that cannot answer ignore, which is honest but silent.
