"""`source.try.use-this-scope` (#6135): a reader chosen for ONE folder is applied at Start to the pages of that
folder, the same as a project-level choice; the rest of the project keeps the project's reader.

WHY: `apply_project_overrides` skipped every folder override, so Use This for a folder was refused (nothing applied it);
the person's choice for a folder of print pages went nowhere.
"""
from __future__ import annotations

from fichero_server.recipes import start
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_start_plan import LINES, READ, _recipe

PPOCR = {"zenodo": "10.5281/zenodo.21788410"}


def _with_folder_override(*folders):
    recipe = _recipe(LINES, READ)
    recipe["overrides"] = [{"step": "read", "scope": "folder", "folder_id": f, "model": PPOCR, "card": "ppocr",
                            "runs_on": "this-mac", "because": "chosen for the folder"} for f in folders]
    return recipe


def _readers(plan):
    return {(r.get("folder_id"), r["model_override"]) for r in plan["workflows"] if "read" in r["steps"]}


def test_the_folders_pages_are_read_by_its_reader_and_the_rest_by_the_projects():
    plan = plan_start(_with_folder_override("f1"), stays_local=True)
    assert plan["refusals"] == []
    assert _readers(plan) == {(None, "kraken-mccatmus"), ("f1", "kraken-zenodo-21788410")}
    base = next(r for r in plan["workflows"] if r.get("folder_id") is None and "read" in r["steps"])
    assert base["exclude_folders"] == ["f1"]
    own = next(r for r in plan["workflows"] if r.get("folder_id") == "f1")
    assert own["exclude_folders"] == [] and own["steps"] == ["lines", "read"], "the folder's pages are lined too"


def test_a_project_with_no_folder_override_plans_exactly_as_before():
    plan = plan_start(_recipe(LINES, READ), stays_local=True)
    assert all("folder_id" not in r and "exclude_folders" not in r for r in plan["workflows"])


def test_two_folders_each_get_their_run_and_each_run_leaves_the_others_out():
    plan = plan_start(_with_folder_override("f1", "f2"), stays_local=True)
    own = {r["folder_id"]: r for r in plan["workflows"] if r.get("folder_id")}
    assert own["f1"]["exclude_folders"] == ["f2"] and own["f2"]["exclude_folders"] == ["f1"]
    base = next(r for r in plan["workflows"] if r.get("folder_id") is None and "read" in r["steps"])
    assert base["exclude_folders"] == ["f1", "f2"]


def test_a_folder_reader_this_mac_cannot_serve_refuses_start_naming_the_folder(monkeypatch):
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve",
                        lambda runs, names=None: ["Read each line cannot run on this Mac"] if any(
                            r.get("model_override") == "kraken-zenodo-21788410" for r in runs) else [])
    plan = plan_start(_with_folder_override("f1"), stays_local=True)
    assert any(r.startswith("For the folder f1:") for r in plan["refusals"])


def test_the_runner_keeps_a_folder_runs_pages_inside_it_and_the_innermost_folder_wins():
    from fichero_server.recipes.runner import _in_the_cards_folders

    tree = {"root": (None, "f", "folder"), "f1": ("root", "f", "folder"), "f2": ("f1", "f", "folder"),
            "p0": ("root", "p", "page"), "p1": ("f1", "p", "page"), "p2": ("f2", "p", "page")}
    pages = ["p0", "p1", "p2"]
    project = {"exclude_folders": ["f1", "f2"]}
    outer = {"folder_id": "f1", "exclude_folders": ["f2"]}
    inner = {"folder_id": "f2", "exclude_folders": ["f1"]}
    assert _in_the_cards_folders(None, project, pages, tree) == ["p0"]
    assert _in_the_cards_folders(None, outer, pages, tree) == ["p1"]
    assert _in_the_cards_folders(None, inner, pages, tree) == ["p2"]


def test_the_runner_treats_a_trashed_override_folder_as_holding_no_pages():
    from fichero_server.recipes.runner import _in_the_cards_folders

    tree = {"root": (None, "f", "folder"), "p0": ("root", "p", "page")}  # f1 is gone from the tree
    assert _in_the_cards_folders(None, {"exclude_folders": ["f1"]}, ["p0"], tree) == ["p0"]
    assert _in_the_cards_folders(None, {"folder_id": "f1", "exclude_folders": []}, ["p0"], tree) == []


def test_an_override_whose_folder_was_trashed_is_skipped_with_the_why_and_the_base_run_keeps_every_page():
    class _Db:  # the project's tree has no f1
        pass

    import fichero_server.recipes.runner as runner

    real = runner.folder_scope
    runner.folder_scope = lambda db, f, tree=None: (_ for _ in ()).throw(LookupError(f"{f} is not a folder in this project"))
    try:
        plan = plan_start(_with_folder_override("f1"), stays_local=True, db=_Db())
    finally:
        runner.folder_scope = real
    assert all(r.get("folder_id") is None for r in plan["workflows"])
    base = next(r for r in plan["workflows"] if "read" in r["steps"])
    assert not base.get("exclude_folders")
    assert any(s["why"].startswith("For the folder f1: it is no longer in this project") for s in plan["skipped"])


def test_another_steps_refusal_is_not_repeated_for_the_folder(monkeypatch):
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve",
                        lambda runs, names=None: ["Review cannot run on this Mac"])
    plan = plan_start(_with_folder_override("f1"), stays_local=True)
    assert not any(r.startswith("For the folder") for r in plan["refusals"])
