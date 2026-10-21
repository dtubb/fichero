"""`ai.where.egress-at-every-call` / `ai.where.one-egress-gate` (#5368): a model call made for a project is judged by the app's
places AND the project's own rule (its saved Set Up answer `cloud_allowed`), bound where the run or the chat starts."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from fichero_server import llm
from fichero_server.llm import EgressRefusedError, LLMConfig, LocalOnlyViolationError
from fichero_server.recipes import places
from fichero_server.recipes.project import write_project_setup

SRC = Path(llm.__file__).parents[1]
CLOUD = LLMConfig(provider="openai", model="m")
THIS_MAC = LLMConfig(provider="ollama", model="m")


@pytest.fixture(autouse=True)
def _app_allows_everything(monkeypatch):
    """The app's places answer nothing here (not answered caps nothing): only the project's own rule is under test."""
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(places, "get_places", lambda: None)


def _project(tmp_path: Path, *, cloud_allowed: bool | None) -> Path:
    library = tmp_path / "p.fichero"
    library.mkdir()
    if cloud_allowed is not None:
        write_project_setup(library, {"purposes": ["transcribe"], "cloud_allowed": cloud_allowed}, None)
    return library


def test_a_project_that_said_nothing_leaves_refuses_a_cloud_call_in_words(tmp_path):
    with places.bound_project(_project(tmp_path, cloud_allowed=False)):
        with pytest.raises(LocalOnlyViolationError) as refused:
            llm.get_langchain_model(CLOUD)
    assert "keeps its pages on this Mac" in str(refused.value) and "nothing left this Mac" in str(refused.value)


def test_the_same_call_for_a_project_that_said_yes_is_not_refused_by_the_gate(tmp_path):
    with places.bound_project(_project(tmp_path, cloud_allowed=True)):
        assert llm._enforce_local_only_provider(CLOUD, kind="chat") is None  # raises if refused


def test_a_project_with_no_saved_set_up_and_a_call_for_no_project_are_refused_as_the_spec_says(tmp_path):
    """`ai.where.one-egress-gate` fails closed: no saved Set Up is no yes, and no project open is refused too (it was the
    bound-project reader that let both through; the gate now has one reader, `llm.egress`)."""
    with places.bound_project(_project(tmp_path, cloud_allowed=None)):
        with pytest.raises(EgressRefusedError):
            llm._enforce_local_only_provider(CLOUD, kind="chat")
    with pytest.raises(EgressRefusedError):
        llm._enforce_local_only_provider(CLOUD, kind="chat")  # bound to nothing


def test_this_mac_is_never_refused_by_the_projects_rule(tmp_path):
    with places.bound_project(_project(tmp_path, cloud_allowed=False)):
        assert llm._enforce_local_only_provider(THIS_MAC, kind="chat") is None


def test_chat_with_tools_and_structured_output_meet_the_projects_rule(tmp_path):
    class Schema(BaseModel):
        x: int = 0

    with places.bound_project(_project(tmp_path, cloud_allowed=False)):
        for call in (lambda: llm.chat_with_tools("hi", [], CLOUD), lambda: llm.structured_output("hi", Schema, CLOUD)):
            with pytest.raises(LocalOnlyViolationError):
                asyncio.run(call())


def test_the_binding_follows_the_work_into_a_thread_and_ends_with_the_block(tmp_path):
    library = _project(tmp_path, cloud_allowed=False)

    async def inside():
        return await asyncio.to_thread(places.bound_library)

    with places.bound_project(library):
        assert asyncio.run(inside()) == library
    assert places.bound_library() is None


def test_each_place_a_run_or_chat_starts_binds_its_project():
    """The run thread (workflow bar, recipe, schedule, MCP all start one) and the chat route bind the library they work in."""
    for rel, fn_name in (("execution/runner.py", "_run_workflow_in_background"), ("api/routes/system/chat.py", "chat")):
        tree = ast.parse((SRC / rel).read_text())
        fn = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name)
        assert "bound_project(" in ast.unparse(fn), f"{rel}::{fn_name} must bind the project the work is for"


def test_a_try_runs_on_a_scratch_copy_but_is_judged_by_the_real_projects_rule(tmp_path):
    """Set Up's tries (`recipes/samples._run_one`) run on a scratch copy with no Set Up of its own (## 789 LOW): the one gate
    reader maps the copy to its real project, so the real project's yes allows it and its no refuses it, in words."""
    said_no = _project(tmp_path, cloud_allowed=False)
    said_yes = tmp_path / "yes.fichero"
    said_yes.mkdir()
    write_project_setup(said_yes, {"purposes": ["transcribe"], "cloud_allowed": True}, None)
    scratch = tmp_path / "try.fichero"
    scratch.mkdir()
    with places.bound_project(scratch):
        with pytest.raises(EgressRefusedError):
            llm._enforce_local_only_provider(CLOUD, kind="chat")  # a copy alone has no yes: why the try must name its project
    with places.scratch_of(scratch, said_yes):
        assert places.bound_library() is None  # nothing bound outside a bound block
        with places.bound_project(scratch):
            assert places.bound_library() == said_yes
            llm._enforce_local_only_provider(CLOUD, kind="chat")  # the real project said yes
    with places.scratch_of(scratch, said_no):
        with places.bound_project(scratch):
            with pytest.raises(EgressRefusedError) as refused:
                llm._enforce_local_only_provider(CLOUD, kind="chat")
    assert "keeps its pages on this Mac" in str(refused.value) and "p" in str(refused.value)
    with places.bound_project(scratch):
        assert places.bound_library() == scratch  # the mapping ends with the try


def test_the_try_names_its_real_project_for_the_copy():
    tree = ast.parse((SRC / "recipes/samples.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_one")
    assert "scratch_of(" in ast.unparse(fn)
