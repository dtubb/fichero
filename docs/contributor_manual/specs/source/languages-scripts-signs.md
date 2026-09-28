# Source Model — Languages, scripts and signs — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: how to say what
> language and script a passage is in, how writing direction works, and how to work with a
> script or a sign that no computer knows yet.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Every behaviour below is tagged **[GAP]** with its issue; everything
> is design unless the foundation's "What exists today" says otherwise. (Today: language is
> recorded once per document; script only on a reading; no direction anywhere; the detector
> knows English and Spanish.)

## Intent

Fichero should be as useful for a language with ten speakers, a script nobody has encoded,
or a text written in a spiral, as it is for printed English. That means language, script,
direction and the identity of a sign are recorded honestly at every level, and that "the
computer has no character for this" never stops the work.

`historical-text-normalization.md` owns what is *done* with text (normalising, dating,
matching names across scripts, detecting language, translating). This slice owns how
language, script, direction and signs are *recorded*.

## The design

### Three facts, never one field

- **Language** — a BCP 47 tag, *and* a Glottolog code where there is one. They are two
  different systems: Glottolog (open licence; covers dialects and under-resourced and
  Indigenous languages) is not part of BCP 47, so the record holds both, and one spelling of
  each is kept for the whole project. Where no registry knows the language, a private tag
  made in the project, with a name and notes. Other sources can be drawn on beside Glottolog, from an
  open list: Native Land Digital (languages and territories; it asks for attribution and says
  it is not authoritative) and FirstVoices (community-owned language archives, where each
  community governs access) are wanted from the start. "Unknown" and "not yet looked at"
  are different values, as they already are for a document's language today.
- **Script** — ISO 15924, including its honest codes: no writing; undetermined; and the
  private-use codes for a script a project declares itself.
- **Encoding** — whether, and how far, the signs have Unicode characters: fully, partly, or
  not at all. Never assumed. Fichero already measures something close for *models* (how well a
  model's vocabulary covers a script's characters, in four tiers, with an honest "cannot
  tell": `llm/script_coverage.py`, served as language fit). The page-level fact builds on that
  measure and its words; it is not a second one.

One language can use several scripts. One page can hold several of each. A Japanese page
holds Chinese characters and two syllabaries at once.

### It cascades

Language, script and direction are set at any level and **inherited downward** until
overridden: app, project, folder, document (a group of pages), page, region, line, word,
character. The engine already resolves a document's language in one place
(`llm/language_policy.py`); the cascade **extends that resolver**, and the same one resolver
answers for models and guidelines too (`source.resolve.one-cascade` in the models slice).
The merging rule (a child overrides its parent; a loop raises) is the prototype system's. A gloss in Basque inside a Latin page overrides for that gloss only. Every value
shown says where it came from ("from the page"; "set here"). This is the ratified cascade
already recorded in the normalization spec; this is where it lives.

A reading can also state its own language and script, which wins for that reading (a
translation is in another language than the ink).

### Direction

Direction is a property of a segment: left to right; right to left; top to bottom; bottom to
top; **alternating** (each line reverses); **follows the baseline** (a spiral, a seal, a
coastline). For columns and lines there is also the direction in which *they* succeed each
other (vertical columns running right to left). Mixed direction inside one line (Arabic with
numerals) follows the Unicode bidirectional rules, and the stored text is always in reading
order, never in display order.

The Reader lays text out in its direction. Where it cannot lay a direction out as running
text (a spiral), it shows the reading in reading order and shows the shape on the image.

### Signs without characters

**How a declared sign sits inside a reading's text** (default taken; morning file): the text
stays an ordinary string, with a project-minted private-use character standing for the sign,
and the reading carries a small map from position to sign. Search, comparison and every
existing reader of a reading's text keep working; the Reader and the exporters use the map.

A **sign** is the unit of a script. Most signs are Unicode characters. When one is not, it is
a **declared sign**, which needs only:

- a name or label;
- a picture, cut from a real segment on a real page.

and may have: notes; a sound or meaning; **references to sign lists** (the authority and the
number in its list: a catalogue of Maya glyphs, a cuneiform sign list, a project's own); a
private-use code point (MUFI's, where MUFI has one); a description of how it is built from
parts; a font that draws it.

A sign's identity can therefore be "number 561 in this catalogue" with no code point at all.
Unicode is one authority among several.

Declared signs live in a **sign list** owned by a project. A reading's text can mix ordinary
characters and declared signs. A whole unencoded script can be built up this way, sign by
sign, from its own sources: each new sign is declared from the page it was first met on, and
every later instance points to it. The list can be exported and shared, and is the evidence
needed for an encoding proposal.

**Variant forms** of an encoded character (the many forms of one Chinese character; a
long s) are recorded the same way: the character, plus which variant.

### What can be done with declared signs

Everything that can be done with characters: transcribe (pick from the list, or draw a box on
the page and say "this one again"); search (by sign, by catalogue number); compare (all
instances of one sign, side by side, across hands and sources); show (the sign's picture in
line in the Reader where no font has it); export (as TEI's declared glyph elements; elsewhere a
placeholder plus a report of what was substituted); train (a recogniser can learn declared
signs as classes).

### Fonts

Font *files* and which reading needs which are this model's; how text is drawn with them
belongs to the typography work (`histnorm.render.no-bundled-fonts`, #3324, #3315): routed.

The font a reading needs is recorded with it. Fichero ships a few open fonts for scripts the
system lacks, a project can carry its own, and a profile can name the fonts it needs. There
is **an easy way to find a font for a script and add it** to the project (searching the open
font collections by script, showing the licence, one step to add), the same in spirit as
finding a model. If a needed font is missing, Fichero says so and shows sign pictures or a fallback;
it never shows empty boxes without explanation.

### Input

Transcribing an unfamiliar script should not depend on the Mac having a keyboard for it: a
palette of the project's signs and of a script's characters, searchable by name and by
catalogue number, inserts into a reading.

### Side by side

Because language, script, signs and letterforms sit on segments, two sources can be compared
by character: a Japanese page beside a Chinese one; the same sign in two hands; every
instance of one abbreviation in a codex.

## Behaviors (each cites its issue on milestone `source-model`, 322)

This section said "every one is **[GAP]**: designed, not built" until 2026-09-26, when an audit
against the code found that most of the language, script and direction half had been BUILT by
slice 9 and the tags had never been moved. A stale `[GAP]` is not harmless: it hides finished work,
it makes the remaining count look worse than it is, and it invites someone to build a second
implementation of what already exists. Every tag below that changed now names the test that pins
it, because a tag with no citation is the thing that went stale in the first place.

Language and script
- `source.lang.three-facts` — **[OK]** (→ #4938) language, script and encoding are recorded
  separately, each with its own provenance, and they resolve independently of one another. Tested by
  `tests/unit/models/test_segment_language_and_script.py::TestASegmentCanHoldItsOwnLanguageAndScript::test_language_and_script_round_trip_with_their_provenance`
  and `tests/unit/llm/test_language_cascade_levels.py::TestScriptIsItsOwnFact::test_language_and_script_resolve_independently`.
  The separateness is the point and is asserted as such: one page can hold the same language in two
  scripts, differing in exactly one fact
  (`test_segment_language_and_script.py::TestOnePageHoldsSeveralLanguagesAtOnce::test_the_same_language_in_a_different_script_differs_in_one_fact_only`).
- `source.lang.registries` — **[PARTIAL]** (#4938; the BCP 47 clause is **[GAP]** → #5078) script is
  ISO 15924 including unwritten (`Zxxx`), undetermined (`Zyyy`) and private-use (`Qaaa`–`Qabx`),
  and a Glottolog code sits beside the tag on the engine's existing language record
  (`LanguageSpec.glottocode`), not in a new registry. Encoding (full, part, none) is recorded by
  Fichero, on the script row (`LibraryScript.encoding`) and read for a page through the cascade.
  **The BCP 47 half is not met and cannot be with the fields that exist**: `Document.language`
  holds a canonical NAME by deliberate choice (→ #2092), so no document, segment or reading can
  state a tag — the tag lives only on `LanguageSpec`, which is a model-coverage lookup and is
  attached to no source. Migrating that field from names to tags is the maintainer's call
  (#5078); a second `language_code` field beside it was rejected, because two fields that can
  disagree about one language, with nothing reconciling `"Spanish"` and `es`, manufactures exactly
  the drift this programme removes.
- `source.lang.project-declared` — **[OK]** (→ #4938) a project can declare a script no registry
  has: `LibraryScript` records the code, a name and an encoding, and `assert_known_script` —
  called by `representation.create` and by `segment.update` — refuses a private-use code the
  library has not declared. Tested by
  `tests/unit/models/test_project_declared_scripts.py::TestTheRefusalIsLive` (through the real
  action) and `::TestADeclaredScriptResolves`. **The language half needs nothing built**: the
  field holds a name, so the declaration and the value are the same string, and a project
  working in an unregistered language already writes its name — a `LibraryLanguage` table would
  be a second place holding one fact, and a test pins its absence.
- `source.lang.unknown-is-not-unexamined` — **[OK]** (→ #4938) "unknown" and "not yet looked at" are
  different. **This is a rule about CONTROL FLOW and not only about storage**, which is the thing
  a reader of the three states is most likely to miss: examined-and-undetermined must STOP the
  cascade's walk, while never-examined must fall through to the next level. A design that stored
  all three states and dispatched on two would pass every storage test and still lose the
  distinction the moment a value was resolved — the difference shows up as which level answers,
  not as which value is stored. **Both halves are pinned, separately, which is what makes this
  [OK] rather than a storage claim**: the storage by
  `tests/unit/models/test_segment_language_and_script.py::TestASegmentCanHoldItsOwnLanguageAndScript::test_examined_and_undetermined_is_a_third_state_here_too`,
  and the control flow by
  `tests/unit/llm/test_language_cascade_levels.py::TestUnknownAtASegmentDoesNotFallThrough`, whose
  two tests assert that an examined-and-undetermined segment is an ANSWER that stops the walk while
  a never-examined one falls through. A clearing route returns a fact to never-determined and it
  falls through the cascade again
  (`tests/unit/api/test_many_languages_per_page.py::TestAFactCanBeClearedNotOnlyCorrected::test_a_cleared_fact_falls_through_the_cascade_again`),
  which is the third state proved live rather than in a resolver.
- `source.lang.cascade` — **[OK]** (→ #4938) language and script inherit downward and can be
  overridden at any level (direction inherits the same way: see `source.dir.per-segment`). The rungs
  are reading → segment → document → project, with a pinned request above all of them; a character
  is a segment (`source.segment.open-kinds`), so the character level needs no rung of its own.
  Tested by `tests/unit/llm/test_language_cascade_levels.py::TestTheLevelIsTheRungTheAnswerCameFrom`
  (six tests, one per rung and one for the pinned request) and
  `::TestScriptIsItsOwnFact::test_it_falls_back_and_says_which_rung_answered`. The project rung is
  pinned separately at
  `tests/unit/models/test_project_declared_scripts.py` because it is the only rung that can REFUSE
  a value rather than supply one.
- `source.lang.says-where-from` — **[OK]** (→ #4938) a shown value says which level it came from
  (`LanguageResolution.level`, the same `LEVEL_*` constants `language_meta` stores). Tested by
  `tests/unit/llm/test_language_cascade_levels.py::TestTheLevelIsTheRungTheAnswerCameFrom::test_a_fallback_reports_the_rung_it_came_from_not_the_one_that_asked`.
- `source.lang.reading-overrides` — **[OK]** (→ #4938) a reading's own language and script win for
  that reading — a transliterated reading of a Latin-script line is in Arabic script and the line is
  not. Tested by
  `tests/unit/llm/test_language_cascade_levels.py::TestScriptIsItsOwnFact::test_a_readings_own_script_wins_for_that_reading`
  and, for direction, `tests/unit/llm/test_direction_cascade.py::TestItWalksTheSameRungs::test_a_reading_overrides_its_segment`.
- `source.lang.many-per-page` — **[OK]** (→ #4938) one page can hold several languages and scripts
  at once. Pinned END TO END rather than in storage alone: three regions of one page are SET to
  three scripts through the real route and READ BACK as three
  (`tests/unit/api/test_many_languages_per_page.py::TestManyPerPageEndToEnd::test_three_regions_are_SET_to_three_scripts_and_READ_BACK_as_three`),
  with the storage half at
  `tests/unit/models/test_segment_language_and_script.py::TestOnePageHoldsSeveralLanguagesAtOnce`.
  This is the behaviour that makes a segment's own answer outrank the document's: a Latin marginal
  note beside a Spanish entry is a fact about the REGION, and the document's answer is the wrong
  one for it.

Direction
- `source.dir.per-segment` — **[PARTIAL]** (→ #4938; the line/column succession clause is
  **[GAP]** → #5087) direction is set per segment: four straight directions, alternating
  (`boustrophedon`), or follows the baseline. **The six values, the cascade and the refusals are
  built**: `tests/unit/llm/test_direction_cascade.py::TestTheVocabulary::test_the_six_directions_a_manuscript_needs`
  names them, `::TestItWalksTheSameRungs` walks the same four rungs language does,
  `::TestTheDerivation` works a direction out from the script and reports `level=derived-from-script`
  so a derived answer is never mistaken for a chosen one, and
  `tests/unit/api/test_many_languages_per_page.py::TestTheWritePathRefusesWhatTheReadPathWouldNotUnderstand::test_a_direction_outside_the_six_is_refused`
  proves the refusal is live. **The direction in which lines or columns succeed is stored nowhere**
  (#5087) — no field, on any rung. It is a second fact and not a consequence of the first: a
  right-to-left page runs its lines top-to-bottom, a vertical page runs its columns right-to-left,
  and PAGE XML carries `readingDirection` and `textLineOrder` as separate attributes for exactly
  that reason.
  **Added 2026-09-28 (#5172):** a segment with no strongly directional character and nothing
  stated (a folio number, a year) takes its block's direction, else its page's, rather than an
  assumed `ltr` (`fichero-server/tests/unit/api/test_a_line_without_letters_takes_its_pages_direction.py::test_a_digit_only_line_takes_its_pages_direction`,
  `::test_the_block_first_then_the_page`).
  **Added 2026-09-28 (#5171, the app):** a direction is stated on a SOURCE -- a folder, a document or a
  page -- from the Library's right-click (**Direction ▸** the six, or **Not Stated**) and from the
  Inspector's Language section, whose **Direction** row shows what the engine resolves and where it came
  from. One audited `source_setting.set` at level node (Not Stated: `source_setting.clear`), ⌘Z by its
  audit id; the set, its ⌘Z and its ⇧⌘Z each re-read the pages the Reader shows, once
  (`SourceDirection`, `SourceDirectionMenu`;
  `ImportedPageDrawsItsBoxesTests.testADirectionStatedOnASourceIsOneUndoableSettingThatReReadsTheReader`).
  A segment's own direction is the Segment menu's (`segment.update_many`).
- `source.dir.logical-order-stored` — **[OK]** (→ #4938) stored text is in reading order; mixed
  direction in a line follows the Unicode bidirectional rules on display. Nothing in the engine
  reorders a string: a mixed-direction reading round trips byte for byte and resolving a direction
  does not touch the text
  (`tests/unit/llm/test_direction_cascade.py::TestStoredTextIsNeverReordered`, both tests), and a
  right-to-left line read from PAGE XML is not reordered on the way in
  (`tests/unit/formats/test_pagexml_read.py`). Bidi is a DISPLAY rule, and the test that matters is
  the one asserting the engine does nothing.
- `source.dir.reader-lays-out` — **[PARTIAL]** (#4938) the Reader lays text out in its direction, and
  falls back to reading order plus the shape on the image where it cannot. **App work, and honestly
  untested** — `test_direction_cascade.py` says so in its own header rather than implying coverage.
  It is also blocked on #5087: the Reader can lay out a line's direction and cannot lay out the
  order the lines run in, which is the other half of the page.
  **Built 2026-09-28 (bugs lane):** the served Reader page lays out `rtl`, `ttb` and mixed pages as
  `source.textedit.every-direction` records, on real files (the direction matrix in
  `acceptance-2026-09-27.md`: 11 of 13 cases passed, the two failures fixed as #5171 and #5172).
  **Still PARTIAL:** the order lines/columns run in (#5087, #5173) and a look on the screen.

Signs
- `source.sign.declared` — **[PARTIAL]** (#4939) a sign with no character can be declared with a name and a picture
  cut from a real page. **Built, engine side:** `DeclaredSign` (`models/signs.py`) and the audited, undoable
  `sign.declare` action. The picture is the segment the sign was met on, and it must be a real one. The maker
  is set by the engine. Pinned on the real MUFI page (Clm 13027 fol. 38r):
  `fichero-server/tests/unit/api/test_declared_signs.py::TestDeclaringASign::test_a_sign_is_declared_from_the_segment_it_was_met_on`. **Not built:** any
  surface to declare one from; that waits for its wireframes.
- `source.sign.list-authority` — **[PARTIAL]** (#4939) a sign can be identified by an authority and a number in its
  list, with no code point (`fichero-server/tests/unit/api/test_declared_signs.py::TestDeclaringASign::test_a_sign_known_only_by_its_list_number_needs_no_code_point`).
  **Not built:** search by catalogue number.
- `source.sign.project-list` — **[PARTIAL]** (#4939) declared signs live in a project's sign list, which can be
  exported and shared. `GET /api/signs` returns the list as the record itself
  (`fichero-server/tests/unit/api/test_declared_signs.py::TestTheSignListAndItsInstances::test_the_project_sign_list_is_the_exportable_record`). One live sign per
  code point (`::TestDeclaringASign::test_a_code_point_names_one_sign`); withdrawal is soft and undoable.
  **Not built:** importing someone else's list.
- `source.sign.in-readings` — **[PARTIAL]** (#4939) a reading's text can mix characters and declared signs.
  **Built as ruled:** the text keeps the private-use character, and the declared sign says what it means.
  Real MUFI text reads and exports unchanged. **Not built:** the position-to-sign map the design names, for
  a sign that has no code point.
- `source.sign.variants` — **[PARTIAL]** (#4939) a variant form of an encoded character is recorded as the character
  plus the variant. A half-stated variant is refused
  (`fichero-server/tests/unit/api/test_declared_signs.py::TestDeclaringASign::test_a_variant_says_both_what_it_varies_and_which_variant`). **Not built:** marking a
  segment's reading as that variant.
- `source.sign.gather-instances` — **[PARTIAL]** (#4939) every instance of one sign in a project can be listed, with
  its picture, from one search. **Built:** `GET /api/signs/{id}/instances` finds every live reading that
  uses the sign's code point in ONE query. On the real MUFI page that is all of its occurrences
  (`fichero-server/tests/unit/api/test_declared_signs.py::TestTheSignListAndItsInstances::test_every_instance_on_the_real_page_is_gathered_by_one_query`). **Not
  built:** each instance's picture, and instances of a sign with no code point.
- `source.sign.shown-as-picture` — **[GAP]** (#4939) where no font has a sign, its picture is shown in line.
- `source.sign.export-honest` — **[PARTIAL]** (#4939) exports carry declared signs where the format can (TEI) and
  report substitutions where it cannot. **TEI:** each use of a sign's character is wrapped
  `<g ref="#sign-…">`, and `<encodingDesc><charDecl>` gives each sign a `<glyph>` with its name as
  `<localProp name="name">` (TEI P5 4.x removed `<glyphName>`, and the vendored schema refused it), its
  sign-list references, and a PUA `<mapping>`. The TEI reader reads it back
  (`fichero-server/tests/unit/api/test_declared_signs.py::TestExportIsHonestAboutSigns::test_tei_wraps_every_use_and_declares_the_sign`,
  `::TestExportIsHonestAboutSigns::test_a_tei_round_trip_keeps_the_declaration`). **Every other format**
  keeps the character and reports "declared signs" as lost, in `write_page` itself so no writer can
  forget (`::TestExportIsHonestAboutSigns::test_alto_keeps_the_character_and_reports_the_meaning_lost`).
  **Not built:** a sign with no code point, which needs the position map.
- `source.font.recorded` — **[GAP]** (#4939) a reading records the font it needs; a project can carry fonts.
- `source.font.find-and-add` — **[GAP]** (#4939) fonts for a script can be searched for in open collections and
  added to a project in one step, with their licence shown.
- `source.font.missing-is-said` — **[GAP]** (#4939) a missing font is reported; no unexplained empty boxes.
- `source.input.palette` — **[GAP]** (#4939) a searchable palette of a script's characters and the project's
  signs inserts into a reading.

Comparison
- `source.compare.side-by-side` — **[GAP]** (#4939) two sources can be shown side by side with matching
  characters or signs aligned.

## Test matrix

To be filled at approval.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
