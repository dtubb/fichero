# Build notes — the interchange harness, and PAGE XML first (#4943, #4944)

Spec: `formats-and-training.md`, "Rules for every format". Foundation: `source-model.md`.
Written 2026-09-26, before any code, because the architecture is the thing that has to be right —
the formats are then each a reader and a writer against it.

**Why this is the pay-off for slices 3–10 and not a new direction.** The north star is a model that
works in **any language, any direction**, and reads and writes **PAGE XML, TEI, ALTO and
eScriptorium**. Those are not new requirements; they are what the source model was shaped for:

- **Slice 9 is "any language, any direction" made concrete.** Language, script and direction per
  segment, with provenance, are PAGE XML's `primaryLanguage` / `script` / `readingDirection` and
  ALTO's `LANG`. `rtl`, `ttb` and `line_progression` — a vertical script whose columns run
  right-to-left — are exactly what a European-only model gets wrong, and they are stored.
- **Slice 10 is PAGE XML's `ReadingOrder` element** and ALTO's reading order. A round trip cannot be
  expressed without named orders: export, re-import, and the sequence has to come back.
- **Polygons and baselines are `Coords` and `Baseline`** — and Kraken's own shape, which is
  eScriptorium's, so that target is closer than it looks.

So the first round trip is also the first real test of whether slices 3–10 hold together.

## The load-bearing rule

`source.format.one-model-one-harness`: **every format reads INTO and writes OUT OF the one source
model, and adding a format adds a reader and a writer and NO field to segments.**

Never a converter per pair. With N formats, pairwise converters are N² of them, each with its own
idea of what a baseline is — the same duplication shape as a third sort key or a fifth vocabulary,
at the scale where it is fatal rather than annoying.

**The reason is empirical, not aesthetic: six times on 2026-09-26 alone, a fix landed on one caller
and not its siblings** — a widened type, a restored artifact, a renamed query flag, a provenance
rule, a sort key, a vocabulary. A converter per format pair IS that shape by construction: five
formats is twenty converters and twenty places for one fact to be mapped differently. One reader and
one writer per format, both against the model, is the only shape that does not multiply. **PAGE XML → ALTO is PAGE XML in, ALTO out**,
through the model, and if that loses something the loss report says so.

## What exists to build on

- **`export_service.iter_export_records`** — the ONE record stream, yielding plain dicts tagged by
  `record_type` (`document`, `entity`, `claim`, …). `source.format.reuses-the-one-stream` extends it
  with segment records; it does not get a sibling. Rights filtering belongs here too
  (`source.format.rights-filtered-once`), where one filter covers every writer, rather than in each
  writer where the fifth one forgets.
- **`importers/`** and the content-hash skip (→ #739) — the mechanism
  `source.format.reimport-recognised` names. An import is not a new mechanism; it is an import.
- **`segment.pass_create` + `segment.create_many`** — `source.format.import-is-pass` is satisfied by
  calling them, so an imported page is a pass beside the machine's and the person's, and overwrites
  nothing.
- **`lxml` and `defusedxml`** are already dependencies. `defusedxml` is what
  `source.format.schemas-on-disk` means in practice: entities and network access OFF when parsing
  anything from outside.

## The harness

New package `fichero_server/formats/`:

```
formats/
  __init__.py        registry: name -> FormatSpec
  harness.py         FormatSpec, LossReport, read/write entry points, validation
  schemas/           the XSDs, on disk, versioned with Fichero
  pagexml.py         reader + writer      (#4944)
  alto.py            reader + writer      (#4944)
  tei.py             reader + writer      (#4945)
  yolo.py            reader + writer      (#4944)
```

**`FormatSpec`** is what a format registers: a name, the extensions it claims, a `read` callable, a
`write` callable, the schema file (or `None` for the formats that have none, which is honest rather
than absent), and whether it round-trips. The registry is the only thing that knows the list, so
`source.format.first-four` is data and not a branch.

**The model side of both directions is ONE intermediate shape**, `SourcePage`: the pass, its
segments with their anchors and shapes, their language/script/direction, the named orders, and the
readings that count. A reader produces one; a writer consumes one. Nothing in a reader or writer
touches the database, which is what makes every format testable from a fixture file with no library
at all — and what stops a format quietly learning a second way to write a segment.

**`LossReport`** is a record, not a log line: `format`, and a list of `{what, count, why}`. Every
writer returns one, and it is part of the export's own output (`source.format.loss-report`). The
round-trip test subtracts exactly what the report names — so a writer that drops something silently
fails the round trip, and a writer that drops something and SAYS SO passes. **That is the whole
design: honesty is the acceptance criterion, not completeness.**

**Validation** (`source.format.export-validated`) runs the written bytes against the schema on disk.
An invalid export is a reported failure, never a written file: a file that exists and does not
validate is worse than no file, because somebody will send it to a colleague.

**Unrecognised content** (`source.format.keeps-unrecognised`) is kept on the pass, in
`metadata["foreign"][<format>]`, labelled with the format it came from, and written back by that
format's writer. On the PASS and not on segments, because the rule says a format adds no field to
segments — and because unrecognised content is usually about the file, not about one line.

## Round trips are the acceptance test

One helper, `assert_round_trip(page, format_name)`, used by every format:

1. write `page` → bytes;
2. validate the bytes against the schema;
3. read the bytes → a second `SourcePage`;
4. compare **segments, shapes, orders and readings**, minus what the loss report named.

The comparison is the thing to get right. It compares **what the model means, not what it stores**:
ids are not compared (a re-import mints new ones, and demanding stability would be demanding that
the format carry our uuids), positions are compared as SEQUENCE rather than as numbers (slice 10's
positions are spacing, not identity), and floats are compared to the precision the format declares —
PAGE XML writes integer pixels, so a normalised 0.3333 comes back 0.3333±half a pixel and asserting
equality would be asserting the format is lossless when it is not.

## PAGE XML first (#4944)

Because its shape is the one we already match, because it is what eScriptorium speaks, and because
its round trip exercises every slice: `Coords` (slice 2's polygons), `Baseline` (slice 2),
`TextRegion`/`TextLine`/`Word` (slice 1's granularities), `ReadingOrder` (slice 10),
`primaryLanguage`/`script`/`readingDirection` (slice 9), `TextEquiv` (slice 8's readings, with
`index` for several), and `custom` for what has no element.

**Known losses to state rather than discover**, each belonging in the first loss report:

- **Several readings of one line.** PAGE XML's `TextEquiv` takes an `index`, so more than one is
  expressible — but the *counting* one (slice 8) has no element. It goes out as the first
  `TextEquiv` with the rest after it, and the loss report says the choice was not carried.
- **Provenance.** `ProvenanceKind`, `created_by`, and who chose which reading counts have no PAGE
  XML home. `Metadata/@creator` takes one name, not a chain.
- **The cascade's level.** PAGE XML records a language; it has nowhere to say the language was
  inherited from the folder, so `says-where-from` cannot survive a round trip.
- **Certainty and typed links.** No element; `custom` can carry them, and reading them back is how
  `keeps-unrecognised` earns its place.

**The first test to write is not a round trip.** It is: read a PAGE XML file produced by
eScriptorium, and assert the segments, their polygons and their reading order come out as the model
would have stored them. A round trip of our own output proves our writer agrees with our reader;
reading somebody else's file is what proves the model is right.

## Open questions for the maintainer

1. **Which PAGE XML version?** The 2019-07-15 schema is the common one; eScriptorium writes 2013 in
   places. Reading both is cheap; writing needs a choice, and writing the older one to please
   eScriptorium may cost the newer one's attributes.
2. **Does an import become the working pass?** `source.format.import-is-pass` says a new pass with
   its provenance. Whether it becomes the pass the app *shows* is a curation decision, not an import
   one — and silently promoting it would answer a scholarly question with an import.
3. **Is a failed validation a refused export or a written file plus a loud report?** The behaviour
   says "a reported failure"; the note above reads that as no file. Worth confirming, because the
   opposite is defensible for a scholar who needs the file anyway.
