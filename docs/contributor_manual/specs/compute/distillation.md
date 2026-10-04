# Compute — Teaching small models from big ones — Design Spec (#5336)

> Milestone: remote-compute
> Manual: TBD — a section, "Making your own model", explaining how a project turns a big model's
> work and its people's corrections into a small model that runs on their own Mac, how to tell
> whether the small one is good enough, and when Fichero still asks the big one.
>
> Design-led (Testing Constitution). **Status: DRAFT; revised 2026-10-03 against the maintainer's
> rulings (`remote-compute.md`, "Ruled 2026-10-03"; `REVIEW-2026-10-03.md`).** Builds on `jobs-and-fine-tuning.md`
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
  on Macs.
- **IIIF by reference.** An archive served over IIIF (for example the British Library's
  Endangered Archives Programme) imports without downloading its images; the remote job fetches
  each image from the Image API at the size its reader needs, politely, and results map back onto
  the canvas.
- **Rounds stop on evidence.** Each round must beat the last on the same fixed held-out pages by
  more than the noise band (0.5 CER), or the loop stops and says so. A student never trains on its
  own unchecked output, and held-out pages never train.

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
- `distill.set.keeps-reasons` — **[GAP]** (#4642) where the teacher gave its reasons, the set keeps them,
  and a student can be trained to give them.
- `distill.reasoning.traces-in-the-ledger` — **[GAP]** (#4642) a reasoning teacher's traces for each line
  (letterforms, abbreviations and expansions, uncertain readings with alternatives, then the
  transcription) are kept in the episode ledger with the teacher's card, prompt file, run, time and
  cost, and its readings name their episode; no second store holds traces.
- `distill.reasoning.answer-is-checked` — **[GAP]** (#4642) in a reasoning set the answer is always the
  person's checked transcription; a trace is kept only where the teacher's own reading is within
  the set CER of it, and the count dropped is stated on the set.
- `distill.reasoning.two-arms` — **[GAP]** (#4642, #5337) the same base, lines, split and settings train an
  answer-only student and a reasoning-and-answer student, so the A/B measures the reasons alone.
- `distill.reasoning.ab-decides` — **[GAP]** (#4642, #5337) both students, the teacher and the cheap baseline
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
  shards, landing idempotently; trained students land in a portable form as well as MLX.
- `distill.scale.iiif-by-reference` — **[GAP]** (#5404) a remote IIIF manifest imports without its
  images; remote reading fetches from the Image API at the reader's size and maps results to canvas
  coordinates.
- `distill.scale.rounds-stop-on-evidence` — **[GAP]** (#5404) a round that does not beat the last on
  the fixed held-out pages by more than the noise band is not adopted, and the loop says why.

## Documentation matrix, preview harness, accessibility identifiers, UX completeness

Filled at approval, from the surfaces this spec settles (see Open questions). Listed here as
missing so the gap is visible: none of the four is written yet. [MISSING]

## Test matrix

To be filled at approval. The fixtures are real corrected pages from the test corpus, with a tiny
teacher stand-in that records its calls, so the loop is tested without a hosted model. The
measurement and the cascade's routing are pinned with known confidences and outcomes.

## Open questions

1. **First job to distil.** Line reading is the best-trodden path and has the most corrected data.
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
