"""Recipes: the job registry, checking a recipe, and assembling one from setup's answers.

Spec: `source/models-chains-and-projects.md` (`source.recipe.*`, `source.onboard.*`). Read-only:
nothing here writes to a library. The setup window, the Inspector, the command line and MCP all
read the same answers from the engine (four architecture rules: logic in the engine).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.recipes.assemble import PURPOSE_STEPS, PURPOSES, Answers, assemble
from fichero_server.recipes.cards import seed_cards
from fichero_server.recipes.jobs import all_jobs
from fichero_server.recipes.recipe import check_recipe

router = APIRouter(prefix="/recipes")


class JobInfo(BaseModel):
    id: str
    name: str
    description: str
    layer: str
    takes: list[str]
    gives: list[str]
    compare: str
    settings: list[str]
    since: str


class JobListResponse(BaseModel):
    items: list[JobInfo]
    count: int


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs() -> JobListResponse:
    """Every job a recipe can name, with the plain description setup and the manual show."""
    items = [
        JobInfo(id=j.id, name=j.name, description=j.description, layer=j.layer,
                takes=sorted(j.takes), gives=sorted(j.gives), compare=j.compare,
                settings=list(j.settings), since=j.since)
        for j in all_jobs()
    ]
    return JobListResponse(items=items, count=len(items))


class AssembleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: str = Field(description=f"one of: {', '.join(PURPOSE_STEPS)}")
    languages: list[str] = Field(min_length=1, description="BCP 47 language tags")
    scripts: list[str] = Field(min_length=1, description="ISO 15924 script codes")
    material: str = "handwriting"
    pages: int = Field(default=0, ge=0, description="roughly how many pages")
    cloud_allowed: bool = False
    mac_memory_gb: Optional[float] = Field(default=None, description="defaults to this machine's memory")


class RecipeCard(BaseModel):
    """The facts on the chosen model's card that setup shows (`source.onboard.proposes-chain`)."""

    id: str = Field(description="<runtime>:<source>@<version>")
    note: str = ""
    licence: str = ""
    open_licence: bool = True
    size_gb: float = 0.0
    memory_gb: float = 0.0
    cer_measured_here: Optional[float] = None
    cer_published: Optional[float] = None
    trainable: bool = False


class RecipeStep(BaseModel):
    id: str
    job: str
    model: Optional[dict[str, Any]] = None
    card: Optional[RecipeCard] = None
    uses_cloud: bool = False
    runs_on: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    gap: Optional[str] = None
    layer: Optional[str] = None
    offered_when: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class AssembledRecipe(BaseModel):
    id: str
    title: str
    purposes: list[str]
    steps: list[RecipeStep]
    gaps: list[str]
    cloud_options: list[str] = Field(
        default_factory=list,
        description="jobs a cloud model would also fit if pages could leave this Mac; "
        "setup asks the egress question only when this is not empty",
    )
    problems: list[str] = Field(description="what the recipe check finds (empty when it can run)")


def _this_machine_memory_gb() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError):
        return 8.0


class PurposeInfo(BaseModel):
    id: str
    title: str
    description: str
    runs_by_itself: bool = Field(description="true: its layers run after Start; false: tools are offered")


class PurposeListResponse(BaseModel):
    items: list[PurposeInfo]
    count: int


@router.get("/purposes", response_model=PurposeListResponse)
async def list_purposes() -> PurposeListResponse:
    """The purposes setup offers, in order, each with its label and whether it runs by itself
    (`source.onboard.purpose-first`)."""
    items = [
        PurposeInfo(id=pid, title=title, description=desc, runs_by_itself=bool(PURPOSE_STEPS[pid]))
        for pid, (title, desc) in PURPOSES.items()
    ]
    return PurposeListResponse(items=items, count=len(items))


@router.post("/assemble", response_model=AssembledRecipe)
async def assemble_recipe(request: AssembleRequest) -> AssembledRecipe:
    """The recipe the rules give for these answers, each choice with its reasons and each gap named
    (`source.onboard.deterministic-recipe`). Proposes; writes nothing."""
    answers = Answers(
        purpose=request.purpose, languages=frozenset(request.languages),
        scripts=frozenset(request.scripts), material=request.material, pages=request.pages,
        cloud_allowed=request.cloud_allowed,
        mac_memory_gb=request.mac_memory_gb or _this_machine_memory_gb(),
    )
    recipe = assemble(answers, list(seed_cards()))
    problems = [] if recipe["gaps"] else check_recipe(recipe)
    return AssembledRecipe(
        id=recipe["id"], title=recipe["title"], purposes=recipe["purposes"],
        steps=[RecipeStep(**s) for s in recipe["steps"]], gaps=recipe["gaps"],
        cloud_options=recipe["cloud_options"], problems=problems,
    )


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: dict[str, Any]


class CheckResponse(BaseModel):
    problems: list[str]


@router.post("/check", response_model=CheckResponse)
async def check(request: CheckRequest) -> CheckResponse:
    """Every reason a recipe cannot run as it stands, step by step (`source.recipe.*`)."""
    return CheckResponse(problems=check_recipe(request.recipe))
