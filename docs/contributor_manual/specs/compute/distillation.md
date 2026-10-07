# Compute — Teaching small models from big ones — Design Spec (#5336)

> Milestone: remote-compute
> Manual: TBD — a section, "Making your own model", explaining how a project turns a big model's
> work and its people's corrections into a small model that runs on their own Mac, how to tell
> whether the small one is good enough, and when Fichero still asks the big one.
> Facts for the maintainer to write it from (no user-manual page yet): `docs/contributor_manual/manual-facts/2026-10-05.md`, section 5.
>
> Design-led (Testing Constitution). **Status: DRAFT; revised 2026-10-03 against the maintainer's
> rulings (`remote-compute.md`, "Ruled 2026-10-03"; the review appendix in `remote-compute.md`).** Builds on `jobs-and-fine-tuning.md`
> (training jobs, LoRA, MLX conversion, #5240), `transfer-and-results.md` (the egress gate and
> landing results), `source/formats-and-training.md` (training sets, measuring against ground
> truth, #4947) and `source/models-chains-and-projects.md` (model cards, #4948). It is the design
> that #4642 (a small palaeography model that explains its readings) asked for, generalised to
> every job a model does in Fichero.

## Intent

The best results today come from very large models: hosted vision-language models, or big open
ones that need a cluster. They are slow, costly, need a network, and send pages to someone else.
A project rarely needs all of what they know. It needs one script, one set of hands, one kind of
document, done well, over and over.

So a project should be able to **teach a small model from a big one**:
1. A big model (the *teacher*) works through a sample of the project's pages.
2. People check and correct its work in the app, as they do now.
3. That checked work becomes a training set.
4. A small model (the *student*) is trained on it and runs locally on the Mac, fast, free and
   offline, through MLX or Kraken.
5. The student is measured against the people's corrections, not against the teacher.
6. It replaces the teacher only for the jobs and pages where it is shown to be good enough.
7. Where it is unsure, Fichero still asks the teacher, or a person.

Every correction then makes the project's own model better. A community's corrections become a
community's model.

**Distillation is an option, never the default** (ruled 2026-10-03). The cheapest local step
stays the default until an A/B on the project's checked pages says otherwise
(`source.recipe.cheapest-local-first`). When a person chooses training in setup, the default
offered is this loop: distil from a large teacher, then fine-tune a small model. It runs by itself
only if it was chosen in setup (`source.recipe.train-never-automatic`). Every student Fichero
adopts must run on a 16 GB Mac.

## Prior art / best practices

- **Knowledge distillation** (Hinton et al. 2015): a student learns from a teacher's soft outputs.
  That needs the teacher's probabilities, which only open models give. A hosted model gives text,
  so learning from its outputs is **sequence-level distillation**, that is, training on its labels
  (Kim and Rush 2016), and in practice on *checked* labels.
- **Rationale distillation:** "Distilling step-by-step" (Hsieh et al. 2023) trains a small model to
  give the teacher's reasons as well as its answer, and gets better results from less data. This
  is #4642's "a model that says why".
- **Self-training and pseudo-labelling:** a model labels unlabelled data and only its confident
  labels are kept (pseudo-labelling, Lee 2013). Noisy Student (Xie et al. 2020) adds noise to the
  student's inputs while it learns, which helps layout detectors more than line readers. Confidence
  thresholds and agreement between several teachers decide what is kept.
- **Active learning:** people correct what the student is least sure of first, so every
  correction teaches most.
- **Cascades and routing:** try the cheap model, and escalate to the expensive one when
  confidence is low (FrugalGPT, Chen et al. 2023; model cascades). Measured per job and per page
  kind. Routing on confidence needs calibrated confidence; temperature scaling (Guo et al. 2017) is
  the standard post-hoc fix for a neural model's over-confidence.
- **The HTR field's practice:**
  - Kraken and eScriptorium train small recognisers from a few hundred corrected lines, and
    fine-tune a base model per manuscript. Transkribus does the same with its Super Models
    fine-tuned per collection.
  - TrOCR and small vision-language models (Florence-2, SmolVLM, Qwen2-VL-2B, PaliGemma) can be
    fine-tuned with LoRA. Each base carries its own licence (PaliGemma's derivatives carry the Gemma
    terms, for example), and the student inherits it.
  - YOLO detectors train from a few hundred boxed pages.
- **Small enough to ship:** LoRA adapters, quantisation to 4 or 8 bits, and MLX for Apple silicon.
- **Synthetic data:** text rendered in historical or project fonts, with augmentation, gives a
  recogniser a start for a new script before people have corrected much (the font work in
  `languages-scripts-signs.md`).
- **Terms of use.** Some hosted-model providers' terms restrict using their outputs to train
  models that compete with them, and the terms change. Whether a teacher's outputs may train a
  student is therefore a recorded fact on the teacher's card, checked before training, with three
  values: training allowed; not allowed; or unknown. Unknown blocks training until a person who has
  read the current terms records an answer. Fichero does not ship a judgement of any provider's
  terms.

## The design

### Which jobs can be distilled

Every job a model does in Fichero has a teacher and a natural student:

| Job | Typical teacher | Small student | Runs on |
|---|---|---|---|
| Layout: regions, signs | big VLM, or a person's boxes | YOLO detector | Mac (Core ML / MLX) |
| Lines and baselines | big VLM, Kraken base model | Kraken segmentation model | Mac |
| Reading a line | big VLM | Kraken recognition model, TrOCR, small VLM with LoRA | Mac |
| Reading with reasons | big VLM with reasoning | small VLM with LoRA, trained step-by-step | Mac (MLX) |
| Identifying signs | big VLM, people | small image classifier | Mac |
| Entities and claims from text | big LLM | small LLM with LoRA, or spaCy | Mac |
| Normalising spelling | big LLM | small sequence model | Mac |
| Picture and text vectors | large encoder | encoder fine-tuned on the project | Mac |

### The loop

1. **Choose the job and the scope:** a project, a script, a hand, a document type.
2. **Collect.** The teacher runs on a sample as an ordinary run. Its output lands as a pass with
   its maker, provenance and cost. Fichero proposes the sample to cover the scope: every hand,
   every layout, not only the easy pages.
3. **Check.** People correct the teacher's work in the app. Only checked work is ground truth.
   Unchecked teacher output can be added deliberately, and is then counted and marked
   (`compute.tune.bootstrapped-data-is-marked`).
4. **Build the set.** The training set is built from the selection (`source.train.*`). It holds the
   reasons as well, where the teacher's run recorded them. A vision run already keeps a thinking
   model's reasoning for each **page**, on the artifact and in the episode ledger (VERIFIED
   `workflows/tools/vision_base.py:4138-4143`, `:4971-5019`); reasons tied to each **line** are
   not recorded yet (#4642). See "Distilling a reasoning model's palaeography". The split is by document,
   never by line (`source.train.split-by-manuscript`).
5. **Train.** On the Mac where the model fits (Kraken and YOLO on a 16 GB Mac), otherwise on
   Hugging Face Jobs, then a cluster such as ACENET (`compute.job.*`, `compute.tune.*`). The student's card records its teacher, its set, its base model and every
   licence.
6. **Measure.** On held-out, human-checked pages, Fichero shows the student beside the teacher
   and beside people's corrections: the one CER (`workflows/transcription_accuracy.py`, through
   the readings/compare route; *agreement*, not CER, where no person checked the reference), word
   error rate, detection precision
   and recall, per hand, per page kind and per sign (`source.train.measured`). It also shows speed
   and cost per page for both.
7. **Adopt where it is good enough.** The project sets a bar per job (for example, CER no worse
   than the teacher's plus one point). The student becomes the default **only for the scope where
   it clears the bar**, recorded on its card (`source.model.suits`). Elsewhere the teacher stays.
8. **Keep learning.** New corrections accumulate. Fichero says when there is enough new checked
   work to retrain, and the new student must beat the old one on the same held-out pages before
   it replaces it.

### Distilling a reasoning model's palaeography

This is #4642's question, made testable: does a small reader learn better from a big model's
**reasons** than from transcriptions alone? The A/B decides; nothing assumes it.

**Inputs.**
- Checked pages of the project (ground truth), split by document (`source.train.split-by-manuscript`).
- A **teacher**: a large reasoning ("thinking") vision model, named by its card, whose terms allow
  training on its outputs (`distill.licence.teacher-terms`).
- A **reasoning prompt**, a file in the recipe (`source.recipe.is-a-file`), asking for each line:
  the letterforms that decided a reading, abbreviations and their expansions, uncertain readings
  with their alternatives, then the transcription.

**Making the traces.** The teacher reads the checked pages as an ordinary run, through the egress
gate. Its reasoning and its transcription are kept with full provenance in the **episode ledger**
(one immutable record per call: prompt, raw output, thinking, model and settings, timing, cost,
images by reference; VERIFIED `observability/episodes.py:1-19`, `:78-117`), and its transcription
lands as a pass whose readings name their episode. No second store is made for traces.

**The training set.** Built from the checked pages, in two forms over the **same** lines and split:
- **A, answer only:** line or page image → the person's checked transcription.
- **B, reasoning and answer:** image → the teacher's reasoning, then the person's checked
  transcription. The answer is always the checked text, never the teacher's. A trace is used only
  where the teacher's own reading of that line is within a set CER of the checked one, so the
  student never learns reasons for a wrong reading; how many were dropped is on the set.

The ledger already exports chat-form training pairs with the person's correction as the answer
(VERIFIED `observability/episodes.py:154`, `export_training_pairs`); the set builder reads from it
rather than writing a second exporter.

**Training.** One base (for example Qwen2.5-VL 3B), LoRA, the same settings for A and B. On
Hugging Face Jobs first, then ACENET (`compute.tune.lora`); the adapters run on a 16 GB Mac.

**Measured, A against B against the teacher and the cheap baseline**, on the held-out checked
pages: the one CER and WER; speed and peak memory per page on a 16 GB Mac (B writes reasoning
before its answer, so it is slower, and B is also measured with its reasoning switched off); the
cost of making the traces and of training; and, for B, whether the readings it calls uncertain
are where its errors are. B is adopted only if its CER beats A by more than the noise band and its
speed is acceptable for the project's volume. The result is recorded on both cards either way.

### The loop at archive scale (ruled 2026-10-03, #5404)

The aim is really good **small** models, each made by a recipe for its material, that then read
an archive of 100,000 to 1,000,000 images, and that get better with every round of use. Fichero is
the harness: any language, script, direction, material or model. The recipe is the method, so a
Japanese recipe is a different recipe, not the Spanish one with the language swapped. Any step can
be distilled this way: the reader, a palaeographer reviewer or thinking model, name normalisation,
entities, claims.

- **Checks have trust levels.** A person's check outranks a model checker's (for example Fable,
  recorded as checked by that model, never as a person), which outranks the teacher's unchecked
  reading. Every training set and held-out set says which levels it holds; a held-out set of
  model-checked pages is labelled so, and its scores read "against Fable's checked reading".
- **Everyday work is data.** Corrections to text, entities and claims (SVO) made in ordinary use
  feed the sets through the episode ledger, with no separate labelling step. A model checker can do
  the same checking by itself where no person has been.
- **Local first, then the cluster.** A recipe is proven on a sample on this Mac (throttled, never
  making the Mac unusable). When the person is happy, the same recipe reads the whole archive on
  Hugging Face Jobs or a cluster: sharded, failed shards resent, landing idempotent. A trained
  model lands in a portable form (Hugging Face / PyTorch) as well as for MLX, since MLX runs only
  on Macs, and it lands inside its project, card and weights (ruled 2026-10-06, #5539;
  `compute.model.lives-in-project` in `compute/jobs-and-fine-tuning.md`).
- **IIIF by reference.** An archive served over IIIF (for example the British Library's
  Endangered Archives Programme) imports without downloading its images; the remote job fetches
  each image from the Image API at the size its reader needs, politely, and results map back onto
  the canvas.
- **Rounds stop on evidence.** Each round must beat the last on the same fixed held-out pages by
  more than the noise band (0.5 CER), or the loop stops and says so. A student never trains on its
  own unchecked output, and held-out pages never train.

### Best practice the loop enforces (maintainer 2026-10-06, #5538)

The first full run (Sergio's notebooks, 2026-10-05/06: McCATMuS 40.4% to 19.6%, PP-OCRv6 24.6% to
18.4% character error) proved the loop and showed where it can flatter itself. Every distillation and
fine-tune, for every model kind (readers, names, layout, vision), follows these rules; the guided path
refuses or warns, in words, when one is not met.

1. **Three sets, kept apart.** Train (teacher lines that passed the check), a small **dev set** (used to
   choose epochs and settings, never trained on) and an untouched **test set** (used once per model,
   to report). A model's validation on its own teacher lines measures agreement with the teacher,
   not the truth, and is never reported as accuracy.
2. **Dev and test sets are corrected readings**, corrected **by a person or by a frontier model**
   (ruled 2026-10-06), each labelled with who corrected it (person, or the model and its version). A
   frontier-model-corrected set is acceptable ground truth; a person-corrected anchor set, where one
   exists, is reported beside it.
3. **A neutral teacher check.** The reader that checks teacher lines is never the model being trained,
   nor its base; where possible two readers must agree. (The first run used PP-OCRv6 to check the lines
   PP-OCRv6 then trained on.)
4. **Test beyond the training material.** The test set includes pages from volumes, notebooks or hands
   that are not in training; scores are reported per volume and per hand, not only as one mean.
5. **Repeat and report the spread.** Each setting is trained more than once where cost allows, and
   scores are reported with their spread; small sweeps (learning rate, augmentation, LoRA rank) are
   chosen on the dev set.
6. **People and frontier models in the loop.** The lines where teacher and student disagree most are
   corrected first (by a person, or a frontier model, labelled); corrections join the next training
   round and the dev set, never the test set.
7. **Every model's card says how it was made:** the teacher and its check, the three sets (sizes,
   which volumes, who corrected), the settings, every score with the set it was measured on, cost and
   time.

The same rules for every kind of model (ruled 2026-10-06: Kraken, YOLO, vision models, spaCy alike);
what a corrected set holds and how it is scored differs by kind:

| Model | Teacher (example) | Neutral check | Corrected sets hold | Scored by |
| --- | --- | --- | --- | --- |
| Kraken line reader | a frontier vision model reading each line | a second reader that is not the one trained | line readings on the page's lines | character and word error rate |
| Vision model (LoRA) | the same, or a larger vision model | as above | line or page readings | character and word error rate; repetition and truncation flagged (#5522) |
| YOLO layout / tables | a frontier model or an existing layout model proposing regions | overlap with a second detector | regions (and table cells) with their kinds | box overlap: precision and recall at a stated overlap, per region kind |
| spaCy names | a frontier model naming people, places, things | agreement with a second tagger | names as mentions on segments (#5488) | precision and recall per kind of name |
| Tesseract line reader (#5554) | a frontier vision model reading each line | a second reader that is not the one trained | line readings on the page's lines, as line image + text | character and word error rate against the base language data |
| Apple Vision (#5554) | — (no training API) | — | the project's names, places and terms as its custom-word list | character and word error rate with and without the list |
| Apple Foundation Models adapter (#5556) | a frontier model doing the text step | agreement with a second model | the step's corrected outputs (names normalised, claims) | the step's own score; retrained when macOS changes the on-device model |
| Create ML word tagger or detector (#5556) | as spaCy names or YOLO regions | as those rows | as those rows | as those rows |

Tesseract fine-tunes its line reader from corrected lines (tesstrain, starting from the language's data), on the CPU, small enough for the 8 GB Mac; the result is a model in the project like any other (#5554).
Apple Vision cannot be trained. It can be given a list of words, so the project's own names, places and
terms are passed to it, and the check pages measure whether the list helps; the app says plainly that this
reader is given words, not trained (#5554).
Models trained elsewhere (YOLO, and Kraken where it converts) can be converted to Core ML to run on the
Neural Engine, in less memory on the 8 GB Mac; a converted model is scored against its original before it
replaces it (#5556).

### Cascade: small first, big when unsure

With a student adopted, a run uses the **student first**. Where its confidence on a line, a box or
a sign falls below the project's threshold, that piece is sent to the teacher, if the egress
gate allows, or queued for a person. The run records which pieces went where. So the cost and
the dependence on the network fall as the student improves, and nothing it is unsure about is
silently accepted.

The thresholds are calibrated on held-out pages, so that "90% confident" is right about nine
times in ten. A student whose confidence is not calibrated is not routed on it.

### Things a project should be doing as well

- **Correct where it teaches most.** The correction queue can be ordered by the student's
  uncertainty (active learning), and by disagreement between teacher and student.
- **Several teachers.** Where two big models agree, their label is more trustworthy. Agreement can
  be used to pick what is pseudo-labelled and what goes to people.
- **Start with synthetic data** for a new script or font, then replace it with real corrections
  as they arrive. The card says how much of the set was synthetic.
- **Per-hand or per-collection adapters.** One base student, with small LoRA adapters for a hand,
  a scribe or a collection, chosen by the resolution cascade (`source.resolve.one-cascade`).
- **Watch for drift.** When a new collection arrives, the student is measured on a checked
  sample of it before it is trusted there.
- **Share the model.** A student and its card can be published (`compute.publish.*`) with its
  teacher, set and licences stated, so other projects on the same script can start from it.

### Licences and egress

- The teacher's terms are part of its model card (`source.model.licence-class`). Before training,
  Fichero checks whether the teacher's outputs may train a student. If they may not, it says so
  and refuses to build the set from them, while people's corrections of them stay usable.
- Pages sent to a hosted teacher go through the one egress gate (`source.egress.one-gate`), and
  rights or consent records can withhold a page from a teacher (#4953).
- The student inherits the most restrictive of its base model's, its training set's and its
  teacher's licences, and its card says which one.

## Behaviors

Tests for `distill.reasoning.*` and `distill.set.keeps-reasons`:
`fichero-server/tests/unit/training/test_distill_reasoning_to_spec.py`, one per behaviour, through the API.

- `distill.offered-not-default` — **[GAP]** (#5337, #4950) distillation is offered, never chosen by default:
  setup offers it as the default *kind* of training when a person chooses training, and a train or
  distil step runs by itself only if that was chosen in setup. *Test:* a project set up without
  training has no train step in its recipe; one set up with automatic training has the distil
  then fine-tune steps.
- `distill.job.any-model-job` — **[GAP]** (#5337) any model job in Fichero (layout,
  lines, reading, signs, entities, normalising, vectors) can be distilled from a teacher into a
  named small student.
- `distill.collect.sample-covers-scope` — **[GAP]** (#5337) the teacher's sample is
  proposed to cover every hand, layout and page kind in the scope.
- `distill.set.keeps-reasons` — **[PARTIAL]** (#4642; built (`training/line_pairs.py` arms `why`, `thinking`, `review`; the vision card's `arm`); not yet trained on real pages) where the teacher gave its reasons, the set keeps them,
  and a student can be trained to give them.
- `distill.reasoning.traces-in-the-ledger` — **[PARTIAL]** (#4642; built: `training/reasons.py`, one episode a call with the teacher, prompt file, run and time, by PAGE line id; not yet: the call's cost, and the teacher's readings landing as a pass that names its episodes) a reasoning teacher's traces for each line
  (letterforms, abbreviations and expansions, uncertain readings with alternatives, then the
  transcription) are kept in the episode ledger with the teacher's card, prompt file, run, time and
  cost, and its readings name their episode; no second store holds traces.
- `distill.reasoning.gather-is-a-job` — **[OK]** (#4642; `training/reasons_job.py`, `POST /api/training/reasons`) asking a palaeographer for its reasons on a
  scope's checked lines is one job in Activity, from the API, the CLI and MCP, with its counts in words
  (lines asked about, with reasons, with thinking, unanswered), held-out pages never asked about, and can
  be stopped before the next line; what was gathered stays. The palaeographer *reviewer* is not a second
  mechanism: it is the check job's readings card (`source.check.readings-card`).
- `distill.reasoning.answer-is-checked` — **[OK]** (#4642; `training/line_pairs.arms_for`; `max_trace_cer` (0.10 by default) and the drops on the set) in a reasoning set the answer is always the
  person's checked transcription; a trace is kept only where the teacher's own reading is within
  the set CER of it, and the count dropped is stated on the set.
- `distill.reasoning.two-arms` — **[OK]** (#4642, #5337; `in_every_arm` and the trainer's `--arm`; `--all-lines` to opt out) the same base, lines, split and settings train an
  answer-only student and a reasoning-and-answer student, so the A/B measures the reasons alone.
- `distill.reasoning.ab-decides` — **[PARTIAL]** (#4642, #5337; built: `training/reasons_ab.py` and `POST /api/training/reasons-ab` (one CER, WER, seconds a line, reasoning on and off, errors on uncertain lines, the noise band, both cards); not yet: peak memory on a 16 GB Mac (the model runs in the MLX server) and the cost of traces and training) both students, the teacher and the cheap baseline
  are measured on held-out checked pages (one CER, WER, speed and peak memory on a 16 GB Mac, with
  and without reasoning at run time, trace and training cost); the reasoning student is adopted
  only if it beats the answer-only one beyond the noise band, and both cards record the result.
- `distill.train.card-names-teacher` — **[GAP]** (#5337) a student's card names its teacher,
  set, base model and every licence.
- `distill.measure.against-people` — **[GAP]** (#5337) the student is measured on held-out
  checked pages beside the teacher and the people's corrections, per hand, page kind and sign,
  with speed and cost per page; the error rate is the one CER, called *agreement* where no person
  checked the reference.
- `distill.adopt.within-bar` — **[GAP]** (#5337) a student becomes the default only for the
  scope where it clears the project's bar, recorded on its card.
- `distill.retrain.must-beat` — **[GAP]** (#5337) a retrained student replaces the old one
  only if it beats it on the same held-out pages.
- `distill.cascade.small-first` — **[GAP]** (#5338) a run uses the student first and sends
  only low-confidence pieces to the teacher or to a person, recording where each piece went.
- `distill.cascade.calibrated` — **[GAP]** (#5338) routing uses confidence calibrated on held-out
  pages (temperature scaling by default), and the calibration error is shown; a student whose
  error is above the project's limit is not routed on.
- `distill.queue.uncertainty-first` — **[GAP]** (#5338) the correction queue can be
  ordered by the student's uncertainty and by teacher–student disagreement.
- `distill.teachers.agreement` — **[GAP]** (#5338) agreement between several teachers can
  decide what is pseudo-labelled and what goes to people.
- `distill.synthetic.marked` — **[GAP]** (#5337) synthetic training data can be generated
  from fonts, and the card states its share.
- `distill.adapters.per-scope` — **[GAP]** (#5240) per-hand or per-collection adapters on one base are
  chosen by the resolution cascade.
- `distill.drift.measured` — **[GAP]** (#5338) a student is measured on a checked sample
  of a new collection before it is trusted there.
- `distill.licence.teacher-terms` — **[GAP]** (#5337) a teacher whose terms forbid training
  on its outputs is refused as a source of training labels, with the reason shown.
- `distill.licence.inherits-strictest` — **[GAP]** (#5240) a student's card carries the most restrictive
  of its base, set and teacher licences (extends `compute.tune.licence-carries` with the teacher).
  That a set holds people-checked work by default, and counts any unchecked teacher output, is
  already `source.train.human-checked-by-default` and `compute.tune.bootstrapped-data-is-marked`.
- `distill.runs-local` — **[GAP]** (#5240, #5397) an adopted student runs on a 16 GB Mac through MLX, Core ML,
  PyTorch or Kraken, throttled like any background work, its speed and peak memory measured there
  (`compute.tune.measured-on-16gb`) (the MLX conversion is `compute.tune.convert-for-mlx`).

- `distill.collect.teacher-reads-the-lines` — **[PARTIAL]** (#5398) *Built (0cbfab3bc, 768c12865): Transcribe in Kraken mode with `lines_read_by: "model"` has Kraken find each line and the run's vision model read each line's crop, a few per call; the pass keeps Kraken's geometry, so its PAGE XML export (one reading per line) is a training set; a line the teacher says holds no writing is dropped and counted; a batch answer that does not match line for line is re-asked one line at a time. Pinned by `fichero-server/tests/unit/workflows/test_teacher_reads_kraken_lines.py` (through the Transcribe tool) and `fichero-server/tests/unit/api/test_readings_not_echoed.py`. Not built: choosing the sample to cover every hand and layout.* the teacher labels the student's own unit of work (a line Kraken found) so the pair needs no alignment.
- `distill.scale.check-trust-levels` — **[GAP]** (#5404) a training or held-out set records the
  check level of each page (person, model checker, unchecked teacher); scores against a
  model-checked reference say so.
- `distill.scale.everyday-corrections-are-data` — **[GAP]** (#5404) corrections to text, entities and
  claims made in ordinary use reach the next training set through the episode ledger.
- `distill.scale.local-first-then-remote` — **[GAP]** (#5404) the same recipe that read a sample on
  this Mac reads a whole archive on Hugging Face Jobs or a cluster, sharded, resending only failed
  shards, landing idempotently; trained students land in a portable form as well as MLX, inside their project
  (#5539, `compute.model.lives-in-project`).
- `distill.scale.iiif-by-reference` — **[GAP]** (#5404) a remote IIIF manifest imports without its
  images; remote reading fetches from the Image API at the reader's size and maps results to canvas
  coordinates.
- `distill.scale.rounds-stop-on-evidence` — **[GAP]** (#5404) a round that does not beat the last on
  the fixed held-out pages by more than the noise band is not adopted, and the loop says why.

### Evaluation against out-of-the-box models (the one home, ruled 2026-10-04, #5441)

A trained model is only worth keeping if it beats what can be downloaded. Every evaluation in
Fichero is this one job: the bake-off at setup, a model scored when it lands
(`compute.tune.scored-against-your-own-pages`) and a student measured against people
(`distill.measure.against-people`).

- `distill.eval.job` — **[PARTIAL]** (#5441) *Built (2026-10-05): `training/evaluation.py`, one
  `evaluate-models` job on the local model lane (Activity shows it and its stop reaches it), started by
  `POST /api/evaluation/runs` (`evaluation.run`, audited, not undoable: a score is a result) and followed
  by `GET /api/evaluation/runs/{id}`; MCP `fichero_evaluation_start` and `fichero_evaluation_status`.
  Each candidate reads the checked pass's own lines on each held-out page (a Kraken reader on the
  lines' baselines and outlines; a vision model on each line's picture, one line a call). Tested in
  `fichero-server/tests/unit/training/test_evaluation_job.py` through the routes, Kraken faked at its seam. Not built: a child row per model and per page (the
  scores by model and page are in the job's result), a remote model target (only this Mac's models; a
  remote provider is refused in words), the vision reading tested against a faked model, and the
  model node's Test action (#5439).* an evaluation job reads a project's held-out pages with each
  candidate model and scores them. It is one job, with a row per model and per page, on the lanes
  (`activity.jobs-are-a-tree`).
- `distill.eval.candidates-out-of-the-box` — **[PARTIAL]** (#5441, #5442) *Built: the candidates named,
  plus the registry's out-of-the-box readers of the same kind that are on this Mac: a trained Kraken
  reader's base, the Kraken catalogue, the vision bases' MLX builds (`training/vision_bases.py`); one
  not on this Mac is named in the plan, never downloaded. Default taken 2026-10-05 (design lead),
  awaiting the maintainer's ruling: the out-of-the-box candidates are the registry's readers of the
  same kind on this Mac, added unless the request says not to (`add_out_of_the_box`). Tested in `fichero-server/tests/unit/training/test_evaluation_job.py`.
  Not built: candidates drawn from onboarding and the recipe (language, script, hand, page count); the
  small models named here are not in the registry yet (#5442).* the candidates are the project's trained
  models and out-of-the-box small vision and OCR models (Qwen3-VL-2B and 4B, dots.ocr, PaddleOCR-VL,
  Nanonets-OCR2-3B; see `source.model.vision-base-catalogue`). They are drawn from onboarding and the
  recipe (language, script, hand, page count), preferring models under 8B, as the recipe decides.
- `distill.eval.held-out-checked-pages` — **[PARTIAL]** (#5441, #5404) *Built: the held-out pages are
  those a training request names, left out of its set (`training/kraken_set.py`) and recorded on the
  trained model's card; with none named, the evaluation scores on the pages every trained candidate's
  card holds out; a page named that is not held out from a trained candidate, and a trained model whose
  card holds no held-out page, are refused in words before anything is queued. The reference is the
  newest pass on the page whose model or name the request gives as `checked`; each page records who
  checked it (`person` for a pass a person wrote, else `model`), and the run counts them. Tested in `fichero-server/tests/unit/training/test_evaluation_job.py`.
  Not built: a hold-out chosen by Fichero (the person names the pages, as the Sergio project's ten
  Fable-checked pages were).* scores come only from held-out pages
  a person or Fable checked, with the check's trust level recorded (`distill.scale.check-trust-levels`),
  and never from a page any candidate trained on.
- `distill.eval.cer-variants` — **[PARTIAL]** (#5441) *Built: each page and each model is scored by the
  one CER (`character_error_rate`) under every named policy (diplomatic, layout-insensitive, lenient,
  accent-blind), per model as total edits over total reference characters, each figure naming its
  policy and carrying the definition. Tested in `fichero-server/tests/unit/training/test_evaluation_job.py`. Not built: per script and per hand; an
  abbreviation-expanded variant (no table is shipped); WER.* each model is scored with CER as the community
  computes it and its variants (the normalisation policies: case, punctuation, abbreviations
  expanded), per model, per page, per script and per hand, so an archive of many scripts and hands
  is judged where it differs. Each figure names its policy.
- `distill.eval.stored-on-the-model-node` — **[PARTIAL]** (#5441, #5439) *Built: each evaluation is
  appended to the model's card (a Kraken reader's install record, a trained vision model's
  `fichero-card.json`, a card of its own for a downloaded vision model) and never overwrites one;
  `GET /api/evaluation/scores` (MCP `fichero_evaluation_model_scores`) reads them back. Tested in `fichero-server/tests/unit/training/test_evaluation_job.py`.
  The training node's routes read them too (`GET /api/training/models`, newest per policy; tested in `fichero-server/tests/unit/training/test_trained_model_nodes.py`). Not built: the node in the app (#5439).* the results are stored on each
  model's card and shown on its node (`source.model.node-inspector`), so models are compared side by
  side. A later evaluation adds to them and never overwrites one.

The bake-off (moved from `source/models-chains-and-projects.md` on 2026-10-04) is this evaluation
run at setup, before the recipe is fixed:

- `source.onboard.bakeoff` — **[GAP]** (#4948, #4951) the bake-off runs the rule-proposed
  candidates on the chosen ground-truth pages and shows, per candidate, error per hand and page
  kind, whole-volume cost, local or remote, speed, carbon estimate and trainability, ranked in the
  fixed order; the person confirms the winner; the ranking stays on the cards and can be re-run.
- `source.onboard.bakeoff-combinations` — **[GAP]** (#4951) for a chain of steps (find lines then
  read; read then correct) the bake-off ranks whole combinations, at most three per step and at
  most nine combinations after pruning by summed rule rank, all on the same pages.
- `source.onboard.bakeoff-records-combination` — **[GAP]** (#4950) the confirmed combination sets
  each step's model in the recipe, and its measurement is kept on the cards and in the recipe's
  measurements.
- `source.onboard.bakeoff-tesseract-baseline` — **[GAP]** (#4951) for print or typescript, when
  Tesseract has data for the language, a Tesseract combination is in every bake-off; for
  handwriting it is never proposed.
- `source.onboard.bakeoff-minimum` — **[GAP]** (#4951) the bake-off needs at least 100 corrected
  lines on at least two pages; below that it says how many more are needed and is offered again
  when there are enough.
- `source.onboard.bakeoff-is-a-job` — **[GAP]** (#4951, #5352) the bake-off runs as a job in
  Activity; the person can leave setup while it runs; the first automatic run waits until the
  winner is confirmed or the bake-off is skipped.
- `source.onboard.bakeoff-skippable` — **[GAP]** (#4951) skipping the bake-off keeps the
  rule-ranked recommendation, and each such step shows "not measured on this project" in the
  Inspector until a bake-off runs.
- `source.onboard.bakeoff-random-sample` — **[GAP]** (#4951) the bake-off draws a random sample stratified
  across folders, hands and page kinds, at least 20 pages and 100 corrected lines where the project
  has them, shows each rank with its line count and confidence range, and marks candidates within
  one CER point "too close to call".

## Documentation matrix, preview harness, accessibility identifiers, UX completeness

Filled at approval, from the surfaces this spec settles (see Open questions). Listed here as
missing so the gap is visible: none of the four is written yet. [MISSING]

## Test matrix

To be filled at approval. The fixtures are real corrected pages from the test corpus, with a tiny
teacher stand-in that records its calls, so the loop is tested without a hosted model. The
measurement and the cascade's routing are pinned with known confidences and outcomes.

## Open questions

1. **Answered** (this spec, ruled 2026-10-03; sergio rulings 2026-10-03): Kraken reader and YOLO detector first, tested on the Sergio notebooks, trained on Hugging Face Jobs first. **First job to distil.** Line reading is the best-trodden path and has the most corrected data.
   Layout (YOLO) is second. **The first test is the Sergio notebooks project** (one hand, 374 page
   photographs, a Qwen-VL draft and a frontier-model draft to check; `fichero-projects`). A second
   customer is a researcher who has corrected many VLM transcriptions in his library: his
   corrections are exactly the checked ground truth step 3 asks for. Recommendation, in this order:
   1. Measure the current drafts against the checked pages, per hand and page kind
      (`distill.measure.against-people`). That alone shows where the big model fails.
   2. Build the set from the checked lines and outlines, split by document.
   3. Fine-tune, smallest first (ruled 2026-10-03): a **Kraken reader** and a **YOLO page
      detector** first, then a small VLM (for example Qwen2.5-VL 3B with LoRA). **Where it
      trains, in order:**
      - **Hugging Face Jobs** first, to prove the training recipe reruns to the same CER
        (`compute.tune.proven-on-huggingface-first`, #5398);
      - **this Mac** for Kraken and YOLO, on 16 GB, in the local ML lane (`compute.tune.on-this-mac`,
        #5397);
      - **ACENET** (Slurm) after that (`remote-compute.md`, `compute.job.*`).

      A VLM LoRA trains on a GPU elsewhere; the adapter comes back to the Mac and runs there,
      quantised, within 16 GB (`compute.tune.convert-for-mlx`).
   4. Adopt it only where it clears the bar.

   For the second customer, corrections made before the page model (edits of the stored page
   text) count only after their pages convert (#5222), so conversion comes first.
2. **The default bar** for adopting a student: relative to the teacher (no worse than its CER
   plus one point) or absolute (CER under 5%)? Recommendation: relative, shown with the absolute
   number.
3. **Cascade default:** on for adopted students, or opt in? Recommendation: on, because the
   alternative silently accepts unsure output, and the run report shows what escalated.
