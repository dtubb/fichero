"""Step 4: time the engine's public surface on the real pages, 5 measured runs after 1 cold.

Every timing is the CLI's own client (`FicheroClient`) in this process, over the engine's
Unix socket, so it is the engine's time plus one local round trip. One row also times the
CLI as a person runs it (`python -m fichero_cli ...`, a new process each time), to show
what the process start adds.

Import is timed as the pass import (`POST /api/documents/{id}/import`, the same audited
`format.import` the folder import calls per pair) of the densest page's ALTO file onto its
own page. Identical bytes are refused as a re-import, so each run appends a unique XML
comment, and each extra pass is deleted again through `DELETE /api/segments/passes/{id}`
so the library is left as the import made it.

Writes ACCEPTANCE_OUT/speed.json. Starts and stops its own engine. Pauses while load > 40.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import OUT, PYTHON, REPO, client, engine, load, load_avg, save, timed, wait_for_load  # noqa: E402

RUNS = 5


def main() -> None:
    rows = load("import.json")
    pages = {(r["key"], Path(p["name"]).stem): p for r in rows for p in r["pages"] if p.get("image")}
    dense = pages[("cherokee-inch1200-densest", "cherokee-phoenix_1828030601_0002")]
    small = pages[("syriac-rtl", "0002_00000017")]
    all_ids = [p["id"] for p in pages.values()]
    dense_xml = OUT / "staging" / "cherokee-inch1200-densest" / "cherokee-phoenix_1828030601_0002.xml"
    results: list[dict] = []

    def record(op: str, stats: dict, **extra) -> None:
        row = {"operation": op, **stats, **extra}
        results.append(row)
        print(row, flush=True)
        save("speed.json", results)

    with engine():
        with client() as c:
            dense_list = c.request("GET", f"/api/segments/document/{dense['id']}")
            n_dense = len(dense_list["segments"])
            small_list = c.request("GET", f"/api/segments/document/{small['id']}")
            line = next(s for s in small_list["segments"] if s["kind"] == "line")
            word = next(s for s in dense_list["segments"] if s["kind"] == "word")

            wait_for_load()
            _, st = timed(lambda: c.request("GET", f"/api/segments/document/{dense['id']}"), RUNS)
            record("list a document's segments (densest page)", st, segments=n_dense)
            _, st = timed(lambda: c.request("GET", f"/api/segments/document/{small['id']}"), RUNS)
            record("list a document's segments (small page)", st, segments=len(small_list["segments"]))

            wait_for_load()
            first = c.request("GET", "/api/segments", params={"document_ids": ",".join(all_ids), "limit": 200, "offset": 0})
            total = first["total"]
            _, st = timed(lambda: c.request("GET", "/api/segments", params={"document_ids": ",".join(all_ids), "limit": 200, "offset": 0}), RUNS)
            record("GET /api/segments, library scope, first page of 200", st, total=total)
            _, st = timed(lambda: c.request("GET", "/api/segments", params={"document_ids": ",".join(all_ids), "limit": 1000, "offset": max(total - 1000, 0)}), RUNS)
            record("GET /api/segments, library scope, last page of 1000", st, total=total)

            def walk():
                seen = offset = 0
                while True:
                    page = c.request("GET", "/api/segments", params={"document_ids": ",".join(all_ids), "limit": 1000, "offset": offset})
                    seen += page["count"]
                    offset += 1000
                    if offset >= page["total"]:
                        return seen

            seen, st = timed(walk, RUNS)
            record("GET /api/segments, whole library paged by 1000", st, total=total, seen=seen)

            wait_for_load()
            _, st = timed(lambda: c.request("GET", f"/api/segments/{line['id']}/readings"), RUNS)
            record("read one line's text (PAGE line, readings route)", st)
            _, st = timed(lambda: c.request("GET", f"/api/segments/{word['id']}/readings"), RUNS)
            record("read one word's text on the densest page", st)
            _, st = timed(lambda: c.request("GET", f"/api/segments/document/{dense['id']}/text"), RUNS)
            record("derive the densest page's whole text", st, segments=n_dense)

            wait_for_load()
            _, st = timed(lambda: c.request("GET", f"/api/documents/{dense['id']}/export/alto"), RUNS)
            record("export the densest page as ALTO", st, segments=n_dense)

            wait_for_load()
            env = dict(os.environ, PYTHONPATH=f"{REPO / 'fichero-cli/src'}:{REPO / 'fichero-server/src'}")
            cli = [PYTHON, "-m", "fichero_cli", "--json", "segments", "list-readings", line["id"]]
            _, st = timed(lambda: subprocess.run(cli, env=env, capture_output=True, check=True), RUNS)
            record("read one line's text via the CLI process (fichero segments list-readings)", st)

            # Import: a new pass of the densest page, 5 times, each deleted afterwards.
            wait_for_load()
            base = dense_xml.read_bytes()
            samples, made = [], []
            try:
                for i in range(RUNS + 1):
                    data = base + f"\n<!-- acceptance timing run {i} {time.time_ns()} -->\n".encode()
                    tmp = OUT / f"timing-{i}.xml"
                    tmp.write_bytes(data)
                    t0 = time.perf_counter()
                    res = c.import_page(dense["id"], tmp, import_format="alto", name=f"acceptance timing {i}")
                    elapsed = (time.perf_counter() - t0) * 1000
                    made.append(res["pass_id"])
                    tmp.unlink()
                    if i:  # the first is the discarded cold run
                        samples.append(elapsed)
                    segments = res.get("segments")
            finally:
                for pass_id in made:
                    c.request("DELETE", f"/api/segments/passes/{pass_id}")
            med = statistics.median(samples)
            record(
                "import the densest page's ALTO as a pass",
                {"median_ms": round(med, 1), "max_ms": round(max(samples), 1), "min_ms": round(min(samples), 1),
                 "runs": RUNS, "load_1m": round(load_avg(), 1)},
                segments=segments, per_1000_segments_ms=round(med / segments * 1000, 1),
            )
    save("speed.json", results)


if __name__ == "__main__":
    main()
