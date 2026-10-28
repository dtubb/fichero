"""While a recipe run reads, its status names the step reading and its pages, never folders, and never says it waits
for a lane only its own pages hold (#5685), tested to the spec: `activity.run.says-what-it-reads`
(docs/contributor_manual/specs/ui/activity-and-automatic-work.md).

WHY: the operator's live run (integration 88b81f01e): while Kraken had read 56 of 87 pages, the run said "Running
step find-lines, read-a-line: 0 of 1 folder done" and "Waiting for the model lane: Transcribe (Kraken) is reading",
waiting for itself. Driven through MCP on the real scheduler, the reader stubbed at the recipe tests' boundary and
held on the second page so the run is caught mid-read.
"""

from __future__ import annotations

import re
import threading
import time

from fichero_server.models import DocType, Document, FileType
from tests.unit.mcp.test_onboarding_journey_through_mcp import _call, agent  # noqa: F401  (fixture)
from tests.unit.mcp.test_reading_journey_through_mcp import UnsureCards, assert_no_download  # noqa: F401
from tests.unit.mcp.test_reading_journey_through_mcp import engine as _engine  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import _png

#: The pages read in parallel, so with the second held the run is caught at 1 or 2 of 3 done: the count is not the claim,
#: the step and the pages are.
SAID = re.compile(r"Reading each line with Kraken: [12] of 3 pages")

RECIPE = {"fichero_recipe": 1, "id": "t/reads", "version": "0.1.0", "title": "Reads", "steps": [
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
]}


def test_a_reading_run_says_which_step_reads_and_how_many_pages(agent, client, db, tmp_path, test_package,  # noqa: F811
                                                                 _engine, monkeypatch):
    from fichero_server.llm import kraken_runtime
    from fichero_server.workflows.default_workflows import seed_default_workflows

    held = threading.Event()
    stub = _engine.recognize

    def recognize(image_path, model_path, **kw):
        if str(image_path).endswith("p1.png"):
            held.wait(60)  # the second page: the run is caught here, mid-read
        return stub(image_path, model_path, **kw)

    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", recognize)
    # One page at a time, so holding the second leaves exactly one read: the fan-out follows the Mac's free memory (#5758).
    monkeypatch.setattr(kraken_runtime, "page_fan_out", lambda cap: 1)
    seed_default_workflows(db)
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    for i in range(3):
        db.save(Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                         path=str(_png(tmp_path / f"p{i}.png"))))
    _call(agent, "fichero_use_library", {"path": str(test_package)})
    _call(agent, "fichero_recipes_save_project_setup",
          {"answers": {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"]}, "recipe": RECIPE})
    run_id = _call(agent, "fichero_recipes_start_project", {})["started"]["job_id"]

    try:
        deadline, status, seen = time.monotonic() + 90, {}, []
        while time.monotonic() < deadline:
            status = _call(agent, "fichero_recipes_run_status", {"job_id": run_id})
            if (status.get("reason") or "") not in seen:
                seen.append(status.get("reason") or "")
            if SAID.match(status.get("reason") or ""):
                break
            time.sleep(0.3)
        said = status.get("reason") or ""
        assert SAID.match(said), (seen, status)
        assert "folder" not in said, said
        assert "model lane" not in (status.get("waiting_for") or ""), status["waiting_for"]
    finally:
        held.set()

    while time.monotonic() < deadline:
        status = _call(agent, "fichero_recipes_run_status", {"job_id": run_id})
        if status["state"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.3)
    assert status["state"] == "done", status
    assert_no_download(db)
