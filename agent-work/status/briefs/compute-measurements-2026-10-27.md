# Compute per engine: measurements (2026-10-27, compute explorer)

For the compute-per-engine design (`compute-per-engine-2026-10-27.md`, fable/compute-per-engine). Scripts:
`fichero-server/scripts/compute_bench.py` (one config a run, threads vs spawned processes, standalone, never imports the
engine) and `compute_bench_run.sh` (one config at a time, `/usr/bin/time -l`, swap before/after, refuses a row without
the memory). Time-boxed at about 2 h, as the owner asked: segmentation first, and rows that taught nothing new were skipped.

## Machines
| | chip | P + E cores | RAM | free disk | state |
|---|---|---|---|---|---|
| M1 Air (`ssh air`) | Apple M1 | 4 + 4 | 8 GB | 25 GB | AC, no thermal limit; 13.4–14.5 GB swap already used before any row (old swap), 2–4 GB free + inactive |
| M4 Air (`ssh m4`) | Apple M4 | 4 + 6 | 16 GB | 8.4 GB | quiet (load 2, Time Machine idle, e2e exited); **dropped off the network mid-batch** (see Surprises) |
| Pro (here) | Apple M1 | 4 + 4 | 16 GB | 27 GB | load 15–32 (other lanes): used only for one-page profiles; absolute times there are inflated |

Versions: kraken 7.1.1, shapely 2.1.2, opencv-headless 4.13 (Air) / 5.0 (M4), spaCy 3.8.14 (es_core_news_sm), duckdb
1.5.5, onnxruntime 1.26, torch 2.12 (Air) / 2.14 (M4, Pro). Pages: 12 open-HTR pages spread over `m4:~/code/htr-corpus/pages106`
(1791×2566 up to 6944×4934; list in the run configs). The MLX benchmark (e) was **not run**: there is no MLX reader on either Air
and no small one in any HF cache, and the brief said not to download.

## Verdict per engine (the knee; threads or processes; how many)
| engine | winner | knee | evidence |
|---|---|---|---|
| Kraken segmentation (blla) | **threads**, 1 torch thread a page | **2 pages at once** on the M1 Air (1.57x; 4 is worse, swapping); 4 on the M4 still gains (1.54x at 2, 1.84x at 4) | below; the M4 rows on 10-20 also showed processes only +12% over threads at N=2 |
| Kraken recognition | threads, 1 torch thread | 2 (Air: 1.19x) | below |
| OpenCV preprocessing | **threads**, `cv2.setNumThreads(1)`, N = **all cores** | 8 on the M1 Air (3.3x), no knee yet | below |
| spaCy | threads, one `nlp` a thread; **not** `n_process` | 4 threads 2.15x; n_process loses at every N | below |
| embedder (e5-large ONNX) | **one session, intra-op threads = P-cores**; not more sessions | 4 intra-op 2.8x; 2 sessions × 2 threads loses (2.1x) | below |
| DuckDB writes | one writer, **one bulk insert a page** (DataFrame / `append`) | 15–18x faster than per-row upserts; ON CONFLICT on new rows in one long transaction runs out of memory | below |
| MLX readers | not measured (no model) | online advice and old code below | |

### What a segmentation page spends its time on (cProfile, 1 torch thread, 3265×2202 page, 27.4 s on the loaded Pro)
- network forward 12.4 s = 45% (convolutions 8.4 s, LSTM 3.0 s)
- vectorizer `vec_lines` → `vectorize_lines` 9.1 s = 33%, of which skimage `sato` ridge filter 6.6 s (scipy `gaussian_filter`, single-threaded)
- polygonizer `calculate_polygonal_environment` 5.0 s = 18% (shapely 2.4 s across 452k calls; `_calc_seam` 1.9 s)

What does and does not make it faster:
| change | effect | pages |
|---|---|---|
| **downscale before segmenting** (to 1800 px high) | **none**: 22.1 → 24.8 s, 22.4 → 20.0 s, same lines (48/48, 88/88). blla resizes every page to the network's 1800 px height (`model.input = (1, 3, 1800, 0)`) and vectorizes and polygonizes at that scale | Pro |
| **network on MPS** (`blla.segment(..., device="mps")`) | **−28%** a page (22.1 → 15.9 s, 22.4 → 17.2 s), same lines. The engine passes no `device` (`kraken_runtime.py:1138`, `:1392`), so segmentation is CPU-only today. MPS ran out of memory on a third page on the 16 GB Pro under load: it needs a memory check | Pro |
| torch threads 1 → 4 | +7% (4.6 → 4.9 pages/min) for +21% CPU | M1 Air |
| 2 pages at once (threads) | +57% (Air) / +54% (M4) | both |

## Tables
Rows show items/min (pages; spaCy docs; embedder batches of 16 lines), CPU-s an item, CPU % of one core, peak RSS GB (summed over processes). Every row has rc=0 unless noted.

### Kraken segmentation, blla alone
| config (pages at once × torch threads) | M1 Air, 8 pages | M4, 12 pages |
|---|---|---|
| thread 1×1 | 4.6 / 12.5 / 96% / 3.0 GB, swap +480 MB | 8.3 / 7.1 / 99% / 7.3 GB, rc=139 at exit |
| thread 1×4 | 4.9 / 14.4 / 117% / 3.3 | (lost with the M4) |
| thread 2×1 | **7.2** / 14.4 / 172% / 3.4 | **12.8** / 8.4 / 180% / 7.1, rc=134 at exit |
| thread 2×2 | 6.2 / 17.1 / 177% / 2.7 | |
| thread 4×1 | 4.9 / 22.5 / 185% / 3.0 | **15.3** / 11.8 / 301% / 7.3, rc=139 at exit |
| process 2×1, 2×2, 4×1 | skipped: < 2.5 GB free | 4×1 row took the M4 off the network (no row) |
M4, 10-20 (`gil-proof-result-2026-10-20.md`, 15 pages ×3, blla at 1 thread): processes 16.0 / 27.7 / 26.4 at N=1/2/4, threads 16.2 / 24.3 / 22.7. Peak RSS is set by the BIGGEST page (7.3 GB for one 6944×4934 page at N=1), not by N: the memory budget has to come from page size.

### Kraken recognition (Kraken 7 `RecognitionTaskModel`, batch 1, CPU, lines pre-segmented; each thread its own reader copy, as `_own_reader` does)
| config | M1 Air, 8 pages |
|---|---|
| thread 1×1 | 12.6 / 4.7 / 100% / 1.47 GB |
| thread 2×1 | 15.0 / 7.4 / 186% / 1.62 GB (1.19x; CPU per page +57%) |
The M4 rows were lost with the M4.

### OpenCV preprocessing (imread → gray → blur → adaptive threshold → open → Canny + HoughLinesP → resize → PNG), 12 pages × 2, M1 Air
| config (workers × cv2.setNumThreads) | pages/min | CPU % | RSS |
|---|---|---|---|
| thread 1×1 | 124 | 100 | 1.18 |
| thread 1×4 | 200 | 202 | 1.30 |
| thread 1×8 | 194 | 199 | 1.32 |
| thread 2×1 | 199 | 168 | 1.32 |
| thread 4×1 | 285 | 271 | 1.74 |
| thread 4×2 | 343 | 394 | 1.67 |
| **thread 8×1** | **406** | 551 | 2.06 |
| process 4×1 | 262 | 266 | 2.34 |
| process 8×1 | 343 | 460 | 3.85 |
cv2's own threads stop paying past 2. Threads release the GIL (imread/JPEG decode included) and beat processes at the same N with half the memory.

### spaCy es_core_news_sm on the read text (8 pages × 40 = 320 short docs), M1 Air
| config | docs/min | CPU % | RSS |
|---|---|---|---|
| 1 thread (`nlp(text)`) | 3152 | 100 | 0.33 |
| 2 threads, one nlp each | 4550 | 164 | 0.39 |
| 4 threads, one nlp each | **6790** | 259 | 0.49 |
| `nlp.pipe(batch_size=50)`, n_process 1 | 3633 | 100 | 0.66 (parent) |
| n_process 2 | 3144 | 160 | 0.61 (parent) |
| n_process 4 | 2548 | 188 | 0.53 (parent) |
`nlp.pipe` batching gives +15% on one thread. `n_process` (spawn on macOS) is slower at every N for a page-sized workload. Combine the two: threads, each with its own nlp and `nlp.pipe` over its pages. The engine never uses `nlp.pipe` (`knowledge/spacy_svo.py:215-223`, `spacy_ner.py:224`).

### Embedder (the app's multilingual-e5-large ONNX, opened read-only with onnxruntime; batches of 16 lines), M1 Air
| config (sessions × intra-op threads) | batches/min | CPU % | RSS |
|---|---|---|---|
| 1 × 1 | 24.0 | 100 | 1.31 |
| **1 × 4** | **67.2** | 400 | 1.35 |
| 2 × 2 (two threads, one shared session) | 50.6 | 300 | 1.58 |
The engine's default is `embed_threads` = half the cores (`core/background_compute.py:63-70`), one call at a time (`:73-77`). That is the right shape: 4 intra-op threads on the M1 is 2.8x. A second concurrent call loses.

### DuckDB writes, scratch file, 200 pages × (35 lines + 20 names), M1 Air
| mode | ms a page | peak RSS GB |
|---|---|---|
| per-row upsert (`INSERT … ON CONFLICT DO UPDATE`), autocommit | 33.0 | 0.17 |
| per-row upsert, one transaction a page | 28.2 | 0.18 |
| `executemany` upsert, one transaction a page | 27.6 | 0.18 |
| **DataFrame `INSERT INTO t SELECT * FROM df`, one transaction a page** | **1.8** | 0.13 |
| `con.append(table, df)`, one transaction a page | 2.7 | 0.13 |
| 1000 pages (55k NEW rows) upserted with ON CONFLICT in ONE transaction | **OutOfMemoryException** ("failed to allocate 32 KiB (6.3 GiB/6.3 GiB used)"), RSS 2.05 GB | — |
| the same 55k rows, plain INSERT, one transaction | 3.1 | 0.16 |
The engine already learned the second lesson (`db/__init__.py:2317-2323`: plain INSERT for new rows inside transactions). The first one (bulk insert per page, not row upserts) is a 15x lever still open wherever lines and names are written row by row. DuckDB's own advice is the same (links below).

## Old code: what it did (read only)
the legacy tools checkout (`fichero_archive`) and the stale-branches bundle of 2026-07-30 (cloned to scratch; `release/2026.07.18`):
- OpenCV went through a **thread pool, one page a task**: `_archive/fichero_legacy/tools/utils/parallel_batch_processor.py:86-89` (ThreadPoolExecutor, `process_image_fn(full_path, out_path)`). cv2 threads were never capped (`tools/rotate.py:33-63`, `tools/segment.py:150-183`: no `setNumThreads` anywhere).
- Worker count on Apple Silicon: `max(2, cores // 2)` (`director/backends/worker_sizing.py:52-55`), capped at 4 per tool when one folder runs and 2 when up to 3 run (`director/backends/implementations/python_backend.py:323-330`).
- The model ran on a **downscaled copy** with coordinates scaled back (`tools/crop.py:300-339`, YOLO at 640 px). That helps a detector with a fixed input. It does **not** help blla, which already resizes to 1800 px (measured above).
- Every tool wrote **one output file a page, as soon as the page finished** (`out_path` in the processor above), plus JSONL manifests (`_archive/library_sqlite/services/tool_execution_service.py:414`). Bulk index writes used `executemany` (`_archive/library_sqlite/storage.py:3003`).
- MLX (July engine): an `mlx_lm` **server in its own process** (`fichero-engine/src/fichero/local_inference.py:515`), `max_concurrency = 1` (`:87`). There is no batching and no `mx.eval`/stream tuning anywhere, in the old code or today (`llm/mlx_in_process.py`, `llm/mlx_runtime.py`).
- The July ingest used `ThreadPoolExecutor(min(8, cores))`, but the whole `ingest_file` ran under one `db_lock` (`importers/ingest.py:1105-1132`). In effect it ran serially: a pool in front of one lock buys nothing.
- Kraken: the old code had no Kraken trick at all. So "the old code was fast" comes from per-page thread pools for OpenCV, writing as each page finished, and a model input downscaled for a detector. None of those is a Kraken lever today, except threads, which the engine already uses.

## Today's engine, where it touches this
`core/cores.py:74-88` (cores: SLURM → cgroup → P-cores → affinity); `llm/kraken_runtime.py:1022` (torch threads = cores ÷ pages inside), `:1033-1035` (`set_num_threads` is PROCESS-wide, so the last page to start sets it for all), `:1051-1054` (a page = its own thread under the gate), `:1294` (`num_line_workers=0`, batch 1 `:1264-1268`), `:1138`/`:1392` (blla with no `device`); `execution/jobs.py:105` (lanes local-ml 1, embed 1, images 2); `db/embed_process.py:3-12` (e5 in a forked child); `db/__init__.py:1050-1064` (one writer gate, a separate read connection).
Per-page logging, which the manager asked about: `_log_page` (`kraken_runtime.py:962-971`) writes one INFO line per page with `priority= qos= threads= throttle=`, but the e2e engine log (`m4:~/fichero-run/out2/uv_uds_*.log`, 1496 lines) holds **no INFO lines**, so it is filtered. Recipe runs also pass `run_call` (`kraken_runtime.py:1417`, `:1441`, `:1500`), which may bypass `_kraken_call` and so never reach `_log_page`.

## Online advice (with the claim each supports)
- PyTorch intra-op threads; must be set before eager work: https://docs.pytorch.org/docs/2.14/generated/torch.set_num_threads.html ; one inter-op pool shared by all tasks, oversubscription warning: https://docs.pytorch.org/2.3/notes/cpu_threading_torchscript_inference.html ; torch ops release the GIL (forum answer, not docs): https://discuss.pytorch.org/t/can-pytorch-by-pass-python-gil/55498/2
- Shapely 2 releases the GIL; GEOS reentrant API: https://pypi.org/project/shapely/2.0.0/ , https://libgeos.org/project/rfcs/rfc03/ . Kraken's tracker shows polygonizer TopologyExceptions but no thread segfault: https://github.com/mittagessen/kraken/issues/575 . The #5929 crash measured here is not GEOS (Surprises).
- OpenCV releases the GIL in its wrappers (`ERRWRAP2` / `PyAllowThreads`): https://answers.opencv.org/question/182036/how-does-the-gil-release-happen-for-drawing-functions-exposed-to-python ; `setNumThreads` sets the threads for the next parallel region: https://forum.opencv.org/t/what-is-setnumthreads-for/3651 (docs.opencv.org refused the fetch, 403)
- spaCy: `n_process` on macOS uses spawn, "can be slow for larger models"; fewer processes with a larger batch for short tasks: https://spacy.io/usage/processing-pipelines
- MLX: not thread-safe until 0.31.2 (fixed by the maintainers' account; streams are thread-bound); in-process parallelism via separate `mx.stream`s plus one `mx.eval`, or separate processes: https://github.com/ml-explore/mlx/issues/3078 ; 0.31.2 stream-from-another-thread regression: https://github.com/waybarrios/vllm-mlx/issues/496 ; unbounded KV cache wired ~75% RAM and panicked a Mac: https://github.com/ml-explore/mlx-lm/issues/883 . The installed mlx is 0.32.2.
- DuckDB: "row-by-row inserts (even with prepared statements) [are] detrimental"; the appender is available in Python: https://duckdb.org/docs/2.0/guides/performance/import.html ; indexes "significantly increase memory" and are "not buffer-managed"; memory_limit 50–60% when the OS kills: https://duckdb.org/docs/2.0/guides/performance/oom.html ; one writer process (1.4): https://duckdb.org/docs/1.4/connect/concurrency
- Apple QoS: background QoS threads run only on E-cores and are never promoted; `taskpolicy -b` confines a process to E-cores: https://eclecticlight.co/2025/05/09/what-is-quality-of-service-and-how-does-it-matter/ ; `pthread_set_qos_class_self_np`: https://opensource.apple.com/source/libpthread/libpthread-301.1.6/sys/qos.h.auto.html

## Surprises
1. **#5929's exit crash is torch 2.14, not threads and not GEOS.** 3 of 3 M4 crash reports (`m4:~/Library/Logs/DiagnosticReports/python3.12-2026-10-27-121726/121838/122000.ips`) crash on the main thread in `exit()` → `__cxa_finalize_ranges` → `libtorch_cpu at::native::mps::MetalShaderLibrary::~MetalShaderLibrary()` (SIGSEGV, or SIGABRT "pointer being freed was not allocated"). This happened with ONE worker thread, on CPU-only runs. Every row had printed before it, so it is exit-time. torch 2.12 on the M1 Air never crashed. PYTHONFAULTHANDLER shows no Python stack, because the crash happens after Python has finished. Fix: end processes with `os._exit` after flushing, or pin torch < 2.14.
2. **Downscaling does nothing for blla**, and the old code's downscale was for a different model.
3. **Segmentation never uses the GPU.** MPS is −28% a page for one keyword argument (memory-guarded).
4. **Torch threads are nearly worthless for blla.** Two-thirds of a page after the convolutions is single-threaded scipy/skimage/shapely. Pages at once is the only lever, and it knees at 2 on the M1 8 GB.
5. **Memory per page is set by the page's pixels.** One 6944×4934 page took a single-thread process to 7.3 GB on the M4 (3 GB on the Air for 8 smaller pages). Peak × N processes is what took the M4 off the network. `compute_bench_run.sh` now refuses a process row without N × `PER_PROC_GB` (7) free.
6. **ON CONFLICT on new rows in one long transaction runs a DuckDB on an 8 GB Mac out of memory at 55k rows.** A plain INSERT of the same rows takes 3 s and 0.16 GB.
7. **OpenCV wants every core, as threads.** It is the one engine here where "max the machine" really means all the cores (3.3x at 8 on the M1; no knee yet).

## Not done (time box)
Process rows for segmentation and recognition on the M4 (the machine dropped); MPS rows on a quiet M4; MLX (no model); the M4 rows for OpenCV, spaCy, embedder and recognition. The configs are in this commit's scripts. On a quiet M4 the next rows are, in order: seg thread 2×1 `--device mps`, seg proc 2×1 (`PER_PROC_GB=7`), rec thread 1/2/4.
