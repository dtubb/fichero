# Source Model — Survey of the field (2026-09-19)

> Manual: TBD — none needed of its own; it is the evidence behind the source-model sections.
>
> Part of the source model (see `source-model.md`, the foundation). This file is the evidence:
> what the standards can hold, what working philologists record, what the field's tools and
> other document models do, and what we take from each. It has no behaviours of its own.
> Everything here was checked against primary sources by research workers unless it is marked
> "not verified". Web facts go stale: recheck before relying on a version number.

## What the field already does (survey, 2026-09-19)

We adopt; we do not invent. This is what each standard can and cannot hold. It sets what our
model must carry, and tells us honestly what each export will lose. Sources are at the end.

| | Holds well | Cannot hold |
|---|---|---|
| **PageXML** (2019 schema) | region > line > word > glyph; polygons; baselines; one reading order (nested groups); direction in four values (left-right, right-left, top-bottom, bottom-top); language and script at every level; several ranked readings per segment; region types (marginalia, footnote, catch-word…); picture, music, map, table regions | scribal hands; editorial marks (damage, restoration); more than one reading order; links richer than "link" or "join"; signs with no Unicode |
| **ALTO** (4.4, 2023) | block > line > string > glyph; polygons; baselines; language; direction and reading order (since 4.3); alternatives and confidence per word and character; tags; processing history | hands; editorial marks; typed links; several reading orders; signs with no Unicode |
| **TEI** (P5) | page surfaces and polygon zones linked to the text both ways; glosses and additions with their place (above, margin, interlinear); marks that reorder reading; scribal hands and changes of hand; editorial layers (abbreviation and expansion, original and regularised, error and correction); unclear, gap, supplied, damaged, deleted; critical apparatus; signs with no Unicode (a declared glyph with a picture); free links between anything | direction is only a style hint; geometry and reading order are weaker than PageXML |
| **MEI** (music) | page surfaces and zones linked to notes; neumes | polygons: its zones are rectangles |
| **W3C Web Annotation** + **IIIF** | pointing at anything: a rectangle, a polygon, a text span, a time span, one inside another; a note that replies to a note; granularity levels page, block, paragraph, line, word, glyph | it is a pointer, not a transcription model. IIIF image crops are rectangles only |
| **YOLO** (layout training) | plain text, not XML: one class and one box or polygon per object | everything else: no text, no hierarchy, no order |
| **Kraken** training | trains from ALTO, PageXML, or line image plus text; also a compiled Arrow dataset. Learns lines (baseline plus polygon) and typed regions; handles right-to-left and vertical | works at the **line**; it does not train on cut-out characters. It has no YOLO segmenter |

Four conclusions:

1. **No one format holds everything.** PageXML and ALTO are the geometry formats. TEI is the
   scholarly format. Our model must be richer than any of them, and each export is a
   projection that says plainly what it left out.
2. **The vocabulary for region and line types already exists**: SegmOnto (main zone, margin
   text zone, graphic zone, music zone, seal zone, stamp zone, damage zone, numbering zone…;
   default line, interlinear line, heading line, music line…). It is what Kraken and
   eScriptorium train on. We adopt it as the default, extensible.
3. **Language and script have registries**: BCP 47 tags for language; ISO 15924 for script,
   including codes for "unwritten", "undetermined" and private-use scripts; and, separately,
   Glottolog (open licence, covers dialects and under-resourced languages; its codes are not
   part of BCP 47). No registry says whether a script is in Unicode: that is ours to record.
   Medievalists already share private-use characters through MUFI.
4. **"Cannot hold" means "has no element of its own for".** PageXML and ALTO both have escape
   hatches (custom attributes, tags, user-defined metadata), and tools such as Transkribus use
   them for hands and structure. We read and write those hatches on import and export, so
   other tools' extras survive a round trip.

## What working philologists record (the worked examples)

These are the test of the design. If one of them needs a special case, the model is wrong.

1. **Tenth-century Spain — the San Millán glosses.** A Latin codex in Visigothic script. Later
   readers added glosses between the lines and in the margins, in Latin, in early Romance and
   in Basque. Some glosses are single letters written above the words to tell the reader what
   order to read the Latin in. There are abbreviations to expand, and music signs (neumes)
   nobody can now turn into pitches. *Needs:* glosses in another language than the text they
   gloss; a gloss tied to the word it glosses; **a second reading order** laid over the first;
   written form versus expanded form; a music segment with no transcription; several hands.
2. **Early Arabic.** The scribe wrote the bare letter shapes. Dots that tell letters apart, and
   vowel marks, were often added later, in another ink, by another hand. One undotted word can
   honestly be read several ways. Margins carry collation notes, reading certificates,
   ownership and endowment notes. Right-to-left text with left-to-right numerals inside it.
   *Needs:* **campaigns** over the same characters, each with its own hand and date; **several
   equally valid readings**, not one best guess; mixed direction inside a line; typed marginal
   notes.
3. **Aramaic, Syriac, Hebrew.** Papyri and potsherds with damage and gaps. Syriac in three
   scripts with two competing vowel systems. Incantation bowls with the text in a **spiral**.
   Palimpsests, where the under-text only shows under special light, so one page has
   **several images**. The Masoretic margin notes. And *ketiv / qere*: the word as written and
   the word as it is to be read, both correct. *Needs:* direction that follows a curved
   baseline; a reading tied to the image it was read from; damage and restoration recorded as
   facts (so the editor's brackets are drawn from the data, not typed into the text);
   **written versus read** as a pair.
4. **Japan and Korea reading Chinese.** A Chinese text with small marks added so it can be read
   aloud in Japanese: marks that reorder the words, marks that add endings, sometimes pressed
   in with a stylus, not inked. Korean has the same practice. Small pronunciation glosses
   beside characters. Vertical columns read right to left. Variant forms of one character.
   Seals. *Needs:* the second reading order again; a gloss subordinate to one character;
   vertical direction; **the identity of a character form** apart from its code point; a seal
   as a picture segment with text inside it.
5. **The Talmud page, the glossed Bible, glossed law.** A central text, with commentaries
   wrapped around it, each quoting the words it comments on, and later commentaries commenting
   on the commentaries. *Needs:* **typed links from segment to segment, to any depth** ("this
   comments on that", "this answers that").
6. **Writing that is not in lines.** Lines that alternate direction; text round a seal or coin;
   names following a coastline on a map; tables read across or down. *Needs:* direction per
   segment, including "follows the baseline".
7. **The ordinary furniture of a page.** Footnotes and their markers in the text; marginal
   notes; running heads; page numbers; catchwords; quire signatures; rubrics and decorated
   initials; captions under pictures; tables. *Needs:* a type for each (they exist already in
   PageXML, SegmOnto and TEI); **a link from the marker to the note, from the caption to the
   picture**; and a way to say "this is page furniture, not the text", so a reading can leave
   it out.
8. **Pictures, seals, stamps, diagrams, maps on a page.** *Needs:* a segment that is not text,
   with a description of what it shows, that can be pulled out on its own.
9. **A map.** An old map is a source like any other. Its place names are text segments, often
   written along a river or a coast. A town symbol is a **point**; a road or a border is a
   **line**; a parish is an area. Tie a few points on the map to their real coordinates and the
   whole sheet is georeferenced: every segment on it then has a place in the world, and the map
   can be laid over a modern one. *Needs:* segments that are points and lines, not only areas;
   **control points** (this spot on the image is this latitude and longitude), with their own
   provenance and certainty; a place name on the map linked to the place it names in the
   knowledge graph; text that follows a path. The same holds for a plan, a survey, a
   sea chart, a sketch map in a diary margin.
10. **A claim about one word.** A knowledge-graph claim that rests on a single word, or a single
   character. *Needs:* the claim points at a segment, and survives the page being
   re-segmented or re-transcribed.

Things a palaeographer records that sit **above** the page — the quire, the ruling pattern,
the part of a codex made at one time — mean the ladder must reach above the page too.


## What the field's tools do, and what we borrow

No existing tool edits the whole ladder. Each covers a slice. All are web applications; we
take their ideas, not their code (the editor is native: see `segment-editor.md`).

| Tool | What it does well | What it lacks | What we borrow |
|---|---|---|---|
| **eScriptorium** (open source) | lines as a baseline plus a mask; typed regions and lines from an editable list; reading order worked out, then corrected by dragging in a list; keyboard-first editing | regions are boxes; nothing below the line; one reading order; no typed links | its keys and tools: double-click a baseline to add a point; scissors to cut lines across columns; join; reverse a line's direction; link a line to a region; show or hide masks and order numbers |
| **Transkribus** (proprietary) | large user base; tags; tables | polygon editing lives only in its old desktop client, now deprecated | the lesson: never split one editor across two clients |
| **Arkindex / Callico** (open source) | any hierarchy of elements over a corpus; image beside text for checking | not verified in detail | the element tree as the closest published match to our ladder |
| **Aletheia**, **LAREX** | ground truth down to glyph outlines (Aletheia); fast semi-automatic region work (LAREX) | closed, or single-purpose | proof that glyph-level ground truth is normal practice |
| **Annotorious + OpenSeadragon** | polygons over deep-zoom images, saved as W3C annotations | maintenance is uncertain (one sister project was archived in 2025) | the W3C annotation as an interchange shape |
| **Archetype** (was DigiPal) | the one published model of letterforms: character > allograph > a scribe's own form > the mark on the page, described by component and feature ("ascender: wedged") | no longer maintained | the letterform model, whole (see `languages-scripts-signs.md`) |
| **VisColl** | quires and collation: one model, several views | — | structure above the page |
| **EVT** | text and image highlight each other; notes as hotspots on the image | read-only | proof the Reader and the editor want the same geometry |
| **CATMA** | annotation sets owned by an author; sets can overlap and disagree; one annotation can cover several separate stretches | text only | named, authored annotation sets; an annotation over several segments |
| **HyperImage / Yenda** | links from a region of one image to a region of another; authored layers; a light table | — | region-to-region links across sources |
| **Kitodo** (METS) | logical structure (work, chapter) kept separate from physical (volume, leaf, page) | — | two structures over the same pages |
| **CVAT, Label Studio, labelme** | the best polygon handling; one click proposes a shape (Segment Anything) which you then adjust | not for text | click-to-propose, run by the engine, corrected by hand |

## What other document models do, and what we borrow

| Model | Ideas worth taking | What it gets wrong for manuscripts |
|---|---|---|
| **Docling** (IBM) | a tree whose items point to each other by reference; body versus page furniture; captions, footnotes and references as lists *on the figure they belong to*; pictures carrying classifications and descriptions with their own provenance; forms as a small graph of keys and values; table cells that point at a text item | boxes only; no baselines, direction, script, competing readings, hands or glyphs |
| **hOCR** | polygon *and* box; baseline; text angle; character cuts and per-character confidence on a line without making character records; a flow id for text that continues across columns or pages; scan resolution and an image checksum | one reading |
| **Azure / AWS / Google document AI** | polygons everywhere; paragraph roles (header, footnote, page number); spans into one text stream as a second way to point; selection marks with a state; table cells with spans and header kind; handwriting flag | the flat text stream is treated as the truth; reading order is implied |
| **Surya** | keeps the model's own label beside the tidy one; an explicit reading-order number | boxes; one reading |
| **DocLayNet** | pages annotated two or three times on purpose: disagreement is data | boxes |
| **OCR-D** | three named levels of transcription, from most faithful to most normalised, with the plain warning that you cannot convert reliably between them | — |
| **HTR-United** | a ready-made description of a training corpus: language, script, period, hands (how many, how sure), volume, guidelines, licence, who did what, Unicode normalisation | — |
| **CATMuS** (Hugging Face) | per-line columns: image, text, shelfmark, script type, genre, century, language, line type, and a split made by manuscript | — |
| **Kraken's Arrow file** | fast; what Kraken trains from | drops hand, century and type for each line: a gap we can close |
| **InkML**, **PencilKit** | the stroke level: points with position, time, pressure and tilt; a note can address part of a stroke run | — |
| **Unihan sources; sign lists** | a sign's identity is an *authority plus a number in that authority's list*, with Unicode as one authority among several | — |

### Ten things these models get wrong, which ours must not

1. Rectangles as the geometry. Ours: a shape, with the box worked out from it, never typed in.
2. One reading for each region. Ours: a set of readings.
3. Reading order left implicit. Ours: named orders, stored.
4. Language and direction once for a page. Ours: at any level, inherited downward.
5. A flat text stream as the truth. Ours: the stream is worked out from the segments.
6. Normalisation baked into the text. Ours: every reading says how normalised it is.
7. Skipped levels with no warning. Ours: an export says what it could not carry.
8. No record of which image, at what size. Ours: every shape names its image, and the image
   has a size and a checksum, so shapes do not rot when a page is rescanned.
9. One number called "confidence". Ours: three different things: how sure the *machine* was,
   how sure the *scholar* is, and how *damaged* the page is.
10. Unicode assumed. Ours: a sign list can be the identity, with no code point at all.

## Sources for the survey

- PageXML schema 2019-07-15: https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd
- ALTO 4.4: https://github.com/altoxml/schema
- TEI P5, manuscripts and facsimiles: https://tei-c.org/release/doc/tei-p5-doc/en/html/PH.html
- TEI P5, non-standard characters and glyphs: https://tei-c.org/release/doc/tei-p5-doc/en/html/WD.html
- MEI facsimiles: https://music-encoding.org/guidelines/dev/content/facsimilesrecordings.html
- W3C Web Annotation Data Model: https://www.w3.org/TR/annotation-model/
- IIIF Image API 3.0: https://iiif.io/api/image/3.0/ · Text Granularity: https://iiif.io/api/extension/text-granularity/
- YOLO segment labels: https://docs.ultralytics.com/datasets/segment/
- Kraken training (ketos): https://kraken.re/4.2.0/ketos.html
- SegmOnto: https://segmonto.github.io/
- ISO 15924 script codes: https://www.unicode.org/iso15924/iso15924-codes.html
- Glottolog: https://glottolog.org/meta/downloads
- SVG 2 text: https://www.w3.org/TR/SVG2/text.html
- San Millán glosses: https://en.wikipedia.org/wiki/Glosas_Emilianenses
- Leiden conventions: https://en.wikipedia.org/wiki/Leiden_Conventions

- eScriptorium segmentation editor: https://escriptorium.readthedocs.io/en/latest/segment/
- Archetype / DigiPal data model: https://www.digipal.eu/help/digipal-data-model/
- VisColl: https://viscoll.org/ · EVT: https://evt-project.github.io/
- CATMA TEI export: https://catma.de/documentation/tei-export/
- Docling document model: https://docling-project.github.io/docling/concepts/docling_document/
- hOCR 1.2: https://github.com/kba/hocr-spec/blob/master/1.2/spec.md
- Azure layout model: https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout
- Surya: https://github.com/datalab-to/surya · DocLayNet: https://huggingface.co/datasets/ds4sd/DocLayNet
- OCR-D transcription levels: https://ocr-d.de/en/gt-guidelines/trans/trLevels.html
- HTR-United schema: https://github.com/HTR-United/schema/blob/main/2023-06-27/schema.json
- CATMuS medieval dataset: https://huggingface.co/datasets/CATMuS/medieval
- Kraken Arrow dataset: https://github.com/mittagessen/kraken/blob/main/kraken/lib/arrow_dataset.py
- InkML: https://www.w3.org/TR/InkML/ · Unihan: https://www.unicode.org/reports/tr38/
- Apple: SwiftUI Canvas https://developer.apple.com/documentation/swiftui/canvas · CATiledLayer
  https://developer.apple.com/documentation/quartzcore/catiledlayer · PencilKit strokes
  https://developer.apple.com/documentation/pencilkit/pkstroke-swift.struct

Not verified in this pass, and marked so: the details of tagged-PDF alt text against the PDF
standard; the current MUFI recommendation version; eScriptorium's internal data model; the
licences of Indigenous-language catalogues other than Glottolog. Also not verified: eScriptorium's
front-end framework; the cuneiform and Maya sign-list conventions (the sites could not be
reached); Unicode variation sequences for Chinese characters; Arkindex's field names; the
IIIF Georeference extension and Allmaps (named in the maps section from general knowledge).

**To recheck before relying on them** (a reviewer doubted these, 2026-09-19): that
eScriptorium's regions are only boxes (they may be polygons); that Transkribus's web app still
cannot edit polygons; how well Kraken handles vertical text; which ALTO release added
direction and reading order; hOCR's polygon and flow properties. The IIIF Georeference
extension and Allmaps do exist and are the right prior art for maps.
