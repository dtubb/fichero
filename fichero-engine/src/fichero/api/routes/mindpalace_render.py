"""Mind Palace render endpoint for vision-capable agents."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database_for_write
from fichero.db import Database
from fichero.spatial_models import SpatialConnection, SpatialNode, SpatialRoom, SpatialStack

router = APIRouter(prefix="/mindpalace", tags=["mind-palace"])

# 1x1 transparent PNG
_PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7aN6kAAAAASUVORK5CYII="
)


class SceneRenderRequest(BaseModel):
    room_id: str
    include_video: bool = True
    width: int = Field(default=1280, ge=320, le=4096)
    height: int = Field(default=720, ge=240, le=4096)
    duration_seconds: float = Field(default=2.0, ge=0.5, le=20.0)


class SceneRenderResponse(BaseModel):
    room_id: str
    rendered_at: str
    png_base64: str
    mp4_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/render", response_model=SceneRenderResponse)
async def render_scene(
    request: SceneRenderRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SceneRenderResponse:
    """Return a scene snapshot payload for multimodal agents.

    Backend currently provides a deterministic placeholder image/video payload
    with room metadata; native RealityKit capture is app-side.
    """
    room = db.get(SpatialRoom, request.room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {request.room_id}")

    nodes = [n for n in db.all(SpatialNode) if n.room_id == room.id]
    connections = [c for c in db.all(SpatialConnection) if c.room_id == room.id]
    stacks = [s for s in db.all(SpatialStack) if s.room_id == room.id]

    mp4_payload: str | None = None
    if request.include_video:
        # Placeholder token: not a playable video yet, but stable wire-shape.
        mp4_payload = base64.b64encode(b"placeholder-mp4").decode("ascii")

    return SceneRenderResponse(
        room_id=room.id,
        rendered_at=datetime.now(timezone.utc).isoformat(),
        png_base64=_PNG_1X1_BASE64,
        mp4_base64=mp4_payload,
        metadata={
            "placeholder": True,
            "resolution": {"width": request.width, "height": request.height},
            "duration_seconds": request.duration_seconds,
            "node_count": len(nodes),
            "connection_count": len(connections),
            "stack_count": len(stacks),
        },
    )
