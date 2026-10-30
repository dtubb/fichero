"""A reader chosen for one folder, planned on its own (`source.try.use-this-scope`, #6135).
Moved out of `start.py`, which is over a thousand lines (`start.plan_start` calls `with_folder_overrides`).
"""
from __future__ import annotations

from typing import Any


def with_folder_overrides(recipe: dict, runs: list[dict[str, Any]], **plan_args: Any
                           ) -> tuple[list[dict[str, Any]], list[dict[str, str | None]], list[str]]:
    """A reader chosen for one folder runs on that folder's pages (`source.try.use-this-scope`, #6135): for each folder
    override, the step is planned again with the override as its choice and that plan's runs are added, tagged
    `folder_id`; every run of the step leaves the other override folders' pages out (`exclude_folders`, applied by
    the runner, nested folders to the innermost). Returns (the runs, what the folder's plan skipped, what it refuses).
    A folder whose reader cannot be planned keeps the project's reader and says why."""
    from fichero_server.recipes.bakeoff import apply_project_overrides
    from fichero_server.recipes.start import plan_start, step_names

    overrides = [o for o in recipe.get("overrides") or [] if o.get("scope") == "folder" and o.get("folder_id")]
    if not overrides:
        return runs, [], []
    out, skipped, refusals = list(runs), [], []
    names = step_names(recipe)
    db = plan_args.get("db")
    if db is not None:  # an override outlives its folder when the folder is trashed: it is skipped, with the why
        from fichero_server.recipes.runner import folder_scope

        live = []
        for o in overrides:
            try:
                folder_scope(db, o["folder_id"])
                live.append(o)
            except LookupError:
                skipped.append({"step": o.get("step"), "fix": None, "why": (
                    f"For the folder {o['folder_id']}: it is no longer in this project, so its own reader is not used "
                    "and its pages keep the project's")})
        overrides = live
    for sid in dict.fromkeys(o.get("step") for o in overrides):
        base = [r for r in out if sid in r["steps"]]
        mine = [o for o in overrides if o.get("step") == sid]
        folders = list(dict.fromkeys(o["folder_id"] for o in mine))
        if not base:
            continue
        for run in base:
            run["exclude_folders"] = list(dict.fromkeys([*run.get("exclude_folders", []), *folders]))  # beside a folder's own answers
        for o in mine:
            as_project = apply_project_overrides({**recipe, "overrides": [{**o, "scope": "project"}]}, [])
            plan = plan_start({**as_project, "overrides": []}, **plan_args)  # the whole recipe: the run keeps the steps it chains
            own = [r for r in plan["runs"] if sid in r["steps"]]
            skipped += [{**s, "why": f"For the folder {o['folder_id']}: {s['why']}"} for s in plan["skipped"]
                        if s.get("step") == sid]
            # only this step's own refusals: the whole recipe is planned again, and another step's repeats nothing new
            refusals += [f"For the folder {o['folder_id']}: {r}" for r in plan["refusals"]
                         if sid in r or names.get(sid, sid) in r]
            if not own:  # nothing runs for the folder's reader: its pages stay with the project's
                for run in base:
                    run["exclude_folders"] = [f for f in run["exclude_folders"] if f != o["folder_id"]]
                continue
            for run in own:
                run["folder_id"] = o["folder_id"]
                run["exclude_folders"] = [f for f in folders if f != o["folder_id"]]
            out += own
    return out, skipped, refusals
