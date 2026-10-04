"""Reading at scale, at scale (#5398 slice 2): 10,000 pages and 1,000 IIIF canvases, with fakes.

The far side and the archive's server are fakes; the job's loop, the runner, the polite fetcher and
the PAGE files are real. Each test says what breaks at a size a sample of ten never shows.
"""
from __future__ import annotations

import io
import json
import threading

import pytest
from PIL import Image

from fichero_server import formats
from fichero_server.execution import jobs
from fichero_server.models import DocType, Document
from fichero_server.remote_read import job as read_job
from fichero_server.remote_read import runner
from fichero_server.remote_read.job import ReadAtScaleRequest
from fichero_server.remote_read.package import ReadPackage
from fichero_server.training.hf_jobs import FarStatus


class ScaleHub:
    """Hugging Face Jobs at a hundred shards: each Job finishes on its second look; the shards in
    `fail` fail on their first try only."""

    def __init__(self, fail):
        self.fail = set(fail)
        self.jobs: dict[str, dict] = {}
        self.list_calls = 0
        self.fetched: list[str] = []
        self.most_running = 0

    def price_per_hour(self, flavor):
        return 0.4

    def send(self, local_dir, job_key):
        pass

    def submit(self, job_key, *, labels, **kw):
        shard = labels["fichero-shard"]
        first = not any(j["shard"] == shard for j in self.jobs.values())
        self.jobs[f"far-{len(self.jobs)}"] = {"shard": shard, "looks": 0, "fails": first and shard in self.fail}
        return f"far-{len(self.jobs) - 1}"

    def statuses(self, job_key):
        self.list_calls += 1
        out = {}
        open_now = 0
        for far_id, j in self.jobs.items():
            j["looks"] += 1
            state = "running" if j["looks"] < 2 else ("failed" if j["fails"] else "done")
            open_now += state == "running"
            out[far_id] = FarStatus(state=state, stage=state.upper(), message="preempted" if j["fails"] else None)
        self.most_running = max(self.most_running, open_now)
        return out

    def last_lines(self, far_id, n=20):
        return ["slurmstepd: preempted"]

    def fetch_part(self, job_key, part, local_dir):
        self.fetched.append(part)
        return local_dir


def test_ten_thousand_pages_in_a_hundred_shards_three_fail_and_only_those_are_resent(db, tmp_path, monkeypatch):
    """WHY (`compute.job.array-by-shard`, `.sparse-resubmit`, `.poll-is-gentle`, `compute.land.idempotent`):
    at 10,000 pages a re-send of everything costs 97 shards of GPU for 3 shards of failure, a poll per
    shard is 100 requests a round, and landing a shard twice doubles a page's passes. Here: 100
    shards, at most 10 at once, 3 fail; the re-send is those 3; every shard lands exactly once."""
    monkeypatch.setattr(read_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(read_job, "resolve_step", lambda request, bucket: {"reader": "kraken", "card": "k",
                                                                           "model_file": "k.mlmodel"})
    folder = Document(name="EAP", doc_type=DocType.folder)
    db.save(folder)
    sources = [{"id": f"page-{i:05d}", "iiif_service": f"https://iiif.example/{i}"} for i in range(10_000)]
    shards = [list(range(i, i + 100)) for i in range(0, 10_000, 100)]
    package = ReadPackage(job_id="x", sources=sources, shards=shards)
    landed: dict[str, int] = {}

    def land(db_, job_id, folder_, *, pass_name, actor):
        shard = int(folder_.name.split("-")[1])
        for i in shards[shard]:
            landed[sources[i]["id"]] = landed.get(sources[i]["id"], 0) + 1
        return {"landed": len(shards[shard]), "already": 0, "unread": 0, "set_aside": 0}

    request = ReadAtScaleRequest(scope_ids=[folder.id], card="k", shard_size=100, max_in_flight=10,
                                 pages_may_leave=True)
    job_id = read_job.start(db, request, started_by="owner", target_factory=lambda: ScaleHub(()))["job_id"]
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [job_id])[0]
    hub = ScaleHub(fail={"13", "57", "99"})
    first = read_job.run(db, subject, target=hub, sleep=lambda s: None, land=land, build=lambda *a, **k: package)

    assert first == {"pending": 0, "submitted": 0, "landed": 97, "failed": 3}
    assert hub.most_running <= 10
    assert hub.list_calls <= 25  # rounds of ten, not 100 shards x looks
    assert sorted(read_job.status(db, job_id)["failed_shards"]) == ["13", "57", "99"]
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [read_job.KIND])[0] == 1

    db.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [job_id])
    assert read_job.resend_failed(db, job_id) == 3
    sent = len(hub.jobs)
    second = read_job.run(db, subject, target=hub, sleep=lambda s: None, land=land, build=lambda *a, **k: package)

    assert second == {"pending": 0, "submitted": 0, "landed": 100, "failed": 0}
    assert sorted(j["shard"] for j in list(hub.jobs.values())[sent:]) == ["13", "57", "99"]
    assert len(hub.fetched) == len(set(hub.fetched)) == 100  # no shard came home twice
    assert len(landed) == 10_000 and set(landed.values()) == {1}
    assert read_job.status(db, job_id)["landing"]["landed"] == 10_000


class StormyIIIFServer:
    """An archive's Image API: scales each canvas to fit the asked size; answers 429 with Retry-After
    to every third request; counts what is in flight."""

    def __init__(self, canvases):
        self.canvases = canvases
        self.calls = 0
        self.in_flight = 0
        self.most_in_flight = 0
        self.lock = threading.Lock()

    def __call__(self, url, timeout):
        with self.lock:
            self.calls += 1
            self.in_flight += 1
            self.most_in_flight = max(self.most_in_flight, self.in_flight)
            calls = self.calls
        try:
            if calls % 3 == 0:
                return 429, {"retry-after": "5"}, b""
            key = url.split("/full/")[0].rsplit("/", 1)[1]
            longest = int(url.split("/full/!")[1].split(",")[0])
            w, h = self.canvases[key]
            scale = min(1.0, longest / max(w, h))
            data = io.BytesIO()
            Image.new("L", (round(w * scale), round(h * scale)), 255).save(data, format="JPEG")
            return 200, {}, data.getvalue()
        finally:
            with self.lock:
                self.in_flight -= 1


def test_a_thousand_canvases_through_a_429_storm_land_on_their_canvases(tmp_path):
    """WHY (EAP by reference): an archive's server throttles, and its canvases differ in size and
    shape. Every 429 must be waited out as asked (or the archive blocks us); every page must still
    be read; and each line must sit at the same place on its own CANVAS, whatever size the server
    scaled it to, or a thousand pages of results land in the wrong place."""
    canvases = {str(i): (3000 + 7 * i, 4500 - 3 * i) if i % 2 else (6000 - 2 * i, 4000) for i in range(1000)}
    sources = [{"id": f"c{i}", "iiif_service": f"https://iiif.archive.example/img/{i}", "canvas": list(canvases[str(i)])}
               for i in range(1000)]
    package = tmp_path / "pkg"
    (package / "_fichero").mkdir(parents=True)
    (package / "_fichero" / "iiif_fetch.py").write_bytes(
        (runner.Path(runner.__file__).parent.parent / "media" / "iiif_fetch.py").read_bytes())
    (package / "job.json").write_text(json.dumps({"step": {"reader": "vlm", "card": "c"}, "fetch": {"longest": 400},
                                                  "shards": [list(range(1000))], "sources": sources}))
    server = StormyIIIFServer(canvases)
    waited: list[float] = []

    def one_line_a_tenth_in(image):
        w, h = image.size
        box = [[w * 0.1, h * 0.2], [w * 0.6, h * 0.2], [w * 0.6, h * 0.24], [w * 0.1, h * 0.24]]
        return [{"polygon": box, "baseline": [box[3], box[2]], "text": "f."}]

    outcome = runner.run_shard(package, 0, tmp_path / "out", reader=one_line_a_tenth_in, get=server,
                               sleep=waited.append)

    assert all(v["ok"] for v in outcome["sources"].values()) and len(outcome["sources"]) == 1000
    assert outcome["fetch"]["throttled"] >= 400 and min(waited) > 4.5  # Retry-After (5 s) honoured every time, less the moments already gone
    assert server.most_in_flight <= 2
    for source in sources[::37]:
        xml = (tmp_path / "out" / "shard-00000" / f"{source['id']}.xml").read_bytes()
        page = formats.read_page("pagexml", xml)
        line = next(s for s in page.segments if s.kind == "line")
        xs = [p[0] for p in line.polygon]
        cw, ch = source["canvas"]
        # Normalised by the size the reader saw, so on the canvas it is 10% in, whatever was fetched.
        assert min(xs) * cw == pytest.approx(0.1 * cw, abs=cw * 0.004)
        assert max(xs) * cw == pytest.approx(0.6 * cw, abs=cw * 0.004)
