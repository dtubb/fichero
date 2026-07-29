"""
Workflow Definition Persistence

Provides CRUD operations and import/export for workflow definitions.
Workflows are stored in DuckDB with full JSON export/import support.

Usage:
    from fichero_server.workflows.workflow_store import WorkflowStore
    from fichero_server.db import Database

    db = Database()
    store = WorkflowStore(db)

    # Create workflow
    workflow = Workflow(name="Transcribe Documents", format="nodes")
    store.save(workflow)

    # List workflows
    workflows = store.list_all()

    # Get by ID
    workflow = store.get(workflow_id)

    # Export/Import
    json_str = store.export_workflow(workflow_id)
    imported = store.import_workflow(json_str)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fichero_server.db import Database
from fichero_server.models import Workflow

logger = logging.getLogger(__name__)


class WorkflowStore:
    """
    Store for managing workflow definitions.

    Provides CRUD operations and import/export for workflows saved
    in the DuckDB database.
    """

    def __init__(self, db: Database):
        """
        Initialize workflow store.

        Args:
            db: Database instance
        """
        self.db = db
        logger.info("Initialized WorkflowStore")

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def save(self, workflow: Workflow) -> None:
        """
        Save workflow definition to database.

        Updates updated_at timestamp automatically.

        Args:
            workflow: Workflow to save

        Raises:
            PermissionError: ``workflow.is_system`` is True — global default
                workflows are read-only (#11 Phase 1); duplicate to edit.
                Internal seeding (``default_workflows.seed_default_workflows``)
                writes ``is_system`` rows via ``Database.save`` directly and
                is unaffected by this guard.
        """
        if getattr(workflow, "is_system", False):
            raise PermissionError(
                "Default workflows are read-only; duplicate to edit."
            )
        workflow.updated_at = datetime.now()
        self.db.save(workflow)
        if self.db.get(Workflow, workflow.id) is None:
            raise RuntimeError(f"Workflow save did not persist row: {workflow.id}")
        logger.info(f"Saved workflow: {workflow.name} ({workflow.id})")

    def get(self, workflow_id: str) -> Workflow | None:
        """
        Get workflow by ID.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow or None if not found
        """
        workflow = self.db.get(Workflow, workflow_id)
        if workflow:
            logger.debug(f"Retrieved workflow: {workflow.name} ({workflow_id})")
        else:
            logger.debug(f"Workflow not found: {workflow_id}")
        return workflow

    def delete(self, workflow_id: str) -> bool:
        """
        Delete workflow by ID.

        Args:
            workflow_id: Workflow ID

        Returns:
            True if deleted, False if not found

        Raises:
            PermissionError: the workflow is ``is_system`` (read-only).
        """
        workflow = self.get(workflow_id)
        if not workflow:
            logger.warning(f"Cannot delete - workflow not found: {workflow_id}")
            return False
        if getattr(workflow, "is_system", False):
            raise PermissionError(
                "Default workflows are read-only; duplicate to edit."
            )

        self.db.delete(workflow)
        logger.info(f"Deleted workflow: {workflow.name} ({workflow_id})")
        return True

    def list_all(self, folder_path: str | None = None) -> list[Workflow]:
        """
        List all workflows, optionally filtered by folder.

        Args:
            folder_path: Optional folder path filter (e.g. "/archive/letters")

        Returns:
            List of workflows, sorted by folder_path and sort_order
        """
        if folder_path:
            workflows = self.db.query(Workflow, folder_path=folder_path)
        else:
            workflows = self.db.query(Workflow)

        # Sort by folder path, then sort_order, then name
        workflows.sort(key=lambda w: (w.folder_path, w.sort_order, w.name))

        logger.debug(
            f"Listed {len(workflows)} workflows (folder: {folder_path or 'all'})"
        )
        return workflows

    def list_templates(self) -> list[Workflow]:
        """
        List all workflow templates.

        Returns:
            List of workflow templates, sorted by name
        """
        templates = self.db.query(Workflow, is_template=True)
        templates.sort(key=lambda w: w.name)

        logger.debug(f"Listed {len(templates)} workflow templates")
        return templates

    def search(
        self,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
        provider: str | None = None,
    ) -> list[Workflow]:
        """
        Search workflows by criteria.

        Args:
            name: Partial name match (case-insensitive)
            tags: Workflows must have all specified tags
            provider: Filter by provider

        Returns:
            List of matching workflows
        """
        workflows = self.db.query(Workflow)

        # Filter by name (case-insensitive substring match)
        if name:
            name_lower = name.lower()
            workflows = [w for w in workflows if name_lower in w.name.lower()]

        # Filter by tags (must have all specified tags)
        if tags:
            workflows = [w for w in workflows if all(tag in w.tags for tag in tags)]

        # Filter by provider
        if provider:
            workflows = [w for w in workflows if w.provider == provider]

        logger.debug(
            f"Search found {len(workflows)} workflows "
            f"(name={name}, tags={tags}, provider={provider})"
        )
        return workflows

    def duplicate(self, workflow_id: str, new_name: str | None = None) -> Workflow:
        """
        Duplicate a workflow with a new ID.

        Args:
            workflow_id: ID of workflow to duplicate
            new_name: Optional new name (defaults to "Copy of {original_name}")

        Returns:
            New duplicated workflow

        Raises:
            ValueError: If workflow not found
        """
        original = self.get(workflow_id)
        if not original:
            raise ValueError(f"Workflow not found: {workflow_id}")

        # Create new workflow with new ID
        duplicate = Workflow(
            **original.model_dump(exclude={"id", "created_at", "updated_at"})
        )
        duplicate.name = new_name or f"Copy of {original.name}"
        # A duplicate is always a personal, editable copy — never inherits
        # is_system (#11 Phase 1: the folded-document mirror derives
        # scope="global"/read_only from is_system).
        duplicate.is_system = False

        self.save(duplicate)
        logger.info(f"Duplicated workflow: {original.name} → {duplicate.name}")
        return duplicate

    def update_folder(self, workflow_id: str, folder_path: str) -> bool:
        """
        Move workflow to a different folder.

        Args:
            workflow_id: Workflow ID
            folder_path: New folder path (Unix-style, e.g. "/archive/letters")

        Returns:
            True if updated, False if not found
        """
        workflow = self.get(workflow_id)
        if not workflow:
            return False

        old_path = workflow.folder_path
        workflow.folder_path = folder_path
        self.save(workflow)

        logger.info(f"Moved workflow: {workflow.name} from {old_path} to {folder_path}")
        return True

    def update_sort_order(self, workflow_id: str, sort_order: int) -> bool:
        """
        Update workflow sort order within its folder.

        Args:
            workflow_id: Workflow ID
            sort_order: New sort order (lower numbers appear first)

        Returns:
            True if updated, False if not found
        """
        workflow = self.get(workflow_id)
        if not workflow:
            return False

        workflow.sort_order = sort_order
        self.save(workflow)

        logger.debug(f"Updated sort order: {workflow.name} → {sort_order}")
        return True

    # =========================================================================
    # Import/Export
    # =========================================================================

    def export_workflow(self, workflow_id: str) -> str:
        """
        Export workflow as JSON string.

        Includes all workflow data for complete portability.

        Args:
            workflow_id: Workflow ID

        Returns:
            JSON string

        Raises:
            ValueError: If workflow not found
        """
        workflow = self.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        # Export with formatting for readability
        data = workflow.model_dump(mode="json")
        json_str = json.dumps(data, indent=2, default=str)

        logger.info(f"Exported workflow: {workflow.name} ({len(json_str)} bytes)")
        return json_str

    def import_workflow(
        self,
        json_str: str,
        *,
        new_id: bool = True,
        folder_path: str | None = None,
    ) -> Workflow:
        """
        Import workflow from JSON string.

        Args:
            json_str: JSON string (from export_workflow)
            new_id: If True, assign new ID (default); if False, keep original ID
            folder_path: Optional folder path override

        Returns:
            Imported workflow

        Raises:
            ValueError: If JSON is invalid or incomplete
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        # Validate required fields
        if "name" not in data:
            raise ValueError("Missing required field: name")

        # Create workflow (will generate new ID if not in data)
        if new_id:
            data.pop("id", None)  # Remove ID to generate new one

        if folder_path:
            data["folder_path"] = folder_path

        try:
            workflow = Workflow(**data)
        except Exception as e:
            raise ValueError(f"Invalid workflow data: {e}")

        self.save(workflow)
        logger.info(f"Imported workflow: {workflow.name} (new_id={new_id})")
        return workflow

    def export_to_file(self, workflow_id: str, file_path: str | Path) -> None:
        """
        Export workflow to JSON file.

        Args:
            workflow_id: Workflow ID
            file_path: Path to write JSON file

        Raises:
            ValueError: If workflow not found
        """
        json_str = self.export_workflow(workflow_id)

        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json_str, encoding="utf-8")

        logger.info(f"Exported workflow to file: {file_path}")

    def import_from_file(
        self,
        file_path: str | Path,
        **kwargs: Any,
    ) -> Workflow:
        """
        Import workflow from JSON file.

        Args:
            file_path: Path to JSON file
            **kwargs: Additional arguments for import_workflow

        Returns:
            Imported workflow

        Raises:
            ValueError: If file not found or JSON invalid
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ValueError(f"File not found: {file_path}")

        json_str = file_path.read_text(encoding="utf-8")
        workflow = self.import_workflow(json_str, **kwargs)

        logger.info(f"Imported workflow from file: {file_path}")
        return workflow

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    def export_all(self, folder_path: str | None = None) -> str:
        """
        Export multiple workflows as JSON array.

        Args:
            folder_path: Optional folder path filter

        Returns:
            JSON string containing array of workflows
        """
        workflows = self.list_all(folder_path=folder_path)
        data = [w.model_dump(mode="json") for w in workflows]
        json_str = json.dumps(data, indent=2, default=str)

        logger.info(
            f"Exported {len(workflows)} workflows "
            f"(folder: {folder_path or 'all'}, {len(json_str)} bytes)"
        )
        return json_str

    def import_all(
        self,
        json_str: str,
        *,
        new_ids: bool = True,
        folder_path: str | None = None,
    ) -> list[Workflow]:
        """
        Import multiple workflows from JSON array.

        Args:
            json_str: JSON string containing array of workflows
            new_ids: If True, assign new IDs to all workflows
            folder_path: Optional folder path override for all workflows

        Returns:
            List of imported workflows

        Raises:
            ValueError: If JSON is invalid
        """
        try:
            data_list = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        if not isinstance(data_list, list):
            raise ValueError("JSON must be an array of workflows")

        imported = []
        for data in data_list:
            if new_ids:
                data.pop("id", None)

            if folder_path:
                data["folder_path"] = folder_path

            try:
                workflow = Workflow(**data)
                self.save(workflow)
                imported.append(workflow)
            except Exception as e:
                logger.warning(f"Skipped invalid workflow: {e}")
                continue

        logger.info(
            f"Imported {len(imported)}/{len(data_list)} workflows (new_ids={new_ids})"
        )
        return imported


# Convenience function to get store from default DB
def get_workflow_store() -> WorkflowStore:
    """
    Get workflow store using default Fichero database.

    Returns:
        WorkflowStore instance
    """
    from fichero_server.db import Database

    db = Database()
    return WorkflowStore(db)
