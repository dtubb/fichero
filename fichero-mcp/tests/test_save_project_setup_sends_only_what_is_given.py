"""`source.project.setup-saves-what-is-sent`, the MCP side (review 456 item 3): the generated tool drops an argument left None,
so a part it is not given is not in the request and the server keeps it; it cannot remove a part."""
from __future__ import annotations

from fichero_mcp import openapi_runtime as runtime
from fichero_mcp import openapi_tools_generated as generated


def _sent(monkeypatch, **arguments):
    seen = {}
    monkeypatch.setattr(runtime, "call", lambda method, path, **kw: seen.update(method=method, path=path, json=kw.get("json")))
    generated.fichero_recipes_save_project_setup(**arguments)
    return seen


def test_a_part_left_out_is_not_sent(monkeypatch):
    recipe = {"steps": [{"id": "lines"}]}
    seen = _sent(monkeypatch, recipe=recipe)
    assert (seen["method"], seen["path"]) == ("PUT", "/api/recipes/project")
    assert seen["json"] == {"recipe": recipe}  # no "answers" key: the saved answers are kept


def test_both_parts_left_out_sends_no_body_at_all(monkeypatch):
    assert _sent(monkeypatch)["json"] is None


def test_both_parts_given_are_both_sent(monkeypatch):
    seen = _sent(monkeypatch, answers={"purposes": ["transcribe"]}, recipe={"steps": []})
    assert seen["json"] == {"answers": {"purposes": ["transcribe"]}, "recipe": {"steps": []}}
