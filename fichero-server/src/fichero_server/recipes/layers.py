"""Adding a layer (or a language) to a project later (#5470, `source.onboard.add-layer`).

The layer joins the project's answers, its steps join the recipe, and the jobs it needs for the material
already in the project are PROPOSED (`recipe/proposed.yaml`): the Start plan shows them with the estimate it
already computes, and nothing runs until the person presses Start. Removing the layer before then withdraws
them. Pure: the engine action (`project.add_layer`, `api/routes/system/recipes.py`) reads and writes the files.
"""
from __future__ import annotations

from typing import Any, Callable

from fichero_server.recipes.assemble import PURPOSE_STEPS, STEP_ORDER, addable_layers, layer_jobs


def _insert(steps: list[dict], new: dict) -> None:
    """Put `new` before the first step the rules order after it, or before the checks and output
    (check, export, publish), which come last."""
    from fichero_server.recipes.jobs import get_job

    rank = STEP_ORDER.index(new["job"])
    for i, step in enumerate(steps):
        job = step.get("job")
        last = (j := get_job(job or "")) is not None and j.layer in ("check", "output")
        if last or (job in STEP_ORDER and STEP_ORDER.index(job) > rank):
            steps.insert(i, new)
            return
    steps.append(new)


def change(setup: dict[str, Any], proposal: dict[str, Any] | None, *, layers: list[str], languages: list[str],
           remove: bool, assemble: Callable[[dict[str, Any]], dict[str, Any]], now: str) -> dict[str, Any]:
    """The project's answers, recipe and proposal after adding (or removing) layers and languages.

    A layer joins `answers.layers`; the steps the rules assemble for it join the recipe beside the steps it
    has (the person's own choices of model stay); its steps are proposed for the material already there.
    A language joins `answers.languages` and the recipe is proposed again from the answers, as the
    Inspector's Languages field does; a language proposes nothing for the material already there.
    Raises ValueError, in words, for anything it cannot do.
    """
    answers = dict(setup.get("answers") or {})
    if not answers.get("purpose"):
        raise ValueError("this project has not been set up yet: run setup first")
    if not layers and not languages:
        raise ValueError("name a layer or a language to add")
    known = addable_layers()
    unknown = [layer for layer in layers if layer not in known]
    if unknown:
        raise ValueError(f"no layer {', '.join(unknown)}: a project can add {', '.join(known)}")
    from fichero_server.recipes.jobs import get_job

    from_purpose = {get_job(j).layer for j in PURPOSE_STEPS.get(answers["purpose"], ())}
    have_layers = list(answers.get("layers") or [])
    have_languages = list(answers.get("languages") or [])
    if remove:
        purpose_owned = [layer for layer in layers if layer in from_purpose]
        if purpose_owned:
            raise ValueError(f"the {', '.join(purpose_owned)} layer comes with the purpose; change the purpose instead")
        absent = [layer for layer in layers if layer not in have_layers]
        absent += [code for code in languages if code not in have_languages]
        if absent:
            raise ValueError(f"the project has no added {', '.join(absent)} to remove")
        new_layers = [layer for layer in have_layers if layer not in layers]
        new_languages = [code for code in have_languages if code not in languages]
        if languages and not new_languages:
            raise ValueError("a project keeps at least one language")
    else:
        already = [layer for layer in layers if layer in have_layers or layer in from_purpose]
        already += [code for code in languages if code in have_languages]
        if already:
            raise ValueError(f"the recipe already has {', '.join(already)}")
        new_layers = have_layers + list(layers)
        new_languages = have_languages + list(languages)
    answers.update(layers=new_layers, languages=new_languages)
    assembled = assemble(answers)
    recipe = setup.get("recipe")
    jobs = {j for layer in layers for j in layer_jobs(layer)}
    if languages or not recipe:
        recipe = assembled
    else:
        recipe = dict(recipe)
        steps = [dict(s) for s in recipe.get("steps") or []]
        if remove:
            steps = [s for s in steps if s.get("job") not in jobs]
        else:
            present = {s.get("job") for s in steps}
            for step in assembled["steps"]:
                if step["job"] in jobs and step["job"] not in present:
                    _insert(steps, step)
        recipe["steps"] = steps
    # Proposed for the material already there: the added layers' steps; removing a layer withdraws its own.
    proposal = dict(proposal or {"layers": [], "steps": []})
    if remove:
        dropped = {s.get("id") for s in (setup.get("recipe") or {}).get("steps") or [] if s.get("job") in jobs}
        proposal["layers"] = [layer for layer in proposal["layers"] if layer not in layers]
        proposal["steps"] = [sid for sid in proposal["steps"] if sid not in dropped]
    elif layers:
        proposal["layers"] = proposal["layers"] + list(layers)
        proposal["steps"] = proposal["steps"] + [s["id"] for s in recipe["steps"]
                                                 if s.get("job") in jobs and s["id"] not in proposal["steps"]]
        proposal["proposed_at"] = now
    return {"answers": answers, "recipe": recipe, "proposed": proposal if proposal["steps"] else None}


def explain(recipe: dict[str, Any] | None, proposal: dict[str, Any] | None) -> dict[str, Any] | None:
    """The proposal as the Start plan shows it: each step's job explained by its topic (the topic registry)."""
    if not proposal:
        return None
    from fichero_server.recipes.jobs import get_job

    by_id = {s.get("id"): s for s in (recipe or {}).get("steps") or []}
    steps = []
    for sid in proposal.get("steps") or []:
        job = get_job((by_id.get(sid) or {}).get("job", ""))
        topic = job.topic if job else None
        steps.append({"step": sid, "job": job.id if job else None, "layer": job.layer if job else None,
                      "topic": topic.id if topic else None, "title": topic.title if topic else sid,
                      "explanation": topic.text if topic else ""})
    return {"layers": list(proposal.get("layers") or []), "steps": steps, "proposed_at": proposal.get("proposed_at")}
