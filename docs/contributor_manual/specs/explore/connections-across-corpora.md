# Explore — Connections across corpora, languages and periods — Design Spec (#5340)

> Milestone: explore
> Manual: TBD — a section, "Finding connections between collections", explaining how to put two
> corpora in different languages, scripts or periods side by side, ask Fichero for passages,
> formulae, names and hands that connect them, use a known language to help with an unknown one
> from the same place, and train a model on several corpora at once, with every proposed
> connection shown as evidence to check.
>
> Design-led (Testing Constitution). **Status: DRAFT.** Builds on `explore/meaning.md` (vectors,
> neighbours, the map, #5030), `source/historical-text-normalization.md` (names across scripts,
> translation, dating), `source/undeciphered-scripts.md` (#5328), `compute/distillation.md`
> (#5336) and `compute/jobs-and-fine-tuning.md` (#5240).

## Intent

Researchers keep collections that belong together but don't share a language: Spanish notarial
records beside French ones from the same trade, Latin charters beside the vernacular, an old
form of a language beside its later one, or a known ancient language beside an unknown one written
in the same place. The connections between them are what they are after: the same person, the
same formula, the same event, the same scribe's habits, the same word in two guises.

Fichero should let a person **put two or more corpora side by side and ask for connections**
across language, script and period, and get back **proposed connections with their evidence**:
the passages, the names, the forms and the reason they were matched. These are never bare
assertions. And it should let a project **train models on several corpora together**, both
recognisers (a VLM or OCR model that learns Spanish and French hands at once) and models that
link meaning across languages, because a model taught on related material transfers what it
learns.

The AI is an instrument here, not an interlocutor. It finds candidates and shows why; people
decide what is a connection.

## Prior art / best practices

- **Multilingual sentence vectors.** LaBSE, multilingual E5 and BGE-M3 place sentences in one
  space across languages. Fichero already embeds with multilingual-e5-large and BGE-M3
  (`db/embeddings.py`), so cross-language neighbours exist in principle today, for corpora that
  have text. An undeciphered corpus has no text to embed; for it, picture vectors
  (`decipher.model.picture-vectors`) are the way in. Bitext mining
  (finding translated or parallel passages) works from these vectors with a margin criterion
  (Artetxe and Schwenk 2019).
- **Historical language is not modern language.** Modern multilingual models degrade on old
  spelling, abbreviation and script. Normalising first, or fine-tuning on the period's text
  (MacBERTh and similar, or adapters per period), is the field's answer. This ties to
  `historical-text-normalization.md`.
- **Change across periods.** Word vectors trained per period and aligned by orthogonal Procrustes
  (Hamilton et al. 2016) show how a word's use moved. The same alignment links two periods of one
  language.
- **Known language helping an unknown one.**
  - Computational decipherment uses a related known language: Ugaritic through Hebrew (Snyder,
    Barzilay and Knight 2010), Linear B through Greek (Luo, Cao and Barzilay 2019, cognate
    matching by minimum-cost flow), and Iberian with a phonetic prior (Luo et al. 2021).
  - Place names, personal names and loanwords are the classic anchors: a name known from the
    known language, found in the unknown script, fixes sign values.
  - Bilingual and digraphic texts are the strongest evidence of all.
- **Multilingual handwriting recognition.** Training one recogniser on many languages that share
  a script transfers letterforms and abbreviations between them. CATMuS Medieval (a multilingual
  Latin-script HTR dataset) and Kraken's multiscript models are the precedents. Fine-tuning a
  small VLM on several corpora with LoRA follows the same idea.
- **Evidence-first linking.** Record linkage and entity resolution across sources (the factoid
  model, prosopography databases) keep each match as a claim with its evidence and confidence,
  never a merged record. Fichero's claims already work this way.

## The design

### Corpora as sets, compared as sets

A **corpus** here is any set the library can already name: a folder, a project, a saved search
or a selection. A comparison names two or more of them and what each one is. Language, script and
period come from the cascade (`source.lang.*`). Nothing is copied.

### Finding connections

Each kind of connection is a method, run on demand, that returns **proposed links**. Each link
is a claim with its evidence (the two passages, highlighted), its score, the method and its
version, and a status a person sets: accepted, rejected or unsure. Accepted links are ordinary
claims and typed links between segments (#5164), and they reach the knowledge graph.

- **Passages that say the same thing** across languages: parallel or translated passages and
  shared formulae, from multilingual vectors with a margin criterion. Optionally the old text is
  normalised first.
- **The same person, place or thing** across languages and scripts: entity matching with name
  variants, transliteration and translation (`histnorm.entities.cross-script-candidates`), backed
  by the shared context (dates, places, roles).
- **The same words over time:** a word or formula traced from period to period with aligned
  period vectors, showing its neighbours in each period.
- **The same hand or workshop** across collections, from letterform and picture vectors
  (`source.letterform.*`, `decipher.model.picture-vectors`).
- **Shared structure:** documents of the same type (a contract, a register entry) recognised
  across languages by their layout and formula sequence.

Every method states what it cannot see: for example, it was trained on modern text; or one
corpus has no normalised text; or the vectors of two periods were aligned on a small anchor
list. Every method is checked against links people already accepted, where there are some, so
its score means something in this library.

### A known language helping with an unknown one

When one corpus is in a known language and another is undeciphered or only partly read, from the
same place or a related period, Fichero can run the decipherment aids that use the known one.
These connect to `undeciphered-scripts.md`:

- **Anchors:** names of places, people and gods known from the known corpus, searched for as
  sign sequences in the unknown one, under each hypothesis of sign values. A good anchor is a
  proposed value assignment, recorded as a hypothesis with its evidence (`decipher.hyp.record`).
- **Cognates under a phonetic prior:** given proposed sign values, the unknown corpus's
  recurring groups (`decipher.seq.recurring-groups`) are matched against the known language's
  vocabulary, and the match quality is compared with a shuffled control.
- **Bilingual and digraphic texts** are marked as such, and their aligned parts are the strongest
  evidence any hypothesis can cite.

All of it is proposals and hypotheses, scored against baselines, never applied on its own.

### Training on several corpora at once

- **Recognisers:** one training set can draw from several corpora (Spanish and French hands, or
  several scripts), with the share of each stated on the card. The model is measured **on each
  corpus separately**, so a gain on one cannot hide a loss on another (`distill.measure.against-people`).
- **Meaning:** an embedding model can be fine-tuned on the project's aligned pairs (accepted
  links and translations) so that the old languages' passages land near each other. It is
  measured on held-out accepted links.
- **A VLM that reads and links:** a small VLM can be fine-tuned with LoRA on page images from
  several corpora, with tasks for reading and pointing out the connection (and translating only where
  the project has aligned pairs, which historical text rarely has). It is
  trained by distillation from a large one where the teacher's terms allow
  (`distill.licence.teacher-terms`).
- These are ordinary jobs, run on the Mac or on a cluster (`compute.job.*`), with results that
  land as passes and claims.

## Behaviors

- `xcorpus.compare.named-sets` — **[GAP]** (#5340, #5341) two or more corpora (folders, projects,
  searches, selections) can be compared without copying them, each with its language, script and
  period from the cascade.
- `xcorpus.link.proposed-with-evidence` — **[GAP]** (#5341) a method returns proposed links,
  each with both passages highlighted, a score, the method and its version.
- `xcorpus.link.person-decides` — **[GAP]** (#5341) a person accepts, rejects or marks each
  proposed link unsure; accepted links become claims and typed segment links.
- `xcorpus.link.parallel-passages` — **[GAP]** (#5341) parallel and translated passages and
  shared formulae are found across languages from multilingual vectors.
- `xcorpus.link.entities-across-languages` — **[GAP]** (#3323) the same person or place is proposed across
  languages and scripts from name variants and shared context.
- `xcorpus.link.words-over-time` — **[GAP]** (#5341) a word or formula is traced across periods
  with aligned period vectors.
- `xcorpus.link.shared-structure` — **[GAP]** (#5341) documents of the same type are proposed across
  languages from their layout and the order of their formulae.
- `xcorpus.link.same-hand` — **[GAP]** (#5341) the same hand or workshop is proposed across
  collections from letterform and picture vectors.
- `xcorpus.method.says-its-limits` — **[GAP]** (#5341) each method states what it cannot see,
  and is checked against links people already accepted.
- `xcorpus.known-unknown.anchors` — **[GAP]** (#5342) names from a known corpus are searched
  as sign sequences in an unknown one under each hypothesis of values, and good anchors become
  hypotheses with evidence.
- `xcorpus.known-unknown.cognates` — **[GAP]** (#5342) recurring groups in the unknown corpus
  are matched against the known language's vocabulary under proposed values, against a shuffled
  control.
- `xcorpus.known-unknown.bilinguals` — **[GAP]** (#5342) bilingual and digraphic texts are
  marked and their aligned parts can be cited as evidence.
- `xcorpus.train.many-corpora` — **[GAP]** (#5343) a recogniser can be trained on several
  corpora at once, with each corpus's share on the card and accuracy reported per corpus.
- `xcorpus.train.meaning-on-pairs` — **[GAP]** (#5343) an embedding model can be fine-tuned on
  the project's accepted pairs and measured on held-out ones.
- `xcorpus.train.vlm-read-and-link` — **[GAP]** (#5343) a small VLM can be fine-tuned on several
  corpora for reading and pointing out connections, and for translating only where the project has
  aligned pairs to learn from, by distillation where the teacher's terms allow.

## Documentation matrix, preview harness, accessibility identifiers, UX completeness

Filled at approval, from the surfaces this spec settles (see Open questions). Listed here as
missing so the gap is visible: none of the four is written yet. [MISSING]

## Test matrix

To be filled at approval. The fixtures are small real parallel sets: one Spanish and French pair
from the test corpus with known accepted links, and one known-and-unknown pair where the answer
is known (Linear B against Greek, treated as unknown), so a method's score can be checked
against truth.

## Open questions

1. **Where does a comparison live?** As an Explore view over two selections, or as a saved
   "comparison" node in the library that holds its proposed links? Recommendation: a saved node,
   because the links are work that must survive.
2. **Normalise first?** Should cross-language search normalise old spelling by default when a
   normalised text exists? Recommendation: yes, and say so on the result.
3. **The first method to build.** Recommendation: parallel passages and shared formulae
   across languages, because the vectors already exist and it shows the whole
   propose-check-accept loop.
