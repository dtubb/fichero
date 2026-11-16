# Final HANDOFF: lane-onboard (2026-11-02, wrap-up)

Branch `lane-onboard`, three batches in order: 97f8157460 (wide onboarding, recipe designer, activity), 1e55762510 (+ engine budget),
the last batch (+ one cap-pause path, Swift budget, parked notes, this file). All Swift here is **uncompiled**: the intake build rung is
its first compile. Engine tests were run per step (one pytest at a time); the full suite was not.

## Built (engine and app halves, by spec line)
- Wide onboarding: condition of the pages, How page and its card, defaults table, suggestions list (incl. Leave Out), risks and chain line,
  try keep/adopt/Start-adopts (adoption A/B), Accept all N, try label outside Set Up, compare keys/compact pager, untied remainder,
  what-to-check (engine + Read card), cloud default for Translate/Names/Statements/Catalogue (#6233).
- Activity: live block stages/ETA/cost, failed pages paged, one log line per page, one row per run, background-line ETA basis, one-bar view-model.
- Budget (#6295, #6294): estimate basis per step and learned from booked usage; typed `fixes[]` and dearest step on a cap refusal;
  `StartRequest.run_cap_usd` held with the project caps (`spend` run-cap.json); `run.change_cap` audited action (Undo restores);
  `proposed_run_cap_usd`; cap route takes `run_cap_usd` and checks the whole request before writing; one cap-pause path
  (`spend._STOPPED_AT_CAP` records the caps; `runner.resume_capped_runs` -> `pause_recipe` = the one Resume); Stop here is the run's Stop;
  Ready shows "This run, at most" (`RecipeRunCapField`, `BudgetBlock`).

## Open items (none is started; each with its issue)
- Text-step Batch API (#6233): PARKED. Page reads batch (seam in `llm.vision` only). Capture stand-ins + `is_capturing()` guards exist only in
  `vision_base` and `observability/episodes`, so capturing a text step could save junk readings. Order: guard every text tool's write path ->
  seam on `chat`/`chat_structured`/`translate_text` -> Translate -> structured steps -> real-key run. Also: lane width at the provider's limit.
- Ceilings (#6076, #6212, #4987): wait on the measured table (M4 run).
- Hugging Face cap line in the Budget block (#6295): the plan carries no HF cap yet.
- "Change the model for <step>" button into the finder (#6295, `designer.budget.refusal-offers-the-fix`): `BudgetBlock.changeModelStep` is read;
  nothing opens `RecipeStepsView.FinderStep` from the cap row. `BudgetRefusalFixTests.swift` not written. `CloudCapFix` still derives raise amounts
  from `needed_*` in the app rather than `fixes[]`.
- Budget block drawn as ONE block above Start with the basis rows inside (#6295, `designer.budget.beside-the-estimate`).
- `CloudCapChangeView` text "Raising a cap does not resume a paused run: use its Resume" is now wrong: a raise resumes (#6295).
- A step that ends with a cap sentence outside a run (no run id to pause) still fails, as before (#6295).
- `project.set_budget` action name: judged unneeded (`project.save_setup` and `run.change_cap` are audited).
- Three Swift readers still to wire, each listed in `scripts/check_endpoint_coverage_matrix_known_gaps.json` (pinned; one change approved by the
  manager): `GET /api/recipes/defaults` (#6052), `GET /api/recipes/chain-risk` (#6052), `GET /api/activity/jobs/{job_id}/failed-pages` (#5960).
  Generated names: `recipeDefaultsApiRecipesDefaultsGet`, `chainRiskApiRecipesChainRiskGet`, `getRunFailedPagesApiActivityJobsJobIdFailedPagesGet`.
- Activity, parked for a measurement run (M4 iMac/Air): 1.8, 1.10, 1.12, 1.13 and 4.2-4.4 (#5931, #5929, #5956, #6236, #6192, #6233, #5939, #6178);
  the exact commands are in the section "ACTIVITY: parked ..." of the lane's working handoff (gitignored; copied below).
- Activity 4.1 (#5359: the Mac's own work as library job rows) and 4.5 (#5376: progress written on purpose): five-line design notes in that file, no code.
- Drawing NOW / UP NEXT / DONE in the Activity window (`activity.window.now-upnext-done-today`; the view-model `ActivityOneBar` exists), `activity.window.acts-on`, 3.3 folder steps.
- Wide: 10.1 Inspector try label, `wide.compare.one-view-from-the-pager`, `replaces-the-captions`, price on the first Compare button,
  `wide.release.solid-per-step` (manager's).

## Measurement commands (verbatim from the lane's working handoff; quiet machine, one pytest at a time, PYTHONPATH=fichero-server/src)
- 1.8: `pytest fichero-server/tests/unit/jobs/test_pages_at_once_sized_from_the_machine_5931.py` (to write) + N x T sweep with `fichero-server/scripts/bench_same_model_pages.py` on 20 Kraken pages.
- 1.10: `pytest fichero-server/tests/unit/jobs/test_compute_fit_learned_from_runs_5931.py fichero-server/tests/unit/knowledge/test_spacy_threads_one_pipeline_each_5956.py fichero-server/tests/unit/llm/test_mlx_one_model_batched*.py` (to write) + the same sweep per engine.
- 1.12: `pytest fichero-server/tests/unit/knowledge/test_names_step_writes_one_batch_per_page_6236.py fichero-server/tests/unit/importers/test_opencv_threads_one_page_a_task_6192.py` (to write) + a 100-page Names run timed before/after.
- 1.13: `pytest fichero-server/tests/unit/remote_read/test_scale_out_batches_6233.py fichero-server/tests/unit/remote_read/test_sizing.py fichero-server/tests/unit/remote_read/test_slurm_target.py`; the Batch leg needs a real provider key; ACEnet needs the cluster.
- 4.2: `pytest fichero-server/tests/unit/jobs/test_model_order_5939.py fichero-server/tests/unit/jobs/test_one_model_at_a_time_on_the_lane.py`, then a 2-model recipe over 100 pages watching model loads.
- 4.3: `pytest fichero-server/tests/perf/test_recipe_run_100_pages.py` on a real machine + `scripts/bench_same_model_pages.py` (`engine.kraken-page-time-is-seconds`, #6178).
- 4.4: `pytest fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py` + a 100-page run with 2 then 3 workers.
