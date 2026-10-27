#!/usr/bin/env python3
"""How to use a Mac's compute, per engine: threads x inner threads in one process against N spawned processes (2026-10-27,
agent-work/status/briefs/compute-measurements-2026-10-27.md). A MEASUREMENT, not a test. Standalone: it never imports
the engine, so it never opens an app library; run it with FICHERO_BASE_PATH=$(mktemp -d) anyway.

  seg    Kraken blla segmentation. Threads share one model (as the engine does); `--inner` = torch threads.
  prep   segment the pages once and pickle the result (--cache), for `rec`.
  rec    Kraken 7 recognition on the cached lines, batch 1, CPU; each thread its own reader copy (as the engine does).
  cv     OpenCV preprocessing (gray, blur, adaptive threshold, open, Canny + Hough, resize, PNG encode); `--inner` =
         cv2.setNumThreads.
  spacy  nlp.pipe over page texts (--texts, one page a line); `--kind proc` = spaCy's own n_process=N, `thread` = N
         threads each with its own nlp; `--inner` = batch size.
  duck   DuckDB writes of a page's lines and names on a scratch file: per-row upsert, one transaction, executemany,
         a DataFrame insert; `--mode upsert-mem|insert-mem` = memory of 50k new rows in ONE transaction.

Each run prints one JSON line: pages/min, CPU-seconds a page, peak RSS (summed over processes), exit details.

  python compute_bench.py seg --images DIR --pages 12 --kind thread --n 2 --inner 2
  python compute_bench.py seg --images DIR --pages 12 --kind proc --n 4 --inner 1
"""

from __future__ import annotations

import argparse
import copy
import json
import multiprocessing as mp
import os
import pickle
import resource
import sys
import threading
import time
from pathlib import Path

POOLS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")


def rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**3  # bytes on macOS


def cpu_s() -> float:
    use = resource.getrusage(resource.RUSAGE_SELF)
    return use.ru_utime + use.ru_stime


def pages_in(images: Path, count: int) -> list[str]:
    files = sorted(str(p) for p in images.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"})
    return files[:count]


# -- the stages: load(inner, args) -> state; work(state, item) ----------------------------------------------------------
def _torch(inner: int) -> None:
    import torch

    torch.set_num_threads(inner)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass


def seg_load(inner, args):
    from importlib import resources

    from kraken.lib import vgsl

    _torch(inner)
    return {"model": vgsl.TorchVGSLModel.load_model(resources.files("kraken").joinpath("blla.mlmodel")),
            "device": getattr(args, "device", "cpu")}


def seg_work(state, path):
    from kraken import blla
    from PIL import Image

    with Image.open(path) as image:  # the engine passes no device (CPU); --device mps runs the network on the GPU
        return blla.segment(image.convert("RGB"), model=state["model"], device=state["device"])


def rec_load(inner, args):
    from kraken.configs import RecognitionInferenceConfig
    from kraken.tasks import RecognitionTaskModel

    _torch(inner)
    config = RecognitionInferenceConfig(accelerator="cpu", device=1, num_line_workers=0)
    if hasattr(config, "batch_size"):
        config.batch_size = 1  # the engine's reader_batch_size (#5854)
    with open(args.cache, "rb") as handle:
        segs = pickle.load(handle)
    return {"net": RecognitionTaskModel.load_model(args.model), "config": config, "segs": segs}


def rec_fork(state):  # each thread its own reader copy, as kraken_runtime._own_reader does
    return {**state, "net": copy.deepcopy(state["net"])}


def rec_work(state, path):
    from PIL import Image

    with Image.open(path) as image:
        return [r.prediction for r in state["net"].predict(image.convert("RGB"), state["segs"][path], state["config"])]


def cv_load(inner, args):
    import cv2

    cv2.setNumThreads(inner)
    return None


def cv_work(_state, path):
    import cv2
    import numpy as np

    image = cv2.imread(path, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 15)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    edges = cv2.Canny(gray, 50, 150)
    cv2.HoughLinesP(edges, 1, np.pi / 180, 200, minLineLength=gray.shape[1] // 4, maxLineGap=20)
    scale = 2000 / max(gray.shape)
    small = cv2.resize(opened, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return len(cv2.imencode(".png", small)[1])


def spacy_load(inner, args):
    import spacy

    return spacy.load(args.spacy_model)


def spacy_work(nlp, text):
    return len(nlp(text).ents)


def embed_load(inner, args):
    """The search embedder's model (fastembed's e5 ONNX) opened READ-ONLY with onnxruntime; `--inner` = intra-op threads."""
    import onnxruntime as ort
    from tokenizers import Tokenizer

    options = ort.SessionOptions()
    options.intra_op_num_threads = inner
    options.inter_op_num_threads = 1
    folder = Path(args.onnx_dir)
    tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
    tok.enable_truncation(512)
    tok.enable_padding()
    return {"session": ort.InferenceSession(str(folder / "model.onnx"), options), "tok": tok}


def embed_work(state, texts):
    import numpy as np

    enc = state["tok"].encode_batch(["passage: " + t for t in texts])
    feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
    names = {i.name for i in state["session"].get_inputs()}
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
    return state["session"].run(None, feed)[0].shape


STAGES = {"embed": (embed_load, None, embed_work),"seg": (seg_load, None, seg_work), "rec": (rec_load, rec_fork, rec_work), "cv": (cv_load, None, cv_work),
          "spacy": (spacy_load, None, spacy_work)}


def _items(args) -> list[str]:
    if args.stage in ("spacy", "embed"):
        texts = [ln.replace("\\n", "\n") for ln in Path(args.texts).read_text().splitlines() if ln.strip()]
        texts = (texts * args.repeat)[: args.pages * args.repeat]
        if args.stage == "embed":  # an item = a batch of 16 lines, as an embed job sends chunks
            lines = [x for t in texts for x in t.split("\n") if len(x.strip()) > 3]
            return [lines[i:i + 16] for i in range(0, len(lines), 16)]
        return texts
    return pages_in(args.images, args.pages) * args.repeat


# -- the fan-outs -------------------------------------------------------------------------------------------------------
def _child(stage, inner, args, items, ready, go, done) -> None:
    load, _fork, work = STAGES[stage]
    state = load(inner, args)
    work(state, items[0])  # warm: lazy imports and first-call allocations are not timed
    ready.put(os.getpid())
    go.wait()
    began, cpu0 = time.time(), cpu_s()
    for item in items:
        work(state, item)
    done.put((began, time.time(), cpu_s() - cpu0, rss_gb()))


def run_procs(args, items):
    for name in POOLS:  # inherited by the spawned children before torch/cv2 load
        os.environ[name] = str(args.inner)
    ctx = mp.get_context("spawn")
    parts = [items[i:: args.n] for i in range(args.n) if items[i:: args.n]]
    ready, done, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    workers = [ctx.Process(target=_child, args=(args.stage, args.inner, args, part, ready, go, done)) for part in parts]
    for w in workers:
        w.start()
    for _ in workers:
        ready.get()
    go.set()
    results = [done.get() for _ in workers]
    for w in workers:
        w.join()
    wall = max(r[1] for r in results) - min(r[0] for r in results)
    return wall, sum(r[2] for r in results), sum(r[3] for r in results) + rss_gb(), [w.exitcode for w in workers]


def run_threads(args, items):
    for name in POOLS:
        os.environ[name] = str(args.inner)
    load, fork, work = STAGES[args.stage]
    if args.stage == "spacy":  # spaCy's nlp is not thread-safe (knowledge/spacy_ner.py): one pipeline a thread
        states = [load(args.inner, args) for _ in range(args.n)]
    else:
        base = load(args.inner, args)
        states = [fork(base) if fork else base for _ in range(args.n)]
    for s in states:
        work(s, items[0])
    errors: list[BaseException] = []

    def loop(state, part):
        try:
            for item in part:
                work(state, item)
        except BaseException as exc:  # noqa: BLE001 -- a crash in a thread is a result
            errors.append(exc)

    pool = [threading.Thread(target=loop, args=(states[i], items[i:: args.n])) for i in range(args.n)]
    began, cpu0 = time.perf_counter(), cpu_s()
    for t in pool:
        t.start()
    for t in pool:
        t.join()
    if errors:
        raise errors[0]
    return time.perf_counter() - began, cpu_s() - cpu0, rss_gb(), []


def run_spacy_pipe(args, items):
    """spaCy's own fan-out: nlp.pipe(n_process=N, batch_size=inner); spawn on macOS, startup included in the wall."""
    nlp = spacy_load(args.inner, args)
    list(nlp.pipe(items[:2]))
    began, cpu0 = time.perf_counter(), cpu_s()
    for doc in nlp.pipe(items, n_process=args.n, batch_size=args.inner):
        len(doc.ents)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.perf_counter() - began, cpu_s() - cpu0 + child.ru_utime + child.ru_stime, rss_gb(), []


def prep(args) -> None:
    model = seg_load(4, args)
    segs = {p: seg_work(model, p) for p in pages_in(args.images, args.pages)}
    with open(args.cache, "wb") as handle:
        pickle.dump(segs, handle)
    if args.model and args.texts:  # the read text of each page, one page a line, for spacy
        state = rec_load(4, args)
        Path(args.texts).write_text("".join("\\n".join(rec_work(state, p)) + "\n" for p in segs))
    print(json.dumps({"stage": "prep", "pages": len(segs), "lines": sum(len(s.lines) for s in segs.values())}))


# -- DuckDB ---------------------------------------------------------------------------------------------------------------
def duck(args) -> None:
    import uuid

    import duckdb
    import pandas as pd

    path = Path(args.db)
    if path.exists() or not str(path.resolve()).startswith(("/private/tmp", "/private/var/folders")):
        sys.exit(f"{path}: must be a NEW file under a temp dir (never an app library)")
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE lines (id VARCHAR PRIMARY KEY, doc VARCHAR, page INT, n INT, text VARCHAR, conf DOUBLE,"
                " box VARCHAR)")
    con.execute("CREATE TABLE names (id VARCHAR PRIMARY KEY, line_id VARCHAR, name VARCHAR, kind VARCHAR)")

    def page_rows(p):
        lines = [(str(uuid.uuid4()), "doc1", p, i, f"línea {i} de la página {p} con algún texto leído" * 2, 0.9,
                  "[[1,2],[3,4]]") for i in range(35)]
        names = [(str(uuid.uuid4()), lines[i % 35][0], f"Nombre {i}", "PER") for i in range(20)]
        return lines, names

    up_l = ("INSERT INTO lines VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET text = excluded.text,"
            " conf = excluded.conf")
    up_n = "INSERT INTO names VALUES (?,?,?,?) ON CONFLICT (id) DO UPDATE SET name = excluded.name"
    pages = [page_rows(p) for p in range(args.pages)]
    mem0 = rss_gb()
    began = time.perf_counter()
    if args.mode == "row-autocommit":
        for lines, names in pages:
            for r in lines:
                con.execute(up_l, r)
            for r in names:
                con.execute(up_n, r)
    elif args.mode == "row-txn-per-page":
        for lines, names in pages:
            con.execute("BEGIN")
            for r in lines:
                con.execute(up_l, r)
            for r in names:
                con.execute(up_n, r)
            con.execute("COMMIT")
    elif args.mode == "executemany-per-page":
        for lines, names in pages:
            con.execute("BEGIN")
            con.executemany(up_l, lines)
            con.executemany(up_n, names)
            con.execute("COMMIT")
    elif args.mode == "df-per-page":
        for lines, names in pages:
            ldf = pd.DataFrame(lines, columns=["id", "doc", "page", "n", "text", "conf", "box"])  # noqa: F841
            ndf = pd.DataFrame(names, columns=["id", "line_id", "name", "kind"])  # noqa: F841
            con.execute("BEGIN")
            con.execute("INSERT INTO lines SELECT * FROM ldf")
            con.execute("INSERT INTO names SELECT * FROM ndf")
            con.execute("COMMIT")
    elif args.mode == "append-per-page":  # DuckDB's Python appender path: con.append(table, DataFrame)
        for lines, names in pages:
            con.execute("BEGIN")
            con.append("lines", pd.DataFrame(lines, columns=["id", "doc", "page", "n", "text", "conf", "box"]))
            con.append("names", pd.DataFrame(names, columns=["id", "line_id", "name", "kind"]))
            con.execute("COMMIT")
    elif args.mode in ("upsert-mem", "insert-mem"):  # ONE long transaction of new rows: ON CONFLICT vs plain INSERT
        sql_l = up_l if args.mode == "upsert-mem" else "INSERT INTO lines VALUES (?,?,?,?,?,?,?)"
        sql_n = up_n if args.mode == "upsert-mem" else "INSERT INTO names VALUES (?,?,?,?)"
        con.execute("BEGIN")
        for lines, names in pages:
            con.executemany(sql_l, lines)
            con.executemany(sql_n, names)
        con.execute("COMMIT")
    wall = time.perf_counter() - began
    rows = con.execute("SELECT (SELECT count(*) FROM lines) + (SELECT count(*) FROM names)").fetchone()[0]
    con.close()
    print(json.dumps({"stage": "duck", "mode": args.mode, "pages": args.pages, "rows": rows, "wall_s": round(wall, 2),
                      "pages_per_s": round(args.pages / wall, 1), "ms_per_page": round(1000 * wall / args.pages, 1),
                      "rss_gb_before": round(mem0, 3), "peak_rss_gb": round(rss_gb(), 3)}), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=[*STAGES, "prep", "duck"])
    ap.add_argument("--images", type=Path)
    ap.add_argument("--pages", type=int, default=12)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--kind", choices=["thread", "proc"], default="thread")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--inner", type=int, default=1)
    ap.add_argument("--device", default="cpu", help="cpu or mps, for seg")
    ap.add_argument("--model", help="a Kraken 7 reader (.safetensors/.mlmodel), for rec")
    ap.add_argument("--cache", default="segs.pkl")
    ap.add_argument("--texts", help="page texts, one page a line, for spacy")
    ap.add_argument("--spacy-model", default="es_core_news_sm")
    ap.add_argument("--onnx-dir", help="the e5 ONNX snapshot folder (model.onnx, tokenizer.json), for embed; read only")
    ap.add_argument("--db", help="a NEW scratch DuckDB file, for duck")
    ap.add_argument("--mode", default="row-autocommit")
    args = ap.parse_args()
    if args.stage == "prep":
        return prep(args)
    if args.stage == "duck":
        return duck(args)
    items = _items(args)
    run = run_spacy_pipe if args.stage == "spacy" and args.kind == "proc" else (
        run_procs if args.kind == "proc" else run_threads)
    wall, cpu, rss, codes = run(args, items)
    print(json.dumps({"stage": args.stage, "kind": args.kind, "n": args.n, "inner": args.inner, "items": len(items),
                      "wall_s": round(wall, 2), "per_min": round(60 * len(items) / wall, 1),
                      "cpu_s_per_item": round(cpu / len(items), 2), "cpu_pct_of_one_core": round(100 * cpu / wall),
                      "peak_rss_gb": round(rss, 2), "child_exit": codes}), flush=True)


if __name__ == "__main__":
    main()
