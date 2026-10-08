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
        keys = sorted(model) if isinstance(model, dict) else model
        out.append(f"{label}: the model {keys!r} is not pinned in a known form "
                   "(a Hugging Face repo and revision, a Zenodo DOI, a spaCy package and version, a "
                   "Kraken built-in and version, Tesseract data, a built-in, a cloud provider and model, or a role)")


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
    seen_ids: set[str] = set()
    for index, step in enumerate(steps, start=1):
        label = f"step {index} ({step.get('id', '?')})"
        if step.get("id") in seen_ids:
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
        if "model" in step:
            _check_model(label, step["model"], out)
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
    out.extend(unmet_inputs([s.get("job", "") for s in steps],
                            starts_with=starts_with([material] if isinstance(material, str) else material)))
    return out


def cloud_steps(recipe: dict[str, Any]) -> list[str]:
    """The ids of steps that send pages off this Mac (shown in the recipe editor; asked about once)."""
    return [s.get("id", "?") for s in recipe.get("steps") or []
            if str(s.get("runs_on", "")).startswith("cloud:") or "cloud" in (s.get("model") or {})]
