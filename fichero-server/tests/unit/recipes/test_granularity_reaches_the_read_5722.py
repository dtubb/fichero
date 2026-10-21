"""The granularity the bake-off measured a reader at is the one Start reads with (#5722): Use This records it on the
step; the run's read node takes it as `read_granularity`; the line reader asks in the requests that granularity names."""
import asyncio

import pytest
from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult
from fichero_server.recipes.start import plan_start
from PIL import Image


def _lines(regions: list[int]) -> OCRGeometryResult:
    """Lines grouped under regions: regions=[2, 3] is two lines under region 0 and three under region 1."""
    boxes = [OCRGeometryBox(text="", bbox=[0, 0, 1, 1], level=OCRGeometryLevel.REGION, provider="kraken",
                            model="blla", source="kraken-blla", metadata={}) for _ in regions]
    n = 0
    for r, count in enumerate(regions):
        for _ in range(count):
            boxes.append(OCRGeometryBox(text="", bbox=[0, 0, 1, 1], level=OCRGeometryLevel.LINE, provider="kraken",
                                        model="blla", source="kraken-blla",
                                        metadata={"polygon_px": [[0, n * 8], [32, n * 8], [32, n * 8 + 8], [0, n * 8 + 8]],
                                                  "parent_box_index": r}))
            n += 1
    return OCRGeometryResult(text="", provider="kraken", model="blla", boxes=boxes, source="kraken-blla")


async def _asked(tmp_path, monkeypatch, regions, granularity):
    page = tmp_path / "page.png"
    Image.new("RGB", (32, 64), "white").save(page)
    monkeypatch.setattr(line_reader, "lines_per_call", lambda config: 3)
    sizes = []

    async def model(images, prompt, config, **_):
        sizes.append(len(images))
        return "[" + ",".join(f'"t{i}"' for i in range(len(images))) + "]"

    monkeypatch.setattr(llm, "vision", model)
    await line_reader.read_lines(str(page), _lines(regions), LLMConfig(provider="omlx", model="m"),
                                 granularity=granularity)
    return sorted(sizes)


@pytest.mark.parametrize("asked, expected", [
    (None, [2, 3]),            # the model's own few-lines-a-call, as before (3 per call over 5 lines)
    ("lines", [1, 1, 1, 1, 1]),
    ("region", [2, 3]),
    ("page", [5]),
])
def test_the_line_reader_asks_in_the_requests_the_granularity_names(tmp_path, monkeypatch, asked, expected):
    assert asyncio.run(_asked(tmp_path, monkeypatch, [2, 3], asked)) == expected


def _plan(granularity):
    from tests.unit.recipes.test_start_plan import _recipe

    step = {"id": "read", "job": "read-a-line", "runs_on": "this-mac",
            "model": {"cloud": "openai", "model": "gpt-5"}}
    if granularity:
        step["granularity"] = granularity
    plan = plan_start(_recipe(step), stays_local=False)
    return next(r for r in plan["runs"] if r["job"] == "read-a-line")


@pytest.mark.parametrize("asked", ["lines", "region", "page"])
def test_start_gives_the_read_node_the_granularity_the_bakeoff_chose(asked):
    assert _plan(asked)["tool_config"]["transcribe"]["read_granularity"] == asked


def test_a_cloud_reader_with_no_chosen_granularity_reads_one_call_a_page():
    """`source.recipe.cloud-reads-lines-per-page`: Kraken finds the lines and the cloud model reads a page's crops in ONE call."""
    assert _plan(None)["tool_config"]["transcribe"]["read_granularity"] == "page"


def test_a_local_reader_with_no_chosen_granularity_sets_none():
    from tests.unit.recipes.test_start_plan import _recipe

    step = {"id": "read", "job": "read-a-line", "runs_on": "this-mac",
            "model": {"hf": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit", "revision": "main"}}
    run = next(r for r in plan_start(_recipe(step), stays_local=False)["runs"] if r["job"] == "read-a-line")
    assert "read_granularity" not in (run.get("tool_config") or {}).get("transcribe", {})
