"""
Action Store for workflow action library.

Provides persistence and management of reusable workflow actions.
"""

import json
import logging
import uuid
from datetime import datetime
from fichero_server.core.timeutil import ensure_utc, utc_now
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from fichero_server.db import Database

logger = logging.getLogger(__name__)


class Action(BaseModel):
    """A reusable workflow action."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    category: str = "custom"
    tags: list[str] = Field(default_factory=list)
    icon: str = "square.stack.3d.up"

    # Node template for single-node actions
    node_template: dict[str, Any] = Field(default_factory=dict)

    # For composite actions (multiple nodes)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)

    # Metadata
    is_builtin: bool = False
    is_composite: bool = False
    author: str = ""
    use_count: int = 0
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(ser_json_timedelta="iso8601")


# Built-in actions
BUILTIN_ACTIONS = [
    Action(
        id="builtin-llm-prompt",
        name="LLM Prompt",
        description="Send a prompt to an LLM and get a response",
        category="ai",
        tags=["llm", "ai", "text"],
        icon="brain",
        node_template={
            "type": "llm",
            "data": {"prompt": "", "model": "default", "temperature": 0.7},
        },
        is_builtin=True,
        author="Fichero",
    ),
    Action(
        id="builtin-summarize",
        name="Summarize Text",
        description="Generate a concise summary of text content",
        category="transform",
        tags=["text", "summary", "llm"],
        icon="doc.text.magnifyingglass",
        node_template={
            "type": "llm",
            "data": {
                "prompt": "Summarize the following text concisely:\n\n{{input}}",
                "model": "default",
            },
        },
        is_builtin=True,
        author="Fichero",
    ),
    Action(
        id="builtin-extract-keywords",
        name="Extract Keywords",
        description="Extract key terms and phrases from text",
        category="extract",
        tags=["text", "keywords", "extraction"],
        icon="tag",
        node_template={
            "type": "llm",
            "data": {
                "prompt": "Extract the main keywords from this text as comma-separated list:\n\n{{input}}",
                "model": "default",
            },
        },
        is_builtin=True,
        author="Fichero",
    ),
    Action(
        id="builtin-translate",
        name="Translate Text",
        description="Translate text to another language",
        category="transform",
        tags=["text", "translation", "language"],
        icon="globe",
        node_template={
            "type": "llm",
            "data": {
                "prompt": "Translate the following text to {{target_language}}:\n\n{{input}}",
                "model": "default",
            },
        },
        is_builtin=True,
        author="Fichero",
    ),
    Action(
        id="builtin-sentiment",
        name="Analyze Sentiment",
        description="Analyze the sentiment of text content",
        category="analyze",
        tags=["text", "sentiment", "analysis"],
        icon="face.smiling",
        node_template={
            "type": "llm",
            "data": {
                "prompt": "Analyze the sentiment of this text:\n\n{{input}}",
                "model": "default",
            },
        },
        is_builtin=True,
        author="Fichero",
    ),
    Action(
        id="builtin-condition",
        name="Conditional Branch",
        description="Branch workflow based on a condition",
        category="logic",
        tags=["condition", "branch", "logic"],
        icon="arrow.triangle.branch",
        node_template={
            "type": "condition",
            "data": {"condition": "", "true_branch": "then", "false_branch": "else"},
        },
        is_builtin=True,
        author="Fichero",
    ),
]


class ActionStore:
    """Store for managing workflow actions."""

    def __init__(self, db: Database):
        self.db = db
        self._ensure_table()
        self._ensure_builtins()

    def _ensure_table(self) -> None:
        """Ensure the actions table exists."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR DEFAULT '',
                category VARCHAR DEFAULT 'custom',
                tags JSON DEFAULT '[]',
                icon VARCHAR DEFAULT 'square.stack.3d.up',
                node_template JSON DEFAULT '{}',
                nodes JSON DEFAULT '[]',
                edges JSON DEFAULT '[]',
                is_builtin BOOLEAN DEFAULT FALSE,
                is_composite BOOLEAN DEFAULT FALSE,
                author VARCHAR DEFAULT '',
                use_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _ensure_builtins(self) -> None:
        """Ensure built-in actions exist."""
        for action in BUILTIN_ACTIONS:
            if not self.get(action.id):
                self._insert(action)

    def _insert(self, action: Action) -> None:
        """Insert an action."""
        self.db.execute(
            """
            INSERT INTO actions (id, name, description, category, tags, icon,
                node_template, nodes, edges, is_builtin, is_composite,
                author, use_count, last_used_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                action.id,
                action.name,
                action.description,
                action.category,
                json.dumps(action.tags),
                action.icon,
                json.dumps(action.node_template),
                json.dumps(action.nodes),
                json.dumps(action.edges),
                action.is_builtin,
                action.is_composite,
                action.author,
                action.use_count,
                action.last_used_at,
                action.created_at,
                action.updated_at,
            ],
        )

    def _update(self, action: Action) -> None:
        """Update an action."""
        action.updated_at = utc_now()
        self.db.execute(
            """
            UPDATE actions SET name=?, description=?, category=?, tags=?, icon=?,
                node_template=?, nodes=?, edges=?, is_composite=?, author=?,
                use_count=?, last_used_at=?, updated_at=?
            WHERE id=?
        """,
            [
                action.name,
                action.description,
                action.category,
                json.dumps(action.tags),
                action.icon,
                json.dumps(action.node_template),
                json.dumps(action.nodes),
                json.dumps(action.edges),
                action.is_composite,
                action.author,
                action.use_count,
                action.last_used_at,
                action.updated_at,
                action.id,
            ],
        )

    def _row_to_action(self, row: tuple) -> Action:
        """Convert database row to Action."""
        return Action(
            id=row[0],
            name=row[1],
            description=row[2],
            category=row[3],
            tags=json.loads(row[4]) if row[4] else [],
            icon=row[5],
            node_template=json.loads(row[6]) if row[6] else {},
            nodes=json.loads(row[7]) if row[7] else [],
            edges=json.loads(row[8]) if row[8] else [],
            is_builtin=row[9],
            is_composite=row[10],
            author=row[11],
            use_count=row[12],
            # naive stored value IS UTC (#4347)
            last_used_at=ensure_utc(row[13]),
            created_at=ensure_utc(row[14]),
            updated_at=ensure_utc(row[15]),
        )

    def get(self, action_id: str) -> Optional[Action]:
        """Get an action by ID."""
        result = self.db.execute_fetchone(
            "SELECT * FROM actions WHERE id = ?", [action_id]
        )
        return self._row_to_action(result) if result else None

    def save(self, action: Action) -> Action:
        """Save an action."""
        if self.get(action.id):
            self._update(action)
        else:
            self._insert(action)
        return action

    def delete(self, action_id: str) -> bool:
        """Delete an action."""
        action = self.get(action_id)
        if not action or action.is_builtin:
            return False
        self.db.execute("DELETE FROM actions WHERE id = ?", [action_id])
        return True

    def list_all(self) -> list[Action]:
        """List all actions."""
        rows = self.db.execute_fetchall("SELECT * FROM actions ORDER BY name")
        return [self._row_to_action(r) for r in rows]

    def list_builtin(self) -> list[Action]:
        """List built-in actions."""
        rows = self.db.execute_fetchall(
            "SELECT * FROM actions WHERE is_builtin = TRUE ORDER BY name"
        )
        return [self._row_to_action(r) for r in rows]

    def list_custom(self) -> list[Action]:
        """List user-created actions."""
        rows = self.db.execute_fetchall(
            "SELECT * FROM actions WHERE is_builtin = FALSE ORDER BY name"
        )
        return [self._row_to_action(r) for r in rows]

    def list_by_category(self, category: str) -> list[Action]:
        """List actions by category."""
        rows = self.db.execute_fetchall(
            "SELECT * FROM actions WHERE category = ? ORDER BY name", [category]
        )
        return [self._row_to_action(r) for r in rows]

    def list_recent(self, limit: int = 10) -> list[Action]:
        """List recently used actions."""
        rows = self.db.execute_fetchall(
            "SELECT * FROM actions WHERE last_used_at IS NOT NULL ORDER BY last_used_at DESC LIMIT ?",
            [limit],
        )
        return [self._row_to_action(r) for r in rows]

    def list_popular(self, limit: int = 10) -> list[Action]:
        """List most used actions."""
        rows = self.db.execute_fetchall(
            "SELECT * FROM actions ORDER BY use_count DESC LIMIT ?", [limit]
        )
        return [self._row_to_action(r) for r in rows]

    def get_categories(self) -> list[str]:
        """Get all categories."""
        rows = self.db.execute_fetchall(
            "SELECT DISTINCT category FROM actions ORDER BY category"
        )
        return [r[0] for r in rows]

    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[Action]:
        """Search actions."""
        sql = "SELECT * FROM actions WHERE 1=1"
        params = []
        if query:
            sql += " AND (name ILIKE ? OR description ILIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY name"
        rows = self.db.execute_fetchall(sql, params)
        actions = [self._row_to_action(r) for r in rows]
        if tags:
            actions = [a for a in actions if all(t in a.tags for t in tags)]
        return actions

    def record_use(self, action_id: str) -> None:
        """Record action usage."""
        self.db.execute(
            "UPDATE actions SET use_count = use_count + 1, last_used_at = ? WHERE id = ?",
            [utc_now(), action_id],
        )

    def export_action(self, action_id: str) -> str:
        """Export action as JSON."""
        action = self.get(action_id)
        if not action:
            raise ValueError(f"Action not found: {action_id}")
        return action.model_dump_json()

    def import_action(self, json_data: str, new_id: bool = True) -> Action:
        """Import action from JSON."""
        data = json.loads(json_data)
        if new_id:
            data["id"] = str(uuid.uuid4())
        data["is_builtin"] = False
        data["use_count"] = 0
        data["last_used_at"] = None
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        action = Action(**data)
        self.save(action)
        return action

    def create_from_node(
        self,
        name: str,
        node: dict[str, Any],
        description: str = "",
        category: str = "custom",
        tags: list[str] = None,
    ) -> Action:
        """Create action from workflow node."""
        action = Action(
            name=name,
            description=description,
            category=category,
            tags=tags or [],
            node_template=node,
            is_composite=False,
        )
        self.save(action)
        return action

    def create_composite(
        self,
        name: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        description: str = "",
        category: str = "custom",
        tags: list[str] = None,
    ) -> Action:
        """Create composite action from multiple nodes."""
        action = Action(
            name=name,
            description=description,
            category=category,
            tags=tags or [],
            nodes=nodes,
            edges=edges,
            is_composite=True,
        )
        self.save(action)
        return action
