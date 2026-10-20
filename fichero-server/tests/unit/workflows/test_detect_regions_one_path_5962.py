"""`prep.regions.one-find-regions` (#5962): the workflow node's Kraken provider runs the recipe's own Find Regions loop."""
import pytest

from fichero_server.llm import LLMConfig


@pytest.mark.asyncio
async def test_the_node_with_provider_kraken_calls_the_one_find_regions(tmp_path, monkeypatch):
    from fichero_server.db.manager import db_manager
    from fichero_server.models import Document, DocType, FileType
    from fichero_server.recipes import regions
    from fichero_server.workflows.tools.detect_regions import detect_regions
    from PIL import Image

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    library = tmp_path / "L.fichero"
    library.mkdir()
    png = tmp_path / "p.png"
    Image.new("RGB", (8, 8)).save(png)
    db = db_manager.get_database(str(library))
    doc = Document(name="p.png", doc_type=DocType.file, file_type=FileType.image, path=str(png))
    db.save(doc)

    calls: list[dict] = []

    def one_find_regions(db_, documents, run_id, model, **kwargs):
        calls.append({"documents": documents, "model": model, **kwargs})
        return {"pages": len(documents), "regions": 0, "no_image": 0}

    monkeypatch.setattr(regions, "find_regions", one_find_regions)
    try:
        result = await detect_regions(
            inputs={"files": [str(png)], "documents": [{"id": doc.id}], "provider": "kraken"},
            state={"library_path": str(library), "task_id": None},
            llm_config=LLMConfig(provider="", model=""),
        )
    finally:
        db_manager.close_all()
    assert not result.get("error"), result.get("error")
    assert len(calls) == 1 and calls[0]["documents"] == [doc.id] and calls[0]["provider"] == "kraken"


@pytest.mark.asyncio
async def test_a_stop_during_the_node_ends_the_run_cancelled_and_the_loop_is_given_it(tmp_path, monkeypatch):
    """## 740: the node hands the one loop a `stop` that follows the run's cancellation, and a stop mid-run settles it
    cancelled (WorkflowCancelled), never done."""
    from fichero_server.db.manager import db_manager
    from fichero_server.execution.cancellation import WorkflowCancelled, clear_cancellation, request_cancellation
    from fichero_server.models import Document, DocType, FileType
    from fichero_server.recipes import regions
    from fichero_server.workflows.tools.detect_regions import detect_regions

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    library = tmp_path / "L.fichero"
    library.mkdir()
    db = db_manager.get_database(str(library))
    doc = Document(name="p.png", doc_type=DocType.file, file_type=FileType.image, path=str(tmp_path / "p.png"))
    db.save(doc)
    seen: dict = {}

    def loop(db_, documents, run_id, model, *, stop=None, say=None, **kwargs):
        seen["stop_before"] = stop()
        request_cancellation("run-740")  # the person presses Stop while a page is being read
        seen["stop_after"] = stop()
        seen["say"] = say
        return {"pages": 0, "regions": 0, "no_image": 0}

    monkeypatch.setattr(regions, "find_regions", loop)
    try:
        with pytest.raises(WorkflowCancelled):
            await detect_regions(
                inputs={"files": ["p.png"], "documents": [{"id": doc.id}], "provider": "kraken"},
                state={"library_path": str(library), "task_id": "run-740"},
                llm_config=LLMConfig(provider="", model=""),
            )
    finally:
        clear_cancellation("run-740")
        db_manager.close_all()
    assert seen["stop_before"] is False and seen["stop_after"] is True and callable(seen["say"])
