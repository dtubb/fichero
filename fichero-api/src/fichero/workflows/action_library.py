"""
Action Library for reusable workflow components.

Provides functionality to:
- Save workflow nodes/subgraphs as reusable actions
- Organize actions by category
- Import/export action templates
- Search and browse action library
"""

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ActionCategory(str, Enum):
    """Categories for organizing actions."""

    TRANSFORM = "transform"
    ANALYZE = "analyze"
    GENERATE = "generate"
    CONVERT = "convert"
    EXTRACT = "extract"
    SEARCH = "search"
    COMMUNICATE = "communicate"
    INTEGRATE = "integrate"
    CUSTOM = "custom"


class ActionParameter(BaseModel):
    """Definition of an action parameter."""

    name: str
    type: str  # string, number, boolean, array, object
    description: str = ""
    required: bool = True
    default: Any = None
    options: list[Any] = Field(default_factory=list)  # For enum-like parameters


class ActionDefinition(BaseModel):
    """Definition of a reusable action."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    category: ActionCategory = ActionCategory.CUSTOM
    icon: str = "gearshape"  # SF Symbol name

    # The actual workflow node(s) this action represents
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)

    # Parameters that can be configured when using the action
    parameters: list[ActionParameter] = Field(default_factory=list)

    # Metadata
    author: str = ""
    version: str = "1.0.0"
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Usage tracking
    use_count: int = 0


class ActionLibraryStore:
    """Persistent storage for action library."""

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = (
                Path.home() / "Library" / "Application Support" / "Fichero" / "actions"
            )
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._actions: dict[str, ActionDefinition] = {}
        self._load_all()

    def _get_action_path(self, action_id: str) -> Path:
        """Get the file path for an action."""
        return self.storage_path / f"{action_id}.json"

    def _load_all(self) -> None:
        """Load all actions from storage."""
        self._actions.clear()
        for path in self.storage_path.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                action = ActionDefinition(**data)
                self._actions[action.id] = action
            except Exception as e:
                logger.error(f"Failed to load action from {path}: {e}")
        logger.info(f"Loaded {len(self._actions)} actions from library")

    def _save_action(self, action: ActionDefinition) -> None:
        """Save a single action to storage."""
        path = self._get_action_path(action.id)
        with open(path, "w") as f:
            json.dump(action.model_dump(mode="json"), f, indent=2, default=str)

    def create(self, action: ActionDefinition) -> ActionDefinition:
        """Create a new action in the library."""
        action.created_at = datetime.now()
        action.updated_at = datetime.now()
        self._actions[action.id] = action
        self._save_action(action)
        logger.info(f"Created action: {action.name} ({action.id})")
        return action

    def get(self, action_id: str) -> Optional[ActionDefinition]:
        """Get an action by ID."""
        return self._actions.get(action_id)

    def update(self, action_id: str, updates: dict) -> Optional[ActionDefinition]:
        """Update an existing action."""
        action = self._actions.get(action_id)
        if not action:
            return None

        # Apply updates
        action_data = action.model_dump()
        action_data.update(updates)
        action_data["updated_at"] = datetime.now()

        updated_action = ActionDefinition(**action_data)
        self._actions[action_id] = updated_action
        self._save_action(updated_action)
        logger.info(f"Updated action: {updated_action.name} ({action_id})")
        return updated_action

    def delete(self, action_id: str) -> bool:
        """Delete an action from the library."""
        if action_id not in self._actions:
            return False

        del self._actions[action_id]
        path = self._get_action_path(action_id)
        if path.exists():
            path.unlink()
        logger.info(f"Deleted action: {action_id}")
        return True

    def list_all(self) -> list[ActionDefinition]:
        """List all actions."""
        return list(self._actions.values())

    def list_by_category(self, category: ActionCategory) -> list[ActionDefinition]:
        """List actions in a specific category."""
        return [a for a in self._actions.values() if a.category == category]

    def search(
        self,
        query: str = "",
        category: Optional[ActionCategory] = None,
        tags: Optional[list[str]] = None,
    ) -> list[ActionDefinition]:
        """Search actions by query, category, and tags."""
        results = list(self._actions.values())

        # Filter by category
        if category:
            results = [a for a in results if a.category == category]

        # Filter by tags
        if tags:
            results = [a for a in results if any(t in a.tags for t in tags)]

        # Filter by query (searches name, description, tags)
        if query:
            query_lower = query.lower()
            results = [
                a
                for a in results
                if query_lower in a.name.lower()
                or query_lower in a.description.lower()
                or any(query_lower in t.lower() for t in a.tags)
            ]

        return results

    def increment_use_count(self, action_id: str) -> None:
        """Increment the use count for an action."""
        action = self._actions.get(action_id)
        if action:
            action.use_count += 1
            self._save_action(action)

    def get_popular(self, limit: int = 10) -> list[ActionDefinition]:
        """Get most popular actions by use count."""
        sorted_actions = sorted(
            self._actions.values(), key=lambda a: a.use_count, reverse=True
        )
        return sorted_actions[:limit]

    def get_recent(self, limit: int = 10) -> list[ActionDefinition]:
        """Get most recently created/updated actions."""
        sorted_actions = sorted(
            self._actions.values(), key=lambda a: a.updated_at, reverse=True
        )
        return sorted_actions[:limit]

    def export_action(self, action_id: str) -> Optional[dict]:
        """Export an action as a portable dictionary."""
        action = self._actions.get(action_id)
        if not action:
            return None

        export_data = action.model_dump(mode="json")
        # Remove usage statistics for export
        export_data.pop("use_count", None)
        return export_data

    def import_action(self, data: dict) -> ActionDefinition:
        """Import an action from a dictionary."""
        # Generate new ID to avoid conflicts
        data["id"] = str(uuid.uuid4())
        data["created_at"] = datetime.now()
        data["updated_at"] = datetime.now()
        data["use_count"] = 0

        action = ActionDefinition(**data)
        return self.create(action)

    def export_all(self) -> list[dict]:
        """Export all actions."""
        return [self.export_action(a.id) for a in self._actions.values()]

    def import_all(self, actions: list[dict]) -> list[ActionDefinition]:
        """Import multiple actions."""
        imported = []
        for data in actions:
            try:
                action = self.import_action(data)
                imported.append(action)
            except Exception as e:
                logger.error(f"Failed to import action: {e}")
        return imported


# Built-in action templates
BUILTIN_ACTIONS = [
    ActionDefinition(
        id="builtin-summarize-text",
        name="Summarize Text",
        description="Generate a concise summary of text content",
        category=ActionCategory.ANALYZE,
        icon="doc.text.magnifyingglass",
        nodes=[
            {
                "id": "llm-summarize",
                "type": "llm",
                "data": {
                    "prompt": "Summarize the following text concisely:\n\n{input}",
                    "model": "default",
                },
            }
        ],
        parameters=[
            ActionParameter(
                name="length",
                type="string",
                description="Summary length",
                default="medium",
                options=["short", "medium", "long"],
            )
        ],
        author="Fichero",
        tags=["text", "summary", "llm"],
    ),
    ActionDefinition(
        id="builtin-extract-keywords",
        name="Extract Keywords",
        description="Extract key terms and phrases from text",
        category=ActionCategory.EXTRACT,
        icon="tag",
        nodes=[
            {
                "id": "llm-keywords",
                "type": "llm",
                "data": {
                    "prompt": "Extract the main keywords and key phrases from this text. Return as a comma-separated list:\n\n{input}",
                    "model": "default",
                },
            }
        ],
        parameters=[
            ActionParameter(
                name="max_keywords",
                type="number",
                description="Maximum number of keywords",
                default=10,
            )
        ],
        author="Fichero",
        tags=["text", "keywords", "extraction"],
    ),
    ActionDefinition(
        id="builtin-translate",
        name="Translate Text",
        description="Translate text to another language",
        category=ActionCategory.TRANSFORM,
        icon="globe",
        nodes=[
            {
                "id": "llm-translate",
                "type": "llm",
                "data": {
                    "prompt": "Translate the following text to {target_language}:\n\n{input}",
                    "model": "default",
                },
            }
        ],
        parameters=[
            ActionParameter(
                name="target_language",
                type="string",
                description="Target language",
                required=True,
                options=[
                    "English",
                    "Spanish",
                    "French",
                    "German",
                    "Chinese",
                    "Japanese",
                ],
            )
        ],
        author="Fichero",
        tags=["text", "translation", "language"],
    ),
    ActionDefinition(
        id="builtin-sentiment-analysis",
        name="Analyze Sentiment",
        description="Analyze the sentiment of text content",
        category=ActionCategory.ANALYZE,
        icon="face.smiling",
        nodes=[
            {
                "id": "llm-sentiment",
                "type": "llm",
                "data": {
                    "prompt": "Analyze the sentiment of this text. Classify as positive, negative, or neutral, and explain why:\n\n{input}",
                    "model": "default",
                },
            }
        ],
        parameters=[],
        author="Fichero",
        tags=["text", "sentiment", "analysis"],
    ),
    ActionDefinition(
        id="builtin-generate-questions",
        name="Generate Questions",
        description="Generate questions about the content",
        category=ActionCategory.GENERATE,
        icon="questionmark.circle",
        nodes=[
            {
                "id": "llm-questions",
                "type": "llm",
                "data": {
                    "prompt": "Generate {num_questions} thoughtful questions about this content:\n\n{input}",
                    "model": "default",
                },
            }
        ],
        parameters=[
            ActionParameter(
                name="num_questions",
                type="number",
                description="Number of questions to generate",
                default=5,
            )
        ],
        author="Fichero",
        tags=["text", "questions", "learning"],
    ),
    ActionDefinition(
        id="builtin-pdf-to-text",
        name="PDF to Text",
        description="Extract text content from a PDF file",
        category=ActionCategory.CONVERT,
        icon="doc.richtext",
        nodes=[
            {
                "id": "extract-pdf",
                "type": "tool",
                "data": {"tool": "extract_text", "params": {"file_path": "{input}"}},
            }
        ],
        parameters=[],
        author="Fichero",
        tags=["pdf", "text", "extraction"],
    ),
    ActionDefinition(
        id="builtin-web-search",
        name="Web Search",
        description="Search the web for information",
        category=ActionCategory.SEARCH,
        icon="magnifyingglass",
        nodes=[
            {
                "id": "web-search",
                "type": "tool",
                "data": {"tool": "web_search", "params": {"query": "{input}"}},
            }
        ],
        parameters=[
            ActionParameter(
                name="num_results",
                type="number",
                description="Number of results",
                default=5,
            )
        ],
        author="Fichero",
        tags=["web", "search", "research"],
    ),
    ActionDefinition(
        id="builtin-email-draft",
        name="Draft Email",
        description="Generate an email draft from notes",
        category=ActionCategory.COMMUNICATE,
        icon="envelope",
        nodes=[
            {
                "id": "llm-email",
                "type": "llm",
                "data": {
                    "prompt": "Write a {tone} email based on these notes:\n\n{input}",
                    "model": "default",
                },
            }
        ],
        parameters=[
            ActionParameter(
                name="tone",
                type="string",
                description="Email tone",
                default="professional",
                options=["professional", "friendly", "formal", "casual"],
            )
        ],
        author="Fichero",
        tags=["email", "communication", "writing"],
    ),
]


def get_action_library(storage_path: Optional[Path] = None) -> ActionLibraryStore:
    """Get or create the action library store."""
    store = ActionLibraryStore(storage_path)

    # Add built-in actions if not present
    for builtin in BUILTIN_ACTIONS:
        if not store.get(builtin.id):
            store._actions[builtin.id] = builtin
            # Don't persist built-ins to disk

    return store
