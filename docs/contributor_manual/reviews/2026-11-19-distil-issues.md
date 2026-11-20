# Issues to file for the model loop (2026-11-19)

One issue per build-order row of `2026-11-19-distil-every-step-review.md` section 5. Each body names the spec step that
owns the acceptance text; read that step before starting. Until these are filed, the new lines cite the nearest open
issues (#5337, #5941, #5971, #6588, #5525, #6675). When an issue is filed, replace that citation on its step with the
new number. File them in order; "Depends on" is the earlier row.

## 1. YOLO runs for real wherever the engine runs

Body: the region detector is imported in every environment the engine runs in (today only the bundle step installs
Ultralytics, and every YOLO test uses a stand-in); find-regions is a job on the local ML lane, taking its turn with the
other heavy models; the device is chosen by measurement on the fixture; the runtime matrix's YOLO row is green on the
8 GB Mac. Spec: `ai/local-runtimes.md` Step 2.1 (`runtime.yolo.imports-wherever-the-engine-runs`,
`runtime.pytorch.device-chosen`). Test to write: `test_yolo_runs_for_real.py`. Size S. Nearest open issue: #5525.

## 2. Kraken on Hugging Face, end to end and for real

Body: read as a Job, train as a Job, the held-out score written on the card at landing, the training start checked
against the project's and the app's caps as price times time limit, the card naming its teacher. Acceptance on the named
machine with the owner's token: 20 public pages segmented and read by a Job and landed once; a reader trained by a Job
lands with its held-out CER and the gate's verdict; spend under the cap; a start with the cap at $0 is refused in words
before anything is sent. Needs from the owner: a fine-grained token with write to repositories and Jobs, billing on for
Jobs, a cap above $0. Spec: `compute/distillation.md` Step 2.1 with `compute/jobs-and-fine-tuning.md` Step 1.1. Test to
write: `test_distil_kraken_on_hf.py`. Size M.

## 3. The one gate, for readers and detectors

Body: one adoption rule with two arms and the project's one noise band replaces the three rules and three bands
(`training/reasons_ab.py`, `recipes/bakeoff.py`, the evaluation job). A retrained model must beat the old one. Spec:
`compute/distillation.md` Step 2.2 (`distill.gate.one-rule`, `distill.retrain.must-beat`). Test to write:
`test_one_gate.py`. Size M. Depends on 2.

## 4. The reader's loop closed: the sample, trust levels, rounds that stop on evidence

Body: the teacher labels a sample that covers the scope; the set keeps each line's check level; a model pass is never
paid for twice; rounds stop when the score stops improving; the student runs locally. Spec: `compute/distillation.md`
Steps 1.1 to 1.3, only what is not yet built. Size M. Depends on 3.

## 5. One answer per step: the loop's state from the engine

Body: the engine answers, for each recipe step, the teacher, the corrections counted as ground truth, the trained model,
its verdict and its place; the app draws the answer and decides nothing. Spec: `compute/distillation.md` Step 2.3
(`distill.loop.one-answer-per-step`). Test to write: `test_step_loop_answer.py`. Size M. Depends on 3.

## 6. The line finder trained from corrected lines

Body: `ketos segtrain` as a Job from corrected line geometry, scored by lines found, gated by the one gate. Spec:
`compute/jobs-and-fine-tuning.md` Step 1.2 (`compute.tune.kraken-segmentation`, `training.eval.lines-found`). Size M.
Depends on 3.

## 7. The layout row: YOLO trained off the Mac

Body: the region detector trained on a Hugging Face Job from corrected regions on edited images, scored by overlap,
gated. Spec: `compute/jobs-and-fine-tuning.md` Step 1.2 (`compute.tune.yolo-layout`, `training.eval.layout-overlap`).
Test to write: `test_yolo_trains_on_edited_images.py`. Size M. Depends on 1 and 3.

## 8. A teacher for any step, its reasoning kept

Body: a hosted model can teach any recipe step, not only reading; its thinking is kept in the ledger for every call.
Spec: `compute/distillation.md` Step 2.4 (`distill.loop.teacher-any-step`, `distill.loop.thinking-kept-every-step`,
`distill.reasoning.traces-in-the-ledger`). Tests to write: `test_teacher_any_step.py`,
`test_thinking_kept_every_step.py`. Size M. Depends on 5. Open question for the owner: whether a hosted model can teach
line finding at all.

## 9. Names and normalising trained and scored

Body: a names tagger and a normaliser trained from corrections and scored by precision and recall. Spec:
`compute/training-and-evaluation.md` (`training.propose.names-tagger`, `training.eval.names-precision-recall`). Size M.
Depends on 3.

## 10. Adapter or full fine-tune; a served model on Hugging Face

Body: the person picks an adapter or every weight; a model can be served on Hugging Face with its cost shown first.
Spec: `compute/distillation.md` Step 2.5 (`distill.train.lora-or-full`, `distill.deploy.served-on-hugging-face`). Tests
to write: `test_lora_or_full.py`, `test_served_on_hugging_face.py`. Size M. Depends on 3. Open questions for the owner:
a served model's cost; where a full fine-tune is offered.

## 11. The window's Recipe steps rows, verbs and verdict

Body: the Models and Cluster window shows each recipe step as a row with its loop state, the verbs, the verdict in the
Inspector and the published state, drawn from the engine's answer. Spec: `ui/models-and-compute-window.md` Step 5.1
(`models.loop.*`). Test to write: `ModelLoopRowTests.swift`. Size M. Depends on 5 and the window's Stage 4.

## 12. A model's run settings

Body: per-model run settings owned by the engine and drawn in the Inspector. Spec: `ui/models-and-compute-window.md`
Step 5.2 (`models.run-settings.per-model`). Tests to write: `test_model_run_settings.py`,
`ModelRunSettingsTests.swift`. Size M. Nearest open issue: #6588.

## 13. Publish: the rehearsal and the card

Body: a dry run builds the files and the card in a scratch folder with no network, shows what would be sent, is private
by default and says what the model beat; a model whose training data may not be released is refused in words. Spec:
`compute/jobs-and-fine-tuning.md` Step 2.1 (`compute.publish.dry-run-first`, `compute.publish.card-says-what-it-beat`).
Tests to write: `test_publish_dry_run.py`, `test_published_card_says_what_it_beat.py`. Size M. Depends on 3.

## 14. Publish for real, and the model found from another Mac

Body: the publish is separate and asked each time, public needs a yes each time, is audited and says what cannot be
undone, uses a narrow token, needs a matching dry run, and the model is found from another Mac. First real publish: a
private repository in the owner's account on the named machine. Spec: `compute/jobs-and-fine-tuning.md` Step 2.2.
Tests to write: `test_publish_needs_a_matching_dry_run.py`, `test_published_model_found_elsewhere.py`. Size M. Depends
on 13.

## 15. Training on a cluster for real

Body: the resumable wrapper wired to the real `ketos` and LoRA trainers so a Job near its limit checkpoints, re-queues
under the same id and resumes. Spec: `compute/jobs-and-fine-tuning.md` Step 1.3 (`compute.tune.survives-the-time-limit`).
Size M. Depends on 2. A recipe is proven on Hugging Face before a cluster.
