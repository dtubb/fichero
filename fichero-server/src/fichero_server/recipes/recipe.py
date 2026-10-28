"""The recipe file format and the check that runs before anything does.

`source/models-chains-and-projects.md` section 9: `source.recipe.folder-format`,
`source.recipe.data-not-code`, `source.recipe.never-holds-keys`,
`source.recipe.names-models-and-where`, `source.recipe.steps-are-jobs`. A recipe is a folder
(`recipe.yaml`, `prompts/*.prompt.md`, ...); it is DATA: it names jobs, models, settings, prompts
and where each step runs. `check_recipe` reports every problem as a plain sentence, step by step,
so a person (or setup) can fix them before a run starts; `[]` means it can run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fichero_server.recipes.jobs import get_job, starts_with, unmet_inputs

#: The newest recipe schema this Fichero reads. A newer one is refused, not guessed at.
SCHEMA_VERSION = 1

#: The only conditions a step may carry (no expressions: a recipe is data).
CONDITIONS = frozenset({"spreads_detected", "confidence_below", "corrected_lines_at_least"})

#: Kinds of place a step can run (a shared recipe never names a person's own cluster account).
PLACES = ("this-mac", "cluster", "gpu-service")

#: The ways a model may be named. Each is a set of keys a `model` mapping must have exactly.
PIN_FORMS = (
    frozenset({"hf", "revision"}),
    frozenset({"zenodo"}),
    frozenset({"spacy", "version"}),
    frozenset({"kraken", "kraken_version"}),
    frozenset({"tesseract", "traineddata"}),
    frozenset({"builtin"}),
    frozenset({"cloud", "model"}),
    frozenset({"role"}),
    # A YOLO layout model by its catalogue name (`yolo_runtime.YOLO_MODELS`), as the shipped card pins it (#5525).
    frozenset({"yolo"}),
)

#: Keys that would make a recipe carry code, credentials or capabilities. Refused anywhere.
_FORBIDDEN_KEYS = frozenset({
    "script", "scripts_to_run", "exec", "command", "shell", "code", "python", "import",
    "api_key", "apikey", "key", "token", "secret", "password", "credentials", "tools", "network",
})
#: `scripts` is allowed only where it means writing systems: in `suits`.
_ALLOWED_SCRIPTS_PARENT = "suits"


def load_recipe(folder: Path) -> dict[str, Any]:
    """Read `recipe.yaml` from a recipe folder with a loader that cannot run code."""
    import yaml

    data = yaml.safe_load((Path(folder) / "recipe.yaml").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("recipe.yaml does not hold a recipe (a mapping at the top)")
    return data


def _walk_forbidden(node: Any, path: str, parent: str, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            k = str(key).lower()
            if k in _FORBIDDEN_KEYS and not (k == "scripts" and parent == _ALLOWED_SCRIPTS_PARENT):
                out.append(f"{path}{key}: a recipe is data, never code or credentials; this entry is refused")
            _walk_forbidden(value, f"{path}{key}.", k, out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_forbidden(item, f"{path}{i}.", parent, out)


def _check_model(label: str, model: Any, out: list[str]) -> None:
    if not isinstance(model, dict) or frozenset(model) not in PIN_FORMS:
        # Said in words, never as the pin's keys (#5664 onboarding: "the model ['yolo'] is not pinned …").
        out.append(f"{label}: its model is not named in a way Fichero knows. Name it by a Hugging Face "
                   "repository and revision, a Zenodo DOI, a spaCy package and version, a Kraken model and "
                   "version, Tesseract data, a built-in, a YOLO layout model, a provider and model, or a role")


def _check_not_gone(label: str, model: Any, out: list[str]) -> None:
    """A pinned Hugging Face model whose last fetch failed because the repository is gone or refuses is said so, from the
    model store's record: no network (`source.recipe.pinned-model-gone`, #5364)."""
    repo = model.get("hf") if isinstance(model, dict) else None
    if not repo:
        return
    from fichero_server.llm import failed_fetches

    why = failed_fetches.last(str(repo))
    if why:
        out.append(f"{label}: its model {repo} can no longer be fetched ({why}); choose another reader for this step")


def _check_prompt(label: str, folder: Path | None, prompt: str, out: list[str]) -> None:
    if folder is None:
        return
    path = folder / prompt
    if not path.is_file():
        out.append(f"{label}: its prompt file {prompt} is missing")
        return
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        out.append(f"{label}: {prompt} has no header (job, model, version, variables)")


def check_recipe(recipe: dict[str, Any], folder: Path | None = None) -> list[str]:
    """Every reason this recipe cannot run as it stands, step by step; [] if it can."""
    out: list[str] = []
    version = recipe.get("fichero_recipe")
    if not isinstance(version, int):
        return ["recipe.yaml does not say which recipe schema it uses (fichero_recipe)"]
    if version > SCHEMA_VERSION:
        return [f"this recipe uses schema {version}; this Fichero reads up to {SCHEMA_VERSION}. Update Fichero to use it"]
    for key in ("id", "version", "title", "steps"):
        if not recipe.get(key):
            out.append(f"recipe.yaml has no {key}")
    _walk_forbidden(recipe, "", "", out)

    steps = recipe.get("steps") or []
    if not isinstance(steps, list):
        out.append("recipe.yaml: steps is not a list of steps")
        steps = []
    seen_ids: set[str] = set()
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):  # a hand edit: a bare word where a step goes (#5364)
            out.append(f"step {index}: is not a step ({step!r}); a step has an id and a job")
            continue
        label = f"step {index} ({step.get('id', '?')})"
        if not step.get("id"):
            out.append(f"{label}: has no id")
        elif step.get("id") in seen_ids:
            out.append(f"{label}: another step already has this id")
        seen_ids.add(step.get("id"))
        job = get_job(step.get("job", ""))
        if job is None:
            continue  # named by unmet_inputs below, once
        if step.get("layer") and step["layer"] != job.layer:
            out.append(f"{label}: says layer {step['layer']!r}, but {job.name} belongs to {job.layer!r}")
        for cond_key in ("when", "offered_when"):
            for name in (step.get(cond_key) or {}):
                if name not in CONDITIONS:
                    out.append(f"{label}: {cond_key} {name!r} is not one of the allowed conditions "
                               f"({', '.join(sorted(CONDITIONS))})")
        if "model" in step and step["model"] is None:
            # A step the rules found no model for says why in the person's words, never "the model None" (#5595).
            problem = step.get("problem") if isinstance(step.get("problem"), dict) else {}
            out.append(f"{label}: {problem.get('sentence') or step.get('gap') or 'no model is chosen for it'}")
        elif "model" in step:
            _check_model(label, step["model"], out)
            _check_not_gone(label, step["model"], out)
        for alt in step.get("alternatives") or []:
            _check_model(f"{label} alternative", alt, out)
        runs_on = step.get("runs_on")
        if runs_on is not None and runs_on not in PLACES and not str(runs_on).startswith("cloud:"):
            out.append(f"{label}: runs_on {runs_on!r} is not a kind of place "
                       "(this-mac, cloud: <provider>, cluster, gpu-service)")
        if step.get("prompt"):
            _check_prompt(label, folder, step["prompt"], out)

    # Material that is already text starts with the page's text, so its recipe needs no reading step (#5553).
    material = (recipe.get("suits") or {}).get("material")
    out.extend(unmet_inputs([s.get("job", "") if isinstance(s, dict) else None for s in steps],
                            starts_with=starts_with([material] if isinstance(material, str) else material)))
    _check_overrides(recipe.get("overrides"), seen_ids, out)
    return out


def _check_overrides(overrides: Any, step_ids: set[str], out: list[str]) -> None:
    """Each kept choice must name a step of this recipe and a scope (#5364): a hand edit that renamed a step left
    the person's choice pointing nowhere. A removed step's record names a step that is gone by design."""
    if overrides is None:
        return
    if not isinstance(overrides, list):
        out.append("recipe.yaml: overrides is not a list")
        return
    for index, o in enumerate(overrides, start=1):
        if not isinstance(o, dict):
            out.append(f"override {index}: is not an override ({o!r})")
            continue
        if override_kind(o) != REMOVED_STEP and o.get("step") not in step_ids:
            out.append(f"override {index}: names step {o.get('step')!r}, which this recipe does not have")
        if o.get("scope") not in ("project", "folder"):
            out.append(f"override {index}: scope {o.get('scope')!r} is not project or folder")


REMOVED_STEP = "removed-step"
PAGE_STEP = "read-a-page"


def add_page_step(recipe: dict[str, Any], model: dict | None = None, runs_on: str | None = None) -> tuple[dict, str]:
    """The recipe's Read the whole page step, added when it has none (#6250 ruling 3): with `model` as its reader, tied to the
    lines (`tie-text-to-lines`, with the line reader's model) and with Find lines if missing. (the step, the sentence saying
    what was added; "" when it was there). Changes `recipe` in place."""
    from fichero_server.recipes.layers import _insert

    steps = recipe.setdefault("steps", [])
    found = next((s for s in steps if s.get("job") == PAGE_STEP), None)
    if found is not None:
        return found, ""
    jobs = {s.get("job") for s in steps}
    line_model = next((s.get("model") for s in steps if s.get("job") == "read-a-line" and s.get("model")), None)
    added = []
    for job, extra in (("find-lines", {}), (PAGE_STEP, {"model": dict(model or {}), "runs_on": runs_on}),
                       ("tie-text-to-lines", {"model": dict(line_model)} if line_model else {})):
        if job not in jobs:
            _insert(steps, {"id": job, "job": job, **{k: v for k, v in extra.items() if v}})
            added.append(job)
    page = next(s for s in steps if s.get("job") == PAGE_STEP)
    return page, ("Your page reader adds the step Read the whole page, tied to the lines"
                  + (", with Find lines" if "find-lines" in added else "") + ".")


def fit_overrides(recipe: dict[str, Any]) -> list[str]:
    """Fit the kept choices to the recipe's steps, never refusing (#6259): a page reader chosen for a recipe with no Read the
    whole page step adds that step with the reader as its model, tied to the lines (and Find lines, if missing), as the #6250
    ruling says; any other choice for a step the recipe no longer has is dropped. The sentences say what changed. Changes
    `recipe` in place."""
    ids = {s.get("id") for s in recipe.get("steps") or [] if isinstance(s, dict)}
    kept, notes = [], []
    for o in recipe.get("overrides") or []:
        if not isinstance(o, dict) or override_kind(o) == REMOVED_STEP or o.get("step") in ids:
            kept.append(o)
            continue
        # A folder's page reader adds the step too, as Use This does: a step is project-wide, the choice stays the folder's.
        if o.get("step") == PAGE_STEP and o.get("scope") in ("project", "folder") and isinstance(o.get("model"), dict) and o["model"]:
            notes.append(add_page_step(recipe, o["model"], o.get("runs_on"))[1])
            ids.add(PAGE_STEP)
            kept.append(o)
        else:
            notes.append(f"Your choice for the step {o.get('step')!r} was dropped: this recipe no longer has that step.")
    if "overrides" in recipe:
        recipe["overrides"] = kept
    return notes


def override_kind(override: dict[str, Any]) -> str:
    """What an override records: a `card` (a chosen reader; every record kept before kinds read as this) or a
    `removed-step` (`source.recipe.take-without-missing-step`, #4949)."""
    return str(override.get("kind") or "card")


def take_without_missing_steps(recipe: dict[str, Any]) -> dict[str, Any]:
    """The recipe without the steps whose job this Fichero lacks, each removal recorded as an override of kind
    `removed-step` ("job not available"); a recipe with none missing comes back as it is. The argument is untouched."""
    import copy

    missing = [s for s in recipe.get("steps") or [] if get_job(s.get("job", "")) is None]
    if not missing:
        return recipe
    out = copy.deepcopy(recipe)
    gone = {s.get("id") for s in missing}
    out["steps"] = [s for s in out["steps"] if s.get("id") not in gone]
    # The step as it was and its place, so offering it back restores it exactly.
    places = {s.get("id"): i for i, s in enumerate(recipe.get("steps") or [])}
    out["overrides"] = [*(out.get("overrides") or []),
                        *({"step": s.get("id"), "kind": REMOVED_STEP, "reason": "job not available",
                           "job": s.get("job"), "scope": "project", "folder_id": None,
                           "step_def": copy.deepcopy(s), "index": places[s.get("id")]} for s in missing)]
    return out


def put_back(recipe: dict[str, Any], step_id: str) -> dict[str, Any]:
    """The recipe with a removed step restored exactly as it was shared, in its place, and its record gone. Refused while
    its job is still missing. The argument is untouched."""
    import copy

    record = next((o for o in offered_back(recipe) if o.get("step") == step_id), None)
    if record is None or not isinstance(record.get("step_def"), dict):
        raise ValueError(f"step {step_id!r} is not a removed step whose job exists now")
    out = copy.deepcopy(recipe)
    out["overrides"] = [o for o in out.get("overrides") or [] if not (override_kind(o) == REMOVED_STEP
                                                                       and o.get("step") == step_id)]
    out["steps"].insert(min(int(record.get("index") or 0), len(out["steps"])), copy.deepcopy(record["step_def"]))
    if not out["overrides"]:
        out.pop("overrides")
    return out


def offered_back(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """The removed steps whose job exists now (after an update): offered back to the person, never put back by itself."""
    return [o for o in recipe.get("overrides") or []
            if override_kind(o) == REMOVED_STEP and get_job(str(o.get("job") or "")) is not None]


def cloud_steps(recipe: dict[str, Any]) -> list[str]:
    """The ids of steps that send pages off this Mac (shown in the recipe editor; asked about once)."""
    return [s.get("id", "?") for s in recipe.get("steps") or []
            if str(s.get("runs_on", "")).startswith("cloud:") or pin_leaves_this_mac(s.get("model"))]


def pin_leaves_this_mac(model: Any) -> bool:
    """Whether a step's model sends its pages off this Mac: a provider and model pin (`{cloud, model}`) does unless
    the provider's address is on this Mac (an Ollama or LM Studio server here, `ai.where.place-is-by-address`,
    #5619); a cloud company's provider never is, at any address. Every other pin runs here."""
    if not isinstance(model, dict) or "cloud" not in model:
        return False
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.places import THIS_MAC, place_of

    return place_of(LLMConfig(provider=str(model["cloud"]), model=str(model.get("model") or ""))) != THIS_MAC
