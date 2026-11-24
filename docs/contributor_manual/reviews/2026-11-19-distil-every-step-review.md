# Review: the model loop on every recipe step (2026-11-19)

The owner's goal, in our words: at every step of a recipe a person can run the step with a big hosted model as a
teacher, correct the result so the corrections are ground truth, train a small model for that step from both (by
fine-tuning, by an adapter, or with every weight; with the teacher's reasoning where there is any), have it scored
against the step's current model on held-out corrected pages before it may replace it, run it on any Mac from 8 GB up,
on Hugging Face or on a cluster, and publish it with its card. The UI is the Models and Cluster window.

Paths are under `fichero-server/src/fichero_server/` unless they say otherwise. Read on 2026-11-19; nothing was run for
this review except the spec guards.

## 1. Top findings

1. **The loop was already specified, three times, for one step.** `compute/distillation.md`,
   `compute/jobs-and-fine-tuning.md` and `compute/training-and-evaluation.md` each described teacher, set, training,
   scoring and adoption, with two tables of "what each kind of model needs" and three adoption rules. It is built for
   ONE row: reading a line. Every other step is prose.
2. **Three adoption rules disagreed.** "Within the project's bar of the teacher" (`distill.adopt.within-bar`), "beats
   the current choice by more than the noise band" (`training.ab.beats-current-by-noise-band`,
   `compute.tune.adopted-by-the-recipe`) and "must beat the old one" (`distill.retrain.must-beat`); the band itself was
   0.5 CER in one spec, one point in `recipes/bakeoff.py` and 0.005 in `training/reasons_ab.py`. Now one gate
   (`distill.gate.one-rule`) with two arms, and the band is the project's one number.
3. **YOLO ships by a side door.** Ultralytics is not a declared dependency and is in no lock file. It reaches a Python
   only through the bundle step (`[tool.fichero.mlx_bundle]` in `fichero-server/pyproject.toml`, installed by
   `scripts/install_mlx_into_engine_bundle.py`); `scripts/setup_venv.sh` runs that step for a development environment
   and checks the import. An environment made any other way lacks it, and no test notices: the detector and the trainer
   are stand-ins in every YOLO test. That is what the runtime matrix reported. The specs also contradicted the code:
   `compute.tune.yolo-layout` said GAP while `training/yolo_local.py` trains a detector on this Mac, and the "What exists
   today" list in `jobs-and-fine-tuning.md` still said nothing trains.
4. **Kraken on Hugging Face is nearly all built and has never been closed into a loop.** Reading and training both run
   as Jobs; what is missing is the score at landing, the gate, the caps on a training start, and a recorded real run
   (section 4).
5. **Corrections as ground truth exist for two kinds only**: a person's line readings (`training/kraken_set.py`) and a
   person's regions (`training/yolo_set.py` `persons_regions`). Corrected line geometry, the case the owner named (500
   pages of lines), trains nothing: there is no `ketos segtrain` call.
6. **Nothing publishes a model.** The only upload is a private dataset (`training/bakeoff_lines.py`
   `push_private_dataset`). The publishing rules were already written (`compute.publish.*`) and are sound: private by
   default, public asked each time, a model from data that may not be released never publishable (built:
   `training/project_models.py` `make_global`).
7. **The window had no loop in it.** `ui/models-and-compute-window.md` listed trained models as rows and left training
   on a folder's menu. It had no per-step view, no verdict, no publish state, and no per-model run settings.
8. **Not specified before today:** a full fine-tune (every weight of a vision or language model), a served model on
   Hugging Face (no code, no line), a teacher for any step but reading, a model's run settings, a published model found
   from another Mac, the card saying what the model beat.

## 2. What is built

| Stage | Built | Where |
| --- | --- | --- |
| Teach | a hosted model reads each line Kraken found; a reasons job per checked line; every call is one episode with its prompt, output and thinking; a provider's batch for a recipe step | `workflows/tools/` (Transcribe, `lines_read_by: "model"`), `training/reasons.py`, `training/reasons_job.py`, `observability/episodes.py`, `remote_read/cloud_batch.py` |
| Correct | a person's readings and regions become sets; flagged lines left out; a person's verdict outranks a model's; held-out pages never written to a set | `training/kraken_set.py`, `training/yolo_set.py`, `training/line_pairs.py` |
| Train | a Kraken reader on Hugging Face Jobs and on this Mac; a vision LoRA on Hugging Face Jobs, converted for MLX on landing; a YOLO region detector on this Mac; a resumable Slurm wrapper (tested with a stub trainer) | `training/job.py`, `training/hf_jobs.py`, `training/hf_kraken_train.py`, `training/local.py`, `training/hf_vision_lora_train.py`, `training/mlx_landing.py`, `training/yolo_local.py`, `training/resumable.py`; routes in `api/routes/training.py` |
| Evaluate | one evaluation job on the local model lane, the one CER under four policies, scores appended to the card atomically; adoption past the band for a Kraken reader; the reasons A/B | `training/evaluation.py`, `training/reasons_ab.py`, `core/atomic_json` |
| Run anywhere | Kraken's line finder and reader, or a trained vision model's transformers build, as shards on Hugging Face Jobs or Slurm, landing idempotently; a card with an MLX build and a transformers build | `remote_read/runner.py`, `remote_read/job.py`, `remote_read/slurm_target.py`, `training/landing.py`, `training/mlx_landing.py` |
| Publish | a model lives in its project, is backed up with it, can be made global; never-publishable is kept | `training/project_models.py` |
| The window | the engine's one list of models and places | `workflows/activity_models.py` (`GET /api/activity/models`) |

Not built at all: training Kraken's line finder, spaCy, a text model, Tesseract; YOLO off the Mac; a teacher for
regions, normalising, names or claims; a full fine-tune; a served model on Hugging Face; any model upload; the loop
anywhere in the app (the training routes have no caller in the app).

## 3. Contradictions, and how the rewrite settles them

| Was | Now |
| --- | --- |
| Three adoption rules, three noise bands | `distill.gate.one-rule`; the band is `training.regression.noise-band-one-number` |
| "Every student must run on a 16 GB Mac" against "8 GB is the floor" | 8 GB is the floor; a model too big says where it fits |
| "On the Mac where it fits" against "Hugging Face first" against "nothing trains here by default" | the person chooses from one compared table; this Mac is offered, never the default; a recipe is proven on Hugging Face before a cluster |
| Two per-kind tables (which jobs; best practice) | one table in `compute/distillation.md`, "One loop, every step", with a Built column |
| `compute.tune.yolo-layout` GAP; "no training code" | PARTIAL, citing the test that exists; the list of what trains is current |
| Corrections-are-data written twice | `distill.scale.everyday-corrections-are-data` owns it and now names geometry; `training.flow.every-correction-is-data` is the sheet's counts |
| Training starts from a folder's menu only; the window shows results | one sheet, opened from either; the window's Recipe steps rows are the loop's UI |
| "Models and Compute" | the owner's name, Models and Cluster; file name and ids unchanged |

Left as they are, and worth a later pass: `compute/remote-compute.md` repeats rulings as a log (history, not
behaviour); `runtime.yolo.none-yet` keeps a stale id for a runtime that exists; `source/recipe-designer.md` Stage 19
(Teach as you go) is the setup door to the same loop and was not touched.

## 4. Kraken on Hugging Face: built, missing, and what a first real run needs

Built:
- **The place**: `training/hf_jobs.py` `HfJobsTarget`: a private bucket in the person's account, `send`, `submit`,
  `statuses` (one call a round), `fetch`, `cancel`; `check_token` refuses a token without `job.write` and
  `repo.write`; `price_per_hour` read before the start; a time limit always sent (`DEFAULT_TIMEOUT`, 4 h;
  `DEFAULT_FLAVOR`, `t4-small`).
- **Training**: `training/hf_kraken_train.py` (`ketos train` from a base reader, constant schedule, batch by GPU);
  `training/job.py` (the `train-a-model` job; `POST /api/training/kraken`; stop at every phase; the places gate);
  `training/landing.py` (the reader lands with a card naming base, set, held-out pages, job and place).
- **Reading**: `remote_read/runner.py` (Kraken's line finder, then a Kraken reader, one PAGE file a page) and
  `remote_read/job.py` (shards, resend only the failed, idempotent landing, the monthly cap read by `_hf_spend`).

Missing:
- the held-out pages stay home and nothing scores them at landing: the evaluation job exists but is started by hand;
- no gate before the model can be used (`distill.gate.one-rule`);
- a training start is not checked against the caps as price times time limit; a cap of $0 only holds the offer
  (`recipes/train_offers.py`);
- the line finder is not trained anywhere (`compute.tune.kraken-segmentation`);
- the card does not name its teacher (`distill.train.card-names-teacher`);
- one trainer in three places is not proven (`compute.tune.one-trainer-three-places`), and there is no recorded real
  run in the repository since the first notebook-corpus runs made by API.

Built since (hf-kraken-1, against a fake Hub; no Job was submitted):
- a training start is checked against the project's monthly cap as the hardware's listed hourly price times the time
  limit, plus what this month's Jobs can already cost; a $0 cap, an unlisted price or an unreadable limit refuses in
  words before anything is queued or sent (`training/job.py` `_within_the_cap`);
- landing starts the evaluation job on the held-out pages and records its id on the row (`held_out_score`); with no
  held-out pages, or no person's reading on them, the row says "not measured" and why; the card entry carries CER by
  policy, pages read and lines scored;
- the evaluation writes the gate's verdict on the card (`training/gate.py`: better by N points on M pages, too close
  to call, worse: kept, not offered, not measured), and the catalogue says it beside the reader;
- the card carries `taught_by`, its teacher in words.

What the first real run will do and cost (dry-run reasoning only, nothing submitted):
1. Start refuses unless the cap is above $0 and `price x 4 h` (the default limit) fits what is left of the month.
   `t4-small` is read from the service at start; at $0.40 an hour (the figure the tests' fake Hub uses, not a
   measured price) the most one training can cost is $1.60, so a cap of $5 covers it with room for a second try.
2. The set goes to a private bucket in the token owner's account, the trainer runs as one Job on `t4-small`, the
   reader comes home and lands inside the project's folder, never as a default.
3. Landing queues one local evaluation job (no Hugging Face cost): the reader and the downloadable readers on this Mac
   read the held-out pages; the card gains the CER, the lines scored and the verdict. The verdict is "not measured"
   until a downloadable reader is on this Mac and at least 15 held-out pages were read.
4. A reading run of 20 pages is one shard Job per shard sent, each at its 2 h limit: the cap check counts every try,
   so the most it can add is shards x tries x price x 2 h.
5. Needed from the owner, unchanged: a fine-grained token (write to the owner's repositories, Jobs), billing enabled
   for Jobs, a cap above $0.

A first end-to-end test needs from the owner: a fine-grained Hugging Face token with write to his own repositories and
to Jobs; billing enabled for Jobs on that account; and a spending cap above $0 on the test project (a few dollars
covers a `t4-small` run inside its limit). Then, on the named machine: 20 public test pages segmented and read by a
Job and landed once; a reader trained by a Job from their lines; its held-out CER on its card with the gate's verdict;
spend under the cap; a start with the cap at $0 refused before anything is sent.

## 5. Build order (each step one worker)

The two runtime steps come first and can run side by side.

| # | Step | Spec and step | Size |
| --- | --- | --- | --- |
| 1 | YOLO runs for real wherever the engine runs: the import made certain, find-regions on the local ML lane, the device measured, the matrix row green on the 8 GB Mac | `ai/local-runtimes.md` Step 2.1 | S |
| 2 | Kraken on Hugging Face end to end, for real: read as a Job, train as a Job, scored at landing, under the cap | `compute/distillation.md` Step 2.1 (with `compute/jobs-and-fine-tuning.md` Step 1.1) | M |
| 3 | The one gate, for readers and detectors | `compute/distillation.md` Step 2.2 | M |
| 4 | The reader's loop closed: the sample, trust levels on the set, rounds that stop on evidence | `compute/distillation.md` Steps 1.1 to 1.3 (what is left of them) | M |
| 5 | One answer per step: the loop's state from the engine | `compute/distillation.md` Step 2.3 | M |
| 6 | The line finder trained from corrected lines, scored by lines found | `compute/jobs-and-fine-tuning.md` Step 1.2 (`compute.tune.kraken-segmentation`), `training.eval.lines-found` | M |
| 7 | The layout row: YOLO trained off the Mac, scored by overlap, gated | `compute/jobs-and-fine-tuning.md` Step 1.2 (`compute.tune.yolo-layout`), `training.eval.layout-overlap` | M |
| 8 | A teacher for any step, its reasoning kept | `compute/distillation.md` Step 2.4 | M |
| 9 | Names and normalising trained and scored | `compute/training-and-evaluation.md` (`training.propose.names-tagger`, `training.eval.names-precision-recall`) | M |
| 10 | Adapter or full fine-tune; a served model on Hugging Face | `compute/distillation.md` Step 2.5 | M |
| 11 | The window's Recipe steps rows, verbs and verdict | `ui/models-and-compute-window.md` Step 5.1 (after its Stage 1) | M |
| 12 | A model's run settings | `ui/models-and-compute-window.md` Step 5.2 | M |
| 13 | Publish: the rehearsal and the card | `compute/jobs-and-fine-tuning.md` Step 2.1 | M |
| 14 | Publish for real, and the model found from another Mac | `compute/jobs-and-fine-tuning.md` Step 2.2 | M |
| 15 | Training on a cluster for real (the resumable wrapper wired to the trainers) | `compute/jobs-and-fine-tuning.md` Step 1.3 | M |

## 6. Open, for the owner

The four questions added to `compute/distillation.md` (the bar; a served model's cost; where a full fine-tune is
offered; whether a hosted model can teach line finding at all), and one here: no issue was filed for the new lines;
they cite the nearest open issues (#5337, #5941, #5971, #6588, #5525, #6675) until the manager files their own.
