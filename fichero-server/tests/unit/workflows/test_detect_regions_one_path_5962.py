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
