"""Project profile loader (pipeline.project-profile): one TOML per project under pipeline/projects/; the runner's
code names nothing project-specific. The profile is chosen by PIPELINE_PROJECT or pipeline/projects/current."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pipeline import ROOT, steps

PROJECTS = ROOT / "pipeline" / "projects"
REQUIRED = {"repo": ["base", "worktrees", "check_paths"], "labels": ["bug", "claimed"], "github": ["allowed_authors", "agent_email"],
            "workers": ["tmux_session", "cost_cap_usd", "retries", "caps", "needs_mb"], "roles": ["coder"]}


def load(name: str | None = None) -> dict:
    name = name or os.environ.get("PIPELINE_PROJECT") or (PROJECTS / "current").read_text().strip()
    cfg = tomllib.loads((PROJECTS / f"{name}.toml").read_text())
    for section, keys in REQUIRED.items():
        for k in keys:
            if k not in cfg.get(section, {}):
                raise ValueError(f"{name}.toml: [{section}] lacks {k}")
    cfg["name"] = name
    if "steps" in cfg and (bad := steps.validate(cfg["steps"])):  # validate before run
        raise ValueError(f"{name}.toml: steps: {'; '.join(bad)}")
    for role in cfg["roles"].values():  # a role names a tier; the provider's tier pair names the model
        for w in role:
            if "model" not in w:
                w["model"] = cfg["tiers"][w["provider"]][w.get("tier", "big")]
    cfg["repo"]["path"] = str(Path(cfg["repo"].get("path") or ROOT).expanduser())
    return cfg


def at_tier(cfg: dict, worker: dict, tier: str) -> dict:
    """The same worker on the provider's other tier; a provider with no tier pair keeps its model."""
    pair = cfg.get("tiers", {}).get(worker["provider"])
    return dict(worker, tier=tier, model=pair[tier]) if pair else dict(worker, tier=tier)


def pi_model_id(worker: dict) -> str:
    return f"{worker['provider']}/{worker['model']}"


def written_by(worker: dict, repo: str, tool: str) -> str:
    """The trailer for work this worker wrote: its model id (or the bare model name) through `[models.display]` of the repo's harness.toml (an unlisted id passes
    through, agent-profiles.trailer.one-line), and the harness the pipeline runs workers in."""
    toml = Path(repo) / "harness.toml"
    names = (tomllib.loads(toml.read_text()) if toml.is_file() else {}).get("models", {}).get("display", {})
    model = pi_model_id(worker)
    return f"Written-By: {names.get(model) or names.get(worker['model']) or model} using pi using {tool}"
