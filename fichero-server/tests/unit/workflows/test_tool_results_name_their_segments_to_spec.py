"""source.tool.results-name-their-segments (docs/contributor_manual/specs/source/segments-and-geometry.md, #5026).

Spec: "a tool's result names the segment ids it was read from (a table cell names its lines), so the output is
anchored instead of free text that must be matched back."
First tool: Extract Table, in rows-as-JSON style. The model is asked for `row_segments` (the line ids each row was read
from); what it names is kept only if it is a segment of the page the tool was given, so a result never names a segment
that is not there.
Driven through the real tool on the Vienna Syriac folio; only the model's answer is a stub.
"""
from __future__ import annotations

import asyncio
import json

from fichero_server.llm import LLMConfig
from fichero_server.tool_context import tool_context
from fichero_server.workflows.tools.table_extract import table_extract
from tests.fixture_paths import sample_file
from tests.unit.api.test_reader_directions import SYRIAC, _import


def test_source_tool_results_name_their_segments__a_table_row_names_the_lines_it_was_read_from(db, test_package,
                                                                                               monkeypatch):
    doc_id = _import(db, SYRIAC)
    real = tool_context(db, doc_id).segment_ids[:2]
    assert len(real) == 2
    image = str(sample_file("sample.jpg"))
    prompts = []

    async def model(images, prompt, config, **kwargs):
        prompts.append(prompt)
        return json.dumps({"headers": ["a", "b"], "rows": [["1", "2"], ["3", "4"]], "row_count": 2, "column_count": 2,
                           "row_segments": [[real[0], "not-a-segment"], [real[1]]]})

    monkeypatch.setattr("fichero_server.llm.vision", model)
    result = asyncio.run(table_extract(
        {"files": [image], "documents": [{"id": doc_id, "name": "folio", "path": image}], "save_to_db": False,
         "output_style": "json_rows"},
        {"library_path": str(test_package)}, LLMConfig(provider="mock", model="mock")))
    assert not result.get("error"), result
    assert "row_segments" in prompts[0], "the model is asked to name the lines each row came from"
    answer = json.loads(result["text"])
    assert answer["row_segments"] == [[real[0]], [real[1]]], "an id that is not a segment of the page is dropped"
