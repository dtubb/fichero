"""Episode ledger v1 (2026-08-12): append-only JSONL provenance per model
call, with correction/invalidation records referencing earlier episodes.
Design: agent-work/reports/episode-ledger-design-2026-08-12.md
"""

import json
from pathlib import Path

from fichero_server.observability import episodes


def _read_ledger(library: Path) -> list[dict]:
    files = sorted((library / "episodes").glob("*.jsonl"))
    lines = []
    for f in files:
        lines += [json.loads(l) for l in f.read_text().splitlines() if l]
    return lines


class TestRecording:
    def test_model_call_appends_one_immutable_line(self, tmp_path):
        token = episodes.set_library(str(tmp_path))
        run_token = episodes.set_run_context(
            {"thread_id": "t1", "workflow_id": "transcribe_pages", "node": "transcribe"}
        )
        try:
            eid = episodes.record(
                subject={"document_id": "doc-1", "page_id": "page-1"},
                model={"provider": "apple", "model": "apple-vision", "use_case": "transcription"},
                exchange={"prompt": "Transcribe this page.", "output": "borojo ledger", "thinking": "faded ink…"},
                timing={"ms": 812},
            )
        finally:
            episodes.set_run_context(None)
            episodes.set_library(None)
            _ = (token, run_token)

        assert eid and eid.startswith("ep_")
        rows = _read_ledger(tmp_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["episode_id"] == eid
        assert row["kind"] == "model_call"
        assert row["run"]["node"] == "transcribe"
        assert row["exchange"]["thinking"] == "faded ink…"
        assert row["model"]["use_case"] == "transcription"

    def test_no_library_in_context_is_a_quiet_noop(self, tmp_path):
        episodes.set_library(None)
        assert episodes.record(exchange={"prompt": "x"}) is None
        assert not (tmp_path / "episodes").exists()

    def test_write_failure_is_loud_but_returns_none(self, tmp_path, caplog):
        # A FILE where the episodes directory should be → OSError inside.
        (tmp_path / "episodes").write_text("not a directory")
        episodes.set_library(str(tmp_path))
        try:
            assert episodes.record(exchange={"prompt": "x"}) is None
        finally:
            episodes.set_library(None)
        assert any("episode ledger write failed" in r.message for r in caplog.records)


class TestCorrectionsAndInvalidations:
    def test_correction_references_the_episode_it_corrects(self, tmp_path):
        episodes.set_library(str(tmp_path))
        try:
            original = episodes.record(
                subject={"document_id": "doc-1"},
                exchange={"prompt": "p", "output": "modle text"},
            )
            correction = episodes.record_correction(
                corrects_episode_id=original,
                artifact_id="art-1",
                corrected_text="model text",
                actor="daniel",
            )
            invalidation = episodes.record_invalidation(
                stale_artifact_ids=["art-svo-1"], caused_by_episode_id=correction
            )
        finally:
            episodes.set_library(None)

        rows = {r["kind"]: r for r in _read_ledger(tmp_path)}
        assert rows["correction"]["corrects_episode_id"] == original
        assert rows["correction"]["exchange"]["corrected_text"] == "model text"
        assert rows["correction"]["actor"] == "daniel"
        assert rows["invalidation"]["subject"]["stale_artifact_ids"] == ["art-svo-1"]
        assert rows["invalidation"]["caused_by_episode_id"] == correction
