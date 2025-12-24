"""Sidebar Sections - Data loaders for sidebar content.

Provides section definitions and loaders for the main sidebar:
- Library (Inbox + Collections)
- Searches (saved searches)
- Workflows (processing workflows)
- Tools (available tools)

Usage:
    from fichero.app.main_window.sidebar_sections import (
        SECTIONS,
        load_all_sections,
        SidebarSection,
    )
    from fichero.app.main_window.sidebar import SourceList

    sidebar = SourceList(...)

    # Load all sections
    items = load_all_sections()
    sidebar.items = items

    # Or load specific section
    library_items = SECTIONS["library"].load()

Features:
    - Dataclass-driven section definitions
    - Database-backed loaders (db.query)
    - Extensible section system
    - Accepts drops for inbox/collections
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.app.main_window.sidebar import SourceListItem

logger = logging.getLogger(__name__)


# =============================================================================
# Section Definition
# =============================================================================

@dataclass(frozen=True)
class SidebarSection:
    """Definition for a sidebar section.

    Attributes:
        id: Unique section identifier
        header: Display text for section header
        icon: SF Symbol name for section icon
        loader: Function that returns section items
        accepts_drops: Whether items in this section accept file drops
        default_expanded: Whether section starts expanded
    """
    id: str
    header: str
    icon: str | None = None
    loader: Callable[[], list[SourceListItem]] = field(default=lambda: [])
    accepts_drops: bool = False
    default_expanded: bool = True


# =============================================================================
# Section Loaders
# =============================================================================

def _create_source_list_item(
    id: str,
    text: str,
    icon: str | None = None,
    badge: str | None = None,
    is_header: bool = False,
    accepts_drops: bool = False,
    children: list | None = None,
    data: Any = None,
) -> SourceListItem:
    """Create a SourceListItem with lazy import.

    This avoids circular imports by importing SourceListItem inside the function.
    """
    from fichero.app.main_window.sidebar import SourceListItem

    return SourceListItem(
        id=id,
        text=text,
        icon=icon,
        badge=badge,
        is_header=is_header,
        accepts_drops=accepts_drops,
        children=children or [],
        data=data,
    )


def load_library() -> list[SourceListItem]:
    """Load library section items.

    Returns:
        List of SourceListItems for:
        - Inbox (recent imports)
        - Collections (document groups)
    """
    from fichero.db import db
    from fichero.models import Document, DocType, Status

    items = []

    # Inbox - count of pending documents
    try:
        pending = db.query(Document, status=Status.pending)
        inbox_count = len(pending)
    except Exception as e:
        logger.warning(f"Failed to count inbox: {e}")
        inbox_count = 0

    items.append(_create_source_list_item(
        id="inbox",
        text="Inbox",
        icon="tray.fill",
        badge=str(inbox_count) if inbox_count > 0 else None,
        accepts_drops=True,
        data={"type": "inbox"},
    ))

    # Collections - all collections from database
    try:
        collections = db.query(Document, doc_type=DocType.collection)
        for col in collections:
            # Count children
            children_count = len(db.query(Document, parent_id=col.id)) if col.id else 0

            items.append(_create_source_list_item(
                id=f"col_{col.id}",
                text=col.name or "Untitled",
                icon="folder.fill",
                badge=str(children_count) if children_count > 0 else None,
                accepts_drops=True,
                data={"type": "collection", "doc_id": col.id},
            ))
    except Exception as e:
        logger.warning(f"Failed to load collections: {e}")

    return items


def load_searches() -> list[SourceListItem]:
    """Load saved searches section items.

    Returns:
        List of SourceListItems for saved searches
    """
    # TODO: Implement saved searches in database
    items = []

    # For now, add placeholder items
    items.append(_create_source_list_item(
        id="search_recent",
        text="Recent",
        icon="clock.fill",
        data={"type": "search", "query": "recent:7d"},
    ))

    items.append(_create_source_list_item(
        id="search_flagged",
        text="Flagged",
        icon="flag.fill",
        data={"type": "search", "query": "flagged:true"},
    ))

    return items


def load_workflows() -> list[SourceListItem]:
    """Load workflows section items.

    Returns:
        List of SourceListItems for available workflows
    """
    from fichero.db import db
    from fichero.models import Workflow

    items = []

    try:
        workflows = db.all(Workflow)
        for wf in workflows:
            # Count recent runs
            run_count = 0  # TODO: Count from Run table

            items.append(_create_source_list_item(
                id=f"wf_{wf.id}",
                text=wf.name or "Untitled Workflow",
                icon="gearshape.2",
                badge=str(run_count) if run_count > 0 else None,
                data={"type": "workflow", "workflow_id": wf.id},
            ))
    except Exception as e:
        logger.warning(f"Failed to load workflows: {e}")

    # Add "New Workflow" item
    items.append(_create_source_list_item(
        id="wf_new",
        text="New Workflow...",
        icon="plus.circle",
        data={"type": "action", "action": "new_workflow"},
    ))

    return items


def load_tools() -> list[SourceListItem]:
    """Load tools section items.

    Returns:
        List of SourceListItems for available tools
    """
    # Static list of available tools
    tools = [
        ("transcribe", "Transcribe", "text.viewfinder"),
        ("enhance", "Enhance Image", "wand.and.stars"),
        ("segment", "Segment", "rectangle.split.3x3"),
        ("convert_pdf", "Convert to PDF", "doc.fill"),
        ("batch", "Batch Process", "square.stack.3d.up"),
    ]

    items = []
    for tool_id, name, icon in tools:
        items.append(_create_source_list_item(
            id=f"tool_{tool_id}",
            text=name,
            icon=icon,
            data={"type": "tool", "tool_id": tool_id},
        ))

    return items


# =============================================================================
# Section Registry
# =============================================================================

# All sidebar sections with their loaders
SECTIONS: dict[str, SidebarSection] = {
    "library": SidebarSection(
        id="library",
        header="LIBRARY",
        icon="books.vertical",
        loader=load_library,
        accepts_drops=True,
        default_expanded=True,
    ),
    "searches": SidebarSection(
        id="searches",
        header="SEARCHES",
        icon="magnifyingglass",
        loader=load_searches,
        accepts_drops=False,
        default_expanded=True,
    ),
    "workflows": SidebarSection(
        id="workflows",
        header="WORKFLOWS",
        icon="gearshape.2",
        loader=load_workflows,
        accepts_drops=False,
        default_expanded=True,
    ),
    "tools": SidebarSection(
        id="tools",
        header="TOOLS",
        icon="wrench.and.screwdriver",
        loader=load_tools,
        accepts_drops=False,
        default_expanded=False,
    ),
}

# Default section order
SECTION_ORDER: tuple[str, ...] = ("library", "searches", "workflows", "tools")


def load_all_sections() -> list[SourceListItem]:
    """Load all sections and return as SourceListItems.

    Returns:
        List of SourceListItems with section headers and items
    """
    items = []

    for section_id in SECTION_ORDER:
        section = SECTIONS.get(section_id)
        if not section:
            continue

        # Create section header
        header = _create_source_list_item(
            id=f"section_{section.id}",
            text=section.header,
            icon=section.icon,
            is_header=True,
            children=[],  # Will be populated below
        )

        # Load section items
        try:
            section_items = section.loader()
            header = _create_source_list_item(
                id=header.id,
                text=header.text,
                icon=header.icon,
                is_header=True,
                children=section_items,
            )
        except Exception as e:
            logger.error(f"Failed to load section {section.id}: {e}")

        items.append(header)

    return items


def load_section(section_id: str) -> list[SourceListItem]:
    """Load items for a specific section.

    Args:
        section_id: ID of section to load

    Returns:
        List of SourceListItems for the section
    """
    section = SECTIONS.get(section_id)
    if not section:
        logger.warning(f"Unknown section: {section_id}")
        return []

    try:
        return section.loader()
    except Exception as e:
        logger.error(f"Failed to load section {section_id}: {e}")
        return []


def refresh_section(section_id: str) -> list[SourceListItem]:
    """Refresh a section's items from database.

    Alias for load_section - kept for clarity.

    Args:
        section_id: ID of section to refresh

    Returns:
        Updated list of SourceListItems
    """
    return load_section(section_id)
