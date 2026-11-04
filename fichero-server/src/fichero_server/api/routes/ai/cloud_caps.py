"""The app-wide cloud spend caps (`ai.cloud.monthly-cap-in-settings`, `ai.cloud.daily-cap`, `ai.cloud.caps-are-one-audited-action`).

They are defaults, not second ceilings: a project with a cap answer of its own uses it, a project with none uses these, and the
one hold (`llm/spend.py`) still judges that project's own ledger. One audited action sets either; Undo is the same call with
the `from` figures."""

from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.api.routes.auth.accounts import _require_owner_or_bootstrap

router = APIRouter()

_KEYS = {"monthly": "cloud_monthly_cap_usd", "daily": "cloud_daily_cap_usd"}


class CloudCaps(BaseModel):
    monthly_cap_usd: float = Field(description="what a project with no cap of its own may spend on cloud calls a (UTC) month, US$; 10 until set")
    daily_cap_usd: Optional[float] = Field(default=None, description="what it may spend a (UTC) day; null: no daily cap")


class CloudCapSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    which: Literal["monthly", "daily"] = Field(description="which app-wide cap")
    cap_usd: Optional[float] = Field(default=None, ge=0, description="the cap in US$ (0 is a cap: nothing is sent); null clears it (monthly returns to 10, daily to none)")


class CloudCapsChanged(CloudCaps):
    audit_id: str = Field(description="the audit row of the change; setting the cap back to its `from` figure undoes it")


def _view() -> CloudCaps:
    from fichero_server.llm import spend

    monthly = spend.app_cap_usd(spend.APP_MONTHLY_KEY)
    return CloudCaps(monthly_cap_usd=spend.DEFAULT_CAP_USD if monthly is None else monthly,
                     daily_cap_usd=spend.app_cap_usd(spend.APP_DAILY_KEY))


@router.get("/ai/cloud-caps", response_model=CloudCaps)
async def get_cloud_caps() -> CloudCaps:
    """The app-wide monthly and daily cloud caps a project with no cap of its own is held to."""
    return await asyncio.to_thread(_view)


@router.put("/ai/cloud-caps", response_model=CloudCapsChanged)
async def put_cloud_cap(body: CloudCapSetting, request: Request) -> CloudCapsChanged:
    """Set or clear one app-wide cap (`app.set_cloud_cap`, audited first: no audit row, no change). Owner only: it decides what
    every project that has no cap of its own may spend."""
    _require_owner_or_bootstrap(request)
    from fichero_server.api.routes.auth.accounts import _current_session_user
    from fichero_server.db.app import get_app_db
    from fichero_server.llm import spend
    from fichero_server.models import ActionAudit

    key = {"monthly": spend.APP_MONTHLY_KEY, "daily": spend.APP_DAILY_KEY}[body.which]
    if body.cap_usd is not None and body.cap_usd != body.cap_usd:
        raise HTTPException(status_code=422, detail="The cap is a number of dollars, 0 or more.")
    before = spend.app_cap_usd(key)
    user = _current_session_user(request)
    actor = "bootstrap" if getattr(request.state, "bootstrap_auth", False) else f"user:{user.id}" if user else "system"
    audit = ActionAudit(action_name="app.set_cloud_cap", actor=actor, target_ids=[], params=body.model_dump(),
                        before={"which": body.which, "cap_usd": before}, after={"which": body.which, "cap_usd": body.cap_usd})
    await asyncio.to_thread(get_app_db().save_chained_account_audit, audit)
    await asyncio.to_thread(spend.set_app_cap_usd, key, body.cap_usd)
    now = await asyncio.to_thread(_view)
    return CloudCapsChanged(**now.model_dump(), audit_id=str(audit.id))
