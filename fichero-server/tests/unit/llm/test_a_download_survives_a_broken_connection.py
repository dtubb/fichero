"""A model download survives a broken connection, and says what it is in words (#5660 items 12 and 10).

WHY: on the maintainer's Mac Zenodo dropped the Kraken reader part-way (IncompleteRead, 8.8 of 63 MB), the
download stopped for good, and Set Up showed the Python exception. The line above it said "Kraken", which ships
inside the app, and elsewhere the engine said ids like kraken-zenodo-21788410. Against a real HTTP server on
this Mac that drops the connection mid-file:

- a broken connection is tried again after a pause and the file CONTINUED (a Range request), or begun again
  where the server cannot continue; only the stated size is kept;
- after the last try, one sentence naming the model, never the exception; the job comes back by itself;
- Stop on a running download's row stops it at its next chunk, keeping what it had; Retry continues it;
- the Kraken reader and the MLX models (Hugging Face) are both covered;
- every progress line names the model as a person sees it.
"""

from __future__ import annotations

from tests._this_thread import sleep_here
import http.server
import json
import threading
import time
from pathlib import Path

import pytest
from fichero_server.execution import jobs
from fichero_server.llm import local_models, model_downloads
from fichero_server.llm.model_downloads import (
    DownloadInterrupted,
    DownloadStopped,
    fetch_file,
)

PAYLOAD = bytes(range(256)) * 8192  # 2 MB
READER = "kraken-zenodo-21788410"  # PP-OCRv6 (medium), the reader Zenodo dropped


class _Server:
    """Serves PAYLOAD at any path. `drops` requests break after `cut` bytes (the headers promise it all);
    `ranges` False ignores Range requests (answers 200 with everything); `delay` slows each 64 KB."""

    def __init__(self, *, drops: int = 0, cut: int = 700_000, ranges: bool = True, delay: float = 0.0) -> None:
        self.drops, self.cut, self.ranges, self.delay = drops, cut, ranges, delay
        self.requests: list[str | None] = []
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_GET(self) -> None:
                asked = self.headers.get("Range")
                server.requests.append(asked)
                start = int(asked.split("=")[1].split("-")[0]) if asked and server.ranges else 0
                body = PAYLOAD[start:]
                self.send_response(206 if start else 200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                stop = server.cut if server.drops > 0 else len(body)
                if server.drops > 0:
                    server.drops -= 1
                for at in range(0, min(stop, len(body)), 65536):
                    self.wfile.write(body[at:min(at + 65536, stop)])
                    if server.delay:
                        time.sleep(server.delay)
                self.wfile.flush()
                self.close_connection = True

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, name: str = "medium.safetensors") -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/{name}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def serve():
    made: list[_Server] = []

    def start(**kwargs) -> _Server:
        made.append(_Server(**kwargs))
        return made[-1]

    yield start
    for server in made:
        server.close()


@pytest.fixture
def quick(monkeypatch):
    """Pauses between tries recorded, not waited; small reads so a stop is heard quickly."""
    paused: list[float] = []
    monkeypatch.setattr(model_downloads.time, "sleep", sleep_here(paused.append))
    monkeypatch.setattr(model_downloads, "CHUNK_BYTES", 65536)
    return paused


# --- the file fetch ---------------------------------------------------------------------------------


def test_a_dropped_connection_is_tried_again_and_the_file_continued(serve, quick, tmp_path):
    server = serve(drops=1)
    dest = fetch_file(server.url(), tmp_path / "w.bin", name="PP-OCRv6", size=len(PAYLOAD))
    assert dest.read_bytes() == PAYLOAD
    assert server.requests == [None, "bytes=700000-"]  # the second asked only for the rest
    assert sum(quick) == model_downloads.BACKOFF_SECONDS[0]  # after a pause
    assert not (tmp_path / "w.bin.part").exists()


def test_a_server_that_cannot_continue_is_read_again_from_the_start(serve, quick, tmp_path):
    server = serve(drops=1, ranges=False)
    dest = fetch_file(server.url(), tmp_path / "w.bin", name="PP-OCRv6", size=len(PAYLOAD))
    assert dest.read_bytes() == PAYLOAD and len(server.requests) == 2


def test_after_the_last_try_one_sentence_names_the_model_and_keeps_what_it_had(serve, quick, tmp_path):
    server = serve(drops=99, cut=100_000)
    with pytest.raises(DownloadInterrupted) as raised:
        fetch_file(server.url(), tmp_path / "w.bin", name="PP-OCRv6 (medium)", size=len(PAYLOAD))
    assert str(raised.value) == "The download of PP-OCRv6 (medium) stopped part-way; it will try again."
    assert len(server.requests) == len(model_downloads.BACKOFF_SECONDS) + 1
    assert not (tmp_path / "w.bin").exists()  # never a short file under the model's name
    assert (tmp_path / "w.bin.part").stat().st_size == 100_000 * len(server.requests)  # each try continued it


def test_a_stopped_download_keeps_what_it_had_and_continues_when_started_again(serve, quick, tmp_path):
    server = serve()
    heard = []
    with pytest.raises(DownloadStopped):
        fetch_file(server.url(), tmp_path / "w.bin", name="PP-OCRv6", size=len(PAYLOAD),
                   should_stop=lambda: len(heard) > 3, on_bytes=lambda have, total: heard.append(have))
    kept = (tmp_path / "w.bin.part").stat().st_size
    assert 0 < kept < len(PAYLOAD)
    fetch_file(server.url(), tmp_path / "w.bin", name="PP-OCRv6", size=len(PAYLOAD))
    assert (tmp_path / "w.bin").read_bytes() == PAYLOAD and server.requests[-1] == f"bytes={kept}-"


def test_a_refused_request_is_not_tried_again(serve, quick, tmp_path):
    """A missing file will not appear by waiting: said at once, not after a minute of tries."""
    import urllib.error

    server = serve()
    server.httpd.RequestHandlerClass.do_GET = lambda self: (self.send_error(404), None)[1]
    with pytest.raises(urllib.error.HTTPError):
        fetch_file(server.url(), tmp_path / "w.bin", name="PP-OCRv6", size=len(PAYLOAD))
    assert quick == []


# --- the Kraken reader, through the download job ----------------------------------------------------


@pytest.fixture
def reader_from(monkeypatch, tmp_path):
    """The reader's record points at the fake server; Kraken itself is here (it ships inside the app)."""
    from fichero_server.llm import kraken_runtime

    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    monkeypatch.setattr(kraken_runtime, "require_installed", lambda: None)
    monkeypatch.setattr(local_models, "say_installed", lambda runtime, model: None)
    monkeypatch.setattr(local_models, "PROGRESS_EVERY_SECONDS", 0.0)
    import types

    import htrmopo

    monkeypatch.setattr(htrmopo, "get_description", lambda doi: types.SimpleNamespace(
        model_type=["recognition"], software_name="kraken"), raising=False)

    def point(server: _Server) -> None:
        monkeypatch.setattr(kraken_runtime, "record_files",
                            lambda doi: [{"url": server.url(), "size": len(PAYLOAD)}])
    return point


def _as_job(db, subject: str):
    job_id = jobs.enqueue(db, local_models.DOWNLOAD_KIND, subject, started_by="owner")
    jobs._current.job_id = job_id
    return job_id


def test_a_kraken_reader_whose_connection_drops_lands_whole_and_says_its_name(db, serve, quick, reader_from,
                                                                               jobs_run_by_the_test):
    from fichero_server.llm import kraken_runtime

    server = serve(drops=1)
    reader_from(server)
    local_models.register_job_kinds()
    job_id = _as_job(db, f"kraken:{READER}")
    try:
        local_models._run_download(f"kraken:{READER}", db)
    finally:
        jobs._current.job_id = None
    assert kraken_runtime.is_recognition_model_installed(READER)
    assert Path(kraken_runtime.recognition_model_path(READER)).read_bytes() == PAYLOAD
    reason = jobs.read_job(db, job_id)["reason"]
    assert reason.startswith("Downloading PP-OCRv6 (medium)") and "of 2.1 MB" in reason, reason
    assert "kraken-zenodo" not in reason and "Kraken reader" not in reason


def test_a_download_that_breaks_on_every_try_says_so_and_comes_back_by_itself(db, serve, quick, reader_from,
                                                                              jobs_run_by_the_test, monkeypatch):
    reader_from(serve(drops=999, cut=100_000))
    monkeypatch.setattr(model_downloads, "BACKOFF_SECONDS", (1.0,))
    local_models.register_job_kinds()
    job_id = _as_job(db, f"kraken:{READER}")
    try:
        for _round in range(local_models.COME_BACK_ROUNDS):
            with pytest.raises(jobs.JobDeferred) as deferred:
                local_models._run_download(f"kraken:{READER}", db)
            assert str(deferred.value) == "The download of PP-OCRv6 (medium) stopped part-way; it will try again."
        row = jobs.read_job(db, job_id)
        assert row["reason"] == str(deferred.value)  # the sentence, never "IncompleteRead"
        assert json.loads(row["detail"])["interrupted"] == local_models.COME_BACK_ROUNDS
        assert db.execute_fetchone("SELECT run_after FROM jobs WHERE id = ?", [job_id])[0] is not None
        with pytest.raises(RuntimeError, match=r"^The download of PP-OCRv6 \(medium\) could not finish; try it again"):
            local_models._run_download(f"kraken:{READER}", db)
    finally:
        jobs._current.job_id = None


def _wait(predicate, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_stop_on_a_running_download_stops_it_and_retry_continues_it(db, serve, reader_from, monkeypatch):
    """#5660 item 11, through the scheduler as Activity drives it: Stop reaches a running download (it used
    to finish regardless), the row ends `cancelled` keeping what it had, and Retry continues the file."""
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(model_downloads, "CHUNK_BYTES", 65536)
    server = serve(delay=0.05)
    reader_from(server)
    local_models.register_job_kinds()
    job_id = jobs.enqueue(db, local_models.DOWNLOAD_KIND, f"kraken:{READER}", started_by="owner", watched=True)
    _wait(lambda: (jobs.read_job(db, job_id)["reason"] or "").startswith("Downloading PP-OCRv6 (medium):"))
    assert jobs.cancel_job(db, job_id) == "running"
    _wait(lambda: jobs.read_job(db, job_id)["state"] == "cancelled")
    part = next((Path(kraken_runtime.recognition_data_home()) / READER).glob("*.part"))
    kept = part.stat().st_size
    assert 0 < kept < len(PAYLOAD) and not kraken_runtime.is_recognition_model_installed(READER)

    server.delay = 0.0
    assert jobs.retry_job(db, job_id) == "waiting"
    _wait(lambda: jobs.read_job(db, job_id)["state"] == "done")
    assert kraken_runtime.is_recognition_model_installed(READER)
    assert server.requests[-1] == f"bytes={kept}-"  # continued, not begun again


# --- MLX models from Hugging Face --------------------------------------------------------------------


def test_an_mlx_download_whose_connection_drops_is_tried_again(tmp_path, quick, monkeypatch):
    """Hugging Face's fetch continues its `.incomplete` files by itself; the store tries it again after a
    broken connection, and only after the last try says one sentence with the model's name."""
    import asyncio

    import huggingface_hub
    import requests
    from fichero_server.llm.mlx_model_store import (
        ManagedModelDownloadJob,
        MLXModelStore,
    )

    store = MLXModelStore(root=tmp_path / "mlx")
    spec = store.spec("Qwen2.5-VL-3B")
    tries = []

    def flaky(**kwargs):
        tries.append(1)
        if len(tries) < 3:
            raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead(8800000 bytes read)")
        return str(tmp_path)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", flaky)
    job = ManagedModelDownloadJob(job_id="mlx-1", model_id=spec.model_id, state="running", current=0, total=1,
                                  message="")
    asyncio.run(store._run_download_in_process(job, spec))
    assert job.state == "completed" and len(tries) == 3

    def broken(**kwargs):
        raise requests.exceptions.ConnectionError("Connection reset by peer")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", broken)
    job = ManagedModelDownloadJob(job_id="mlx-2", model_id=spec.model_id, state="running", current=0, total=1,
                                  message="")
    asyncio.run(store._run_download_in_process(job, spec))
    assert job.state == "failed"
    assert job.error == f"The download of {spec.display_name} stopped part-way; it will try again."


# --- names a person sees ----------------------------------------------------------------------------


def test_every_model_is_named_as_a_person_sees_it():
    """#5660 item 10: the card's name, never an id and never "Kraken" (which ships inside the app)."""
    named = {
        ("kraken", READER): local_models.model_display_name("kraken", READER),
        ("kraken", "kraken-mccatmus"): local_models.model_display_name("kraken", "kraken-mccatmus"),
        ("kraken", "kraken-zenodo-1"): local_models.model_display_name("kraken", "kraken-zenodo-1"),
        ("yolo", "yolo-doclaynet-11n"): local_models.model_display_name("yolo", "yolo-doclaynet-11n"),
    }
    assert named[("kraken", READER)].startswith("PP-OCRv6 (medium)")
    assert named[("kraken", "kraken-mccatmus")] and "kraken-" not in named[("kraken", "kraken-mccatmus")]
    assert named[("kraken", "kraken-zenodo-1")] == "the reader from Kraken's repository (record 1)"
    assert named[("yolo", "yolo-doclaynet-11n")] == "the layout model DocLayNet (printed and born-digital pages)"
    for (runtime, model), name in named.items():
        assert model not in name and name != "Kraken"
