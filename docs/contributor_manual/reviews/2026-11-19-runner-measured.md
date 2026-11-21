# Runner, measured: the runtime matrix on two Macs (2026-11-19)

`scripts/runtime_matrix.py` (#6675) run on the iMac and the M4 Air, every runtime, 5 fixture pages twice, each runtime in a
fresh process. The measurement of Kraken's memory and the embedder is in the read-only review
`kraken-embedder-review` (iMac, same day); this page records the matrix numbers and what was done about them.

## Machines

| Mac | Chip | RAM | macOS | Free at start |
|---|---|---|---|---|
| iMac | Apple M4 | 24 GB | 26.7.3 | 12,056 MB |
| M4 Air | Apple M4 | 16 GB | 27.2.1 | 3,228 MB |

The 8 GB M1 Air was not run. The M4 Air ran everything from the external dev disk.

## Numbers

| Runtime | Mac | Result | First page s | s/page | Peak RSS MB | Loads per run |
|---|---|---|---|---|---|---|
| Kraken segment | iMac | ok | 10.32 | 7.05 | 9,540 | 1 |
| Kraken segment | M4 Air | ok | 11.23 | 7.35 | 5,271 | 1 |
| Kraken recognise | both | unavailable: no reader installed in the model store | - | - | - | - |
| Embedder | iMac | ok | 118.25 (a model download) | 0.00 | 3,509 | 1 |
| Embedder | M4 Air | ok | 86.75 (a model download) | 0.00 | 1,931 | 1 |
| spaCy names | iMac | ok | 1.40 | 0.003 | 334 | 1 |
| spaCy names | M4 Air | ok | 2.41 | 0.003 | 339 | 1 |
| OpenCV preprocess | iMac | ok | 0.28 | 0.002 | 122 | n/a |
| OpenCV preprocess | M4 Air | ok | 0.35 | 0.003 | 122 | n/a |
| MLX VLM, Whisper, YOLO | both | not measured: the gate venvs lack `mlx_vlm`, `mlx_whisper`, `ultralytics` | - | - | - | - |
| Apple Vision | iMac | unavailable (needs macOS 27) | - | - | - | - |
| Apple Vision | M4 Air | unavailable (no Python entry; the app's Swift bridge calls it) | - | - | - | - |

Every measured model loaded once per run: no per-page reload.

## What the numbers mean (from the review)

- **Kraken's 9.5 GB is the fixtures, not real pages.** The fixtures are 100 to 900 px wide and Kraken scales every page to
  1800 rows, so the 900 x 400 fixture is a 4050 x 1800 network input. A real portrait page peaks at 3.8 GB, a two-page
  spread at 7.5 GB; either will not fit an 8 GB Mac with other work. Cause: torch's CPU convolutions keep an im2col
  buffer for the whole page.
- **The embedder's 87 to 118 s was a download** (2.27 GB), not a load. Loaded from disk it takes 0.5 to 2.2 s and 1.7 GB.
- **MLX, Whisper and YOLO were not measured.** The matrix could only run under the Python it was started with.

## Done in this lane

| Change | Test |
|---|---|
| Kraken's convolutions run 32 output rows at a time: portrait 3.8 to 1.9 GB, spread 7.5 to 3.4 GB, identical lines and polygons | `test_kraken_banded_convolutions_perf1.py` |
| The embedder and Kraken are never loaded together (owner rule 2026-11-19); a load frees the other or waits | `test_kraken_and_embedder_never_resident_together_perf1.py` |
| Kraken's guard is 0.5 GB + 0.6 GB per megapixel of the 1800-row network input, not a flat 2.5 GB | `test_kraken_guard_sized_by_the_page_perf1.py` |
| The matrix: an A4 page at 300 dpi in the sample, the embedder offline, footprint beside RSS, `--python PATH` | `test_runtime_matrix.py` |

Run the matrix under the shipped engine's Python so MLX VLM, Whisper and YOLO are measured:
`PYTHONPATH=fichero-server/src python3 scripts/runtime_matrix.py --engine-app <the built engine .app> --out matrix.json`
(its bundled Python and `Contents/Resources/app_packages`, where `ultralytics`, `mlx_vlm` and `mlx_whisper` ship; `--python PATH` names an
interpreter directly). YOLO's weights must be downloaded to the model store first, else its row says so. Not yet run: workers cannot
reach the Macs, so YOLO, MLX and Whisper are still unmeasured.

## Kraken on 7 real archive pages (iMac M4, 2026-11-19)

Handwritten and printed pages, 3000 x 2000 to 3264 x 2448 px, one fresh process per row. "Default" is Kraken as it was,
"banded" is 32-row convolutions (shipped), "banded + height 1200" also lowers the network height from 1800 to 1200.

| Page | Variant | s/page | Peak RSS MB | Lines |
|---|---|---|---|---|
| 1 | default | 7.44 | 5,515 | 17 |
| 1 | banded | 6.19 | 3,338 | 17 |
| 1 | banded + height 1200 | 3.05 | 1,871 | 17 |
| 2 | default | 6.79 | 7,719 | 22 |
| 2 | banded | 6.66 | 3,572 | 22 |
| 2 | banded + height 1200 | 3.36 | 1,890 | 22 |
| 3 | default | 10.85 | 7,165 | 105 |
| 3 | banded | 10.69 | 3,178 | 105 |
| 3 | banded + height 1200 | 6.27 | 1,774 | 116 |
| 4 | default | 9.60 | 7,145 | 104 |
| 4 | banded | 9.63 | 3,176 | 104 |
| 4 | banded + height 1200 | 5.38 | 1,780 | 126 |
| 5 | default | 10.05 | 7,119 | 104 |
| 5 | banded | 9.97 | 3,180 | 104 |
| 5 | banded + height 1200 | 5.65 | 1,782 | 120 |
| 6 | default | 3.13 | 4,092 | 43 |
| 6 | banded | 3.13 | 1,994 | 43 |
| 6 | banded + height 1200 | 1.53 | 1,200 | 50 |
| 7 | default | 4.65 | 4,153 | 42 |
| 7 | banded | 4.63 | 2,033 | 42 |
| 7 | banded + height 1200 | 2.54 | 1,168 | 36 |

- **Banded 32 rows** keeps the line count on all 7 pages, cuts the peak from 4.1 to 7.7 GB down to 2.0 to 3.6 GB, and is
  the same speed or faster. It is the default.
- **Network height 1200** halves the time and brings the peak to about 1.8 GB, but the line count changes on 5 of 7 pages
  (105 to 116, 104 to 126, 104 to 120, 43 to 50, 42 to 36). It is not a default. It becomes an opt-in "fast, less exact"
  setting for small Macs, in the Models window (models-window lane); not built here.

## Not measured, not done: issues to file

No GitHub token reaches a worker, so these are written here for the manager to file (milestone `recipes-run`).

1. **MLX VLM, Whisper and YOLO have no measurement** (not measured on either Mac). Re-run the matrix with `--python` on the
   iMac, the M4 Air and the M1 Air; MLX failures are top priority.
2. **Kraken recognise has no reader on either Mac**, so its load time, per-page time and memory are unmeasured. Install a
   reader in the model store and run the matrix.
3. **Kraken segment 7.0 to 7.4 s per page**: does the banded 2.0 to 3.6 GB fit the 8 GB M1 Air? Run the matrix with the
   real-size page on it. The opt-in "fast, less exact" network height 1200 setting (Models window, models-window lane) is
   to build: the real pages above show it changes line counts, so it is never the default.
4. **Kraken in a seed-forked child**: the memory leaves after a run and a runaway page can be killed (the line vectoriser
   is unbounded on noisy pages, kraken issue #765). Medium work.
5. **Smaller embedder** (fp16 or int8): saves up to 1 GB, costs a re-embed of every library.
6. **The test `test_one_model_at_a_time_on_the_lane.py::test_an_embed_during_a_kraken_run_unloads_nothing` fails at the base
   commit** (the fake embed job never runs beside a held Kraken job) and asserts the embedder beside Kraken, which the
   owner rule 2026-11-19 reverses; it needs rewriting by whoever owns that lane test.

Not measured on the M1 Air: nothing here ran on it (#6745 item 5, Kraken blla 20 s a page on 4000 px images).
