# Runner review 2: security, speed and memory (measured), tokens and batching, Kraken, training and ground truth (2026-11-18)

> The reviewer, for the owner. Companion of `2026-11-18-runner-reliability.md` and its plan. Read against
> `origin/integration` d01807cd12 (the code; file and line) and measured on the iMac (M4, 4 performance cores, 24 GB,
> macOS 26.7.3) against `origin/integration` 49a400161 in a temp worktree under `/tmp` with the rebuilt venv; nothing on
> the Pro, nothing in the owner's checkout. Paths are relative to `fichero-server/src/fichero_server/` unless they start
> with `fichero/`, `scripts/` or `docs/`. Everything not marked MEASURED is read, not run. Three read-only surveys fed the
> code sections; the measured numbers are the driver logs under `/tmp/fichero-perf-out` on the iMac (kept until the owner
> says delete).

## The ten things that matter most

1. **A Google API key is written to the engine log in clear.** `api/routes/ai/provider_keys.py:551` puts the key in the
   URL's query (`?key=`), and so does `provider_models.py:573`; httpx logs every request URL at INFO and the root logger
   is INFO (`__main__.py:37-39`), which the app captures as `engine.log`. HIGH. Header `x-goog-api-key` and
   `logging.getLogger("httpx").setLevel(WARNING)`.
2. **The YOLO layout model is an unpinned pickle.** `llm/yolo_runtime.py:81` downloads `yolov11n-doclaynet.pt` with no
   `revision` and no digest and `:112` loads it with `YOLO(path)`; the code's own rule elsewhere is "never unpickle a
   repository" (`llm/trocr_runtime.py:6-8`). HIGH. Pin a commit, check a sha256, or convert to safetensors.
3. **No downloaded model is checksummed anywhere** (embeddings from `main`, `llm/local_models.py:511`; Kraken readers
   fall back to `main` and are checked by size only, `llm/kraken_runtime.py:258-259, 368`; the HF Job's base model loads
   `main` unless an adapter pins it, `remote_read/runner.py:141-142`). TrOCR (`trocr_runtime.py:70-129`) and Whisper/MLX
   (pinned commits) are the good pattern. MED.
4. **An editor can stop the owner's runs.** `activity.stop_all` and the per-run cancel are library-write checks, not
   owner-or-starter (`api/routes/system/activity.py:2265-2266`, `execution/jobs.py:3195-3211` "a person's runs too");
   the run record stores no starter to compare against (`api/main.py:2026-2041`). MED.
5. **A training set to Hugging Face is not "names only" and is never deleted.** `training/kraken_set.py:380-388` ships
   original file names, display names and `str(exc)` (which can carry a path), and full-resolution scans
   (`media/upright.py:64-68` copies bytes); `training/hf_jobs.py:228-229` syncs to a private bucket that nothing ever
   removes. MED, two fixes.
6. **Speed (MEASURED, §2):** 110 printed pages through Kraken on the M4 take **31.7 min** (3.8 s a page to find lines,
   12.2 s a page to read, 2 pages at once, 2.4 cores busy), the engine tree peaking at **7.9 GB**; the embedder was
   fetched and loaded TWICE during that Kraken-only run ("something let it go mid-run"). The perf suite's engine tests are
   fast (cold start 3.8 s, dense page 8.0 s, 200 searches 5.8 s, each under 1 GB); the recipes unit suite takes 17 min with
   six tests at exactly 60 s (real engine timers); the standard load leg itself cannot run on a fresh Mac (its home guard
   and the one-venv recipe's missing Kraken step, §2.1).
7. **Nothing is cached or batched for the cloud steps except the line read.** No `cache_control` anywhere
   (`ai.where.prompt-prefix-cached` [GAP] #5947); the result cache is in-process and FIFO-capped at 1,000
   (`llm/__init__.py:203-230`, #5949); the static instruction block (0.3-0.9k tokens) and the per-page known-entity list
   are re-sent on every page. Only `llm/line_reader.py` packs 16 lines (max 40) per call. The provider batch path exists
   (Anthropic, OpenAI, Gemini; `remote_read/cloud_batch.py:31`) but is taken only for `read-a-page`/`read-a-line` at
   100+ pages with one reader, never for names, statements or the catalogue, never for OpenRouter (which has no batch
   API), and it has never run against a real provider.
8. **Image size to the cloud is one number, not per provider.** `vision_base.py:3321` sends up to 2048 px (JPEG q95),
   while the node schema says 8192 (`:267-270`); no provider rule exists (`ai.where.image-sized-for-the-place` [GAP]
   #5948). The code's own planning note measured ~56k input tokens a page on Gemini (`recipes/start.py`), 15 times the
   258-per-tile rule: the cost table in §3 shows both.
9. **Kraken keeps per-character positions and the server cuts words from them, but the segmenter is fixed and the two
   shipped readers are a provisional pick** (`kraken_runtime.py:160-183`: "NOT a considered pick" for the owner's hand);
   a user's trained reader does become a card (`kraken-trained-<job>`) and is choosable; per-page segment and read
   timings are recorded nowhere in the perf baseline (`recipes-run.kraken.reliability-measured` [GAP]).
10. **Only two things train today** (the Kraken reader, on HF Jobs or this Mac; a vision LoRA on HF Jobs) plus YOLO
    regions on this Mac; Kraken segmentation, the embedder, spaCy, Whisper and the reviewer/judge steps have no trainer
    (§C). Ground truth is a pass-level flag with no app control and no sidebar listing (§D, and the new
    `specs/source/ground-truth.md`).

## 1. Security review of the runners

Severity: HIGH (a secret leaves or code runs that should not), MED (a boundary the design promises is not held), LOW,
OK. Fixes are one line each; the plan at the end files them.

### 1.1 Keys and tokens in logs, call logs and run records

| Finding | Where | Severity | Fix |
|---|---|---|---|
| Google key in a logged URL (`?key=`) | `api/routes/ai/provider_keys.py:551`, `provider_models.py:573`; httpx INFO under `__main__.py:37-39` | HIGH | header + silence httpx |
| Keychain write passes the key in argv (`-w <key>`; visible to `ps`) | `security/keychain.py:336-338` (#4818 still open) | MED | stdin (`-i`) or Security.framework |
| `security` resolved from PATH | `security/keychain.py:121` | LOW | `/usr/bin/security` |
| raw provider exception text to ERROR log and breaker state, unredacted | `llm/__init__.py:535`, `workflows/circuit_breaker.py:478` | MED | `redact(str(exc))[:300]` |
| run record stores `error` raw; redaction only at export | `workflows/activity_store.py:184-186, 294-295`, `workflows/tools/llm_base.py:1176-1181` | LOW | redact at write |
| `llm/failure.redact` misses bare-hex and vendor-prefixed keys (Mistral, Cohere, DeepL `:fx`, `pplx-`, `tvly-`, `jina_`) | `llm/failure.py:74-87` | LOW | add shapes + a test per provider |
| HF token: header only, no argv/env; whether the Job container gets it is the Hub's business | `training/hf_jobs.py:163-261` | LOW (verify) | job-scoped token |
| OK: bug report redacts all three parts (`api/routes/system/bug_report.py`); auth refusals log a 6-hex prefix (`api/auth.py:756-783`); second factor and key paths never logged (`remote_read/ssh_prompts.py:64`); no Swift log prints a key | | OK | |

### 1.2 What leaves the Mac, to each remote place, over what

| Place | What leaves | Over what | Finding |
|---|---|---|---|
| Cloud provider (plain call) | prompt + page image ≤ 2048 px JPEG q95, or 16-40 line crops ≤ 1600 px + a 768 px page context | HTTPS, SDK clients with `api_key=` headers | OK; gated by the project's yes (`llm/__init__.py:1305-1329`) |
| Cloud batch | the same, as a batch file; `custom_id` is the cache key, not content | HTTPS | OK; gated (`remote_read/cloud_batch.py:64`) |
| HF Jobs (read at scale) | `images/<sha256>.jpg` at 2000 px (EXIF dropped), `job.json` with document UUIDs, IIIF URLs, the prompt and card; no Mac path, no project name | HTTPS to a private bucket | OK (`remote_read/package.py:34-216`); `shutil.rmtree(out)` on an existing out dir, check callers (`:179`) |
| HF Jobs (training) | original file names, display names, `str(exc)`, FULL-resolution scans; the bucket is never deleted | HTTPS, private bucket | MED ×2 (`training/kraken_set.py:380-388, 333-349`; `media/upright.py:64-68`; `hf_jobs.py:228-229`, no delete) |
| Cluster (Slurm) | the read package, written with `cat > <quoted>` over ssh stdin | system `ssh`, ControlMaster, `StrictHostKeyChecking=accept-new` | OK; TOFU on the host key is LOW (`workflows/remote_jobs.py:595`) |
| Another Mac (transfer) | the package plus `records.json` carrying the sender's ABSOLUTE library path and hostname | HTTPS to `*.ts.net`, bearer, system CAs, no SPKI pin | MED (`transfer/remote.py:139, 176, 186`); LOW no pin (`transfer/machines.py:101-108`) |
| CLI agents (`claude -p`, `codex exec`, `ollama run`) | the prompt with page text as `context` | a local process that is a cloud service | MED: no egress gate on this path (`workflows/tools/cli_agent.py:90-94, 204`) |
| Two egress gates, not one | `llm/egress.project_allows_leaving` for model calls; `core/egress.check_egress` for DOI, Wikidata, geocoder, web, authority, machines | | MED: the CLI agent path and `recipes/discovery.py:1102` pass neither; `ai.where.one-egress-gate` |

### 1.3 Subprocess and shell construction

No `shell=True`, `os.system`, `bash -c` anywhere (OK). `build_ssh_command` quotes every argv and puts `--` before the
destination (`workflows/remote_jobs.py:574-606`). Findings: `#SBATCH --partition={config.partition}` and
`--account=`/`--job-name=`/`--output=` are f-strings of owner-entered fields with no character check
(`remote_jobs.py:111-120`, `remote_read/slurm_target.py:345`; a newline becomes a script line on the cluster; MED, only
the owner can set them); the MLX runtime installs `mlx-lm`, `mlx-vlm`, `mlx-whisper` with `pip install` at run time,
versions pinned but no hashes, no lock, `PIP_INDEX_URL` honoured (`llm/mlx_runtime.py:329-354`; MED; #4973); the cluster
key is made with an empty passphrase (`ssh_prompts.py:216`; LOW, 0600 in 0700); Whisper, landing, importers use argv lists
(OK).

### 1.4 Downloaded models and wheels

| Runtime | Pinned? | Checksum? | Pickle? | Finding |
|---|---|---|---|---|
| YOLO (`yolo_runtime.py:23, 81, 112`) | no `revision` | none | `.pt` pickle via `YOLO()` | HIGH |
| Embeddings (`local_models.py:511`; fastembed `db/embeddings.py:422`) | no | none | ONNX | MED |
| Kraken readers (`kraken_runtime.py:258-259, 368`; Zenodo via htrmopo) | `sha or "main"` | size only | `.mlmodel` (verify) | MED |
| HF Job base model (`remote_read/runner.py:141-142`) | only with an adapter | none | `use_safetensors=True` | MED |
| TrOCR (`trocr_runtime.py:70-129`) | commit required | none | refused | OK (the pattern) |
| Whisper, MLX (`whisper_runtime.py:76-126`; `mlx_model_store.py:113-234`) | commits | none | MLX loads safetensors | OK |
| spaCy pipelines (`local_models.py:164-283`) | version | none | data only; code suffixes refused | LOW |
| `trust_remote_code` | | | | none anywhere (OK) |

### 1.5 The local socket and the network API's auth on run and stop verbs

- Token file 0600, 256-bit (`api/auth.py:251, 404`); the bearer is checked on UDS too (`:521-537, 887`) (OK).
- **UDS socket mode never set**: `__main__.py:160-176` binds without `chmod`; the mode is the umask's. MED (defence in
  depth; the bearer still holds). `os.chmod(path, 0o600)` after bind.
- TLS mandatory on TCP with an SPKI pin the app checks (`__main__.py:476-480`, `security/remote_access_tls.py:90, 294-305`,
  `fichero/fichero/App/AppState/AppState+Heartbeat.swift:232-234`); no cookies, bearer only, so no CSRF surface
  (`api/main.py:1488-1500`) (OK).
- Run and stop verbs: `/api/activity/jobs/{id}/cancel`, `/retry`, `/pause-all`, `/continue-all`, `/stop-all` are
  library-write actions through the registry (`api/routes/system/activity.py:1656-1907`, `actions/registry.py:316-334`);
  the workflow-execution router checks per run (`api/routes/workflow_execution/__init__.py:21`); recipes Start is a
  write action (`api/routes/system/recipes.py:3020-3026`); HPC writes are owner-only (`api/routes/ai/hpc.py:210-474`),
  HPC reads open to viewers (LOW). **An editor can stop or pause the owner's runs and cancel training** (MED, finding 4).
- Login limiter is in-process only, 5 per window (`api/routes/auth/accounts.py:45, 326-331`); pairing codes 40 bits,
  10 min (`pairing.py:37, 440-444`) (LOW).

## 2. Speed, RAM and optimisation (MEASURED on the iMac)

Method: a detached worktree of `origin/integration` 49a400161 at `/tmp/fichero-perf-20261118`, the rebuilt venv
(`~/code/fichero/fichero-server/.venv`, Python 3.12.13), `FICHERO_BASE_PATH` under `/tmp`, `/usr/bin/time -l` around each
pytest run (wall, user, sys, maximum resident set), `--durations=15` for the slowest tests, cProfile of the dense-page
read and the recipes suite, 110 synthetic printed pages (2000×2800 JPEG, 40 lines each) for the load leg. The load leg
needed `HOME` under `/tmp` (the engine home guard, `tests/_engine_home_guard.py:56`) and a temp model store; it ran with
`FICHERO_LOAD_LEG_PURPOSES=transcribe` so the 4 GB embedder was not fetched. py-spy is not installed on the iMac and
installing into the venv was out of bounds, so the profiles are cProfile.

### 2.1 The perf suite and the unit suites

MEASURED on the iMac, 2026-11-18 15:38-16:27 (`/usr/bin/time -l` around each pytest run; RSS is the pytest process,
which IS the engine for the unit and perf suites, in-process). The machine was otherwise idle (load 1.5).

| Run | Result | Wall | CPU (user+sys) | Peak RSS | Slowest tests |
|---|---|---|---|---|---|
| `tests/perf/test_engine_cold_start_perf.py` | 1 passed | 6.6 s (test 3.8 s) | 5.8 s | 357 MB | the cold start itself |
| `tests/perf/test_dense_page_whole_read_perf.py` | 1 passed | 11.2 s (test 8.0 s) | 10.9 s | 902 MB | one cold whole-page read of a 20k-line page |
| `tests/perf/test_document_pipeline_perf.py` | 3 passed, **1 failed** (`documents.list` 768.8 ms vs best 9.8 ms: the ratchet, not a budget) | 6.8 s | 7.1 s | 905 MB | `test_document_list_100_images` 2.0 s |
| `tests/perf/test_search_workload_perf.py` | 1 passed | 9.0 s (200 queries 5.8 s) | 5.1 s | 617 MB | — |
| `tests/perf/test_recipe_run_100_pages.py` (the load leg) | **cannot run as written**: the engine home guard refuses both the real HOME and a temp HOME set for pytest (`tests/_engine_home_guard.py:56`, `REAL_HOME` is read from the same `$HOME`); and the rebuilt venv has no `kraken`, `htrmopo` or `psutil` (the one-venv recipe `scripts/setup_venv.sh` syncs `uv.lock` only; Kraken is the separate bundle step, `pyproject.toml` `[tool.fichero.kraken_bundle]`) | 0.9 s | — | — | see §2.3 for the run made another way |
| `tests/unit/recipes` | 2023 passed, **25 failed**, 5 xfailed | **17 min 16 s** | 12 min 27 s | **1.57 GB** | six tests at exactly 60 s each (the resume-after-a-quit waits: `test_every_stage_resumes_after_a_stop_1134.py`, `test_start_stop_restart_resumes.py`, `test_recipe_batches_to_spec.py` ×2, `test_folder_shows_steps_done.py`, `test_leave_out_account_in_the_run_status.py`); `test_pinned_model_gone_5364.py` 52 s |
| `tests/unit/jobs` | 723 passed, **2 failed** | 7 min 07 s | 3 min 38 s | 1.29 GB | `test_provider_share.py` stuck-provider case **120.8 s**; `test_one_model_at_a_time_on_the_lane.py` and `test_embed_off_the_reading_lane.py` 30 s each, both FAILED |
| `tests/unit/execution` | 47 passed | 28 s | 8 s | 565 MB | `test_close_pauses_running_work_6588.py` 17 s |
| `tests/unit/llm` | 1679 passed, **4 failed, 11 errors** | 2 min 39 s | 57 s | 1.28 GB | `test_a_download_survives_a_broken_connection.py` 59 s; the failures and errors are the venv's (`No module named 'htrmopo'` ×5, `es_core_news_sm` ×8), not the code's |

What the suites say:
- **The two jobs failures are the spec change of #6673.** `test_embed_off_the_reading_lane.py:69` and
  `test_one_model_at_a_time_on_the_lane.py` assert that an embed RUNS beside a Kraken page; `recipes-run.memory.one-heavy-model-in-sequence`
  now holds it. The tests contradict the spec and must be rewritten, not the rule.
- **Six recipe tests cost exactly 60 s each**: every one is a "lost with the engine, then resumed" case, and 60 s is the
  engine's real timer, not a stub: `GENTLE_START_SECONDS = 60.0` (one page at a time for a minute after a restart) and
  `ORPHAN_FIRST_GRACE_SECONDS = 60.0` (`execution/jobs.py:2733`); `PAUSED_LOOK_AGAIN_SECONDS` is only 5 s
  (`recipes/runner.py:1185`). Injecting the clock would take ~6 min off a 17-min suite. `test_provider_share.py`'s 120.8 s
  ("a stuck provider leaves room for another", two 60 s timers) is the same shape.
- **25 recipe failures** on a clean venv: the names seen in the profile run include `test_step_that_cannot_start_5684.py`,
  `test_variant_a_cost_before_the_run.py` ("builds the plan off the event loop") and `test_start_stop_restart_resumes.py`; some
  are the venv's missing extras, some may be real; the harness's gate on the iMac must say which (filed below).
- **Peak RSS of a unit suite is 1.3-1.6 GB** with no model loaded: the engine's import set plus DuckDB's budget
  (`duckdb_session.py:367` logs "2329 MiB each library ... budget 2457 MiB" at start of EVERY suite).

### 2.2 The slowest paths (cProfile, cumulative)

cProfile of the dense-page read under pytest (`/tmp/fichero-perf-out/dense_profile.txt`, 42.1M calls, 21.4 s with
profiling on; the test alone is 8 s):

| Cumulative | What | Where |
|---|---|---|
| 4.1 s | imports (`fichero_server.api.main` alone 2.3 s; 3,397 Pydantic model classes built, 1,006 FastAPI routes registered: 1.0 s) | `api/main.py:1`, pydantic `_model_construction.py:84`, fastapi `routing.py:961` |
| 3.8 s | **43,755 `uuid4()` calls** = 0.98 s in `posix.urandom` plus Python overhead | `uuid.py:723`, called from the segment writers |
| 3.4 s | **DuckDB `_set_limit`**: 4 calls at 0.86 s each, under `apply_memory_limit` → `_rebalance` → `rebuild_secondary_indexes` (3.41 s in ONE call) | `core/duckdb_session.py:324, 351, 386, 532` |
| 1.4 s | `Database.save` (2 calls) | `db/__init__.py:2392` |
| 1.2 s | 236,609 Pydantic `validate_python` calls | the hydration of rows |
| 0.77 s | `_hydrate_row` 46,510 calls, with **312,393 `_check_rect`** calls (0.69 s) | `db/__init__.py:8071`, `models/anchors.py:488` |
| 0.62 s | `jobs.first` (9 calls) | `execution/jobs.py:5646` |

Reading: of the 8 s the test takes, about 3.4 s is DuckDB rebuilding secondary indexes at open (`rebuild_secondary_indexes`,
the WAL-replay rule of `duckdb-wal-replay-breaks-indexes`), ~1 s is minting UUIDs one urandom call at a time (a batch
`os.urandom(16*n)` would make it ~0), and ~1 s is validating 46k anchors rectangle by rectangle. The engine's import cost
(2.3-4 s) is paid once per process, which is every unit test module under pytest's collection. The recipes-suite profile did
not land (`recipes.prof` was not written after the 19-min run; the driver's second cProfile pass is to redo with
`--profile-svg`-free output or `py-spy record` once installed).

### 2.3 The 100-page recipe run (Kraken segment + read on a temp engine)

MEASURED on the iMac, 16:31-17:04, through `fichero-server/scripts/e2e_recipe_run.py` (the same engine harness the perf
test uses, without pytest's home guard), in a temp venv at `/tmp/fichero-perf-venv` built by `scripts/setup_venv.sh`
plus the Kraken bundle step's packages (`kraken==7.1.1 --no-deps`, `htrmopo`, `torchvision==0.29.0`, …), `HOME` and the
model store under `/tmp`, purposes `transcribe` (find lines → leave out → read → find documents), 110 synthetic printed
pages, Kraken's segmenter and the shipped reader fetched into the temp store, no cloud key. Report:
`/tmp/fichero-perf-out/loadleg3/report.json`; engine log `uv_uds_899ebb.log`.

| Measure | Value |
|---|---|
| Run | **done**, no step failed; 1,904 s (31.7 min) for 110 pages; the whole script 1,938 s wall |
| CPU | 4,260 s user + 308 s sys over 1,938 s wall = **2.4 cores busy on average** (4 performance cores available; `pages_at_once` 2) |
| Peak RSS (largest process in the tree) | **7.93 GB**; the engine's own warning "engine RSS reached 6.3 GiB, past 25% of this Mac's 24 GiB" fired once |
| Find lines (Kraken segmenter), 110 pages | 422 s = **3.8 s a page of wall time**; the run's own median **14.6 s a page** (each page's own clock, pages overlapping) |
| Leave out | done, no per-page figure |
| Read each line (Kraken reader), 110 pages | 1,343 s = **12.2 s a page of wall**; median **46.9 s a page** |
| Find documents | 67.5 s, 0 pages (synthetic text; nothing to group) |
| Model loads | the engine log has **no `model-lane: loaded` lines**: the harness starts uvicorn with `--log-level warning` (`scripts/_engine_harness.py:220-224`), so the INFO lines `recipes-run.timing.slow-path-logged` promises are not written; only two WARNINGs survive: the RSS line and **"model loaded again: embedder BAAI/bge-m3, 561 s after its last load (load 2 in this engine, 3.7 s): something let it go mid-run"** |
| Memory per step | `steps[].memory` (the `recipes-run.memory.recorded-per-step` [OK] field) is **not in the run status the script saved**; the per-step RAM, swap and pressure figures could not be read back from the report |
| Health | not sampled by the script (the perf test samples it; it could not run, above) |

What this one run says:
- **Kraken on an M4 reads about 110 printed pages in half an hour: 3.8 s a page to find lines, 12 s a page to read them**,
  with 2 pages at once and ~2.4 cores busy. A 1,000-page box is ~4.5 hours; 100,000 pages is 19 days on one Mac: the
  scale-out spec (`compute/recipe-steps-at-scale.md`) is the right answer, and these are the first measured figures for
  `recipes-run.kraken.reliability-measured` and `#6076`'s table.
- **An embed ran during a Kraken-only recipe, and the embedder was unloaded and reloaded mid-run.** The transcribe recipe
  queued no embed, but the IMPORT before Start did (today's import-time behaviour, ruling 5 of `recipes-run.md` covers only
  a project whose recipe has started), the engine fetched bge-m3 (4 GB, over the network, in the middle of the run) and
  loaded it twice. The one-heavy-model-in-sequence rule held Kraken (no Kraken reload warning), but the embedder's own
  release and reload is exactly the "loading and unloading all the time" the owner asked about, now seen on a clean Mac.
- **The engine tree reached 7.9 GB** for Kraken (2 pages) plus the embedder plus DuckDB's 2.3 GiB budget: on a 16 GB Mac
  this run would page. The ceiling table (#6076) should start from 6.3 GiB engine RSS at 2 pages in flight.
- **The fan-out hands all 110 pages to the node in the same second** ("Node 'Detect Segments (Kraken)' … (1/110)" to
  (110/110) within 30 ms), as rows not bitmaps (`recipes-run.memory.fan-out-does-not-decode-ahead` [OK]); the lane then
  admits 2 at a time.
- **Three things kept this from being the standard load leg:** the perf test's home guard contradiction, the one-venv
  recipe's missing Kraken step, and the harness's WARNING log level hiding the model-load lines. All three are filed below.
  A hand run every night is not a gate; the test must run.

### 2.4 What the reading says about memory (code)

- One heavy model at a time and the embed lane waiting under Kraken are built and pinned
  (`execution/jobs.py:4641-4690`, `test_one_heavy_model_in_sequence_6673.py`); Kraken's resident cache is one segmenter and
  one reader template with a bounded copy pool (`kraken_runtime._RESIDENT`), idle-released after 120 s (`:1321`).
- `release_idle_models` frees EVERY idle embedder at once under pressure (`idle_seconds=0`); a write right after reloads
  it: the reload storm `engine-silent-failures.md` rows 1-3 recorded (389k lines) is one symptom.
- The throttle's first paging sample never holds and warn-level pressure alone never holds (`execution/throttle.py:99-137,
  206-220`); Kraken's need is a constant 2.5 GiB plus 1.5 GiB a page in flight (`kraken_runtime.py:511, 1362`), not a
  measurement (`recipes-run.memory.peak-ceiling-per-model-kind` [GAP] #6076).
- The engine records memory per step now (`recipes-run.memory.recorded-per-step` [OK]); the load leg's report is where
  the measured ceilings should come from (§2.3).

## 3. Tokens and batching

### 3.1 What is recorded

Per call: `_record_usage` (`llm/__init__.py:433-493`) books spend, appends to the run's usage and to the job row of the
lane slot (`execution/jobs.py:569`, `detail["usage"]`), so **tokens per page are on the page's job row**; cached-input
tokens are parsed (`llm/usage.py:173`) and priced; no image-token rule and no batch discount live in `usage.py`
(`spend.py:542-546` applies `BATCH_SHARE = 0.5` or the list's batch rate).

### 3.2 Prompts: what is repeated per page

| Step | Prompt | Static size | Repeated per page |
|---|---|---|---|
| read a page (vision) | `workflows/tools/handwriting.py:177, 262` | ~2.1k chars ≈ 530 tokens | the whole prompt and the page image |
| read a line (cloud) | `llm/line_reader.py:49` + page context `:60` | 540 + 240 chars ≈ 200 tokens | per call of ≤16 lines (`LINES_PER_CALL`, `:35`; max 40); the 768 px page context on EVERY call (`:63`) |
| correct | `workflows/tools/clean_text.py:129` | ~1.75k chars ≈ 440 tokens | yes |
| find names | `extract_all.py:438` as `system=` (`extract_entities_only.py:487`) | ~1.1k chars ≈ 280 tokens | identical text every page |
| find statements | `extract_all.py:746, 1125`; per section `extractors.py:945` | 3.3-3.5k chars ≈ 815-866 tokens + the known-entity list | the list changes, the instructions do not |
| describe for the catalogue | `resources/prompts/catalogue/narrative_v3.md` (1.7 KB) | ≈ 430 tokens + ≤ 6k tokens of readings | per folder |
| find documents | no model (`recipes/jobs.py` `needs_a_model=False`) | 0 | — |

Caching: `cache_control` appears nowhere; `supports_prompt_caching` is read from the registry (`llm/model_types.py:399`)
and used by nothing. At Sonnet's cache-read rate a cached 815-token prefix saves ~$0.0015 a call: about $0.15 per 100
pages. The unique page image dominates input, so caching buys little on vision; batching and image sizing buy more.

### 3.3 Which providers can batch, what the engine supports, and many-per-request

| Provider | Provider batch API | Engine support | Many segments per request |
|---|---|---|---|
| Anthropic | Message Batches (inline, 100k requests, 24 h, half price) | `llm/provider_batch.py` `AnthropicBatches`, in `CLIENTS` (`remote_read/cloud_batch.py:31`) | the line read packs 16 lines per message (`line_reader.py:35`); pages one per request |
| OpenAI | Batch (file, 50k, 24 h, half price) | `OpenAIBatches`, in `CLIENTS` | same |
| Google Gemini | Batch Mode (inline or file, 48 h, half price) | `GeminiBatches`, in `CLIENTS` (inline answers by position) | same |
| OpenRouter | **no batch API** | not in `CLIENTS`; plain calls only | 16 lines per call via the line reader; the per-provider cap of 4 in flight (`PROVIDER_CALLS_AT_ONCE`) |
| Hugging Face router / Inference Endpoints | no batch | plain calls | — |

When the batch path is taken: only `read-a-line`/`read-a-page`, one reader, provider in `CLIENTS`, and
`goes_as_batch(pages, waiting=False)` with `BATCH_THRESHOLD = 100` (`provider_batch.py:22, 50-52`;
`recipes/start.py:910-937`). The caller hard-codes `waiting=False`, so a Read Now press that reaches 100 pages would be
batched against the spec's rule (`ai.where.provider-batch-is-an-offer` [GAP] #5940). Never batched: names, statements,
catalogue, translate. No real provider batch has run (`compute.recipe.cloud-batch-*` built against fakes).

**Cost and speed against today's per-call path** (per 100 pages, from the table in §3.4): a batch halves the price and
costs up to a day of wall time; today's plain path is bounded by the per-provider cap (4 calls in flight) and the
provider's latency (a Sonnet page read is ~10-20 s, so ~100 pages in 5-10 min at 4 in flight). Packing MORE lines per
call is the cheaper lever for line reads: 16 lines per call already divides the prompt and page-context cost by 16; the
one 768 px page context re-sent per call is the remaining waste (~1k tokens a call on Anthropic). For whole-page reads
there is nothing to pack: one page is one request, and the saving is in the image size (§3.5) and in the batch.

### 3.4 Cost per 100 pages per provider, from the code's own price list

From `resources/model_prices.json` (LiteLLM shape). Assumptions: a 2000×1500 page; Anthropic image tokens w·h/750 after
the 1568 px resize = 2,459; Gemini 258 per 768 px tile = 1,548; OpenAI high detail = 765; 530 static tokens + 300 output
for a vision read; names = 1,500 text + 280 static in, 200 out; batch = half the listed rate. Provider defaults are
`llm/providers.py:232-277`.

| Model | $/M in | $/M out | image tok/page | vision $/100 plain | batch | names $/100 plain | batch |
|---|---|---|---|---|---|---|---|
| Anthropic claude-sonnet-5-5 (default) | 2.00 | 10.00 | 2,459 | 0.90 | 0.45 | 0.56 | 0.28 |
| Anthropic claude-sonnet-4-6 | 3.00 | 15.00 | 2,459 | 1.35 | 0.67 | 0.83 | 0.42 |
| Anthropic claude-haiku-4-5 | 1.00 | 5.00 | 2,459 | 0.45 | 0.22 | 0.28 | 0.14 |
| Google gemini-3-pro-preview (default) | 2.00 | 12.00 | 1,548 | 0.78 | 0.39 | 0.60 | 0.30 |
| Gemini / OpenRouter gemini-3-flash-preview | 0.50 | 3.00 | 1,548 | 0.19 | 0.10 (no batch on OpenRouter) | 0.15 | 0.07 |
| Gemini gemini-3.1-flash-lite-preview | 0.25 | 1.50 | 1,548 | 0.10 | 0.05 | 0.07 | 0.04 |
| OpenAI gpt-5 (default) | 1.25 | 10.00 | 765 | 0.46 | 0.23 | 0.42 | 0.21 |
| OpenAI gpt-5-mini | 0.25 | 2.00 | 765 | 0.09 | 0.05 | 0.08 | 0.04 |
| OpenRouter openai/gpt-4o-mini (default) | 0.15 | 0.60 | 765 | 0.04 | — | 0.04 | — |

**Sensitivity.** The code's own measured figure for a Gemini Flash-Lite page read is ~56k input tokens over two calls and
400 output (`recipes/start.py` `PAGE_READ_TOKENS_IN`, $0.0143 a page), 15× the per-tile rule: by that figure 100 pages
cost $1.46 on Flash-Lite, $2.92 on Flash and $11.68 on gemini-3-pro-preview (half for batch). The owner's real run of
2026-10-27 (#6271) matches: $6.06 for 4,121 Gemini calls, about $0.018 per page with text. The table above is the floor;
the measured figure is what to budget. The gap is the image: a 2048 px re-encoded page is far more than 6 tiles to
Gemini, which is exactly why `ai.where.image-sized-for-the-place` (#5948) is the first saving to build.

### 3.5 Image sizes sent

Whole page: `file_to_data_uri(max_dimension=2048)` LANCZOS, JPEG q95 (`workflows/tools/vision_base.py:3321, 3372, 3390`);
the node schema says 8192 (`:267-270`) and the function default 2048 (`:4000`): which one a live run uses is to verify.
PDF pages 2048 (`:3409, 3481`), Apple Vision 4096 (`:1247`). Line crops: padded a third of the line height, width capped at
1600 px (`llm/line_cut.py:14`), JPEG q90 (`line_reader.py:135`); the page context 768 px q70 (`:63, :128`). Remote read
package: 2000 px q92 (`remote_read/package.py:34, 107`). No provider-specific rule anywhere.

## 4. Kraken

- **Word-level output.** Kraken returns per-line text with per-character confidences and cuts; `ReadLine`
  (`llm/kraken_runtime.py:100-133`) keeps `char_confidences` and `char_positions` (0-1 along the baseline), written on each
  line by `read_given_lines` (`:1571-1573`). Kraken writes no word boxes; the SERVER cuts words from the positions:
  `segment.cut_words` (`api/routes/document/segments.py:3985-4099`, `cut_source` `ctc` or `ink-gap`), run after each read
  by `cut_words_after_read` (`llm/working_lines.py:275`) for lines that have positions (`vision_base.py:5888-5923`). Stored
  as `word` child segments of the line (not in the line's geometry). Shown and editable: the Segments pane lists word
  kinds (`fichero/fichero/Views/.../SegmentsPane.swift:134`), Cut Words is a menu item (`SegmentMenuCommands.swift:25-26, 84`,
  ⇧⌘W) and an action (`SegmentEdit+Tools.swift:145-154`); `ui/segment-editor.md` still tags it [PARTIAL] (`:450-458`), behind
  the code.
- **Other Kraken models.** One segmenter only (`llm/local_model_catalog.py:29-31`, `kraken-blla`; no choice). Readers:
  two shipped Zenodo cards (`kraken_runtime.py:167-183`, 16 MB each, the comment calls the pick provisional), every
  Zenodo/HTRMoPo record as `kraken:zenodo/<doi>@pinned` (`recipes/discovery.py:891`), Hub repos as `kraken-hf-<owner>--<repo>`
  (`:342`), and a user's trained reader as `kraken-trained-<job>` (`:385`, `training/landing.py:49-51`, the project's
  `models/<id>/fichero-card.json`), listed by `trained_readers()` into the catalogue (`local_model_catalog.py:218`). Chosen by
  the finder (`GET /api/recipes/candidates`, `api/routes/system/recipes.py:1634-1650`, ranked by `step_choices.py:66-70`,
  `assemble.py` `_frontier_first` swapping in a cloud reader for handwriting when allowed); a pinned id resolves in
  `resolve_recognition_model` (`kraken_runtime.py:432-462`). Gaps: no segmenter choice (`recipes-run`/`designer` steps
  #6054, #6014), the trained reader is choosable but never default (`compute.tune.not-default-until-chosen` [GAP]), and the
  "reader not on this Mac" error is untyped (review 1).
- **Speed per page, segment vs read.** Nothing recorded: no Kraken entry among the 3,789 perf-baseline rows; the only
  spec figure is a bug ("6832.3 s a page on 1 page"). The gate is 2 pages at once (`PAGES_AT_ONCE_GATE_5929`, `:895`),
  threads = cores / pages (`:898-901`), 1 page while paging or resuming. The measured segment and read times from the
  load leg are in §2.3.

## C. Training and fine-tuning: what trains today, from what, where

The shared path: a route calls an `@action` (`api/routes/training.py:110-160`) → a `jobs` row (`training/job.py:135-176`)
→ `build_training_set` (`:263`) → a target (`HfJobsTarget`, `training/hf_jobs.py:147`; `training/local.py` on this Mac) →
landing (`training/landing.py`, `training/mlx_landing.py`, `training/project_models.py` `fichero-card.json`). The MCP tools
are generated: `fichero_training_start_kraken`, `_start_kraken_here`, `_start_vision_lora`, `_start_regions_here`,
`_start_reasons_ab`, `_start_gathering_reasons`, `_preview_set`, `_job_status`, `_cancel_job`, `_list_trained_models`,
`fichero_evaluation_start`, `_model_scores`.

| What | Trainable today | Data | Where | Lands as | Measured | Gaps (spec ids) |
|---|---|---|---|---|---|---|
| Kraken segmentation | **no** (no `segtrain` code) | — | — | — | — | `compute.tune.kraken-segmentation` [GAP] #5240 |
| Kraken reader | **yes**: `POST /api/training/kraken` (HF Jobs), `/kraken/here` (this Mac, `training/local.py`, ketos in-process, gentle) | `training/kraken_set.py:318`: a teacher model's lines or `PERSON` (corrected or chosen lines, minus empty/null/rejected); empty set refused | HF Jobs default; this Mac; cluster target exists but refused without a key (`training/job.py:121-128`), no offer | `kraken-trained-<job>` card in the project | held-out CER only through `training/evaluation.py` | `compute.tune.kraken-recognition` [PARTIAL], `.scored-against-your-own-pages` [GAP], `.not-default-until-chosen` [GAP], `.adopted-by-the-recipe` [GAP] #5337, `training.place.slurm` [GAP] #5642, `training.place.other-macs` [GAP] #5238 |
| Vision LoRA (VLM) | **yes**, HF Jobs only (`/vision-lora`, `training/hf_vision_lora_train.py`) | the same set + line pairs (`training/line_pairs.py`), arms answer/why/thinking/review | HF Jobs; MLX conversion on this Mac (`mlx_landing.py`, 4-bit) | `fichero-trained/<name>/` MLX + adapter card | evaluation (role `trained`); reasons A/B (`reasons_ab.py`, 0.5 CER band) | `compute.tune.lora` [PARTIAL], `.convert-for-mlx` [PARTIAL] (never run on a real model), `.local-mlx-shown-never-default` [GAP], `compute.model.training-is-a-recipe-step` [GAP] #5539 |
| YOLO layout | **yes**, this Mac only (`/regions/here`, `training/yolo_local.py`) | `training/yolo_set.py`: human regions and tables; held-out pages as validation | this Mac, gentle | `kind: yolo` card | mAP50 on held-out pages | `compute.tune.yolo-layout` [GAP] #5240 (HF, cluster, lines), `training.eval.layout-overlap` [GAP] #5525 |
| Search embedder | **no** ("chosen, not trained", `recipes/jobs.py:187`) | — | — | — | — | no spec id exists: to write (the plan files it) |
| spaCy names / statements | **no** (`train_offers.py:46-50` "no spaCy trainer") | designed: confirmed names | designed: this Mac, HF, Create ML | — | designed: precision/recall | `training.propose.names-tagger` [GAP] #5536, `training.eval.names-precision-recall` [GAP] #5545 |
| Reviewer / judge steps | **not models**: the teacher-line check is a fixed rule (`checking/line_check.py`), the bake-off judge is deterministic CER (`training/evaluation.py:489-555`), Correct writes a reading | corrections and verdicts feed the PERSON set | this Mac | verdicts | — | `training.flow.every-correction-is-data` [GAP] #5404, `distill.scale.check-trust-levels` [GAP] |
| Whisper | **no** | — | — | — | — | no spec id: to write |

Cross-cutting: the pages-leave gate holds for training (`compute_requests.py:12-20`, `train_offers.training_stays_local`);
a person's pass never teaches as a teacher (`train_offers.py:207-212`); the bake-off's reads never become training lines
(`training/bakeoff_lines.py` has no caller; `compute.tune.bakeoff-reads-become-training-lines` [GAP] #5894); two stale tags
(`compute.tune.kraken-recognition` says "on this Mac not built" while `/kraken/here` exists; `source.train.ground-truth`
[GAP] while the pass flag exists).

## D. Ground truth today, and the spec for it

Today: one rule, `made_by_a_person` (`models/segments.py:666-673`: provenance `human` or `SegmentPass.ground_truth`), read
by the bake-off (`recipes/bakeoff.py:310-346`), the evaluation (`training/evaluation.py:288-312`) and the person training set
(`training/kraken_set.py:318`); one mark, on a whole PASS (`PUT /api/segments/passes/{id}/ground-truth`,
`api/routes/document/segments.py:1185-1201`, undoable), which the app reads (`Models/Segment.swift:315-316`) but offers no
control for; a correction or a chosen reading counts (`segment_readings.py:956-992`); imports are not truth until marked
(`segments.py:1197-1199`); verdicts outrank by trust (`checking/verdicts.py:18-30`); the markup ✓ is a rating no set reads.
**Nothing lists ground truth**: no saved search, smart folder or sidebar node filters on it (`search.smart-folders-as-sidebar-folders`
[PARTIAL] #4114). The spec is new: `docs/contributor_manual/specs/source/ground-truth.md` (DRAFT): one mark at three grains
(reading, region, page), one rule for every consumer, a Ground Truth group of smart folders per kind with counts equal to
the Train offer's, feeding training and the bake-off, exported with provenance; three build steps.

## Plan: issues to file and build-order steps

Issues to file (title; one paragraph each in the body, cited above):

1. Google key in a logged URL (`provider_keys.py:551`, `provider_models.py:573`): header + silence httpx INFO. HIGH.
2. YOLO layout model: pin the commit and check a sha256 before `YOLO()`, or convert to safetensors (`yolo_runtime.py:81, 112`). HIGH.
3. Every model download carries a pinned revision and a checksum (embeddings, Kraken readers, the HF Job's base model);
   TrOCR's pattern is the model (`local_models.py:511`, `kraken_runtime.py:368`, `remote_read/runner.py:141`). MED.
4. Stop/pause/cancel need owner-or-starter; `started_by` stored on the run; stop-all owner-only (`activity.py:2265`,
   `jobs.py:3195`). MED.
5. Training set to HF: document ids only, no display names, no `str(exc)`, downscaled scans; delete the bucket's data when
   the job ends (`kraken_set.py:380-388`, `hf_jobs.py:228`). MED ×2.
6. Transfer to another Mac sends absolute paths and the hostname (`transfer/remote.py:139-186`); pin the SPKI on that
   client. MED/LOW.
7. The CLI agents (`claude -p`, `codex exec`) pass no egress gate (`cli_agent.py:90-204`); one gate for every outbound path
   (`ai.where.one-egress-gate`). MED.
8. Redact at the write: breaker detail, ERROR logs and the run record (`llm/__init__.py:535`, `circuit_breaker.py:478`,
   `activity_store.py:184`); extend `redact` to the vendor key shapes. MED/LOW.
9. UDS socket chmod 0600 after bind (`__main__.py:175`); keychain write on stdin (#4818); `/usr/bin/security`. MED/LOW.
10. `#SBATCH` fields validated against a character set (`remote_jobs.py:111-120`). MED.
11. MLX runtime installs with hashes from a shipped requirements file and an explicit index (`mlx_runtime.py:329-354`; #4973). MED.
12. Image sized per provider before sending (`ai.where.image-sized-for-the-place` #5948), with the measured Gemini figure
    as the acceptance (100 pages under the per-tile floor ×2). The first cost saving.
13. Prompt prefix cached where the provider supports it (#5947); the line read's page context sent once per page, not per
    call (`line_reader.py:63`).
14. Batch for names, statements and the catalogue, not only the reads; `waiting` honoured (`start.py:917`); one real
    500-page batch per provider recorded (#5940, #6251).
15. Kraken per-page segment and read time recorded in the run's timing and the perf baseline
    (`recipes-run.kraken.reliability-measured`); the load leg's figures as the first row.
16. A Kraken segmenter choice (blla variants, a trained segmenter) and `segtrain` as a training kind
    (`compute.tune.kraken-segmentation`).
17. Trainers for the embedder, spaCy names and Whisper: a spec id each (none exists), the data each needs, where each runs.
18. Ground truth: the reading and region grains, the app's "Mark as Ground Truth", the sidebar's Ground Truth smart
    folders (`specs/source/ground-truth.md`, Steps 1.1-3.1).
19. Spec hygiene: `ui/segment-editor.md` Cut Words to [OK] with its tests; `compute.tune.kraken-recognition`'s "this Mac"
    note; `source.train.ground-truth` tag against the pass flag.
20. The measured ceilings table (#6076) from the load leg's `peak_footprint_bytes` and per-step `memory`, into
    `recipes-run.memory.peak-ceiling-per-model-kind`; this run's 6.3 GiB engine RSS and 7.9 GB peak as the first row.
21. The load leg cannot run: `tests/_engine_home_guard.py:56` refuses the real HOME and a temp HOME alike (`REAL_HOME` is
    read from the same `$HOME`), the `_engine_wait._share_real_model_cache` it names does not exist, and `scripts/_engine_harness.py`
    never sets the child's HOME; the harness must give the engine a temp HOME with the model cache shared, and the test
    must run on the iMac gate (`recipes-run.reliability.hundred-pages-finish`).
22. The one-venv recipe (`scripts/setup_venv.sh`, `uv.lock` only) leaves out Kraken, htrmopo, psutil, MLX and the spaCy
    language wheels: a freshly set-up Mac fails 25 recipe tests and 15 llm tests and cannot run a Kraken recipe; either the
    bundle steps join the recipe or the suites skip with the reason, never fail.
23. Two jobs tests contradict `recipes-run.memory.one-heavy-model-in-sequence` (#6673): `test_embed_off_the_reading_lane.py:69`
    and `test_one_model_at_a_time_on_the_lane.py` expect an embed beside a Kraken page; rewrite them to the rule.
24. Eight tests wait on the engine's real 60 s timers (`GENTLE_START_SECONDS`, `ORPHAN_FIRST_GRACE_SECONDS`): inject the
    clock; the recipes suite drops from 17 to ~11 minutes and jobs from 7 to ~4.
25. Hot spots from the profile: 43,755 `uuid4()` calls (1 s of urandom) per dense page, DuckDB `rebuild_secondary_indexes`
    3.4 s at open, 312k `_check_rect` validations per hydrate (`core/duckdb_session.py:532`, `models/anchors.py:488`).
26. The engine harness runs uvicorn at `--log-level warning`, so the model-load, per-page-climb and `run step` INFO lines
    the slow-path spec promises never reach the load leg's log; run the harness at INFO for the load leg, or log those at
    WARNING.
27. An import before Start queues per-page embeds that then run (and fetch a 4 GB model) during the recipe's Kraken
    stage; the embedder is released and reloaded mid-run ("model loaded again … 561 s"). Hold import-time embeds while
    any recipe stage has pages in flight, and never fetch a model nobody's step named during a run.

Build-order steps (for the harness; each one lane, one at a time): **S1** the two HIGHs and the socket/keychain
(issues 1, 2, 9) · **S2** pinned and checksummed downloads (3, 11) · **S3** who may stop a run; redaction at the write
(4, 8) · **S4** what leaves the Mac: training set, transfer, CLI agents, one gate (5, 6, 7, 10) · **S5** image per
provider and the page context once (12, 13) · **S6** batching for every cloud step and one real batch per provider (14) ·
**S7** Kraken timing, segmenter choice, `segtrain` (15, 16) · **S8** ground truth Steps 1.1-3.1 (18) · **S9** trainers
for the embedder, spaCy and Whisper (17) · **S10** the ceilings table and the spec hygiene (19, 20) · **S11** the load leg
runs on the iMac gate: the home guard, the venv's Kraken step, the log level, the two contradicting tests, the clock
injection (21-24, 26) · **S12** the import's embeds held under a running stage; the three profile hot spots (25, 27).
