"""Every download-model job says its bytes (#6592): `activity.download.says-bytes-and-time-left` (spec
docs/contributor_manual/specs/ui/activity-pane.md, "Ruled 2026-11-14").

Only the Kraken download used to pass `on_bytes`; embeddings, Whisper, spaCy and YOLO said "Downloading X" once and
then nothing for minutes. A watcher thread now measures the model's folder growing against the catalogue's size and
says it, until the fetch ends. Nothing here touches the network: the fetch is a stub writing chunks into the folder.
"""

from __future__ import annotations

import threading
import time

from fichero_server.llm import local_models


def test_a_stub_download_writing_ten_chunks_reports_rising_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(local_models, "MODELS_BASE", tmp_path)
    monkeypatch.setattr(local_models, "PROGRESS_EVERY_SECONDS", 0.01)
    monkeypatch.setattr(local_models, "say_installed", lambda runtime, model: None)
    said: list[tuple[str, dict]] = []
    monkeypatch.setattr(local_models, "_say_progress", lambda db, words, **numbers: said.append((words, numbers)))
    model = "BAAI/bge-m3"

    def fetch(self, model_type, model_id):
        folder = self.embeddings_path / "BAAI--bge-m3"
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(10):
            (folder / f"chunk{i}").write_bytes(b"x" * 100_000)
            time.sleep(0.04)

    monkeypatch.setattr(local_models.LocalModelManager, "download_model", fetch)
    before = threading.active_count()
    local_models._run_download(f"embeddings:{model}")

    have = [n["bytes_done"] for _, n in said if n.get("bytes_done")]
    assert len(have) >= 5 and have == sorted(set(have)), have  # at least five reports, each further than the last
    assert all(n["bytes_total"] == local_models.EMBEDDINGS_MODELS[model]["disk_mb"] * 1_000_000
               for _, n in said if n.get("bytes_done"))
    assert any(words.startswith("Downloading") and " of " in words for words, _ in said)
    assert threading.active_count() <= before  # the watcher stopped with the fetch
