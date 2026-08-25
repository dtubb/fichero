"""Economy HTR must crop true line boxes, isolate failures, and never fall back silently.

The properties, each with a test:

1. Crops come from the NORMALIZED line bboxes with padding — not fixed-height
   strips — and a degenerate box is skipped, not written as a 0-px file.
2. The ``apple`` backend is a pure re-serialization of Apple Vision's own
   line text (the free floor): joined in box order, no model loaded.
3. A missing capability is a TYPED error naming the missing piece (kraken
   model path / kraken CLI / transformers) — never a silent fallback to a
   different backend, and never an abort of sibling files.
4. The tool emits the canonical ``records`` port ([{doc_id, text}]) only for
   files that produced text AND have a paired document.
5. The shipped economy workflow JSON references only registered tools and
   wires edges between ports that exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.workflows.tools.economy_htr import (
    crop_line_strips,
    economy_htr,
    economy_htr_file,
    kraken_transcribe_page,
)

def _box(x, y, w, h, text="hola", confidence=0.9):
    return SimpleNamespace(bbox=[x, y, w, h], text=text, confidence=confidence)


@pytest.fixture
def page_image(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "folio.png"
    Image.new("RGB", (1000, 800), "white").save(path)
    return path


# ---------------------------------------------------------------- property 1


def test_crop_line_strips_uses_bbox_geometry(page_image: Path, tmp_path: Path):
    boxes = [_box(0.1, 0.10, 0.8, 0.05, "line one"), _box(0.1, 0.30, 0.8, 0.05, "line two")]
    crops = crop_line_strips(page_image, boxes, pad_x=0.0, pad_y=0.0, scale=1.0, out_dir=tmp_path / "crops")

    assert [c["index"] for c in crops] == [0, 1]
    assert [c["text"] for c in crops] == ["line one", "line two"]
    from PIL import Image

    with Image.open(crops[0]["path"]) as strip:
        # 0.8 * 1000 wide, 0.05 * 800 tall, no padding, scale 1
        assert strip.size == (800, 40)


def test_crop_line_strips_pads_and_scales(page_image: Path, tmp_path: Path):
    crops = crop_line_strips(
        page_image, [_box(0.1, 0.5, 0.5, 0.05)], pad_x=0.0, pad_y=0.5, scale=2.0, out_dir=tmp_path / "crops"
    )
    from PIL import Image

    with Image.open(crops[0]["path"]) as strip:
        # height 0.05*800=40, padded 50% top+bottom -> 80, scaled 2x -> 160
        assert strip.size == (1000, 160)


def test_crop_line_strips_skips_degenerate_box(page_image: Path, tmp_path: Path):
    boxes = [_box(0.5, 0.5, 0.0, 0.0), _box(0.1, 0.1, 0.5, 0.05)]
    crops = crop_line_strips(page_image, boxes, out_dir=tmp_path / "crops")
    assert [c["index"] for c in crops] == [1]


# ---------------------------------------------------------------- property 2


def test_apple_backend_is_geometry_text(page_image: Path, monkeypatch):
    import fichero_server.workflows.tools.vision_base as vision_base

    monkeypatch.setattr(
        vision_base,
        "apple_vision_ocr_with_geometry",
        lambda path, language: SimpleNamespace(
            text="ignored", line_boxes=[_box(0.1, 0.1, 0.8, 0.05, "En la çibdad"), _box(0.1, 0.2, 0.8, 0.05, "de Santa Fe")], word_boxes=[]
        ),
    )
    result = economy_htr_file(str(page_image), backend="apple")
    assert result["error"] is None
    assert result["text"] == "En la çibdad\nde Santa Fe"
    assert [l["bbox"] for l in result["lines"]] == [[0.1, 0.1, 0.8, 0.05], [0.1, 0.2, 0.8, 0.05]]


def test_low_confidence_lines_filtered(page_image: Path, monkeypatch):
    import fichero_server.workflows.tools.vision_base as vision_base

    monkeypatch.setattr(
        vision_base,
        "apple_vision_ocr_with_geometry",
        lambda path, language: SimpleNamespace(
            text="", line_boxes=[_box(0.1, 0.1, 0.8, 0.05, "keep", 0.9), _box(0.1, 0.2, 0.8, 0.05, "drop", 0.1)], word_boxes=[]
        ),
    )
    result = economy_htr_file(str(page_image), backend="apple", min_line_confidence=0.5)
    assert result["text"] == "keep"


# ---------------------------------------------------------------- property 3


def test_pdf_input_is_a_typed_error(tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = economy_htr_file(str(pdf))
    assert "prepare_images" in result["error"]


def test_unknown_backend_errors(page_image: Path, monkeypatch):
    import fichero_server.workflows.tools.vision_base as vision_base

    monkeypatch.setattr(
        vision_base,
        "apple_vision_ocr_with_geometry",
        lambda path, language: SimpleNamespace(text="", line_boxes=[_box(0.1, 0.1, 0.8, 0.05)], word_boxes=[]),
    )
    result = economy_htr_file(str(page_image), backend="quantum")
    assert "Unknown backend" in result["error"]


def test_kraken_without_model_path_names_the_gap(page_image: Path):
    result = economy_htr_file(str(page_image), backend="kraken")
    assert "kraken_model_path" in result["error"]


def test_kraken_missing_cli_names_kraken(tmp_path: Path, monkeypatch):
    model = tmp_path / "catmus.mlmodel"
    model.write_bytes(b"x")
    monkeypatch.setattr("fichero_server.workflows.tools.economy_htr.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="kraken"):
        kraken_transcribe_page(str(tmp_path / "img.png"), str(model))


def test_no_lines_is_an_error_not_empty_success(page_image: Path, monkeypatch):
    import fichero_server.workflows.tools.vision_base as vision_base

    monkeypatch.setattr(
        vision_base,
        "apple_vision_ocr_with_geometry",
        lambda path, language: SimpleNamespace(text="", line_boxes=[], word_boxes=[]),
    )
    result = economy_htr_file(str(page_image), backend="apple")
    assert "no text lines" in result["error"]


# ---------------------------------------------------------------- property 4


@pytest.mark.asyncio
async def test_tool_records_and_error_isolation(page_image: Path, monkeypatch):
    import fichero_server.workflows.tools.vision_base as vision_base

    monkeypatch.setattr(
        vision_base,
        "apple_vision_ocr_with_geometry",
        lambda path, language: SimpleNamespace(
            text="", line_boxes=[_box(0.1, 0.1, 0.8, 0.05, "texto")], word_boxes=[]
        ),
    )
    missing = str(page_image.parent / "missing.xyz")
    result = await economy_htr(
        {
            "files": [str(page_image), missing],
            "documents": [{"id": "doc-1", "sequence": 1}, {"id": "doc-2", "sequence": 2}],
            "backend": "apple",
        },
        {},
        None,
    )
    # good file produced a record; bad file recorded its error without aborting
    assert result["records"] == [{"doc_id": "doc-1", "text": "texto"}]
    assert result["texts"][0] == "texto"
    assert result["error"] is not None
    assert result["results"][1]["error"]


@pytest.mark.asyncio
async def test_tool_without_documents_emits_no_records(page_image: Path, monkeypatch):
    import fichero_server.workflows.tools.vision_base as vision_base

    monkeypatch.setattr(
        vision_base,
        "apple_vision_ocr_with_geometry",
        lambda path, language: SimpleNamespace(
            text="", line_boxes=[_box(0.1, 0.1, 0.8, 0.05, "texto")], word_boxes=[]
        ),
    )
    result = await economy_htr({"files": [str(page_image)], "backend": "apple"}, {}, None)
    assert result["records"] == []
    assert result["text"] == "texto"


# ---------------------------------------------------------------- property 5


def test_economy_workflow_json_is_wired_to_real_tools():
    from fichero_server.workflows import tools  # noqa: F401  (registers everything)
    from fichero_server.workflows.registry import list_tools

    path = (
        Path(__file__).resolve().parents[3]
        / "src/fichero_server/resources/default_workflows/transcribe_paleography_economy.json"
    )
    workflow = json.loads(path.read_text())

    node_ids = {node["id"] for node in workflow["nodes"]}
    registered = {tool.name for tool in list_tools()}
    for node in workflow["nodes"]:
        assert node["tool"] in registered, f"unregistered tool: {node['tool']}"
    for edge in workflow["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids

    economy_nodes = [n for n in workflow["nodes"] if n["tool"] == "economy_htr"]
    assert len(economy_nodes) == 1
    # the cheap default: free Apple floor + exactly one LLM cleanup node
    assert economy_nodes[0]["config"]["backend"] == "apple"
    llm_nodes = [n for n in workflow["nodes"] if n["tool"] == "transcribe_review"]
    assert len(llm_nodes) == 1
