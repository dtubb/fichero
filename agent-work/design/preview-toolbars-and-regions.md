# Preview: two Golden-Gate toolbars, regions as first-class, annotations at the top

**Status:** design brief, AWAITING DANIEL — then a worker lane
**Date:** 2026-08-29 (late), from Daniel's live-testing rulings
**Surfaces:** Preview pane only. Preview/Reader/Inspector stay three surfaces.

## Daniel's rulings (paraphrased)

1. **Regions need selection and deletion in Preview.** Today regions render
   as overlay boxes but cannot be selected as objects, and cannot be deleted.
   Five regions picked in the attribute browser also cannot be combined —
   region curation has no verbs anywhere.
2. **Two mini-toolbars, not one full-width bottom bar.** A top bar and a
   bottom bar, both in the Tahoe/Golden-Gate idiom: floating lozenge
   clusters like the pane head, not a chrome strip spanning the pane.
3. **Division of labour:** bottom = navigation and inspection (find,
   metadata, renditions flip, page left/right — though he is unsure whether
   renditions/paging belong top or bottom); top = the mode tools. When you
   enter Edit, its tools already arrive at the top — annotation tools
   (highlight, lines, shapes) should arrive the same way, as a top cluster,
   instead of living behind the bottom bar's "…" overflow menus.
4. **Kill the "…" menus** for zoom / magnifier-bar toggle / annotation
   tools. "I hate that." Zoom stays reachable but must not bury the drawing
   verbs.
5. **The top-header view selector (Preview ∨ / Edit) is good** — keep it as
   the mode switch; annotation mode may simply be part of this grammar.
6. **Swipe conflict:** left/right swipe paging in Preview stops working when
   scroll bars are visible — the scroll view eats the horizontal gesture.
   Any redesign must make paging reliable (explicit page arrows in the
   bottom cluster are the fallback that always works).
7. **Show different regions in Preview somehow** — a region lens/strip, so a
   page's regions can be walked without the reader.

## Proposal sketch (for the worker, after Daniel's yes)

- **Bottom cluster (lozenges, centred):** page ‹ › and count · zoom −/%/+ ·
  find · info/metadata toggle · renditions flip. This is "where am I and
  what am I looking at".
- **Top cluster (appears with mode, like Edit's tools today):** in Preview
  mode nothing extra; pick the annotate lens → highlight / line / shape /
  note tools slide in as a top lozenge row; pick the regions lens → region
  select / combine / delete / renumber verbs slide in the same way. "The
  tools come to you when the mode needs them."
- **Regions as selectable objects:** click a region box to select (accent
  stroke), ⇧-click to add, Delete key deletes (with engine-side artifact
  update — persistent curation, import-rule discipline), a Combine verb
  merges selected regions' bboxes + concatenates their texts in reading
  order. Same verbs exposed on the attribute-browser multi-selection.
- **Engine needs:** region delete + region merge endpoints (curation-grade:
  audit trail, soft delete). Check what `resolve-document-text-regions` and
  the artifacts routes already offer before adding anything.

8. **Rubber-band run** (late addition, refined 2026-08-29 ~22:30): the
   marquee is EPHEMERAL first — drawing it persists nothing. Two exits:
   promote to a region node ("New Region"), or run a workflow on the crop
   directly from the bar (the marquee outranks everything in the scope
   ladder; the chip names it "a selection of <page>"). Preview.app's
   selection rectangle is the model.
9. **Top-right lens icons** (late addition): Preview's pane head gets
   region-overlay and renditions toggles as compact icons, the way the
   reader's head carries its lenses — instead of the bottom bar's menus.

## RESOLVED (Daniel, 2026-08-29 ~22:20, Preview.app as the model)
1. **Annotate + Edit arrive at the TOP**: a toggle in the pane head slides a
   tool row out UNDER the head, over the image — exactly Preview.app's
   markup bar. Annotation overlays Preview; it is not a separate mode lens.
   The slide-out row holds: select ⬚, draw-region ▭, line, highlight, text
   note, delete, combine.
2. **Head lenses, reader-style**: region show/hide toggle and the renditions
   menu sit top-right by the breadcrumb (renditions as a menu like the
   reader's transcript/translation menu). Pages ‹ › sit LEFT of the
   breadcrumb.
3. **Bottom bar goes quiet**: filter / find-in-image / metadata /
   what-to-show — the library-bottom grammar. No zoom, no annotation entry,
   no "…" menus.
4. **The magnification FAMILY is one bottom-right floating cluster**
   (follow-up ruling): mini-map on top, zoom pill beneath (− % + · fit ·
   1:1), then two toggles — the LOUPE and the magnifier bar. The loupe
   follows the cursor when on (the draggable window "is not very good"),
   scroll adjusts its power, ⌥ summons it temporarily; the magnifier-bar
   toggle slides the strip up from the bottom edge. Hiding the map
   collapses the cluster to the zoom pill.
5. **Combine = merge destructively**: one region remains (union bbox, texts
   joined in reading order), originals soft-deleted and recoverable through
   curation history.
