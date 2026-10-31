"""A folder's own answers to Prepare Images' questions, applied to the start plan (`answers.job_answers_by_folder`).
Moved out of `start.py`, which is over a thousand lines. The two questions a folder can answer for itself are
`the_paper` (gates the prepare run) and `two_pages_per_image` (gates the split).
"""
from __future__ import annotations

from typing import Any


def prepare_how(paper: list[str]) -> str:
    """The prepare step's sentence: the engine's, then what the paper answers name that is not built yet."""
    from fichero_server.recipes.prepare import NOT_BUILT_YET
    from fichero_server.recipes.start import how_it_works as _how_it_works

    return " ".join([_how_it_works("prepare-the-image") or "", *[NOT_BUILT_YET[o] for o in paper if o in NOT_BUILT_YET]]).strip()


def with_folder_answers(runs: list[dict[str, Any]], job_answers: dict | None, by_folder: dict | None,
                         skip: Any, names: dict[str, str]) -> list[dict[str, Any]]:
    """A folder that answered a Prepare Images question for itself runs that step with its own answer (`answers.
    job_answers_by_folder`): the project's run leaves the folder out (`exclude_folders`, applied by the runner as for a
    folder's reader) and the folder gets a run of its own, `folder_id`. The paper answer gives the folder its own prepare
    run. The two-pages answer gates the split: an explicit no skips it, with its why; no answer keeps today's behaviour, so
    an older project does not change; a folder's yes runs the split on that folder even where the project says no."""
    answers = {f: a for f, a in (by_folder or {}).items() if isinstance(a, dict)}
    project_no = (job_answers or {}).get("two_pages_per_image") is False
    if not answers and not project_no:
        return runs
    out: list[dict[str, Any]] = []
    for run in runs:
        if run.get("job") == "prepare-the-image":
            own = {f: list(a["the_paper"] or []) for f, a in answers.items() if isinstance(a.get("the_paper"), list)}
            out.append({**run, "exclude_folders": [*run.get("exclude_folders", []), *own]})
            out += [{**run, "folder_id": f, "paper": paper, "exclude_folders": [], "how": prepare_how(paper)}
                    for f, paper in own.items()]
        elif run.get("job") == "split-pages":
            said = {f: a["two_pages_per_image"] for f, a in answers.items() if isinstance(a.get("two_pages_per_image"), bool)}
            yes = [f for f, v in said.items() if v]
            if not project_no:
                out.append({**run, "exclude_folders": [*run.get("exclude_folders", []), *(f for f, v in said.items() if not v)]})
            elif yes:
                out += [{**run, "folder_id": f, "exclude_folders": []} for f in yes]
            else:
                sid = run["steps"][0]
                skip(sid, f"{names.get(sid, sid)}: Two pages in one picture? is answered no, so the pictures are not cut", None)
        else:
            out.append(run)
    return out
