# Source Model — Undeciphered and partly deciphered scripts — Design Spec (#5328)

> Milestone: source-model
> Manual: TBD — a section, "Working with a script nobody can read yet", explaining how to mark
> signs whose meaning is unknown, keep rival sign lists and rival identifications side by side,
> let a model propose segments, groupings and readings, look for patterns in how signs combine,
> record a hypothesis and test it against the corpus, and share all of it with other researchers.
>
> Design-led (Testing Constitution). **Status: DRAFT.** A slice of the source model: read
> `source-model.md` and `languages-scripts-signs.md` first. This slice builds on declared signs
> (#4939), letterforms and hands (#4935), rival readings (#4934), training sets (#4947), remote
> compute (`compute/`), and the meaning map (`explore/meaning.md`). It adds what those do not
> cover: identification as a debated judgement, rival sign lists, sign parts, machine proposals
> for unlabelled signs, the statistics of sign sequences, and hypotheses tested against the corpus.

## Intent

Some scripts cannot be read by anyone. For others only part is understood: a number system and
little else, say, as with proto-Elamite. The people working on them mark up the images, argue about
which marks are one sign and which are two, and argue about whether a small stroke changes a
sign's meaning or is a scribe's habit. They keep sign lists that other scholars dispute. They
want to move from "these are the signs" to "these are the patterns" to "this is what they might
mean", and a growing number of them use machine learning on the way.

Fichero should make that work **possible, honest and shareable**:

- **Possible:** a mark can be recorded before anyone knows what it is; several sign lists and
  several opinions about one mark can sit side by side; models can propose segments, groupings
  and identifications; and the corpus can be counted and modelled as sequences of signs.
- **Honest:** every identification says who made it and how sure they were; every statistic
  says which sign list, which identifications and which pages it was computed from, and how
  much it changes under a rival list; and a model's proposal is never mistaken for a scholar's
  judgement.
- **Shareable:** the sign list, the instances with their pictures, the rival identifications,
  the sequences and the analyses leave as standard, citable data, so other researchers can
  check the work and build on it, with or without Fichero.

This is not a decipherment engine. Fichero does not claim to read a script. It keeps the
evidence, runs the methods the field already uses, and shows their results with their
uncertainty, so the people doing the reading can argue from the same evidence.

## Prior art / best practices

- **Sign lists and concordances.** Undeciphered and early scripts are worked through numbered
  sign lists (for example GORILA for Linear A, the Mahadevan and Parpola concordances for the
  Indus script, Barthel's catalogue for rongorongo, the CDLI and Meriggi lists for proto-Elamite).
  Lists disagree on how many signs there are. Scholars cite by list and number and keep
  concordances between lists. Fichero models lists as authorities and keeps concordances as
  claims with authors, never one merged list.
- **Palaeography's model.** Archetype and DigiPal describe a mark as character, allograph and
  hand, with components and features from controlled lists. Fichero already follows it
  (`source.letterform.*`). This slice adds that the *character* itself may be unknown or disputed.
- **Distributional linguistics.** Two forms that never occur in the same context (complementary
  distribution) are likely variants of one unit; two that contrast in the same context are
  likely distinct. This is the classic test for "is this stroke significant?", and it can be
  computed from the corpus.
- **Statistics of undeciphered corpora.** Sign frequency and its distribution (Zipf), n-grams
  and conditional probabilities, positional preferences (signs that open or close an entry), and
  conditional entropy (Rao et al. 2009 for the Indus script). The entropy argument was strongly
  contested (Sproat 2010 and later), which teaches the rule this spec adopts: **every statistic is
  shown against baselines**, such as a shuffled corpus or texts in known languages and non-linguistic
  sign systems, and never on its own.
- **Machine learning on sign images.**
  - Object detection, in the YOLO family, finds sign boxes on tablets and seals.
  - Classification over a sign list proposes identifications with confidence.
  - Metric learning (Siamese or contrastive networks) and self-supervised vision encoders
    (DINOv2 and similar) give each sign picture a vector, so similar marks are near each other.
  - Clustering (HDBSCAN) proposes groups. Outlier scores flag possible new signs or bad cuts.
  - Active learning asks people to label the cases that would teach the model most.
- **Distributional embeddings of signs.** word2vec-style vectors trained on sign *sequences*
  place signs used in similar contexts near each other. Read together with visual similarity,
  they help with "these two look alike, but are they the same sign?".
- **Restoration models.** Ithaca (Assael et al. 2022) predicts missing characters of damaged
  Greek inscriptions, with ranked alternatives. A sign-sequence model can do the same for a
  broken sign, and can flag a transcription that the rest of the corpus makes improbable.
- **Annotation practice.** Double, blind annotation with agreement measured by Cohen's kappa or
  Krippendorff's alpha, followed by adjudication. Low agreement on a sign is itself evidence that
  the sign is debated.
- **Arithmetic as a check.** Where a number system is known, accounting texts that state totals
  let readings of numeral signs be checked against their sums. This method has been used on
  proto-cuneiform and proto-Elamite tablets.
- **Interchange.** TEI `<charDecl>` and `<glyph>` for signs (already written,
  `source.sign.export-honest`), IIIF and W3C annotations for instances on images (`iiif.md`), and
  Hugging Face datasets and Zenodo for published sets (`source.train.*`, `compute.publish.*`).

## What exists today (and what this slice reuses)

- **Signs:** `DeclaredSign` (`models/signs.py`) and the `sign.declare` action, with `GET /api/signs` and
  `/api/signs/{id}/instances` (`api/routes/document/signs.py`). A sign can be known only by a
  list number. Instances are found by code point, so a sign with no code point cannot yet be
  gathered (`source.sign.*`, #4939). There is no app surface (#5166).
- **Letterforms and hands:** the character, allograph and hand chain; components and features
  from open lists; and rival hand attributions with certainty and judge (`source.letterform.*`,
  `source.hand.attributed`, #4935). Engine side only.
- **Segments:** a character or sign is a segment with an open kind, cut to its shape
  (`source.segment.one-primitive`, `source.segment.picture-by-shape`). Every segment and reading
  records its maker.
- **Readings:** rival readings coexist, and a project rule works out which counts
  (`source.reading.equal-alternatives`, `source.reading.chosen-follows-project-rule`).
- **Detection and training:** YOLO in and out (`source.format.yolo-*`, [OK]). Sign-picture training
  sets and measuring a model against ground truth are designed (`source.train.sign-pictures`,
  `source.train.measured`, #4947). Training on a cluster is designed (`compute.tune.*`, #5240).
- **Vectors:** text-only today (LanceDB through `db/embeddings.py`). There is no image vector, no
  clustering and no projection (`explore/meaning.md` says so itself). Projection and grouping
  are designed there (`explore.meaning.*`, #5030, #5033, #5035, #5036).
- **Interpretive lenses:** `kg/hermeneutic-layer.md` (#4692) applies a named lens to material.
  This slice uses it to view a corpus under a hypothesis.

## The design

### 1. A mark before a sign

A **mark** is a segment of kind sign (or character) that nobody has identified yet. It needs
nothing but its shape on the page. Students can box every mark on a tablet first and argue about
identity later. A mark's picture, position, line and neighbours are known from the start, so it
can already be counted, compared and clustered.

### 2. Identification is a judgement, and judgements compete

Saying "this mark is sign 23" is an **identification**: a claim about a mark, made by a person or
a model, with a certainty from 0 to 1, a sign list, and an optional note giving the argument. It
is the same shape as a hand attribution (`source.hand.attributed`), and it is stored the same
way, never as an overwrite.

- A mark can carry several identifications at once: two students who disagree, a model's top
  three, and the lead's adjudication.
- **Which one counts** follows the project's rule, as readings do: the adjudicated one; else the
  most certain human one; else none. Machine proposals never count until a person accepts them.
- A mark can be identified as *unclear*, *damaged* or *not a sign* (a crack, a ruling), and these
  are values in their own right. They are not missing data (`explore.count.missing-is-a-value`).
- The text of a line is **derived** from the counting identifications in reading order. So
  changing an identification changes every count, search and export that reads the line, with
  nothing to resynchronise.

### 3. Sign lists are authorities, and they disagree

- A project can hold **several sign lists**: its own, a published one it imports (CSV, TEI
  `<charDecl>`, or another Fichero project's export), and a colleague's. Each list is **versioned**.
  A sign merged, split or renumbered makes a new version, and the old one stays readable, because
  published arguments cite it.
- **Concordances** relate signs across lists: the same; splits into; merges with; the
  relation disputed. Each relation has an author and a note, like an identification.
- **One active list per view.** The corpus can be *read through* any list. Identifications made
  against list A are translated through the concordance into list B where they can be. Where they
  cannot, they are shown as unresolved, never guessed. Every count, chart and model states the
  list and version it used.

### 4. Parts of a sign, and whether they matter

A sign can be described by its **components**, such as a crossing stroke, a middle line or a
number of dots. A component is either a sub-segment drawn on the sign or a feature from the
project's list (`source.letterform.features`).

The question "does this component change the sign?" gets a tool, not just a field:

- Compare the two forms (with the component and without) by **distribution**: their positions
  in a line or entry, and the signs before and after them. The tool reports whether they behave
  alike (complementary or overlapping distribution, suggesting variants) or contrast (minimal
  pairs, suggesting different signs). It shows the evidence instances, the counts, and how much
  data the answer rests on.
- Compare them by **context** as well: covariates such as site, period, object type, hand and
  scribe. A variant that follows the site or the period is more likely a regional or dated habit
  than a difference in meaning.
- The answer is recorded as a **hypothesis** (section 8), with its evidence. The sign list is
  not changed automatically.

### 5. Ground truth with students

- **Campaigns** assign pages or tablets to annotators under a named, versioned guideline
  (`source.reading.author-and-guideline`). Annotation can be blind, so annotators don't see each
  other's identifications until they have finished.
- **Agreement** is measured per sign, per annotator and per page (Cohen's kappa for pairs,
  Krippendorff's alpha for more). The signs people most disagree on are listed. That list is
  itself a finding: where the sign list is weakest.
- **Adjudication** is a separate step. The lead sees the rival identifications side by side,
  with the pictures, and records a decision, which is again an identification with its maker.

### 6. Models that propose

Each of these leaves its output as a **pass** of proposals with the model's maker (a mark, an
identification or a grouping), never as accepted fact (`source.pass.never-overwrites`).

- **Find the signs.** A detector (YOLO family, trained from the students' boxes) proposes marks
  on new images. Kraken proposes lines where the script has them.
- **Propose identities.** A classifier trained on the current list proposes the top few signs
  for each mark, with confidence.
- **Picture vectors.** Every mark's picture gets a vector from a named image encoder: a pretrained
  self-supervised one, or one fine-tuned on the project's identified marks. "More like this mark"
  then works across the whole corpus, and the meaning map (`explore.meaning.view-mode`) can lay
  marks out by look.
- **Propose groups.** Clustering over the picture vectors proposes "these marks may be one sign".
  Each group says how **stable** it is, that is, whether it survives re-running on resampled data.
  The odd ones out are listed as candidate new signs or bad cuts.
- **Ask the right questions.** Active learning orders the marks so that annotators label first
  the ones the model is least sure of, or that would most change it.
- **Measured honestly.** Every model reports its accuracy on marks it was not trained on, split by
  tablet or manuscript, never by line (`source.train.split-by-manuscript`). It reports per sign,
  so rare signs aren't hidden behind common ones.
- **Where it runs.** Small jobs run on the Mac and throttle themselves (the "machine always
  useful" rule). Training a detector, a classifier or an encoder, and embedding tens of thousands
  of marks, can go to a cluster as a job (`compute.job.*`, `compute.tune.*`). Results land as passes
  (`compute.land.*`).

### 7. Patterns in how signs combine

Analyses read the corpus as **sequences of signs**: the counting identifications, through one
sign list, over a chosen set of pages, lines or entries.

- **Counts:** frequency of each sign, rank against frequency, hapax signs, and signs by position
  (first, last, alone).
- **Sequences:** n-grams, and the probability of a sign given the one or two before it
  ("after A and B, C is likely; D is never seen"). Recurring groups are proposed as possible
  words or formulae (repeated-sequence and minimum-description-length segmentation).
- **Signs by their company:** sequence-trained vectors put signs used in similar contexts near
  each other. Shown beside the picture vectors, they separate "look alike and behave alike" from
  "look alike and behave differently".
- **Prediction:** a sign-sequence model, from an n-gram model up to a small transformer, does
  three jobs:
  - it proposes ranked candidates for a damaged or missing sign, as a restoration;
  - it flags identifications the rest of the corpus makes improbable, as a check for errors;
  - it scores how well each rival sign list or hypothesis explains the corpus (held-out
    likelihood).
- **Structure:** for texts with a layout (headings, entries, totals), the position of a sign
  within an entry is a variable like any other.
- **Known subsystems:** where some signs' values are known (a number system), those values are
  entered, and arithmetic checks run where a text states a total. A failed sum flags the readings
  of its entries for checking.

Every result is **shown with its controls**:
- the same statistic on a shuffled version of the corpus;
- on reference corpora where the project supplies them (a known language, a non-linguistic sign
  system);
- under each rival sign list, as a sensitivity check.

A result that does not stand clear of its baselines says so. The meaning map's rule applies
here too: a distance or a score is not a measurement of meaning
(`explore.meaning.distance-is-not-a-measurement`).

### 8. Hypotheses are records, and they can be tried on

A **hypothesis** ("sign 23 is the numeral ten"; "the middle stroke is a variant, not a new
sign"; "the sign before a total is a commodity sign") is a record with:
- an author;
- a statement;
- the evidence it cites (marks, analyses and texts, each by link);
- a status: proposed, supported, contradicted or withdrawn;
- a discussion.

A hypothesis can be **applied as a lens** (`kg/hermeneutic-layer.md`): the corpus is re-read
under it, with values or merges substituted, and every analysis can be re-run to show what
changes. Fichero never applies a hypothesis to the stored identifications on its own. Accepting
one is a person's act, recorded with its maker and undoable.

### 9. Sharing it with other researchers

- **A citable package.** It contains:
  - the sign list (all versions) and the concordances;
  - every mark, with its picture and its IIIF location on the page (`iiif.md`);
  - every identification, with maker and certainty;
  - the sequences, read through any list;
  - the analyses, with their inputs.

  The package leaves as CSV and Parquet, TEI, W3C annotations, and a Hugging Face dataset, with
  the rights and licence of the images and of the work (#4953). It can be published to Zenodo
  for a DOI.
- **Reproducible analyses.** Every analysis is saved as a recipe: its inputs (list version, page
  set, identification rule, model versions) and its method. It can be re-run in Fichero, or
  exported as a notebook that reproduces it from the package without Fichero.
- **Importing another team's work.** Another team's package imports as their list, their
  identifications and their hypotheses, all attributed to them, beside the project's own,
  never merged into it.

### 10. Seeing signs, and correcting them where you see them

Arguing about signs is done with the pictures in front of you. Each of these is a **view mode
over a selection of marks**: a sign, a group the model proposed, a page, a search. Each one is
**also a place to correct**. Selecting marks in any view and identifying them, splitting them
off, merging them into another sign or marking them unclear is an identification with its
maker, audited and undoable. Every mark in every view opens its page with the mark highlighted.

- **Instance sheet.** Every instance of a sign (or a proposed group) as a grid of its cut
  pictures, at one scale and aligned on their centres. It can be sorted or grouped by:
  - closeness to the typical form (the odd ones out first or last);
  - confidence;
  - who identified it;
  - site, period, hand or object type.

  Dragging instances onto another sign re-identifies them. This is the main working view.
- **Side by side.** Two signs, or two proposed groups, as two sheets with their distribution
  test (section 4) between them: "do these behave as one sign?" answered next to "do they look
  like one?".
- **Overlay.** The instances of a sign superimposed, as an average image and a variance image,
  to show the typical form and where scribes differed. The difference between two signs'
  averages shows exactly which part sets them apart, the middle stroke for example.
- **Map of the picture space.** Every mark as its thumbnail, placed by its picture vector,
  projected to two dimensions with the method named (`explore.meaning.methods-are-named`). It can
  be coloured by:
  - the current identification;
  - the annotator;
  - the model's proposal;
  - site or period;
  - agreement.

  Marks whose identification differs from their neighbours' stand out. A lasso selects a
  region of the map for identifying. The projection's distortions are stated, since distance on
  the map is not a measurement (`explore.meaning.distance-is-not-a-measurement`).
- **Two maps, linked.** The picture-space map beside the context-space map (section 7): selecting
  a sign in one lights it in the other, so "looks alike" and "used alike" are read together.
- **Confusion grid.** Rows are one judge's identifications and columns another's: two students,
  a student and the lead, or the model and the people. Each cell opens its instances, so the
  pairs of signs people confuse can be seen and corrected.
- **Sign in context.** Every occurrence of a sign, lined up on the sign with its neighbours to
  the left and right (keyword in context, as in `explore.corpus.keyword-in-context`, but with sign
  pictures), sortable by the sign before or after.
- **Variation across place and time.** A sign as small multiples: one cell per site, period or
  hand, each holding its typical form and count. This shows whether a variant is a place's or a
  period's habit.
- **Components.** Instances filtered by a component, with or without it, and the component
  highlighted on each picture.
- **Sequence views.** A transition diagram (which signs follow which, with arrow widths by
  probability, against the baseline) and a position grid (signs against position in a line or
  entry). Clicking a cell opens the instances.
- **The sign list as a table.** Every sign with its picture, its numbers in each list, its
  frequency, its agreement score and its open hypotheses, sortable. This is the index the other
  views open from.

The same selection carries from view to view, so a group found on the map can be checked on an
instance sheet, overlaid, tested by distribution and corrected, without being lost.

## Behaviors

Seeing and correcting:
- `decipher.see.correct-in-any-view` — **[GAP]** (#5339) selecting marks in any of these views lets a
  person identify, split, merge or mark them unclear, audited and undoable, and every mark opens
  its page with the mark highlighted.
- `decipher.see.instance-sheet` — **[GAP]** (#5339) every instance of a sign or group is shown as an
  aligned grid of pictures, sortable by closeness to the typical form, confidence, judge and
  context, and dragging instances re-identifies them.
- `decipher.see.side-by-side` — **[GAP]** (#5339) two signs or groups are shown as two sheets with their
  distribution test between them.
- `decipher.see.overlay` — **[GAP]** (#5339) a sign's instances are superimposed as average and variance
  images, and two signs' averages can be differenced.
- `decipher.see.picture-map` — **[GAP]** (#5339) marks are laid out as thumbnails by picture vector, with
  the method and its distortions named, coloured by identification, judge, proposal, context or
  agreement, with a lasso to select.
- `decipher.see.linked-maps` — **[GAP]** (#5339) the picture-space and context-space maps are linked, so
  selecting a sign in one lights it in the other.
- `decipher.see.confusion-grid` — **[GAP]** (#5339) one judge's identifications against another's, with
  each cell opening its instances.
- `decipher.see.in-context` — **[GAP]** (#5339) every occurrence of a sign is lined up with its
  neighbours, as pictures, and sortable by the sign before or after.
- `decipher.see.variation` — **[GAP]** (#5339) a sign is shown as small multiples by site, period or hand.
- `decipher.see.components` — **[GAP]** (#5339) instances are filtered by a component and the component
  is highlighted on each picture.
- `decipher.see.sequences` — **[GAP]** (#5339) a transition diagram and a position grid, against the
  baseline, with each cell opening its instances.
- `decipher.see.list-table` — **[GAP]** (#5339) the sign list as a sortable table with picture, numbers in
  each list, frequency, agreement and open hypotheses.
- `decipher.see.selection-carries` — **[GAP]** (#5339) the same selection carries from view to view.

Marks and identifications:
- `decipher.mark.before-sign` — **[GAP]** (#5329) a mark can be recorded with only its shape and
  no identification, and is counted, compared and clustered as a mark.
- `decipher.ident.is-a-judgement` — **[GAP]** (#5329) identifying a mark as a sign is a claim
  with its maker, certainty, sign list and note, and never overwrites another identification.
- `decipher.ident.rivals-coexist` — **[GAP]** (#5329) a mark can carry several identifications
  at once, from people and models, shown side by side.
- `decipher.ident.counting-rule` — **[GAP]** (#5329) which identification counts follows the
  project's rule; a machine proposal never counts until a person accepts it.
- `decipher.ident.unclear-is-a-value` — **[GAP]** (#5329) unclear, damaged and not-a-sign are
  values, counted as such.
- `decipher.text.derived-from-identifications` — **[GAP]** (#5329) a line's text is worked out
  from its counting identifications, so a change reaches every count, search and export.
- `decipher.instances.without-code-point` — **[GAP]** (#4939) every instance of a sign is gathered with
  its picture, including a sign with no code point (closes `source.sign.gather-instances`).

Sign lists:
- `decipher.list.several` — **[GAP]** (#5330) a project holds several sign lists, its own and
  imported ones, each attributed.
- `decipher.list.versioned` — **[GAP]** (#5330) a merge, split or renumbering makes a new version
  of a list, and earlier versions stay readable and citable.
- `decipher.list.import` — **[GAP]** (#5330) a published list imports from CSV, TEI `<charDecl>`,
  or another project's export (closes the "importing someone else's list" half of
  `source.sign.project-list`).
- `decipher.concordance.claims` — **[GAP]** (#5330) relations between signs in different lists
  (same, splits, merges, disputed) are claims with authors.
- `decipher.list.read-through` — **[GAP]** (#5330) the corpus can be read through any list;
  identifications that cannot be translated are shown as unresolved; every result names the list
  and version it used.

Parts of signs:
- `decipher.parts.recorded` — **[PARTIAL]** (#4935) a sign's components are recorded as sub-segments or
  features. **Built:** features from open lists, engine side (`source.letterform.features`).
- `decipher.parts.distribution-test` — **[GAP]** (#5331) two forms that differ by a component are
  compared by position and neighbours, and the tool reports complementary, overlapping or
  contrastive distribution, with the evidence and the amount of data.
- `decipher.parts.covariates` — **[GAP]** (#5331) the same comparison runs against site, period,
  object type, hand and scribe.

Ground truth:
- `decipher.campaign.blind` — **[GAP]** (#5329) a campaign assigns pages to annotators under a
  versioned guideline, optionally blind.
- `decipher.campaign.agreement` — **[GAP]** (#5329) agreement is measured per sign, annotator and
  page, and the most-disputed signs are listed.
- `decipher.campaign.adjudication` — **[GAP]** (#5329) the lead adjudicates rival
  identifications side by side, and the decision is an identification with its maker.

Models:
- `decipher.model.detect` — **[PARTIAL]** (#5332) a detector trained from the project's boxes
  proposes marks as a pass. **Built:** YOLO in and out (`source.format.yolo-*`).
- `decipher.model.classify` — **[GAP]** (#5332) a classifier over the active list proposes the top
  few identities for each mark, with confidence, as machine identifications.
- `decipher.model.picture-vectors` — **[GAP]** (#5332) every mark's picture has a vector from a named
  encoder, and "more like this mark" works across the corpus.
- `decipher.model.groups-with-stability` — **[GAP]** (#5332) clustering proposes groups of marks,
  each with its stability under resampling, and lists the odd ones out.
- `decipher.model.active-learning` — **[GAP]** (#5332) annotators can be shown first the marks the
  model is least sure of.
- `decipher.model.measured-per-sign` — **[GAP]** (#4947) a model reports accuracy on held-out tablets,
  per sign.
- `decipher.model.runs-where-it-fits` — **[GAP]** (#5240) training and large embedding jobs can run on
  a cluster, and their results land as passes.

Sequences:
- `decipher.seq.counts` — **[GAP]** (#5333) frequency, rank and frequency, hapaxes, and position
  within a line or entry, for any page set read through any list.
- `decipher.seq.ngrams` — **[GAP]** (#5333) n-grams and the probability of a sign given those before
  it, with the instances behind each number.
- `decipher.seq.recurring-groups` — **[GAP]** (#5333) recurring sign groups are proposed as possible
  words or formulae.
- `decipher.seq.context-vectors` — **[GAP]** (#5333) signs get vectors from the contexts they occur in,
  shown beside their picture vectors.
- `decipher.seq.restore` — **[GAP]** (#5333) a damaged or missing sign gets ranked candidates from a
  sign-sequence model.
- `decipher.seq.flag-improbable` — **[GAP]** (#5333) identifications the corpus makes improbable are
  flagged for checking.
- `decipher.seq.compare-lists` — **[GAP]** (#5333) rival lists and hypotheses are scored by how well
  they explain held-out text.
- `decipher.seq.baselines` — **[GAP]** (#5333) every statistic is shown beside a shuffled corpus,
  any reference corpora, and each rival list; a result that does not stand clear says so.

Known subsystems and hypotheses:
- `decipher.known.values` — **[GAP]** (#5334) known values (a number system) can be entered for
  signs.
- `decipher.known.sums-check` — **[GAP]** (#5334) where a text states a total, the sum is checked and
  a failure flags the entries' readings.
- `decipher.hyp.record` — **[GAP]** (#5334) a hypothesis is a record with author, statement, linked
  evidence, status and discussion.
- `decipher.hyp.as-lens` — **[GAP]** (#5334, #4692) a hypothesis can be applied as a lens, and
  analyses re-run under it, without changing stored identifications.
- `decipher.hyp.accept-is-a-person` — **[GAP]** (#5334) accepting a hypothesis into the
  identifications is a person's audited, undoable act.

Sharing:
- `decipher.share.package` — **[GAP]** (#5335) the list, concordances, marks with pictures and IIIF
  locations, identifications, sequences and analyses leave as one package (CSV and Parquet, TEI,
  W3C annotations, Hugging Face dataset), with rights and licence.
- `decipher.share.publish` — **[GAP]** (#5335) a package can be published for a DOI
  (`compute.publish.*`).
- `decipher.share.recipes` — **[GAP]** (#5335) every analysis is a re-runnable recipe, exportable
  as a notebook that works from the package alone.
- `decipher.share.import-attributed` — **[GAP]** (#5335) another team's package imports beside the
  project's own, attributed and never merged.

## Test matrix

To be filled at approval. The fixtures are real, openly licensed corpora: a public proto-Elamite or
proto-cuneiform set (CDLI) for numerals and sums, and a published sign list with a concordance.
They are not invented signs. The statistics tests pin both a known result on a reference corpus
and its baseline.

## Open questions

1. **Where does this live in the app?** As its own view mode for a project ("Signs"), holding
   the list, marks, groups and analyses, with the analysis charts in Explore. Or spread across
   the Inspector, the Segments pane and Explore. Recommendation: a Signs view for the list and
   marks, and Explore for analyses, linked both ways.
2. **Which image encoder ships first?** A general self-supervised encoder works on day one but
   knows nothing about the script. A fine-tuned one needs identified marks. Recommendation: ship
   the general one, and make fine-tuning a job (cluster or Mac) once a project has enough marks.
3. **Default counting rule** for identifications in a project with students: the adjudicated one
   only, or also the most certain human one when nobody has adjudicated? Recommendation: the
   adjudicated one, else the most certain human one, with the rule shown on every result.
4. **Reference corpora** for baselines: does Fichero ship some (a known language, a
   non-linguistic sign system), or does each project bring its own? Recommendation: ship two small
   openly licensed ones, and let projects add their own.
