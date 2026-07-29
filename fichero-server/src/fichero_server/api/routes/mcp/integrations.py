"""
API routes for app integrations.

Provides endpoints for:
- Listing available integrations
- Checking integration status
- Listing/searching items from integrated apps
- Importing/exporting items
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fichero_server.integrations.base import get_integration_registry
from fichero_server.models import IntegrationListResponse

router = APIRouter(prefix="/integrations", tags=["integrations"])


# Response Models
class IntegrationInfo(BaseModel):
    """Information about an integration."""

    name: str
    bundle_id: str
    status: str
    version: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None


class IntegrationItem(BaseModel):
    """An item from an integrated app."""

    external_id: str
    name: str
    source_app: str
    item_type: str
    file_path: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    metadata: dict = {}
    created_at: Optional[str] = None
    modified_at: Optional[str] = None


class ExportRequest(BaseModel):
    """Request to export a file to an app."""

    file_path: str
    metadata: Optional[dict] = None
    # App-specific options
    database: Optional[str] = None  # DEVONthink
    group: Optional[str] = None  # DEVONthink
    container: Optional[str] = None  # Tinderbox
    prototype: Optional[str] = None  # Tinderbox


class ExportResponse(BaseModel):
    """Response from export operation."""

    success: bool
    external_id: Optional[str] = None
    error: Optional[str] = None


class ImportRequest(BaseModel):
    """Request to import an item from an app."""

    external_id: str
    target_path: Optional[str] = None


class ImportResponse(BaseModel):
    """Response from import operation."""

    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


class OpenItemResponse(BaseModel):
    success: bool


class DatabaseListResponse(BaseModel):
    databases: list


class LibraryListResponse(BaseModel):
    libraries: list


class CitationResponse(BaseModel):
    citation: str
    style: str


class DocumentListResponse(BaseModel):
    documents: list


class CreateNoteResponse(BaseModel):
    success: bool
    id: str


class AttributesResponse(BaseModel):
    attributes: dict


class SetAttributesResponse(BaseModel):
    success: bool


# Routes
@router.get("", response_model=IntegrationListResponse)
async def list_integrations():
    """List all available integrations and their status."""
    registry = get_integration_registry()
    integrations = []

    for integration in registry.list_all():
        info = integration.app_info
        integrations.append(
            IntegrationInfo(
                name=integration.name,
                bundle_id=integration.bundle_id,
                status=info.status.value,
                version=info.version,
                path=str(info.path) if info.path else None,
                error=info.error_message,
            )
        )

    return IntegrationListResponse(items=integrations, count=len(integrations))


@router.get("/available", response_model=IntegrationListResponse)
async def list_available_integrations():
    """List only integrations that are currently available."""
    registry = get_integration_registry()
    integrations = []

    for integration in registry.list_available():
        info = integration.app_info
        integrations.append(
            IntegrationInfo(
                name=integration.name,
                bundle_id=integration.bundle_id,
                status=info.status.value,
                version=info.version,
                path=str(info.path) if info.path else None,
                error=info.error_message,
            )
        )

    return IntegrationListResponse(items=integrations, count=len(integrations))


@router.get("/{app_name}", response_model=IntegrationInfo)
async def get_integration(app_name: str):
    """Get information about a specific integration."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    info = integration.app_info
    return IntegrationInfo(
        name=integration.name,
        bundle_id=integration.bundle_id,
        status=info.status.value,
        version=info.version,
        path=str(info.path) if info.path else None,
        error=info.error_message,
    )


@router.post("/{app_name}/refresh", response_model=IntegrationInfo)
async def refresh_integration(app_name: str):
    """Refresh the status of an integration."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    # Force re-check availability
    integration._app_info = None
    integration.check_availability()

    info = integration.app_info
    return IntegrationInfo(
        name=integration.name,
        bundle_id=integration.bundle_id,
        status=info.status.value,
        version=info.version,
        path=str(info.path) if info.path else None,
        error=info.error_message,
    )


@router.get("/{app_name}/items", response_model=IntegrationListResponse)
async def list_items(
    app_name: str,
    limit: int = Query(default=100, ge=1, le=1000),
    search: Optional[str] = None,
    item_type: Optional[str] = None,
    database: Optional[str] = None,  # DEVONthink
    container: Optional[str] = None,  # Tinderbox
):
    """List items from an integrated app."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    if not integration.is_available:
        raise HTTPException(
            status_code=503,
            detail=f"{integration.name} is not available: {integration.app_info.error_message or 'App not found'}",
        )

    # Call list_items with app-specific parameters
    kwargs = {"limit": limit, "search": search, "item_type": item_type}

    # Add app-specific parameters
    if app_name.lower() == "devonthink" and database:
        kwargs["database"] = database
    elif app_name.lower() == "tinderbox" and container:
        kwargs["container"] = container

    items = await integration.list_items(**kwargs)

    return [
        IntegrationItem(
            external_id=item.external_id,
            name=item.name,
            source_app=item.source_app,
            item_type=item.item_type,
            file_path=str(item.file_path) if item.file_path else None,
            url=item.url,
            content=item.content,
            metadata=item.metadata,
            created_at=item.created_at.isoformat() if item.created_at else None,
            modified_at=item.modified_at.isoformat() if item.modified_at else None,
        )
        for item in items
    ]


@router.get("/{app_name}/items/{external_id}", response_model=IntegrationItem)
async def get_item(app_name: str, external_id: str):
    """Get a specific item from an integrated app."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    if not integration.is_available:
        raise HTTPException(
            status_code=503, detail=f"{integration.name} is not available"
        )

    item = await integration.get_item(external_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{external_id}' not found")

    return IntegrationItem(
        external_id=item.external_id,
        name=item.name,
        source_app=item.source_app,
        item_type=item.item_type,
        file_path=str(item.file_path) if item.file_path else None,
        url=item.url,
        content=item.content,
        metadata=item.metadata,
        created_at=item.created_at.isoformat() if item.created_at else None,
        modified_at=item.modified_at.isoformat() if item.modified_at else None,
    )


@router.post("/{app_name}/import", response_model=ImportResponse)
async def import_item(app_name: str, request: ImportRequest):
    """Import an item from an integrated app."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    if not integration.is_available:
        raise HTTPException(
            status_code=503, detail=f"{integration.name} is not available"
        )

    target_path = Path(request.target_path) if request.target_path else None

    try:
        result_path = await integration.import_item(request.external_id, target_path)
        if result_path:
            return ImportResponse(success=True, file_path=str(result_path))
        else:
            return ImportResponse(success=False, error="Import failed")
    except Exception as e:
        return ImportResponse(success=False, error=str(e))


@router.post("/{app_name}/export", response_model=ExportResponse)
async def export_item(app_name: str, request: ExportRequest):
    """Export a file to an integrated app."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    if not integration.is_available:
        raise HTTPException(
            status_code=503, detail=f"{integration.name} is not available"
        )

    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=400, detail=f"File not found: {request.file_path}"
        )

    try:
        # Build kwargs based on app
        kwargs = {"file_path": file_path, "metadata": request.metadata}

        if app_name.lower() == "devonthink":
            if request.database:
                kwargs["database"] = request.database
            if request.group:
                kwargs["group"] = request.group
        elif app_name.lower() == "tinderbox":
            if request.container:
                kwargs["container"] = request.container
            if request.prototype:
                kwargs["prototype"] = request.prototype

        external_id = await integration.export_item(**kwargs)
        if external_id:
            return ExportResponse(success=True, external_id=external_id)
        else:
            return ExportResponse(success=False, error="Export failed")
    except NotImplementedError as e:
        return ExportResponse(success=False, error=str(e))
    except Exception as e:
        return ExportResponse(success=False, error=str(e))


@router.post("/{app_name}/open/{external_id}")
async def open_item(app_name: str, external_id: str) -> OpenItemResponse:
    """Open an item in its native app."""
    registry = get_integration_registry()
    integration = registry.get(app_name)

    if not integration:
        raise HTTPException(
            status_code=404, detail=f"Integration '{app_name}' not found"
        )

    if not integration.is_available:
        raise HTTPException(
            status_code=503, detail=f"{integration.name} is not available"
        )

    # Check if integration has open_item method
    if not hasattr(integration, "open_item"):
        raise HTTPException(
            status_code=501, detail=f"{integration.name} does not support opening items"
        )

    success = await integration.open_item(external_id)
    return OpenItemResponse(success=success)


# DEVONthink-specific endpoints
@router.get("/devonthink/databases")
async def list_devonthink_databases() -> DatabaseListResponse:
    """List DEVONthink databases."""
    registry = get_integration_registry()
    integration = registry.get("devonthink")

    if not integration:
        raise HTTPException(status_code=404, detail="DEVONthink integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="DEVONthink is not available")

    databases = await integration.list_databases()
    return DatabaseListResponse(databases=databases)


# Bookends-specific endpoints
@router.get("/bookends/libraries")
async def list_bookends_libraries() -> LibraryListResponse:
    """List Bookends libraries."""
    registry = get_integration_registry()
    integration = registry.get("bookends")

    if not integration:
        raise HTTPException(status_code=404, detail="Bookends integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="Bookends is not available")

    libraries = await integration.list_libraries()
    return LibraryListResponse(libraries=libraries)


@router.get("/bookends/citation/{external_id}")
async def get_bookends_citation(external_id: str, style: str = Query(default="APA")) -> CitationResponse:
    """Get a formatted citation for a Bookends reference."""
    registry = get_integration_registry()
    integration = registry.get("bookends")

    if not integration:
        raise HTTPException(status_code=404, detail="Bookends integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="Bookends is not available")

    citation = await integration.get_citation(external_id, style)
    if citation:
        return CitationResponse(citation=citation, style=style)
    raise HTTPException(status_code=404, detail="Citation not found")


# Tinderbox-specific endpoints
@router.get("/tinderbox/documents")
async def list_tinderbox_documents() -> DocumentListResponse:
    """List Tinderbox documents."""
    registry = get_integration_registry()
    integration = registry.get("tinderbox")

    if not integration:
        raise HTTPException(status_code=404, detail="Tinderbox integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="Tinderbox is not available")

    documents = await integration.list_documents()
    return DocumentListResponse(documents=documents)


class CreateNoteRequest(BaseModel):
    """Request to create a Tinderbox note."""

    name: str
    text: str = ""
    container: Optional[str] = None
    prototype: Optional[str] = None
    attributes: Optional[dict] = None


@router.post("/tinderbox/notes")
async def create_tinderbox_note(request: CreateNoteRequest) -> CreateNoteResponse:
    """Create a new note in Tinderbox."""
    registry = get_integration_registry()
    integration = registry.get("tinderbox")

    if not integration:
        raise HTTPException(status_code=404, detail="Tinderbox integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="Tinderbox is not available")

    note_id = await integration.create_note(
        name=request.name,
        text=request.text,
        container=request.container,
        prototype=request.prototype,
        attributes=request.attributes,
    )

    if note_id:
        return CreateNoteResponse(success=True, id=note_id)
    raise HTTPException(status_code=500, detail="Failed to create note")


class SetAttributesRequest(BaseModel):
    """Request to set Tinderbox note attributes."""

    attributes: dict


@router.get("/tinderbox/notes/{external_id}/attributes")
async def get_tinderbox_attributes(
    external_id: str,
    attributes: str = Query(..., description="Comma-separated list of attribute names"),
) -> AttributesResponse:
    """Get specific attributes of a Tinderbox note."""
    registry = get_integration_registry()
    integration = registry.get("tinderbox")

    if not integration:
        raise HTTPException(status_code=404, detail="Tinderbox integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="Tinderbox is not available")

    attr_list = [a.strip() for a in attributes.split(",")]
    values = await integration.get_attributes(external_id, attr_list)
    return AttributesResponse(attributes=values)


@router.put("/tinderbox/notes/{external_id}/attributes")
async def set_tinderbox_attributes(external_id: str, request: SetAttributesRequest) -> SetAttributesResponse:
    """Set attributes on a Tinderbox note."""
    registry = get_integration_registry()
    integration = registry.get("tinderbox")

    if not integration:
        raise HTTPException(status_code=404, detail="Tinderbox integration not found")

    if not integration.is_available:
        raise HTTPException(status_code=503, detail="Tinderbox is not available")

    success = await integration.set_attributes(external_id, request.attributes)
    return SetAttributesResponse(success=success)
