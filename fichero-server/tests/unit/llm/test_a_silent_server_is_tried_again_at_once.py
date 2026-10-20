"""A server that takes the request and sends nothing is tried again after READ_TIMEOUT_SECONDS, not a minute (#5865).

WHY: the reader download stalled ~3 min: the server dropped the first connection after 0 bytes, the read waited
60 s, and the retry then took 2 s. Also the Hugging Face error line was empty ("HuggingFace API error:") for a
timeout; it now says it in words.
"""

from __future__ import annotations

import http.server
import threading
import time

from fichero_server.api.routes.ai.models import hf_error_words
from fichero_server.llm import model_downloads

BODY = b"x" * 1000


def test_a_silent_first_connection_is_retried_within_the_first_byte_timeout(tmp_path, monkeypatch):
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(1)
            if len(seen) == 1:
                time.sleep(3)  # takes the request, says nothing
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(model_downloads, "READ_TIMEOUT_SECONDS", 0.5)
    started = time.monotonic()
    try:
        out = model_downloads.fetch_file(f"http://127.0.0.1:{server.server_port}/m.bin", tmp_path / "m.bin",
                                         name="the reader", size=len(BODY), backoff=(0.0,))
    finally:
        server.shutdown()
    assert out.read_bytes() == BODY and len(seen) == 2
    assert time.monotonic() - started < 3


def test_a_hugging_face_timeout_is_said_in_words():
    class ReadTimeout(Exception):
        pass

    assert hf_error_words(ReadTimeout()) == "Could not reach Hugging Face: it did not answer in time."
    assert "Hugging Face" in hf_error_words(RuntimeError("boom")) and "boom" in hf_error_words(RuntimeError("boom"))


def test_the_row_says_how_long_a_download_has_been_going():
    assert model_downloads.progress_words("the reader", 0, 63_000_000, 23.4) == "Downloading the reader, 23 s in"
    assert model_downloads.progress_words("the reader", 8_800_000, 63_000_000, 12) == (
        "Downloading the reader: 8.8 MB of 63.0 MB, 12 s in")
    assert model_downloads.progress_words("the reader", 0, None) == "Downloading the reader"
