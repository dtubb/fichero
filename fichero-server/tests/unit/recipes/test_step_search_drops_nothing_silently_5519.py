"""A model the finder cannot run is listed with why, never dropped (#5519, `ai.where.never-dropped-silently`):
a GGUF-only repository found for a step is a row that says this build runs MLX builds only."""
from __future__ import annotations

import asyncio

from fichero_server.recipes import discovery


def test_a_gguf_only_repository_is_listed_not_runnable_with_its_reason(monkeypatch):
    job = next(iter(discovery.STEP_SEARCHES))
    task = discovery.STEP_SEARCHES[job][0][0]
    found = [{"id": "someone/model-GGUF", "pipeline_tag": task, "library_name": "gguf", "tags": ["gguf"],
              "downloads": 5, "likes": 1}]

    async def fetch(**kwargs):
        return found

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)

    rows = asyncio.run(discovery.search_hugging_face_for_step(job, frozenset()))

    row = next(r for r in rows if r["repo"] == "someone/model-GGUF")
    assert row["runs_here"] is False
    assert "GGUF" in row["cannot_run_because"]
