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

8. **Rubber-band run** (late addition): drag a marquee over part of the
   image and run a workflow on JUST that crop — Preview.app's selection
   rectangle as the model (his Mellel-guide screenshots). This is the
   region story's input end: rubber-band → region node → the bar's verbs
   scope to it.
9. **Top-right lens icons** (late addition): Preview's pane head gets
   region-overlay and renditions toggles as compact icons, the way the
   reader's head carries its lenses — instead of the bottom bar's menus.

## Open questions for Daniel
1. Renditions flip + page arrows: top or bottom? (Sketch says bottom.)
2. Is "Annotate" a lens in the existing header selector, or a toggle in the
   top cluster?
3. Combine-regions semantics: union bbox + concatenated text, or keep
   originals and add a grouping parent?
