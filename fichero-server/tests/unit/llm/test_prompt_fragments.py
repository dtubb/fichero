"""Reader prompt fragments and the 2x2 measure (`image.enhance.reader-prompt-fragment`,
`image.enhance.prompt-and-cleanup-measured-2x2`, #6199). The model call is stubbed at `vision`; the prompt, the plan and
the run's result are the engine's own."""
from __future__ import annotations

import asyncio

import pytest
from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader, prompt_fragments
from fichero_server.models.knowledge import LibrarySetting
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult
from PIL import Image
from tests.unit.workflows.test_one_line_pass_read_many import page  # noqa: F401  (the shared fixture)


def test_the_three_fragments_exist_at_version_one_with_a_wording_per_reader():
    assert set(prompt_fragments.FRAGMENTS) == {"ignore-show-through@1", "ignore-furniture@1", "read-over-stamps@1"}
    assert "do not read it" in prompt_fragments.FRAGMENTS["ignore-show-through@1"][prompt_fragments.LINE]
    assert "colour card" in prompt_fragments.FRAGMENTS["ignore-furniture@1"][prompt_fragments.PAGE]
    assert prompt_fragments.FRAGMENTS["ignore-furniture@1"][prompt_fragments.LINE] is None


def test_resolve_joins_the_wordings_records_ids_and_versions_and_skips_what_the_project_switched_off():
    names = ["ignore-show-through@1", "ignore-furniture@1", "read-over-stamps@1"]
    text, records = prompt_fragments.resolve(names, prompt_fragments.LINE)
    assert text == (prompt_fragments.FRAGMENTS["ignore-show-through@1"]["line"] + " "
                    + prompt_fragments.FRAGMENTS["read-over-stamps@1"]["line"])
    assert records == [{"id": "ignore-show-through", "version": 1, "reader": "line"},
                       {"id": "ignore-furniture", "version": 1, "reader": "line"},
                       {"id": "read-over-stamps", "version": 1, "reader": "line"}]
    text, records = prompt_fragments.resolve(names, prompt_fragments.PAGE, off={"ignore-show-through"})
    assert "mirrored" not in text and "ruler" in text
    assert [r["id"] for r in records] == ["ignore-furniture", "read-over-stamps"]
    assert prompt_fragments.resolve(None, prompt_fragments.LINE) == ("", [])


def test_an_unknown_fragment_or_version_is_refused():
    with pytest.raises(ValueError):
        prompt_fragments.resolve(["ignore-show-through@2"], prompt_fragments.LINE)


def test_a_project_switches_a_fragment_off_through_its_setting(db):
    assert prompt_fragments.project_off(db) == frozenset()
    db.save(LibrarySetting(id=prompt_fragments.OFF_SETTING, value="ignore-show-through, read-over-stamps"))
    assert prompt_fragments.project_off(db) == {"ignore-show-through", "read-over-stamps"}


def _lines(n: int) -> OCRGeometryResult:
    boxes = [OCRGeometryBox(text="", bbox=[0, i / n, 1, 1 / n], level=OCRGeometryLevel.LINE, provider="kraken",
                            model="blla", source="kraken-blla",
                            metadata={"polygon_px": [[0, i * 8], [32, i * 8], [32, i * 8 + 8], [0, i * 8 + 8]]})
             for i in range(n)]
    return OCRGeometryResult(text="", provider="kraken", model="blla", boxes=boxes, source="kraken-blla")


def test_the_line_reader_sends_the_fragment_text_after_its_own_prompt(tmp_path, monkeypatch):
    img = tmp_path / "page.png"
    Image.new("RGB", (32, 16), "white").save(img)
    seen = []

    async def model(images, prompt, config, **_):
        seen.append(prompt)
        return '["a"]'

    monkeypatch.setattr(llm, "vision", model)
    text, _ = prompt_fragments.resolve(["ignore-show-through@1"], prompt_fragments.LINE)
    asyncio.run(line_reader.read_lines(str(img), _lines(1), LLMConfig(provider="omlx", model="m"), fragments=text))
    asyncio.run(line_reader.read_lines(str(img), _lines(1), LLMConfig(provider="omlx", model="m")))
    assert seen[0].startswith(line_reader.prompt_for(1)) and seen[0].endswith(text)
    assert seen[1] == line_reader.prompt_for(1), "no fragment named: the prompt is unchanged"


@pytest.mark.asyncio
async def test_the_transcribe_tool_sends_the_fragment_and_its_result_records_id_and_version(page, monkeypatch):  # noqa: F811
    """Through the real tool: Kraken finds the lines, the stubbed teacher reads them; the prompt carries the line wording and
    the result names the fragment."""
    from tests.unit.workflows.test_one_line_pass_read_many import _transcribe

    prompts: list[str] = []

    async def teacher(images, prompt, config, **_):
        prompts.append(prompt)
        return '["primera", "segunda", "tercera"]'

    monkeypatch.setattr(llm, "vision", teacher)
    wording = prompt_fragments.FRAGMENTS["ignore-show-through@1"]["line"]
    result = await _transcribe(page, lines_read_by="model", read_granularity="page",
                               prompt_fragments=["ignore-show-through@1"])
    assert prompts and all(p.endswith(wording) for p in prompts)
    assert result["prompt_fragments"] == [{"id": "ignore-show-through", "version": 1, "reader": "line"}]


@pytest.mark.asyncio
async def test_a_fragment_the_project_switched_off_is_not_sent_or_recorded(page, monkeypatch):  # noqa: F811
    from tests.unit.workflows.test_one_line_pass_read_many import _transcribe

    prompts: list[str] = []

    async def teacher(images, prompt, config, **_):
        prompts.append(prompt)
        return '["primera", "segunda", "tercera"]'

    monkeypatch.setattr(llm, "vision", teacher)
    page["db"].save(LibrarySetting(id=prompt_fragments.OFF_SETTING, value="ignore-show-through"))
    result = await _transcribe(page, lines_read_by="model", read_granularity="page",
                               prompt_fragments=["ignore-show-through@1"])
    assert prompts and not any(prompt_fragments.FRAGMENTS["ignore-show-through@1"]["line"] in p for p in prompts)
    assert result["prompt_fragments"] == []


def test_the_2x2_reports_show_through_words_per_page_for_the_four_cells():
    pages = [{"id": f"p{i}", "show_through": ["ghost", "mirror"]} for i in range(3)]

    def read(_page, fragment, cleanup):
        n = 4 - (2 if fragment else 0) - (1 if cleanup else 0)  # the stub: each switch removes some show-through words
        return "plain words " + " ".join(["ghost"] * n)

    out = prompt_fragments.measure_2x2(pages, read)

    assert set(out["cells"]) == {"fragment=off,cleanup=off", "fragment=on,cleanup=off", "fragment=off,cleanup=on",
                                 "fragment=on,cleanup=on"}
    assert out["cells"]["fragment=off,cleanup=off"]["per_page"] == {"p0": 4, "p1": 4, "p2": 4}
    assert out["cells"]["fragment=on,cleanup=on"]["per_page"] == {"p0": 1, "p1": 1, "p2": 1}
    assert out["cells"]["fragment=on,cleanup=off"]["total"] == 6
    assert set(out["cells"]["fragment=off,cleanup=on"]["seconds_per_page"]) == {"p0", "p1", "p2"}
