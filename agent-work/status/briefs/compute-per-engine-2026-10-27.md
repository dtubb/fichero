# Compute per engine: how Fichero uses a machine for each kind of model work (Fable, 2026-10-27)

Read-only against origin/integration 19e4492fb. Nothing was run. Every claim is marked **measured** (a number
from a brief, an issue comment or a crash report) or **inferred** (follows from the code read, or from how the
library works; not yet measured here). Spec changes are in `docs/contributor_manual/specs/ui/activity-and-automatic-work.md`,
section "Proposed for the maintainer (compute per engine, 2026-10-27)", awaiting approval.

## The short version

- The knee is not the GIL and not the core count. On the M4 Air, Kraken's line finder plateaus at two pages at once in
  processes as well as in threads (measured). Past two, extra workers burn CPU for nothing. The limit is something the
  performance cores share (inferred: memory bandwidth or the matrix unit). So "pages at once = performance cores" is a
  ceiling, not the answer; the answer is measured per machine and per model and stored.
- #5929 is not a thread crash. It is torch's static destructor at process exit, triggered by Kraken's model load
  (measured: 25 crash reports, isolated tests). The engine already leaves by `fast_exit.leave`. What is owed is the same
  way out in the scripts and children, and one clean N=4 engine run on the M4. Then the gate of 2 is lifted.
- Each engine gets its own rule: Kraken segmenting (CPU, GIL-bound, knee at 2), Kraken reading (CPU, torch releases the
  GIL, scales with threads), spaCy (threads with one pipeline copy each, never processes), MLX (one model on the GPU, sequences
  batched), the embedder (a forked child, ONNX threads), cloud (the provider's limit, no cores).
- The morning's 39 s/page on Find Lines is withdrawn (section 7.5): a quiet M4 segments these pages in about 5 s and
  reads them in about 6 s (measured). The rule as built still reads an automatic run one page on one thread, which
  #6230 and #5931 fix. The writer, not the cores, is the knee of the names step (section 7.2).

## 1. Per engine: where the time goes, and threads or processes

### Kraken segmentation (Find Lines, blla)

- **Where the time goes (measured by the explorer, cProfile, kraken 7.1.1, one torch thread, a 3265x2202 page):** the
  network forward 45% (convolutions 8.4 s, LSTM 3.0 s of a 27 s page on a loaded Pro), the vectorizer 33% (scikit-image's
  `sato` ridge filter alone 6.6 s, plus scipy gaussian filters), the polygonizer 18% (`calculate_polygonal_environment`
  5.0 s, of which shapely 2.4 s across 452k calls). My earlier inference that GEOS dominated was wrong: the ridge filter
  and the network do. Everything outside the forward is single-threaded numpy, scipy and shapely, which is why torch
  threads barely matter (1 → 4 threads: 4.6 → 4.9 pages/min on the M1 Air, CPU 96% → 117%). Image decode and the DB are
  under 1%. Downscaling before segmenting gains nothing (measured): blla already resizes every page to 1800 px high and
  the vectorizer and polygonizer work at that scale (24.8 vs 22.1 s, 20.0 vs 22.4 s, identical line counts).
  **MPS for the network only: 28% faster a page (22 → 16 s, 22 → 17 s, same lines; measured).** The engine calls
  `blla.segment` without `device=` (`kraken_runtime.py:1138, :1392`), so segmentation always runs on the CPU; under load on
  a 16 GB Mac MPS hit out-of-memory on a third page, so it needs the memory guard, and the reader's MPS graph growth
  (#5529) is a separate question from blla's. Decision 10.
- **Does it release the GIL?** Partly (the forward does; the numpy, scipy and shapely half mostly does not). Measured consequence: threads lose to processes by only 12% at N=2 and
  30% at N=8, so the GIL is second-order; the first-order limit is shared hardware (both models plateau at N=2:
  processes 16.0 → 27.7 → 26.4 → 27.1 pages/min at N=1, 2, 4, 6; threads 16.2 → 24.3 → 22.7 → 21.1).
- **Threads or processes:** threads, one torch thread a page, two pages at once (measured on both Macs: M1 Air 8 GB 1 × 1 = 4.6/min,
  2 × 1 = 7.2 (1.57x), 2 × 2 = 6.2, 4 × 1 = 4.9 and swapping at 3 GB; M4 knee at 2, 1.7x, flat after). Threads, in this engine, at the measured knee. Processes buy at most 14% at N=2 (measured) and
  cost a fork taken before threads start (the only process model the shipped engine has; see the embedder). Not worth
  it today. The CPU-seconds a page rising 4x past N=2 while pages/min stays flat (measured) says more workers only heat
  the Mac.
- **Today's 39 s a page (measured, 106 pages, 3600x2800):** inferred causes, in order: (1) an automatic run gets
  `background` → a quarter of the performance cores = 1 thread, 1 page (`apply_to_this_thread`, `pages_at_once`);
  (2) the pages are about 3x the area of the GIL proof's, and the postprocessing scales with area and line count;
  (3) the engine peaked at 6.3 GB on a 16 GB Mac with swap growing 0.6 → 2.4 GB. The per-page log line
  (`kraken page …: load … segment … recognise … | priority= qos= threads=`) in `~/fichero-run/out` on the M4 settles
  (1) and the segment/recognise split; it is the first measurement to pull (section 6, M0).
- **Is the polygonizer thread-safe, and the #5929 cause?** No to the second (measured). The TopologyException lines are
  GEOS warnings about degenerate line polygons, printed during the run; the crash is at `exit()` on the main thread in
  `libtorch_cpu` `MetalShaderLibrary::~MetalShaderLibrary` (25 crash reports), after every row printed, and the
  isolated trigger is Kraken's model load through vgsl/coremltools, CPU or MPS alike (`runtime.torch.exits-cleanly`).
  Shapely 2 uses GEOS's reentrant API with a context per thread (inferred from the library), so the per-thread calls do
  not share state. Why `procs` mode "never crashed" (inferred from `gil_proof.procs`): its parent never imports torch,
  and it only `join()`s the children without reading `exitcode`, so the children's exit-time faults were not seen.

### Kraken recognition (Read, the PP-OCRv6 reader)

- **Where the time goes (measured):** recognise is 4.17 s a page at one thread on the GIL-proof pages, the same at the
  default thread count (4.21 s) for twice the CPU. Batch of one line is the fast setting (#5854: batch 16 took 43 s).
  The per-page deep copy of the reader (60 MB) is now one copy per pipeline (#5952). Today's 6 s a page at one
  thread on larger pages (measured) is consistent.
- **Does it release the GIL?** Yes (inferred from torch; measured consequence: "reading scales with its threads,
  sub-linearly", `source.read.pages-at-once-scales`).
- **Threads or processes:** threads. The lever here is torch intra-op threads per page, not pages at once: one page
  reading alone should get the performance cores, two pages half each.
- **`torch.set_num_threads` is process-wide, and the code sets it per page (measured from the code, `kraken_runtime.py`
  ~1020-1035):** page A enters alone and sets 4; page B enters, sees two inside and sets 2 for the whole process, so A
  drops to 2 mid-page; when B leaves A stays at 2. `set_num_interop_threads` can only be set once. The OpenMP/BLAS
  variables are `setdefault`, so only the first value ever sticks. The fix is to set the thread count once per plan
  (N and T decided at the gate from the fit record), not per page. This is a BROKEN line under #6229.

### spaCy (names, statements)

- **Where the time goes:** the parse is 1 to 4 s a page including the write (measured, #6236, pages 1-86). The 20-minute
  stall at page 87 is not the parse: the page alone parses in seconds, and the hot thread is native (DuckDB or a
  regex) after `upsert_entity … creating a second row` lines (measured). Inferred: entity resolution against a growing
  table. The names step's time is the database path, not spaCy.
- **Does it release the GIL?** Enough to scale (measured by the explorer, M1 Air 4P+4E, `es_core_news_sm`, one `nlp`
  object per thread: 3152 docs/min at 1 thread, 4550 at 2, 6790 at 4, 2.15x; RSS 0.33 → 0.49 GB, about 55 MB a copy).
  The code's own note "GIL-bound anyway" is wrong for the small pipelines: thinc's numpy ops and the Cython components
  release it.
- **Threads or processes:** threads, each with its own `nlp` object. One shared `Language` is not thread-safe (measured:
  two pages at once on the one cached pipeline crashed, hence `_spacy_lock`); the fix is a copy per thread, not a lock.
  `nlp.pipe(n_process=N)` is out: spawn runs `sys.executable`, the sandboxed stub. So: N threads, one pipeline copy
  each, N from the fit rule and bounded by memory per copy (the prior N = performance cores ÷ 2), on the embed lane,
  people first at the turn. The earlier draft of this report said "one call at a time"; the measurement overrides it.
- **The old code (explorer):** the 2026.07 ingest ran 8 threads under one `db_lock`, so it ran serially: a pool in
  front of one lock buys nothing. The same trap waits for the names step unless the writer takes one batch per page
  (section 7.2).

### MLX readers (a local vision model)

- **Where the time goes (inferred, unmeasured here):** prefill of the image tokens is compute-bound on the GPU; decoding
  is memory-bandwidth-bound (each token reads the whole weights once). `mlx_order_proof.py` was written to measure
  s/page, load, unload and memory beside Kraken, and the results file `mlx-results-2026-10-20.md` was never written:
  there is no MLX number in the tree.
- **GIL:** MLX's Metal kernels run outside the GIL; the server is uvicorn on a thread in the engine process
  (`mlx_in_process.py`), one model preloaded.
- **One model with batched pages, or several copies?** One model, batched (inferred, and already the design):
  `MLX_VLM_MAX_NUM_SEQS` = `reads_at_once_for` (half the Mac's memory minus the weights, at a 1 GB margin per read,
  cap 4). On unified memory a second copy of the weights doubles the one thing that is scarce and gains nothing: the GPU
  is one device, and batching shares one weight read per decode step across the pages. The GPU budget is therefore
  memory, not cores, and is separate from the CPU budget. Owed: a served-path measurement at 1, 2 and 4 sequences.

### The embedder (search vectors)

- **Where the time goes:** ONNX Runtime inference in a forked child (`embed_process.py`), one batch at a time,
  intra-op threads = `embed_threads()` = half the performance cores. ONNX Runtime releases the GIL in `Run`, and its
  Initialize once held the GIL for 18 minutes (measured, the reason for the child).
- **Threads or processes:** a process, forked, with threads inside it. The problem (measured, #6237): the fork happens at
  first use (`RemoteEmbedder._start`), after uvicorn's loop and LanceDB's background event loop thread exist, so the
  child inherits a dead kqueue selector and LanceDB's loop dies with EBADF. The fix is structural: a thread-less seed
  process forked once at engine start, before the loop, which forks the embedder (and any later worker) on request
  over a pipe. Apple Vision's worker (`apple_vision_worker.py`, fork at first use) has the same exposure (inferred).

### Cloud calls

- No cores. The width is the provider's rate limit (`network` lane 4, a share per provider), and the cost is the loop
  being free: a blocked event loop stalls every cloud call at once (measured, #6178). The one compute rule is "never on
  the loop"; batch APIs (#5940, #6233) are a cost question, not a compute one.

## 2. The rule: the fit, per machine and per model

One record, the **fit**, keyed by (this machine, the step kind, the model): `{pages_at_once N, threads T, pages_per_min,
cpu_s_per_page, page_peak_bytes, measured_at, source}`. Stored in the app's settings table (it is per Mac already), key
`compute.fit.<kind>.<model-id>`; a cluster task or container has none and uses the cores it was given.

- **Find the knee from real runs, not an idle calibration.** The first run of a model on a machine is its calibration:
  it starts at the prior (below), reads a window of pages (about 8), then tries one step up (N+1 at the same T, then T+1
  at the same N, never past N × T ≤ performance cores and never past what free memory holds at the page's measured peak)
  for the next window; a step is kept only if pages/min gains at least 10%; the search stops at the first step that
  does not. An idle calibration job is not built: it costs battery and heat for a number a run gives for free, and the
  owner ruled no dogfood loops. (Decision 1.)
- **What counts as best:** the most pages a minute; among configurations within 5% of that, the fewest cores (N × T),
  with cpu-s a page as the tie-break. (Decision 2.)
- **Priors per engine (until a fit exists):** Kraken segment N=2, T=1 (M4 measured); Kraken read N=1, T=performance
  cores (inferred from "scales with threads"); spaCy and the embedder N=1 (never more); MLX N=`reads_at_once_for`
  sequences in one server, T not applicable.
- **Live step-down, every page window:** swap growing or the Mac paging (`paging_now_on_this_mac`), thermal state
  serious, battery, or pages/min falling more than 10% below the fit → N or T down one step, and the fit is NOT
  overwritten (a slow window under pressure is not a measurement). Step-up only on a clean window and only when it
  gains ≥10%; a fit is re-measured when the machine's core count or memory differs from the record's.
- **In use (#6230) applies on top:** half the performance cores, so N × T ≤ cores ÷ 2 while the Mac is used; the fit is
  looked up for that ceiling too (a second record under the halved cores), so an in-use run does not re-learn.
- **On the run's grey line:** "4 pages at once, 1 thread each; fastest measured on this Mac" / "2 pages at once, 2
  threads each; the Mac is in use, half the cores" / "1 page at a time; free memory holds one" / "2 pages at once; not
  yet measured on this Mac".

## 3. CPU and GPU side by side, bounded by memory (#6000)

Two budgets: the CPU one from the fit (N × T ≤ performance cores, N × page peak ≤ free memory beyond the model), the GPU
one from `reads_at_once_for` (half the memory minus the weights). The sum is bounded by one memory rule: free memory −
Kraken's need − the served weights − N_cpu × page peak − N_gpu × read margin ≥ the reserve, and on a 16 GB Mac or less
#6000 says one heavy model at a time, so side by side is only above 16 GB. One caveat before allowing it even there
(inferred): the M4's blla knee at two is a shared-hardware limit, and a GPU model beside it draws on the same unified
memory bandwidth, so the two may slow each other; measure first (section 6, M4).

## 4. "Use the whole Mac", and the other machines

"The whole Mac" means the measured best, never every core: on the M4 Air that is 4 pages × 1 thread for reading
(11.2 pages/min, measured, +17% over 2 × 1 for 0.6 GB more) and 2 × 1 for segmenting; more threads only heat it. A
person's run uses the full fit; an automatic run the half-cores fit while the Mac is used. ACEnet/Slurm: `cores_available`
= `SLURM_CPUS_PER_TASK`, one page pipeline a task, T = the cores given, N from array tasks (ruled); the fit record is
not used there. Containers: the cgroup quota the same way. Never `os.cpu_count`.

## 5. Measurements to run on the M4 (one job at a time, on AC, engine stopped, scratch base; safe unattended)

Setup as the earlier briefs: `D=$(mktemp -d); mkdir -p "$D/state" && cp -R ~/"Fichero Dev Test/reader-seed/kraken-models" "$D/state/"`,
the `model_path` fix on the copy, `export FICHERO_BASE_PATH="$D/state" HF_HUB_OFFLINE=1 PYTHONPATH=fichero-server/src`,
`PY=~/code/fichero/.venv/bin/python; S=fichero-server/scripts/gil_proof.py; M="$D/state/kraken-models/htr-data/kraken-zenodo-21788410/medium.safetensors"`.
IMG = 15 of the 106-page run's pages (HTRomance and AMSMB, public) copied to a temp folder: the large pages, not the
GIL proof's. Every `gil_proof` row logs `pmset -g therm` and refuses N over 4 or over 80% of free RAM.

- **M0 (no run, settles today's 39 s):** on the M4, `grep -h "kraken page" ~/fichero-run/out/*.log | head -20` and
  `grep -h "Threads:" ~/fichero-run/out/*.log | sort | uniq -c`: the threads a page got, and the segment/recognise split.
- **M1 (thread knee per stage, N=1):** `for T in 1 2 4; do $PY $S profile --images $IMG --model $M --pages 3 --batches 1 --torch-threads $T > profile-T$T.txt; done`
  → segment s and predict s a page at each T. Expected: segment flat, predict falls to about T=2 then flat.
- **M2 (the N × T grid on the engine seam):** `$PY $S engine --images $IMG --model $M --pages 15 --repeat 2 --n 1,2,4 --threads one --out grid.jsonl`,
  then the same with `--threads default`. Six rows: pages/min, stage means, cpu-s a page, peak GB, therm. The fit's
  prior for Kraken comes from these.
- **M3 (names the shared limit, numpy only, no engine):** N spawned processes each running for 20 s (a) a pure-Python
  loop, (b) a 1024x1024 float32 matmul loop with `OMP_NUM_THREADS=1`, (c) a 512 MB array copy loop; wall and iterations at
  N=1, 2, 4. If (a) scales to 4 and (b) or (c) flatten at 2, the knee is bandwidth or the matrix unit, and no
  process model will move it. Script: `fichero-server/scripts/gil_proof.py micro` is the place (not written; ten lines of
  `multiprocessing.get_context("spawn")` + numpy; the brief for the builder).
- **M4 (CPU beside GPU):** `$PY scripts/mlx_order_proof.py --images $IMG --kraken-model $M --mlx Qwen2.5-VL-3B --pages 5 --out "$D/order"`
  (the model must already be in the scratch store: the install step of `briefs/mlx-arm-m4-run.md`). Gives MLX s/page,
  load/unload, MLX active/peak GB, and the Kraken block before and after. The side-by-side (Kraken N=2 while a page
  reads on MLX) needs one more mode of the same script; owed.
- **M5 (#5929 closed on evidence):** `$PY -m pytest fichero-server/tests/unit/llm/test_torch_exit_5929.py -q` (the
  trigger cases xfail, the `fast_exit` case passes), then `$PY $S threads --images $IMG --pages 15 --n 1,4 --pools one; echo rc=$?`
  after the script leaves by `fast_exit.leave`: rc 0 is the proof the scripts are fixed.
- **M6 (spaCy):** `$PY fichero-server/scripts/bench_spacy_pipe.py --pages 200 --model es_core_news_sm --runs 3; echo rc=$?`
  (rc 0 = build the batcher). For #6236, during the next e2e run's Names step: `sample <engine pid> 10 -file ~/names-stall.txt`
  (no root) when a page passes 60 s.
- **M7 (energy, if passwordless sudo exists; else skip):** `sudo -n powermetrics --samplers cpu_power -i 5000 -n 1`
  before and during M2's N=4 row; otherwise `pmset -g therm` in the rows is the heat reading.

## 6. Decisions for the owner

1. **Calibrate from real runs, not an idle job.** Recommend: the first run of a model on a machine is its calibration
   (one step up per window, kept at ≥10%); no separate idle job; a Settings button "measure this Mac" can come later if
   runs prove too noisy.
2. **"Best" = most pages a minute; within 5% of that, the fewest cores.** Recommend: yes, with cpu-seconds a page as
   the tie-break and the page's measured peak as the memory cap. Priority (fast/balanced/background) changes the QoS
   class and the in-use ceiling, never the fit.
3. **A seed process (zygote) forked at engine start, before any thread, is the only way the engine makes worker
   processes.** Recommend: yes; it fixes #6237 for the embedder, covers Apple Vision's worker, and leaves the door open
   to blla in processes if M3 ever shows it pays. The alternative (exec the bundle's own signed Python) is unproven in
   the sandbox.
4. **Lift the gate of 2 before or after the owed #5929 pieces?** Recommend: keep the ruled order (1.7 then 1.8), but
   narrow 1.7 to what is actually owed: the scripts and children leave by `fast_exit`, and one N=4 engine run on the
   M4 is clean mid-run. The crash is exit-time, so a running engine is not at risk; the gate's lifting is then one line.

## 7. Added scope (the manager's five additions, 2026-10-27)

Each answered against the code; what Activity, the database and the HPC path already do was read first and is built on.

### 7.1 The compute choice, shown graphically

Checked first (iterate, never replace): the project window already has the run strip (`ProjectRunStrip`) with the
pages-at-once words from the run status (`RecipeRunPagesAtOnce`: count and reason, #6217); the Activity popover has the
Mac state row (`ActivityMacStateRow`: SF Symbol + short value per reading, `.caption`, `.secondary`, orange only for a
problem, the full reading in `.help` and the accessibility label); the details view lists peak memory. Nothing draws
cores, pages side by side or the GPU share. So the design extends `RecipeRunPagesAtOnce` into one small view, drawn in
the run strip and in the opened run's details, in the Mac state row's idiom:

```
[▪▪▪▪ ▫▫▫▫▫▫]  ⫶⫶⫶⫶  ▮▮▮▯  ✓
 cores          pages  GPU   fit
```

- **Cores:** one small square per core, performance cores first (filled when a page thread runs on them, outlined
  when free), efficiency cores after (always outlined: they are the app's and the person's). On a 4P+6E Mac reading
  four pages at one thread each: four filled, six outlined.
- **Pages side by side:** one page glyph (`doc`) per page in flight, up to the fit's N; a dimmed glyph for a slot the
  fit allows but memory or the in-use rule took away.
- **GPU share:** a short bar for the MLX budget in use (sequences in flight over `reads_at_once_for`), drawn only while
  a GPU step runs.
- **The fit's state:** `checkmark.seal` in `.secondary` = measured best on this Mac; `arrow.down.circle` in orange when
  stepped down, with the cause's symbol beside it (`memorychip` paging, `thermometer.medium` heat, `battery.25`
  battery, `person` in use); `questionmark.circle` while not yet measured.
- **Fonts and words:** `.caption`, semantic only; no text in the view beyond the two counts; the words live in `.help`
  and in one accessibility label: "4 pages at once on 4 of 4 performance cores, 1 thread each; measured best on this
  Mac" / "2 pages at once on 2 of 4 performance cores; slowed, the Mac is in use". One accessibility element, as the
  Mac state row does it.
- **Where:** the run strip (while live) and the opened run's details (live, and the last value when ended, so a run's
  record can be compared). The engine serves the fields on the run status beside `pages_at_once`: threads, cores in
  use, performance cores, GPU share, fit state, step-down cause. The Activity window's run rows do not get it (a row
  is one line); the popover's Mac state row stays as it is.

### 7.2 DuckDB's one writer as a knee

**As built (measured from the code):** one `Database` per library with one connection, one `RLock` round every
statement and one `_transaction_gate` round every transaction (`db/manager.py`, `db/__init__.py:1063-1073`,
`transaction()`). Every write of every page, from every thread, queues on that gate. `open_transaction()` names who
holds it and for how long, but nothing sums the hold per page, so the figure the owner asks for does not exist yet.

**Per page, by step (read from the code):**
- Kraken lines and readings: a handful of `db.save` calls on the page document and its artifacts (`vision_base.py`
  3133, 3264, 3764) plus the lines through the segments route; each `save` is one autocommitted ON CONFLICT statement
  under the lock unless an ambient transaction is open. A page's write is milliseconds against seconds of model time
  (measured 2026-10-20: DB writes under 1% at N=1), so for Kraken the writer is not the knee today.
- Names: `_entity_writer.py` writes one `db.save` per entity, claim, mention and match candidate (twelve call sites),
  each its own autocommitted ON CONFLICT upsert: 20 to 80 lock trips a page, each a full statement. Because each
  commits at once, the DuckDB 1.5 cost of ~32 KB per column per new row until commit (duckdb#26830) does not
  accumulate here; it would if the page were wrapped in one transaction of plain upserts, which is why `save_many(new=True)`
  uses a plain INSERT for fresh rows. The #6236 stall is a lookup against a growing entity table, not upsert memory
  (inferred; the page alone parses in seconds).
- Vectors: `embed_many` appends to LanceDB once per batch, outside the DuckDB gate; the single-doc `embed` once per page.

**The old code (explorer, measured from `fichero_archive`):** the 2026.07 ingest ran 8 threads under one `db_lock` (`importers/ingest.py:1105-1132`), so it ran serially. A pool in front of one lock buys nothing; that is the trap the names step is in today.

**Where the writer becomes the knee (inferred):** pages at once helps until N × (page write time) approaches the model
time of one page. At 5 s of model time and tens of milliseconds of writes, Kraken reaches that only past N≈50, so
never on a Mac. The names step is the other way round: its parse is a second and its writes are tens of statements, so
there the writer is already the knee, and the fix is fewer, larger statements, not more spaCy calls.

**Rule (spec line `activity.lane.writer-batched-per-page`):** a page's results are handed to the writer as ONE
batch per page and per step (one transaction: `save_many` for new rows, updates after), never a row at a time; a
worker never holds the gate while a model runs; the per-page record (section 7.5) carries "db <ms>" so the writer's share
is visible on the row. Not a dedicated writer thread: the one connection is already the serial point, a thread adds a
queue without removing it; what helps is fewer transactions and the reads off the gate (#6178's committed reads, built).

**M4 measurement (M8, scratch library, no engine):**
```
PYTHONPATH=fichero-server/src FICHERO_BASE_PATH=$(mktemp -d) $PY - <<'PY'
import time, tempfile, uuid
from pathlib import Path
from fichero_server.db import Database
from fichero_server.models.kg import KnowledgeEntity
db = Database(Path(tempfile.mkdtemp()) / "t.fichero", create=True)
rows = [KnowledgeEntity(id=str(uuid.uuid4()), canonical_name=f"n{i}", entity_type="person") for i in range(2000)]
t = time.perf_counter(); [db.save(r) for r in rows[:1000]]; one = time.perf_counter() - t
t = time.perf_counter(); db.save_many(rows[1000:], new=True); many = time.perf_counter() - t
print(f"1000 x save: {one:.2f}s ({one:.4f} s/row)   save_many(1000): {many:.2f}s")
PY
```
(the import names are the ones the tree uses; the builder fixes a renamed field). Plus, on the next e2e run, the
page record's "db <ms>" column summed per step, and `grep loop_lag` on the engine log. For the names stall, #6236's own
repro with `sample <pid> 10` past 60 s.

### 7.3 Target machines: the rule must land well on each without hand-tuning

| Machine | Cores (P+E) | Memory | GPU | Kraken segment prior (N × T) | Kraken read prior | MLX | Note |
|---|---|---|---|---|---|---|---|
| M1 Air (tester) | 4P + 4E | 8 or 16 GB | 7/8-core | 2 × 1 | 1 × 4 | 3B only at 16 GB; one read at a time at 8 GB | memory caps N to 1 at 8 GB (`page_fan_out`) |
| M1 Pro 16 GB (manager) | 8P + 2E | 16 GB | 16-core | 4 × 1 (prior = P ÷ 2, cap 4) | 1 × 8 | 3B; 7B refused under 24 GB | the owner measured "an M1 maxes at 4" |
| M4 Air 16 GB (fanless) | 4P + 6E | 16 GB | 10-core | 2 × 1 (measured knee) | 1 × 4 | 3B | heat step-down matters: fanless |
| M5 24 GB (Ann, to confirm with `sysctl hw.perflevel0.physicalcpu hw.perflevel1.physicalcpu`) | likely 4P + 6E (M5 Pro: more P) | 24 GB | 10-core, neural accelerators per GPU core | 2 × 1, learned up | 1 × 4 | 7B fits (24 GB floor); prefill faster on M5's GPU, so MLX favoured more | the fit learns the rest; the first run is its calibration |
| 36 to 48-core Mac (Ultra class) | 24 to 32P + 8E | 64 GB and up | 60 to 80-core | 4 × 1, learned up to the knee (bandwidth is wider, so likely 6 to 8) | 1 × 8 (torch stops scaling before P) | 7B+, 4 reads at once | never "N = P": the fit finds the knee |
| Cluster node / container | `SLURM_CPUS_PER_TASK` or the cgroup quota | the job's | the task's GPU | 1 pipeline a task, T = the cores given | same | vLLM offline batch in the task | parallelism = array tasks (section 7.4) |

The prior is `N = min(4, max(1, P ÷ 2))` for the line finder (the M4 knee at P ÷ 2 and the owner's M1 figure agree),
`T = 1`; `N = 1, T = P` for the reader; always capped by memory. The fit replaces the prior after the first run.

### 7.4 Scale-out: HPC (ACEnet/Slurm) and Hugging Face Jobs, one design

**What exists (built, read):** `remote_read/job.py` runs one job row (`read-at-scale`, lane `remote`) over shards:
package once, at most `max_in_flight` shards in flight, one status call a round, each finished shard landed at once
through PAGE import as a new pass, never over an existing one, a landed page never landed again, failed shards re-sent
only when asked (`compute.land.idempotent`, `compute.job.sparse-resubmit`). `HfJobsTarget` runs a Job per shard with a
flavor and `price_per_hour`; `SlurmTarget` submits one `sbatch --array` for the whole run (the loop still sends a
single-task array per shard: `compute.hpc.submit-array` GAP), reads every task in one `sacct` call, and brings each
task's tar home. `sizing.size_run` sizes a shard from a measured pages/s to 80% of the shortest walltime class (3 h) and
gives GPU-hours. `dry-run-submit` exists but counts files, not pages (`compute.hpc.plan-before-send` GAP).

**Two layers (spec line `activity.lane.scale-out-batches-and-result-files`):**
1. *Inside a task:* the per-engine knee rule with the cores the task was given (`cores_available`: `SLURM_CPUS_PER_TASK`
   or the cgroup quota) and its GPU; no fit record, one page pipeline a task, T = its cores; a vision model as vLLM
   offline batch in the task (built).
2. *Across tasks:* scale out. P pages → K = ceil(P ÷ S) tasks, S = `size_run`'s shard size from the measured per-page
   time (a 20-page pilot task first when no rate is known; the local fit's pages/min is the first estimate), capped by
   the queue's limits (`--array=0-K%M` on Slurm, `max_in_flight` on HF; M from the site profile or the HF plan). Retries
   per task from `sacct`/the Job state: once automatically for NODE_FAIL and PREEMPTED, with a half-size slice for
   OUT_OF_MEMORY and TIMEOUT, twice failed → set aside and offered as "Read these pages again" (already specified under
   `compute.hpc.failure-states-in-words`; the same words for HF).
   *Results:* no DuckDB over the network. Each task writes its result files beside the job (PAGE XML per page, one JSON
   record per page with the per-page compute record, vectors as one Parquet shard per task), one tar per task; the
   library imports each returned task in ONE batched pass (`save_many` + `embed_many` in one transaction per task), as
   it comes back (partial returns land; the run row counts pages landed), and a returned page is never rerun
   (`compute.land.idempotent`, the never-rerun rule #6127).
   *Before submit:* one plan sheet for either place: pages, tasks and their size, the `--array` or flavor line, the
   time (K ÷ M × the task's walltime, plus the queue wait from `sinfo` or HF's own), the cost (HF: flavor price × GPU-hours,
   `price_per_hour`; ACEnet: allocation GPU-hours, and the queue wait in words), and the local estimate beside them
   (pages ÷ the local fit's pages/min). Nothing is sent before the sheet is agreed (`compute.hpc.plan-before-send`).
   *Progress, graphically:* one run row with a strip of K small cells (done, running, queued, failed in the status
   colours) and "3,400 of 6,000 pages landed", from the one status call; a task's own line on open. The same cell strip
   for HF Jobs.

**The choice per run, per step:** cloud by default per step (#6233) picks the model's place; among places the ruling
"cheapest and local first" (remote-compute, 2026-10-03) picks the machine: local when the local estimate finishes within
the person's wait (recommend one hour, or any run under 200 pages); else the cheapest remote that is set up and allowed
to receive the pages (`compute.leave.one-gate`): HF when a key and a budget exist, ACEnet when a cluster is configured;
the stage page shows the three estimates and the person can override per step. (Decision 7.)

### 7.5 Busy machines, and what a run records per page

On a quiet M4 the 106 large pages segmented in 531 s, about **5 s a page** (measured); recognition about 6 s a page.
The morning's 39 s a page overlapped a Time Machine restore and probably Spotlight indexing, so it is not used anywhere
above; the causes listed under Kraken segmentation for it are withdrawn except the first (an automatic run reads one
page on one thread), which stands as read from the code. Two things follow and are now spec lines:

- **Every run records what it chose per page** (`activity.run.records-what-it-chose-per-page`): threads, QoS class,
  pages at once, the throttle's state and the fit's source, on the page row and served with the run status, so two runs
  can be compared. Today the engine's per-page log line has threads and QoS but nothing serves it, and the `Threads:`
  note is in the call log only; the run status has `pages_at_once` and its reason (`run_view.py`,
  `RecipeRunPagesAtOnce` in the app) and nothing else.
- **The fit skips or flags a busy machine** (`activity.lane.fit-skips-a-busy-machine`): a calibration window is not a
  measurement when the one-minute load average exceeds the performance cores, when `backupd`, `mds`/`mds_stores` or
  `photoanalysisd` are busy (the same `pgrep` the build probe uses), or when the Mac is paging; the window runs at the
  current fit and is marked "measured while the Mac was busy", never stored as the best.

### 7.6 The explorer's measurements (M1 Air 4P+4E, 8 GB, 12 real pages x2, every row rc=0, no swap)

- **OpenCV preprocessing** (imread, gray, blur, adaptive threshold, open, Canny+Hough, resize, PNG), pages/min: 1 thread
  with `cv2.setNumThreads(1)` 124; 1 × 4 cv2 threads 200; 1 × 8 194; 2 × 1 199; 4 × 1 285; 8 × 1 406; 4 × 2 343;
  processes 4 × 1 262, 8 × 1 343 (3.85 GB against 2.06 GB for threads). Reading: cv2's internal threads stop paying
  past 2; Python threads with `setNumThreads(1)` scale to every core (3.3x at 8); processes lose and double the memory.
  The old code ran OpenCV in a `ThreadPoolExecutor`, one page a task, cv2 threads never capped, workers =
  `max(2, cores // 2)`, and model work on a 640 px downscaled copy. So the engine's image steps (Cleanup, #6192;
  derivatives) take the OpenCV rule: threads, one page a task, `cv2.setNumThreads(1)`, N from the fit with the prior
  N = the cores. One tension for the owner: on this Air the measured best used the efficiency cores too (8 × 1 beat
  4 × 1 by 1.4x), while the ruling keeps the efficiency cores for the app and the person; the fit's ceiling stays the
  performance cores by that ruling, and lifting it for light image work is decision 9.
- **spaCy**: above (section 1). `n_process` rows pending from the explorer; they do not change the rule, since spawn
  cannot run in the shipped engine.
- **Prior M4 data** agrees with section 1: blla knees at N=2 in threads and processes; default torch threads = same speed,
  twice the CPU.

## 8. Further decisions for the owner

5. **The compute graphic lives in the run strip and the opened run's details**, extending the pages-at-once view the
   strip already has; not in the Activity window's rows. Recommend: yes.
6. **The writer fix is one batch per page and per step, not a writer thread.** Recommend: yes; and the names step first,
   where the writer is already the knee.
7. **Local versus HF versus ACEnet:** local when the local estimate finishes within one hour or the run is under 200
   pages, else the cheapest remote that is set up; always shown with the three estimates before anything leaves.
   Recommend: yes, with the hour as a setting-free constant.
8. **The priors table (section 7.3) is the starting point for every Mac**, and Ann's M5 is confirmed by `sysctl` before
   its first run. Recommend: yes; no hand-tuning per machine.
9. **Light image work (OpenCV) may use the efficiency cores.** Measured 1.4x on the M1 Air from 4 to 8 threads at
   `setNumThreads(1)`. The ruling keeps the efficiency cores for the app and the person; the fit honours it. Recommend:
   keep the ruling for model work, and let image steps alone take the efficiency cores at background QoS, where the
   scheduler already puts background work.
10. **Kraken's line finder may run its network on the GPU (MPS) when memory allows.** Measured 28% faster a page with the
    same lines; the engine passes no `device=` today. The risk is memory (OOM on a third page under load), and #5529's
    reader-side MPS graph growth is not yet measured for blla. Recommend: a bounded trial on the M4 (blla on MPS, N = 2,
    the memory guard on, footprint sampled over 50 pages) before any default changes; the CPU stays the default until then.
    Not recommended from the data: pre-downscaling, more torch threads.
