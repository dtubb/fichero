# Compute — The model loop: teach, correct, train, evaluate, run anywhere, publish — Design Spec (#5336)

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

> **Revised 2026-11-19 (the owner's goal for every recipe step).** This file is the ONE home of the loop. It OWNS: the
> six stages and what each means for each kind of step (the table below), the one gate a trained model passes before it
> replaces a step's model, the reasons arms, the evaluation job and the bake-off. It does NOT own, and only cites: the
> training job, the trainers, where a model lives and publishing (`compute/jobs-and-fine-tuning.md`, `compute.tune.*`,
> `compute.model.*`, `compute.publish.*`); the Train sheet, the places table, the scorers and the A/B table
> (`compute/training-and-evaluation.md`, `training.*`); what counts as ground truth (`source/ground-truth.md`); how each
> runtime ships and runs (`ai/local-runtimes.md`); and the loop's UI, which is the Models and Cluster window
> (`ui/models-and-compute-window.md`, `models.loop.*`, `models.run-settings.*`).

## Intent

The best results today come from very large hosted models. They are slow, costly, need a network, and send pages to
someone else. A project rarely needs all of what they know. It needs one script, one set of hands, one kind of
document, done well, over and over. So **every step of a recipe** (find the page and its regions, find lines, read,
review, normalise, names, claims) has the same loop, and a person can stop at any stage of it:

1. **Teach.** Run the step on a sample with a big hosted model (a provider's model, or a big open one on a GPU) as the
   *teacher*. Its work lands as an ordinary pass, with its cost and, where the provider returns it, its reasoning.
2. **Correct.** People correct the step's output in the app, as they do now: line outlines, region boxes, readings,
   normalised forms, names. Each correction is ground truth for that step; there is no separate labelling.
3. **Train.** A small model (the *student*) for that step is trained from the corrections, and from the teacher's
   output and reasons where they passed the check: by fine-tuning a small model whole (Kraken, YOLO, spaCy), or a vision
   or language model by LoRA or with all its weights. On this Mac, on Hugging Face Jobs, or on a cluster.
4. **Evaluate.** The student is scored against the step's current model on held-out corrected pages. It can lose.
   Only one that wins beyond the noise may replace the current model, and the person chooses.
5. **Run anywhere.** The adopted model runs where the step runs: any Mac from 8 GB up, Hugging Face, or a cluster.
6. **Publish.** The person may keep it in the project, make it available to every project on their Macs, or publish it
   with its card. A model trained on a project's private pages is private until the person says otherwise.

What this buys: better prompts (the teacher's reasons show what a prompt must ask for), better results on this
project's hands, and cheap, private, offline runs. Every later correction makes the next round better.

**The loop is an option, never the default** (ruled 2026-10-03). The cheapest local step stays the default until an
A/B on the project's checked pages says otherwise (`source.recipe.cheapest-local-first`). When a person chooses
training in setup, the default offered is this loop. It runs by itself only if that was chosen in setup
(`source.recipe.train-never-automatic`). The floor for a student Fichero adopts is an 8 GB Mac (`distill.runs-local`).

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

### One loop, every step

The six stages are the same for every step; what each holds differs by the kind of step. This is the one table (it
replaces the two this spec had: which jobs can be distilled, and the best-practice table of #5538). A step with no row
cannot be taught or trained, and says so (`training.distil.per-step`).

| Step | Teacher | What a person corrects (the ground truth) | Small model, and how it is trained | Neutral check of teacher output | Scored on held-out corrected pages by | Built (read 2026-11-19) |
| --- | --- | --- | --- | --- | --- | --- |
| Find the page; regions, tables | a hosted vision model or an existing layout model proposing regions | the page box; regions with their kinds; table cells | a YOLO detector, fine-tuned whole | overlap with a second detector | precision and recall at a stated overlap, per region kind (`training.eval.layout-overlap`) | the detector runs here (`llm/yolo_runtime.py`, `recipes/regions.py`); it trains here from a person's regions (`training/yolo_set.py`, `training/yolo_local.py`); no teacher, no training off the Mac, no gate |
| Find lines | the base line finder; a hosted model's line boxes are too coarse to teach from, so the lesson is the person's corrections | lines: baselines and outlines | Kraken's line finder, fine-tuned whole (`ketos segtrain`) | agreement with a second line finder | lines found at a stated overlap, and the CER of reading the lines it found (`training.eval.lines-found`) | runs here and in the remote runner (`remote_read/runner.py`); no training |
| Read a line | a hosted vision model reading each line the line finder found | line readings | a Kraken reader fine-tuned whole; or a small vision model by LoRA or with all its weights | a second reader that is not the one trained, nor its base | the one CER, and WER | teacher reads the lines; the set; training on Hugging Face Jobs and here; landing; the evaluation job (see Behaviors) |
| Read with reasons; review | a hosted reasoning model | readings; the answer is always the checked text, the reasons are the teacher's | a small vision model by LoRA or with all its weights, in two arms | as above | CER and WER, answer-only against reasons; repetition and truncation flagged (#5522) | the reasons job, the two arms, the A/B; a LoRA on Hugging Face Jobs |
| Read print (Tesseract, #5554) | a hosted vision model reading each line | line readings, as line image and text | Tesseract's line reader, from the language's data (tesstrain), on the CPU | a second reader | CER and WER against the base language data | not built |
| Read (Apple Vision, #5554) | none: it cannot be trained | the project's names, places and terms | none; it is given the words as its custom-word list, and the app says so | — | CER with and without the list | not built |
| Normalise spelling; expand | a hosted language model | normalised forms | a small text model by LoRA or with all its weights | agreement with a second model | exact match per word, and CER against the corrected forms | not built |
| Names | a hosted language model naming people, places, things | names as mentions on segments (#5488) | a spaCy pipeline trained whole; or a Create ML word tagger (#5556) | agreement with a second tagger | precision and recall per kind of name (`training.eval.names-precision-recall`, the scorer `kg.teach.names-scorer`) | spaCy runs; a person's rulings on a mention are kept per span; no set builder, no scorer, no trainer, no mark that a page's names were checked through (`kg/kg-entities-and-statements.md` section J, where the set, the scorers and the trainers for names, statements and links are specified and a first measurement is recorded) |
| Claims; fields; finding documents | a hosted language model | corrected claims, field values, document boundaries | a small language model by LoRA or with all its weights; an Apple Foundation Models adapter when a toolkit for the current macOS exists (#5556, below) | agreement with a second model | the step's own score (`training.eval.fields-exact-and-cer`, `training.eval.boundaries`; statements by `kg.teach.statements-set-and-scorer`) | not built; the adapter for a small language model on a Mac is `kg.teach.extractor-lora-on-this-mac` |
| Identifying signs | a hosted vision model, or people | sign labels | a small image classifier | — | accuracy per sign | not built |
| Picture and text vectors | a large encoder | pairs drawn from corrections | an encoder fine-tuned on the project | — | retrieval on held-out pairs | not built |

### The six stages

1. **Teach.** The teacher runs the step on a sample as an ordinary run, through the one egress gate, on any place a
   step can run (a provider's model, a provider's batch, a big open model on Hugging Face or a cluster;
   `compute/recipe-steps-at-scale.md`). Its output lands as a pass with its maker, provenance and cost
   (`distill.loop.teacher-any-step`). The sample is the person's choice per run: a covering sample or the first N pages
   (`distill.collect.first-n-or-covering-sample`). Each call's prompt, raw output and reasoning are one record in the
   episode ledger (`observability/episodes.py`); no second store holds traces (`distill.loop.thinking-kept-every-step`).
2. **Correct.** People correct the step's output where they work. A correction is ground truth for its step the moment
   it is made, and is counted (`distill.scale.everyday-corrections-are-data`; the mark and the smart folders are
   `source/ground-truth.md`'s). Checks have trust levels (`distill.scale.check-trust-levels`). Where a person corrected
   what the teacher produced, the person's is the lesson (`training.distil.corrections-outrank-teacher`). Unchecked
   teacher output can be added deliberately, and is counted and marked (`compute.tune.bootstrapped-data-is-marked`).
3. **Train.** The set is built from the selection (`source.train.*`), split by document, in three parts kept apart
   (best practice, below). It holds the teacher's reasons where the run recorded them (`distill.set.keeps-reasons`).
   How the student is trained is a recorded choice (`distill.train.lora-or-full`). Where it trains is the person's
   choice from one compared table of places with time, cost and what leaves the Mac (`training.place.compared`): this
   Mac where it fits (offered, never the default: `compute.tune.local-mlx-shown-never-default`), Hugging Face Jobs, a
   cluster. A training recipe is proven on Hugging Face Jobs before it is sent to a cluster
   (`compute.tune.proven-on-huggingface-first`). One trainer runs in all three (`compute.tune.one-trainer-three-places`).
4. **Evaluate: the one gate.** Every trained model is scored by the evaluation job (`distill.eval.job`) on held-out
   corrected pages no candidate trained on, beside the step's current model, with speed, peak memory and cost per page.
   It replaces the current model only when it passes the gate (`distill.gate.one-rule`): better than the current model
   by more than the project's noise band on the same pages; or, when the current model is a hosted teacher, no worse
   than the teacher by more than the project's bar, because it is cheaper and private. A model that does not pass is
   kept as a card, shown as not better, and not offered. Passing the gate offers it; the person chooses
   (`compute.tune.not-default-until-chosen`), unless automatic training was chosen in setup.
5. **Run anywhere.** The card names a build for each place it can run (`compute.engine.same-card-resolves-by-platform`):
   Kraken, YOLO and spaCy models as they are; a vision or language student as a 4-bit MLX build for a Mac and as
   transformers weights for a Linux GPU (`distill.student.transformers-base-on-hf-mlx-copy-local`). A place where no
   build fits says so and names one where it does (`training.fit.by-memory-before-start`). Run settings that make a
   model fit a small Mac (image size, batch, device, threads, precision) are per model and per place
   (`models.run-settings.per-model`).
6. **Publish.** In the project by default (`compute.model.lives-in-project`); to every project on the person's Macs
   (`compute.model.make-global`); or published with its card (`compute.publish.*`), private unless the person chooses
   otherwise each time, refused where the training data may not be released.

Then **keep learning**: new corrections accumulate; Fichero says when there is enough new checked work to retrain; the
retrained model passes the same gate against the one it would replace (`distill.retrain.must-beat`).

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
Hugging Face Jobs first, then a cluster (`compute.tune.lora`, `distill.train.lora-or-full`); the 4-bit MLX build runs on the person's Mac.

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
  more than the project's noise band (`training.regression.noise-band-one-number`), or the loop stops and says so. A student never trains on its
  own unchecked output, and held-out pages never train.

### Best practice the loop enforces (maintainer 2026-10-06, #5538)

The first full run (a notebook corpus, 2026-10-05/06: McCATMuS 40.4% to 19.6%, PP-OCRv6 24.6% to
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

The same rules hold for every kind of model (ruled 2026-10-06: Kraken, YOLO, vision models, spaCy alike); what a corrected
set holds, the neutral check and the score, by kind, are the columns of the one table in "One loop, every step".

Tesseract fine-tunes its line reader from corrected lines (tesstrain, starting from the language's data), on the CPU, small enough for the 8 GB Mac; the result is a model in the project like any other (#5554).
Apple Vision cannot be trained. It can be given a list of words, so the project's own names, places and
terms are passed to it, and the check pages measure whether the list helps; the app says plainly that this
reader is given words, not trained (#5554).
Models trained elsewhere (YOLO, and Kraken where it converts) can be converted to run on the Neural Engine
(Core AI on macOS 27 only, below), in less memory on the 8 GB Mac; a converted model is scored against its original
before it replaces it (#5556).

**Apple's training paths, checked 2026-10-10** (the app supports macOS 26 and 27 and iOS 26 and 27, ruled
2026-10-17, reversing the 2026-10-10 "27 only"; 27-only APIs are availability-gated and the UI says "needs macOS 27"
where there is no 26 path, #5730):
- **Foundation Models adapters: no path today.** Apple's adapter toolkit 26.0.0 is its last release and trains
  adapters only for the macOS 26 on-device model; it does not work with 27's model, and no toolkit for 27 is
  published. When one is, training needs a Mac with at least 32 GB or a Linux GPU (a Hugging Face GPU job, not
  the 8 and 16 GB Macs here); an adapter (about 160 MB) fits one on-device model version and is retrained when
  macOS updates it; deploying needs Apple's adapter entitlement and arrives by Background Assets, never in the
  bundle.
- **Create ML** (on the Mac, small): the word tagger (names) and object detector (regions) are unchanged in 2026
  and train on any of these Macs.
- **Core AI** (WWDC26) succeeds Core ML for neural networks on macOS 27: inference only, models converted from
  PyTorch with its own converter (`torch.export` to an `AIProgram`). A model trained elsewhere (YOLO; Kraken where
  it converts) is converted to Core AI to run on the Neural Engine, scored against its original first. Core ML
  stays for classical models. Nothing trains in Core AI.
- **macOS 27's Foundation Models** take images with text, give each response's token counts, and have an OCR
  tool and Dynamic Profiles: available to every step that uses Apple Intelligence.

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
- `distill.collect.first-n-or-covering-sample` — **[GAP]** (#6407; owner scenario 2026-11-08, "the first 100 pages with Gemini"; manager ruling 2026-11-08) the person chooses PER RUN how the teacher's sample is drawn: a covering sample (`distill.collect.sample-covers-scope`, the default) or the first N pages in the project's reading order; N is editable (the owner starts with 100) and is the `sample_pages` the distil route already prices (`recipes/routes.py` `routes_for_volume`), so the route card's figures follow the choice. The choice is asked where the route is chosen (Set Up's How, `designer.how.teach-as-you-go` in `source/recipe-designer.md`) and recorded on the run; it is never a hidden constant. Acceptance: with "first 100" chosen the teacher labels pages 1–100 in order and no other; with the covering sample chosen it labels a sample drawn across the scope's folders and hands; the route card's label cost names the N chosen. *Test:* `test_teach_as_you_go_end_to_end.py` (not yet written, the one test across this spec and `source/recipe-designer.md` Stage 19) and the existing `test_kraken_training_set.py`.
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
- `distill.adopt.within-bar` — **[GAP]** (#5337) where a step's current model is a hosted teacher, a student becomes
  the default only for the scope where it is no worse than the teacher by more than the project's bar (asked in setup;
  one point of the kind's unit until then, labelled), recorded on its card. This is the second arm of the one gate
  (`distill.gate.one-rule`).
- `distill.retrain.must-beat` — **[GAP]** (#5337) a retrained student replaces the old one only if it passes the one
  gate against it on the same held-out pages (`distill.gate.one-rule`).
- `distill.cascade.small-first` — **[GAP]** (#5338) a run uses the student first and sends
  only low-confidence pieces to the teacher or to a person, recording where each piece went.
- `distill.cascade.calibrated` — **[GAP]** (#5338) routing uses confidence calibrated on held-out
  pages (temperature scaling by default), and the calibration error is shown; a student whose
  error is above the project's limit is not routed on. The fit, its error and the bands a person sees are
  `hands.calib.fitted-per-hand-and-shown` and `hands.calib.four-bands-in-the-reader` (`source/read-any-hand.md`,
  Stage 1; owner 2026-11-21: measurement moves up); this line keeps the routing rule and is built on that fit.
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
- `distill.runs-local` — **[GAP]** (#5240, #5397) an adopted student runs on the person's Macs (8 GB is the floor; 16 GB
  and above fit more) through MLX, Core AI, PyTorch or Kraken, throttled like any background work, its speed and peak
  memory measured there (`compute.tune.measured-on-16gb`); a student whose smallest build does not fit an 8 GB Mac says
  which Macs and places it does fit (the MLX conversion is `compute.tune.convert-for-mlx`).

- `distill.collect.teacher-reads-the-lines` — **[PARTIAL]** (#5398) *Built (0cbfab3bc, 768c12865): Transcribe in Kraken mode with `lines_read_by: "model"` has Kraken find each line and the run's vision model read each line's crop, a few per call; the pass keeps Kraken's geometry, so its PAGE XML export (one reading per line) is a training set; a line the teacher says holds no writing is dropped and counted; a batch answer that does not match line for line is re-asked one line at a time. Pinned by `fichero-server/tests/unit/workflows/test_teacher_reads_kraken_lines.py` (through the Transcribe tool) and `fichero-server/tests/unit/api/test_readings_not_echoed.py`. Not built: choosing the sample to cover every hand and layout.* the teacher labels the student's own unit of work (a line Kraken found) so the pair needs no alignment.
- `distill.scale.check-trust-levels` — **[GAP]** (#5404) a training or held-out set records the
  check level of each page (person, model checker, unchecked teacher); scores against a
  model-checked reference say so.
- `distill.scale.everyday-corrections-are-data` — **[GAP]** (#5404) a correction made in ordinary use is ground truth
  for its step with no labelling step: line outlines and baselines (find lines), region and page boxes (find regions),
  readings, normalised forms, names, fields, document boundaries and claims. Each reaches the step's next training set
  (geometry from the person's passes, text through the episode ledger), and the step's count of corrected pages and
  lines rises as they are made, so 500 pages of corrected lines are 500 pages of ground truth for the line finder.
  Built for a person's regions (`training/yolo_set.py` `persons_regions`) and line readings (`training/kraken_set.py`).
- `distill.student.transformers-base-on-hf-mlx-copy-local` — **[GAP]** (#6407, #6406; PROVISIONAL, owner to confirm; manager 2026-11-08) a student that is to run on Hugging Face is fine-tuned from a TRANSFORMERS base there (Kraken or a safetensors vision model, the two kinds the Job and the remote reader already load), and the bulk read on Hugging Face runs that transformers student; for fast runs on a Mac the same student is converted to an MLX copy (`compute.tune.convert-for-mlx`) that lives in the project beside it (`compute.model.lives-in-project`); MLX itself NEVER runs on Hugging Face. The student's card names both forms with where each runs (`distill.train.card-names-teacher`; the places rule `source.onboard.hf-place-one-rule-everywhere`: "runs on Hugging Face as its base; the MLX copy runs here"). An MLX-only model the person picked as the base is refused for a Hugging Face fine-tune in words naming its transformers original when the Hub lists one. Acceptance: a distil run placed on Hugging Face trains the transformers student there, reads the rest there with it, and lands an MLX copy in the project whose card says "this Mac"; a run placed on this Mac trains Kraken here and converts nothing. *Test:* `test_teach_as_you_go_end_to_end.py` (not yet written) and the existing `test_vision_student_lands.py`.
- `distill.scale.local-first-then-remote` — **[GAP]** (#5404) the same recipe that read a sample on
  this Mac reads a whole archive on Hugging Face Jobs or a cluster, sharded, resending only failed
  shards, landing idempotently; trained students land in a portable form as well as MLX, inside their project
  (#5539, `compute.model.lives-in-project`).
- `distill.scale.iiif-by-reference` — **[GAP]** (#5404) a remote IIIF manifest imports without its
  images; remote reading fetches from the Image API at the reader's size and maps results to canvas
  coordinates.
- `distill.scale.rounds-stop-on-evidence` — **[GAP]** (#5404) a round that does not beat the last on
  the fixed held-out pages by more than the noise band is not adopted, and the loop says why.

### The one loop, every step (the owner's goal of 2026-11-19)

Tests to write, one file a line, in `fichero-server/tests/unit/training/`, each through the API with a recording stand-in
for the teacher and the trainer.

- `distill.loop.one-answer-per-step` — **[GAP]** (#5941, #5337) the engine answers, for one step of a project's
  recipe, the state of its loop in one read: the step's current model and where it runs; its teacher runs (model, pages,
  cost); its ground truth counted in the step's own unit (pages and lines corrected, by trust level, and how many since
  the last training); its training jobs; its trained candidates, each with its held-out score beside the current
  model's and the gate's verdict in words; where each candidate can run; and whether it is published. The recipe's
  cycle section (`compute.tune.loop-is-one-visible-cycle`) and the window (`models.loop.steps-are-rows`) read this one
  answer; neither computes a stage itself. A step with no row in the table answers "this step cannot be trained" with
  why. *Test (to write):* test_step_loop_answer.py (a step with a fake teacher run, 12 corrected pages, one landed
  candidate that lost: every stage reads back, in order, with the verdict).
- `distill.loop.teacher-any-step` — **[GAP]** (#5337, #5940) any step with a Teacher column in the table can be run on
  a chosen sample with a hosted model as its teacher: a provider's model, a provider's batch, or a big open model on
  Hugging Face or a cluster. The result is an ordinary pass or artifact of that step with its maker and cost; the same
  input and model are never sent twice (`activity.read.page-read-once`). Built for reading a line
  (`distill.collect.teacher-reads-the-lines`) and for reasons (`distill.reasoning.gather-is-a-job`); not for regions,
  normalising, names, claims or fields. *Test (to write):* test_teacher_any_step.py (a fake hosted model proposes
  regions on five pages: a region pass per page with its maker and cost; a second run sends nothing).
- `distill.loop.thinking-kept-every-step` — **[GAP]** (#4642, #5337) where a teacher returns reasoning, the episode of
  each call keeps it for every step, not only reading, tied to the unit the step works on (a line, a region, a name);
  a trace enters a training set only where the teacher's own answer for that unit agrees with the checked one
  (`distill.reasoning.answer-is-checked`, generalised), and the count dropped is on the set. Built per page for a vision
  run and per line for the reasons job. *Test (to write):* test_thinking_kept_every_step.py.
- `distill.train.lora-or-full` — **[GAP]** (#5240) how a student is trained is chosen on the start sheet and recorded
  on its card, one of: **whole** (a small model's every weight: Kraken, YOLO, spaCy, Tesseract; the only way for these);
  **adapter** (LoRA, or QLoRA where memory calls for it: a vision or language model; the default for these); **full
  fine-tune** (every weight of a vision or language model). A full fine-tune is offered only on a place whose memory
  holds it, with its time and cost beside the adapter's, and is refused in words on one that cannot; it returns merged
  weights in the portable form and is converted for MLX like an adapter's merge (`compute.tune.convert-for-mlx`); it
  passes the same gate. Built: the adapter path for a vision model on Hugging Face Jobs
  (`training/hf_vision_lora_train.py`). *Test (to write):* test_lora_or_full.py (a tiny model trained both ways on CPU
  loads and scores; a full fine-tune asked of a place too small is refused naming one that fits).
- `distill.gate.one-rule` — **[GAP]** (#4951, #5337) one rule, one code path, decides whether a trained or downloaded
  model may replace a step's current model, for every kind of step: on the same held-out corrected pages, by the kind's
  scorer, it is better than the current model by more than the project's noise band
  (`training.ab.beats-current-by-noise-band`, `training.regression.noise-band-one-number`); or, where the current model
  is a hosted teacher, it is within the project's bar of it (`distill.adopt.within-bar`). The verdict is words on the
  card: "better by 2.1 points on 40 pages", "too close to call", "worse: kept, not offered", or "not measured: no
  held-out corrected pages". A model with no verdict is never offered as a replacement. Built: adoption past the band
  for a Kraken reader (`fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py`), as its own path.
  *Test (to write):* test_one_gate.py (a better, a too-close, a worse and an unmeasured candidate, for a reader and
  for a detector, each give their verdict from the same function).
- `distill.deploy.served-on-hugging-face` — **[GAP]** (#5240, #5398) a trained model's transformers build can be
  served from the person's own Hugging Face account as an endpoint that is a provider row like any other
  (`compute.engine.session-adds-and-removes-a-row`): private, its hourly price shown before it starts, stopped when
  idle, counted against the caps; Hugging Face Jobs stay the place for batch runs. No code today
  (`compute/recipe-steps-at-scale.md`, "What exists"). *Test (to write):* test_served_on_hugging_face.py (a recorded
  Hub: the endpoint is created private, the row appears, an idle one is paused).

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
  Not built: a hold-out chosen by Fichero (the person names the pages, as the notebook corpus project's ten
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
- `distill.eval.card-writes-are-atomic` — **[PARTIAL]** (#6136; engine tested) writing an evaluation on a model's card is one step that cannot be interleaved or half done: `training/evaluation.record_on_card` reads, appends and writes under a lock for that card's path, and writes a temp file in the card's folder then replaces the card with it (`os.replace`), so two evaluations finishing together both land (the card holds both) and a reader never sees half a file (a card that does not parse is still never overwritten). Test: `fichero-server/tests/unit/training/test_record_on_card_is_atomic_6136.py`. *One engine process is assumed; a second process writing the same card is not guarded.*
- `distill.card.every-writer-is-atomic` — **[OK]** (#6137; engine tested) every writer of a model card or marker uses the one helper `core/atomic_json` (`write_json_atomic`: a temp file in the folder, then `os.replace`; `card_lock(path)`, the lock `record_on_card` holds): the Kraken marker, the trained-card writes of the Kraken, MLX and project landings, the project-to-global copy, the TrOCR record, and the Reasons A/B card entry, which reads and writes under the same lock as an evaluation. A card or marker is never half written, and the A/B and an evaluation finishing together both land. Test: `fichero-server/tests/unit/core/test_atomic_json_6137.py`.
- `distill.card.evaluations-survive-a-rewrite` — **[PARTIAL]** (#6138, from review ## 1254) a card written again keeps the `evaluations` and `reasons_ab` entries recorded on the card it replaces: a re-download of a Kraken reader carries them from the old marker into the new one when it fetched the same weights (the pinned revision or DOI is unchanged; a different one is a different model, so its measurements are dropped) (`kraken_runtime.download_recognition_model`, under the card's lock), and Make Global of a Kraken reader reads the project's card after copying the weights, under the card's lock, so an evaluation recorded meanwhile comes along (`project_models._kraken_global`) (`fichero-server/tests/unit/training/test_a_new_card_keeps_the_old_evaluations_6138.py`). Owed: Make Global of an MLX model copies the card whole from the project's build with the build's evaluations, so none is dropped, but that copy is not held under a lock against an evaluation recorded at the same moment; not reproduced.

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

## Build order (written 2026-11-07 for milestone 5, HF: the distil half; the cascade, drift and licence lines are placed when their milestone is cut)

### Stage 1 — label with a cloud model, distil Kraken on Hugging Face Jobs, run the rest on the student, never rerun a pass

The person's door to this stage is Set Up's How option Teach as you go (`source/recipe-designer.md` Stage 19, written 2026-11-08 for #6407 and the owner's scenario); the first-N choice and the provisional Hugging Face decision below came from it.

#### Step 1.1 — the teacher labels the sample: a cloud model reads Kraken's lines, the sample covers the scope, the set keeps check levels (#5398, #5337, #5404)
- Behaviours: `distill.collect.teacher-reads-the-lines`, `distill.collect.sample-covers-scope`, `distill.collect.first-n-or-covering-sample`, `distill.scale.check-trust-levels`, `distill.set.keeps-reasons`
- Tests: fichero-server/tests/unit/training/test_kraken_training_set.py, fichero-server/tests/unit/training/test_line_pairs.py, test_teacher_labels_the_sample.py (not yet written), test_teach_as_you_go_end_to_end.py (not yet written)
- Size: M

Built: Transcribe in Kraken mode with `lines_read_by: "model"` (Kraken finds each line, the run's vision model reads each line's crop; the pass keeps Kraken's geometry, so its PAGE export is a training set); the Kraken set writer (`training/kraken_set.py`). Left: the sample chosen to cover the scope (hands, periods, folders, as the project's answers name them) not the first N pages; each page's check level (person, model checker, unchecked teacher) recorded on the set and on a held-out set; the reasons kept beside the readings where the teacher gave them. Acceptance: a Gemini teacher (a fake) labels a 60-page sample drawn across three folders and two hands; the set names each page's level `teacher` and a corrected page's `person`; the held-out part is one in five and never trained on.

- test (to write): `test_teacher_labels_the_sample.py` in fichero-server/tests/unit/training/ (the sample's coverage; the levels; the held-out split)

#### Step 1.2 — distil Kraken on Hugging Face Jobs from the labels, the student measured against people and adopted within the bar (#5337, #5240, #5404)
- Behaviours: `distill.job.any-model-job`, `distill.train.card-names-teacher`, `distill.measure.against-people`, `distill.adopt.within-bar`, `distill.scale.local-first-then-remote`
- Tests: fichero-server/tests/unit/training/test_hf_jobs_target.py, fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py, test_distil_kraken_on_hf.py (not yet written), test_teach_as_you_go_end_to_end.py (not yet written)
- Depends on: 1.1
- Size: M

Built: the Hugging Face target and the Kraken trainer in the Job (`compute/jobs-and-fine-tuning.md` Step 1.1); adoption past the project's noise band. Left: the distil job as a kind any model job can take, Kraken first (the student's card names its teacher, set, place and scores); the student measured on the held-out checked pages against PEOPLE's readings (a model-checked reference saying so); adoption within the bar the project sets; the same recipe that read the sample here reading the whole archive on Hugging Face, sharded, resending only failed shards, landing idempotently, the student landing in a portable form and MLX inside its project. Acceptance: from Step 1.1's set a fake Job returns a Kraken student whose card names Gemini as teacher; its held-out CER against the person-checked pages is on the card with the band; one past the band is adopted as the step's card, one inside is not and says so; the archive's remaining 940 pages run on the student through Step 1.3 of the scale spec with two batches in flight.

- test (to write): `test_distil_kraken_on_hf.py` in fichero-server/tests/unit/training/ (the job kind; the card's teacher; the measure against people; adopt within the bar; the rest of the corpus on the student)

#### Step 1.3 — nothing is read twice: a model pass is reused, the rounds stop on evidence, the student runs local (#5404, #5240, #5397)
- Behaviours: `distill.scale.rounds-stop-on-evidence`, `distill.runs-local`, `distill.scale.everyday-corrections-are-data`, `distill.scale.iiif-by-reference`, `distill.student.transformers-base-on-hf-mlx-copy-local`
- Tests: fichero-server/tests/unit/remote_read/test_reading_at_scale.py, fichero-server/tests/unit/training/test_copied_pages_train_5699.py, fichero-server/tests/unit/training/test_vision_student_lands.py, test_distil_rounds_and_reuse.py (not yet written), test_teach_as_you_go_end_to_end.py (not yet written)
- Depends on: 1.2
- Size: M

Built: reading at scale lands idempotently (`compute.land.idempotent`); a page is read once (`activity.read.page-read-once`, the standing rule: same input and same model reuse the result). Left: a distil round reuses every teacher reading and every student reading already landed (a second round labels only the new sample pages and measures only new held-out pages); the rounds stop when the held-out gain is inside the band for two rounds or the budget is spent, saying which; the adopted student runs on the person's Macs through Kraken on the background lane with its speed and peak memory measured there; everyday corrections join the next set; IIIF pages travel by reference. Acceptance: a second round on the same project sends no page the teacher read already and measures no held-out page twice (a counting fake sees 0 repeats); two rounds inside the band stop with "no gain past the band"; the student reads a page here with its seconds and peak recorded; a person's correction made after round one is in round two's set.

- test (to write): `test_distil_rounds_and_reuse.py` in fichero-server/tests/unit/training/ (zero repeats; the stop rule; the local run's figures; the correction in the next set)

Across Steps 1.1–1.3 and `source/recipe-designer.md` Stage 19, ONE end-to-end test (#6407, written 2026-11-08): `test_teach_as_you_go_end_to_end.py` in fichero-server/tests/unit/training/ (a fake Gemini labels the first 100 pages of a 1,000-page fake project (and, in a second case, a covering sample); a fake Job returns a student; the student's CER and WER on the held-out checked pages clear the gate; the remaining 900 pages run on the student on a fake Hugging Face target; a counting fake sees every page read exactly once by exactly one model: zero repeated passes, `activity.read.page-read-once`; the switch is recorded). Named on Steps 1.1 and 1.2 above and on Stage 19's steps so one file pins the whole story.

### Stage 2 — the loop on every step (written 2026-11-19 from `reviews/2026-11-19-distil-every-step-review.md`)

Two things come first and together, the two runtimes the loop stands on, proven for real: YOLO running wherever the
engine runs (`ai/local-runtimes.md` Step 2.1, `runtime.yolo.imports-wherever-the-engine-runs`) and Kraken on Hugging
Face end to end (Step 2.1 here). Steps of other specs that this stage needs are named with their spec.

#### Step 2.1 — Kraken on Hugging Face, end to end and for real: lines and readings as a Job, training as a Job, the model home and gated (#5398, #5337)
- Behaviours: `distill.eval.job`, `distill.eval.held-out-checked-pages`, `distill.eval.stored-on-the-model-node`
- Tests: fichero-server/tests/unit/training/test_hf_jobs_target.py, fichero-server/tests/unit/training/test_trained_reader_lands.py, fichero-server/tests/unit/training/test_evaluation_job.py, fichero-server/tests/unit/remote_read/test_read_at_scale_job.py, test_distil_kraken_on_hf.py (not yet written)
- Depends on: 1.1
- Size: M

This is Step 1.2 above (whose behaviours stay there) carried to a real run, with the score that makes it a loop: the
evaluation job run at landing. Built: `training/hf_jobs.py` `HfJobsTarget` (a private bucket in the
person's account, send, submit, statuses, fetch, cancel; the token checked first for `job.write` and `repo.write`; the
hardware price read first; a time limit always sent); `training/hf_kraken_train.py` (`ketos train` from a base reader);
`training/job.py` (the `train-a-model` job, `POST /api/training/kraken`); `training/landing.py` (the reader lands with
its card); `remote_read/runner.py` and `remote_read/job.py` (Kraken's line finder and a Kraken reader as a Job, shard
by shard, landing idempotently; the monthly cap read by `_hf_spend`). Left: the held-out score written on the card at
landing (the held-out pages stay home and nothing scores them by itself); the line finder trained as a Job
(`compute.tune.kraken-segmentation`); the training start checked against the project's and the app's caps as price times
time limit (today a $0 cap only holds the offer, `recipes/train_offers.py`); the card naming its teacher. A first real
run needs, from the owner: a fine-grained Hugging Face token with write to his own repositories and Jobs, billing
enabled for Jobs on that account, and a spending cap above $0 for the project (a few dollars covers a `t4-small` run
inside its 4 h limit). Acceptance, on the named machine with that token: 20 public test pages are segmented and read by
a Job and land once; a reader trained by a Job from their lines lands with its held-out CER on its card and the gate's
verdict; the spend recorded is under the cap; a second start with the cap at $0 is refused in words before anything is
sent.

- test (to write): `test_distil_kraken_on_hf.py` in fichero-server/tests/unit/training/ (the fake-Hub half of the above; the real half is a named-machine run recorded in the review)

#### Step 2.2 — the one gate, for readers and detectors (#4951, #5337)
- Behaviours: `distill.gate.one-rule`, `distill.retrain.must-beat`
- Tests: fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py, fichero-server/tests/unit/training/test_noise_band_per_project_5692.py, test_one_gate.py (not yet written)
- Size: M

#### Step 2.3 — one answer per step, and corrections counted as ground truth for every step (#5941, #5404)
- Behaviours: `distill.loop.one-answer-per-step`
- Tests: fichero-server/tests/unit/training/test_train_on_the_persons_corrections_5700.py, test_step_loop_answer.py (not yet written)
- Depends on: 2.2
- Size: M

#### Step 2.4 — a teacher for any step, its reasoning kept (#5337, #4642)
- Behaviours: `distill.loop.teacher-any-step`, `distill.loop.thinking-kept-every-step`, `distill.reasoning.traces-in-the-ledger`
- Tests: fichero-server/tests/unit/training/test_distill_reasoning_to_spec.py, test_teacher_any_step.py (not yet written), test_thinking_kept_every_step.py (not yet written)
- Depends on: 2.3
- Size: M

#### Step 2.5 — adapter or full fine-tune, and a served model on Hugging Face (#5240)
- Behaviours: `distill.train.lora-or-full`, `distill.deploy.served-on-hugging-face`
- Tests: fichero-server/tests/unit/training/test_vision_lora_trainer.py, test_lora_or_full.py (not yet written), test_served_on_hugging_face.py (not yet written)
- Depends on: 2.2
- Size: M

The corrections counted for every step (`distill.scale.everyday-corrections-are-data`, `distill.scale.check-trust-levels`)
and the bar (`distill.adopt.within-bar`) are built in Stage 1's steps, which hold them. The steps of the other specs in this stage, in order after the gate (Step 2.2): the layout row trained off the Mac and
the line finder trained (`compute/jobs-and-fine-tuning.md` Step 1.2, `compute.tune.yolo-layout`,
`compute.tune.kraken-segmentation`); names and normalising trained (`compute/training-and-evaluation.md`,
`training.propose.names-tagger`, `training.eval.names-precision-recall`); publishing
(`compute/jobs-and-fine-tuning.md` Stage 2); the window's loop rows and run settings
(`ui/models-and-compute-window.md` Stage 5).

## Test matrix

To be filled at approval. The fixtures are real corrected pages from the test corpus, with a tiny
teacher stand-in that records its calls, so the loop is tested without a hosted model. The
measurement and the cascade's routing are pinned with known confidences and outcomes.

## Open questions

1. **Answered** (this spec, ruled 2026-10-03; notebook corpus rulings 2026-10-03): Kraken reader and YOLO detector first, tested on a notebook corpus, trained on Hugging Face Jobs first. **First job to distil.** Line reading is the best-trodden path and has the most corrected data.
   Layout (YOLO) is second. **The first test is a notebook corpus project** (one hand, 374 page
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
4. **The bar, asked where?** The gate's second arm (a student may be worse than a hosted teacher by the bar) needs a
   number per project. Recommendation: one question in setup beside the spending cap, one point of the kind's unit until
   answered, shown on every verdict.
5. **A served model on Hugging Face** (`distill.deploy.served-on-hugging-face`) costs by the hour while it is up.
   Recommendation: Jobs first for every batch; the endpoint only when a person asks for a model to be reachable from
   another device, stopped when idle, always under the caps.
6. **Full fine-tune of a vision model**: offered on every place that holds it, or only on a cluster? Recommendation:
   wherever the memory holds it, with its cost beside the adapter's; the adapter stays the default.
7. **A hosted teacher for line finding.** The table says a hosted model's line boxes are too coarse to teach a line
   finder, so the lesson is the person's corrections of the base line finder. To be measured on the first project before
   it is relied on.
