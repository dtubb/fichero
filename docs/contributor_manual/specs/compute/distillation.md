# Compute — Teaching small models from big ones — Design Spec (#5336)

> Milestone: remote-compute
> Manual: TBD — a section, "Making your own model", explaining how a project turns a big model's
> work and its people's corrections into a small model that runs on their own Mac, how to tell
> whether the small one is good enough, and when Fichero still asks the big one.
>
> Design-led (Testing Constitution). **Status: DRAFT.** Builds on `jobs-and-fine-tuning.md`
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

## Prior art / best practices

- **Knowledge distillation** (Hinton et al. 2015): a student learns from a teacher's soft outputs.
  That needs the teacher's probabilities, which only open models give. A hosted model gives text,
  so learning from its outputs is **sequence-level distillation**, that is, training on its labels
  (Kim and Rush 2016), and in practice on *checked* labels.
- **Rationale distillation:** "Distilling step-by-step" (Hsieh et al. 2023) trains a small model to
  give the teacher's reasons as well as its answer, and gets better results from less data. This
  is #4642's "a model that says why".
- **Self-training and pseudo-labelling:** a model labels unlabelled data, and only its confident
  labels are kept (Noisy Student). Confidence thresholds and agreement between several teachers
  decide what is kept.
- **Active learning:** people correct what the student is least sure of first, so every
  correction teaches most.
- **Cascades and routing:** try the cheap model, and escalate to the expensive one when
  confidence is low (FrugalGPT, model cascades). Measured per job and per page kind.
- **The HTR field's practice:**
  - Kraken and eScriptorium train small recognisers from a few hundred corrected lines, and
    fine-tune a base model per manuscript. Transkribus does the same with its Super Models
    fine-tuned per collection.
  - TrOCR and small vision-language models (Florence-2, SmolVLM, Qwen2-VL-2B, PaliGemma) can be
    fine-tuned with LoRA.
  - YOLO detectors train from a few hundred boxed pages.
- **Small enough to ship:** LoRA adapters, quantisation to 4 or 8 bits, and MLX for Apple silicon.
- **Synthetic data:** text rendered in historical or project fonts, with augmentation, gives a
  recogniser a start for a new script before people have corrected much (the font work in
  `languages-scripts-signs.md`).
- **Terms of use.** Several hosted-model providers forbid using their outputs to train models
  that compete with them. Whether a teacher's outputs may train a student is a licence fact,
  checked before training. It is not an afterthought.

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
   reasons as well, where the teacher gave them and the job keeps them. The split is by document,
   never by line (`source.train.split-by-manuscript`).
5. **Train.** On the Mac for small jobs, on a cluster for larger ones (`compute.job.*`,
   `compute.tune.*`). The student's card records its teacher, its set, its base model and every
   licence.
6. **Measure.** On held-out, human-checked pages, Fichero shows the student beside the teacher
   and beside people's corrections: character error rate, word error rate, detection precision
   and recall, per hand, per page kind and per sign (`source.train.measured`). It also shows speed
   and cost per page for both.
7. **Adopt where it is good enough.** The project sets a bar per job (for example, CER no worse
   than the teacher's plus one point). The student becomes the default **only for the scope where
   it clears the bar**, recorded on its card (`source.model.suits`). Elsewhere the teacher stays.
8. **Keep learning.** New corrections accumulate. Fichero says when there is enough new checked
   work to retrain, and the new student must beat the old one on the same held-out pages before
   it replaces it.

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

- `distill.job.any-model-job` — **[GAP]** (#5337) any model job in Fichero (layout,
  lines, reading, signs, entities, normalising, vectors) can be distilled from a teacher into a
  named small student.
- `distill.collect.sample-covers-scope` — **[GAP]** (#5337) the teacher's sample is
  proposed to cover every hand, layout and page kind in the scope.
- `distill.set.checked-only-by-default` — **[GAP]** (#4947) a training set holds people-checked work
  by default; unchecked teacher output is added only deliberately, and counted.
- `distill.set.keeps-reasons` — **[GAP]** (#4642) where the teacher gave its reasons, the set keeps them,
  and a student can be trained to give them.
- `distill.train.card-names-teacher` — **[GAP]** (#5337) a student's card names its teacher,
  set, base model and every licence.
- `distill.measure.against-people` — **[GAP]** (#5337) the student is measured on held-out
  checked pages beside the teacher and the people's corrections, per hand, page kind and sign,
  with speed and cost per page.
- `distill.adopt.within-bar` — **[GAP]** (#5337) a student becomes the default only for the
  scope where it clears the project's bar, recorded on its card.
- `distill.retrain.must-beat` — **[GAP]** (#5337) a retrained student replaces the old one
  only if it beats it on the same held-out pages.
- `distill.cascade.small-first` — **[GAP]** (#5338) a run uses the student first and sends
  only low-confidence pieces to the teacher or to a person, recording where each piece went.
- `distill.cascade.calibrated` — **[GAP]** (#5338) routing uses calibrated confidence,
  checked on held-out pages; an uncalibrated student is not routed on.
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
  of its base, set and teacher licences.
- `distill.runs-local` — **[GAP]** (#5240) an adopted student runs on the Mac through MLX, Core ML or
  Kraken, throttled like any background work.

## Test matrix

To be filled at approval. The fixtures are real corrected pages from the test corpus, with a tiny
teacher stand-in that records its calls, so the loop is tested without a hosted model. The
measurement and the cascade's routing are pinned with known confidences and outcomes.

## Open questions

1. **First job to distil.** Line reading is the best-trodden path and has the most corrected data.
   Layout (YOLO) is second. **The first real customer is a researcher who has corrected a large
   number of VLM transcriptions** in his library: his corrections are exactly the checked
   ground truth step 3 asks for. Recommendation, in this order:
   1. Measure the current VLM's character and word error rates against his corrections, per hand
      and page kind (`distill.measure.against-people`). That alone tells him where the VLM fails.
   2. Build the set from his corrected lines, split by document.
   3. Fine-tune a small VLM of about 3 GB quantised (for example a 2–3B Qwen-VL-class model with
      LoRA), with a Kraken student beside it. **Where it trains, most realistic first:**
      - ACENET or another Digital Research Alliance of Canada cluster, as a Slurm job
        (`remote-compute.md`, `compute.job.*`);
      - a rented GPU through Hugging Face Jobs (the `gpu` image in `linux-server-image.md`);
      - a Mac with 32 GB or more through MLX, for the smallest runs.

      The trained adapter comes back to the Mac and runs there, quantised (`compute.tune.convert-for-mlx`).
   4. Adopt it only where it clears the bar.

   His corrections made before the page model (edits of the stored page text) count only after
   their pages convert (#5222), so conversion comes first.
2. **The default bar** for adopting a student: relative to the teacher (no worse than its CER
   plus one point) or absolute (CER under 5%)? Recommendation: relative, shown with the absolute
   number.
3. **Cascade default:** on for adopted students, or opt in? Recommendation: on, because the
   alternative silently accepts unsure output, and the run report shows what escalated.
