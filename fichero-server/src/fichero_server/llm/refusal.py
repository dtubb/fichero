"""One typed refusal for money and for images (`ai.cloud.one-typed-refusal`, #6349, #6350): what was refused, which cap or rule,
the figures, the words and the fixes a client offers as buttons. Served by the engine and computed by no client. It rides on
`CloudSpendRefusedError` and `EgressRefusedError`, on a hand run's 400 (`detail.refusal`), on a run paused at a cap and on a
page's failure."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

CAP_CONTROL = "settings.ai.cloudCaps"
ALLOW_CONTROL = "settings.ai.cloudAllowed"


class CloudRefusalFix(BaseModel):
    kind: Literal["raise-to", "allow-everywhere", "allow-project", "allow-once", "over-cap-once", "open-settings"] = Field(
        description=(
            "`raise-to`: raise the cap this refusal names to `usd` (an app cap raises the app setting, a project's its own); "
            "`allow-everywhere`: images only, set the APP default (the audited places action); `allow-project`: say yes for this "
            "project (`project.allow_cloud`); `allow-once` / `over-cap-once`: this run only; `open-settings`: open `control`"))
    usd: Optional[float] = Field(default=None, description="`raise-to`: the cap, to the cent, that lets the refused call or run through")
    control: Optional[str] = Field(default=None, description="`open-settings`: the control's id (`settings.ai.cloudAllowed`, `settings.ai.cloudCaps`)")


class CloudRefusal(BaseModel):
    kind: Literal["cap-monthly", "cap-daily", "cap-project", "cap-run", "images"] = Field(description="which rule refused")
    scope: Literal["app", "project"] = Field(description="whose setting is refusing: the app's default or this project's own")
    project: Optional[str] = Field(default=None, description="the project's name; null when no project is open")
    cap_usd: Optional[float] = Field(default=None, description="a cap kind: the cap")
    spent_usd: Optional[float] = Field(default=None, description="a cap kind: what is booked against it")
    estimate_usd: Optional[float] = Field(default=None, description="this call's worst case, or the run's estimate")
    words: str = Field(description="what happened, in a sentence, naming the figures")
    fixes: list[CloudRefusalFix] = Field(default_factory=list, description="the buttons, in the order to offer them")


class CloudRefusalDetail(BaseModel):
    """The `detail` of a 400 that is a cloud refusal."""

    message: str
    refusal: Optional[CloudRefusal] = None


class CloudRefusalError(BaseModel):
    """The body of a 400 that is a cloud refusal: FastAPI's `{"detail": ...}` with the typed refusal inside."""

    detail: CloudRefusalDetail


def for_cap(*, kind: str, scope: str, project: str | None, cap_usd: float, spent_usd: float, estimate_usd: float, words: str) -> CloudRefusal:
    """A cap refusal and its fixes: raise the cap it names, run past it once, or open the caps in Settings."""
    from fichero_server.llm.spend import needed_cap_usd

    fixes = [CloudRefusalFix(kind="raise-to", usd=needed_cap_usd(spent_usd, estimate_usd)),
             CloudRefusalFix(kind="over-cap-once"),
             CloudRefusalFix(kind="open-settings", control=CAP_CONTROL)]
    return CloudRefusal(kind=kind, scope=scope, project=project, cap_usd=cap_usd, spent_usd=spent_usd,
                        estimate_usd=estimate_usd, words=words, fixes=fixes)


def for_images(*, project: str | None, words: str) -> CloudRefusal:
    """An images refusal: allow for every project, for this one, once, or open the switch. With no project open there is no
    project to allow and no run to allow once for."""
    fixes = [CloudRefusalFix(kind="allow-everywhere")]
    if project:
        fixes += [CloudRefusalFix(kind="allow-project"), CloudRefusalFix(kind="allow-once")]
    fixes.append(CloudRefusalFix(kind="open-settings", control=ALLOW_CONTROL))
    return CloudRefusal(kind="images", scope="project" if project else "app", project=project, words=words, fixes=fixes)
