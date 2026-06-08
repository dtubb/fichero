# Demo punch-list — friend demo @ 1pm, June 8
Library: Demo.fichero (IIIF import of marshall 1923, English, no re-transcribe)

## P0 — demo happy-path (open lib → page → image+transcript → KG → entities → timeline/map)
- [ ] DATA: IIIF import + English KG (in progress)
- [ ] Blank image until you click something (reading surface render)
- [ ] Selecting a file in 2D/3D view updates the inspector
- [ ] Inspector tab order: Content, Annotations, Notes, KG, Outline, Entities, Attributes, Info
- [ ] Entity browser in sidebar broken → library → entity in inspector

## P1 — sidebar IA cleanup (look intentional)
- [ ] Hide Mind Palace (dropped as separate-from-library-folder)
- [ ] Batches in sidebar is wrong (remove/fix)
- [ ] Entities + Research: keep sidebar visible, use library/workspace view (like workflows/batches/activity), not content-replacing modes

## P1 — KG showcase
- [ ] SVO: click verb AND object in inspector to edit
- [ ] Events show in WebKit timeline
- [ ] Map (WebKit) shows places mentioned (infer country from docs)

## P2 — if time
- [ ] 3D library view: default GRID not circle; layout saves (existing issue)

## NEW (live QA, batch 2)
- [ ] Delete option (alongside Reject) — entity + claim  [LANE: curation]
- [ ] Context menu broken on multi-select; context-menu Merge doesn't fire  [LANE: curation]
- [ ] Entity edit/rename + Add entity (create missing place)  [LANE: curation]
- [ ] Events in WebKit timeline  [LANE: webkit]
- [ ] Map of places (infer Colombia)  [LANE: webkit]
- [ ] Excluded-from-processing: grey (not blue) + "Excluded" badge + greyed preview in library view  [LANE: reading]
- [ ] Exclude = also hide from parent library output + search + KG (not just processing)  [LANE: reading/backend]
- [ ] Click entity → library shows docs mentioning it (entity-as-filter)  [stretch]
- [ ] Entity source-count shown consistently/correctly (some have 3 sources)  [LANE: curation/density]
- [ ] Entity lozenges = text-width, flow into rows (info-dense), not full-width  [LANE: curation/density]

## NEW (search list view, batch 3)
- [ ] Search results: excerpt = the RELEVANT matching snippet (highlight query context), not page's first content line. Backend returns match span/passage.  [LANE: search]
- [ ] Search list: entity panel updates to the RESULTS' entities (not whole-library 1546)  [LANE: search]
- [ ] Relevance label → move right + clarify meaning; title (filename) kept but de-emphasized  [LANE: search]
- [ ] Search relevance: hybrid ranking — boost EXACT/keyword matches above semantic neighbours (andagueda→Andagoya ranked #1 w/o literal term)  [LANE: search/backend]

## DATA QUALITY (deep — post-demo, entity-detail rework sidesteps for demo)
- [ ] SVO claims are Spanish + heavily duplicated → set SVO/claim extractor model to CLAUDE HAIKU (Apple Vision/on-device ignores 'write in English'); dedupe claims; re-extract.
- [ ] Entity detail for a PLACE should be "mentioned on [date]" not fabricated subject-statements (LANE entitydetail in progress).
