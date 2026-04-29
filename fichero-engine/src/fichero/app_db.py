"""
App-Wide Database

Stores app-level configuration that is shared across all libraries:
- Provider configurations (Anthropic, OpenAI, etc.)
- API keys (stored in Keychain, referenced here)
- App preferences
- User settings

Location: ~/Library/Application Support/com.fichero.fichero/app.duckdb

This is separate from library databases which store:
- Documents, workflows, conversations
- Provider references (which providers this library uses)
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import duckdb
from fichero.storage import settings
from fichero.models import Provider, Model

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Get the path to the app-wide database."""
    return str(settings.app_db_path)


class AppDatabase:
    """App-wide database for providers and settings."""

    def __init__(self, path: str | Path | None = None):
        """
        Initialize app-wide database connection.

        Args:
            path: Path to app database file. Defaults to ~/Library/Application Support/com.fichero.fichero/app.duckdb
        """
        if path is None:
            path = settings.app_db_path
        else:
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = duckdb.connect(str(path))
        # DuckDB connections are not thread-safe and the Python binding leaves a
        # "pending query result" on the connection if a prior `.execute()`
        # didn't have its `.fetchone()` consumed. Under FastAPI's threadpool,
        # concurrent requests using `self.conn` collide and raise
        # `InvalidInputException: Attempting to execute an unsuccessful or
        # closed pending query result`. A reentrant lock around every conn
        # operation serializes access on this single shared connection. (#704
        # follow-up — Daniel logs 2026-04-25.)
        import threading
        self._lock = threading.RLock()

        logger.info(f"Opened app-wide database: {path}")
        self._initialize_schema()

    def _initialize_schema(self):
        """Create tables if they don't exist."""

        # Providers table (app-wide)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                provider_type VARCHAR NOT NULL,
                api_base VARCHAR,
                enabled BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Models table (app-wide, associated with providers)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id VARCHAR PRIMARY KEY,
                provider_id VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                model_id VARCHAR NOT NULL,
                capabilities VARCHAR,
                is_default BOOLEAN DEFAULT FALSE,
                enabled BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                input_cost FLOAT,
                output_cost FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES providers(id)
            )
        """)

        # MCP Servers table (app-wide)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_servers (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL UNIQUE,
                description VARCHAR DEFAULT '',
                transport VARCHAR NOT NULL,
                command VARCHAR,
                args JSON DEFAULT '[]',
                env JSON DEFAULT '{}',
                url VARCHAR,
                headers JSON DEFAULT '{}',
                tool_name_prefix BOOLEAN DEFAULT TRUE,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Settings table (key-value store for app preferences)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR PRIMARY KEY,
                value VARCHAR NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_providers_type ON providers(provider_type)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled)"
        )

        logger.info("App database schema initialized")

    def save_provider(self, provider: Provider) -> Provider:
        """Save or update a provider."""
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO providers (id, name, provider_type, api_base, enabled, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name,
                    provider_type = excluded.provider_type,
                    api_base = excluded.api_base,
                    enabled = excluded.enabled,
                    sort_order = excluded.sort_order,
                    updated_at = excluded.updated_at
            """,
                [
                    provider.id,
                    provider.name,
                    provider.provider_type.value
                    if hasattr(provider.provider_type, "value")
                    else provider.provider_type,
                    provider.api_base,
                    provider.enabled,
                    provider.sort_order,
                    datetime.now(),
                ],
            )
            self.conn.commit()
        return provider

    def get_provider(self, provider_id: str) -> Provider | None:
        """Get a provider by ID."""
        from fichero.models import ProviderType

        with self._lock:
            result = self.conn.execute(
                "SELECT * FROM providers WHERE id = ?", [provider_id]
            ).fetchone()

        if not result:
            return None

        return Provider(
            id=result[0],
            name=result[1],
            provider_type=ProviderType(result[2]),
            api_base=result[3],
            enabled=result[4],
            sort_order=result[5],
            created_at=result[6],
            updated_at=result[7],
        )

    def list_providers(self) -> list[Provider]:
        """List all providers."""
        from fichero.models import ProviderType

        with self._lock:
            results = self.conn.execute(
                "SELECT * FROM providers ORDER BY sort_order, created_at"
            ).fetchall()

        return [
            Provider(
                id=row[0],
                name=row[1],
                provider_type=ProviderType(row[2]),
                api_base=row[3],
                enabled=row[4],
                sort_order=row[5],
                created_at=row[6],
                updated_at=row[7],
            )
            for row in results
        ]

    def delete_provider(self, provider_id: str):
        """Delete a provider and its associated models."""
        with self._lock:
            self.conn.execute("DELETE FROM models WHERE provider_id = ?", [provider_id])
            self.conn.execute("DELETE FROM providers WHERE id = ?", [provider_id])
            self.conn.commit()

    def save_model(self, model: Model) -> Model:
        """Save or update a model."""



        capabilities_json = (
            json.dumps(model.capabilities) if model.capabilities else "[]"
        )

        self.conn.execute(
            """
            INSERT INTO models (
                id, provider_id, name, model_id, capabilities,
                is_default, enabled, sort_order, input_cost, output_cost, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                provider_id = excluded.provider_id,
                name = excluded.name,
                model_id = excluded.model_id,
                capabilities = excluded.capabilities,
                is_default = excluded.is_default,
                enabled = excluded.enabled,
                sort_order = excluded.sort_order,
                input_cost = excluded.input_cost,
                output_cost = excluded.output_cost,
                updated_at = excluded.updated_at
        """,
            [
                model.id,
                model.provider_id,
                model.name,
                model.model_id,
                capabilities_json,
                model.is_default,
                model.enabled,
                model.sort_order,
                model.input_cost,
                model.output_cost,
                datetime.now(),
            ],
        )
        self.conn.commit()
        return model

    def list_models(self, provider_id: str | None = None) -> list[Model]:
        """List models, optionally filtered by provider."""
        with self._lock:
            if provider_id:
                results = self.conn.execute(
                    "SELECT * FROM models WHERE provider_id = ? ORDER BY sort_order, name",
                    [provider_id],
                ).fetchall()
            else:
                results = self.conn.execute(
                    "SELECT * FROM models ORDER BY sort_order, name"
                ).fetchall()

        return [
            Model(
                id=row[0],
                provider_id=row[1],
                name=row[2],
                model_id=row[3],
                capabilities=json.loads(row[4]) if row[4] else [],
                is_default=row[5],
                enabled=row[6],
                sort_order=row[7],
                input_cost=row[8],
                output_cost=row[9],
                created_at=row[10],
                updated_at=row[11],
            )
            for row in results
        ]

    def get_default_model(self) -> tuple[str, str] | None:
        """Get the default provider and model.

        Checks category defaults first (text), then falls back to
        the legacy is_default column on models table.

        Returns:
            Tuple of (provider_type, model_id) or None if no default is set.
        """
        # Try text default from settings table first
        cat_default = self.get_default_model_for_category("llm")
        if cat_default:
            return cat_default

        # Legacy fallback: check is_default column on models table
        result = self.conn.execute("""
            SELECT p.provider_type, m.model_id
            FROM models m
            JOIN providers p ON m.provider_id = p.id
            WHERE m.is_default = TRUE AND m.enabled = TRUE AND p.enabled = TRUE
            ORDER BY m.updated_at DESC
            LIMIT 1
        """).fetchone()

        if result:
            return (result[0], result[1])
        return None

    # =========================================================================
    # Settings (key-value store)
    # =========================================================================

    def get_setting(self, key: str) -> str | None:
        """Get a setting value by key."""
        result = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", [key]
        ).fetchone()
        return result[0] if result else None

    def set_setting(self, key: str, value: str):
        """Set a setting value (upsert)."""


        now = datetime.now()
        self.conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """,
            [key, value, now],
        )
        self.conn.commit()

    def delete_setting(self, key: str):
        """Delete a setting."""
        self.conn.execute("DELETE FROM settings WHERE key = ?", [key])
        self.conn.commit()

    def get_ai_defaults(self) -> dict[str, str]:
        """Get all AI default settings as a dict."""
        keys = [
            "default_vision_provider",
            "default_vision_model",
            "default_text_provider",
            "default_text_model",
            "default_audio_provider",
            "default_audio_model",
            "default_video_provider",
            "default_video_model",
            "default_embeddings_provider",
            "default_embeddings_model",
            "default_temperature",
            "default_max_tokens",
            "default_prompt_prefix",
        ]
        result = {}
        for key in keys:
            val = self.get_setting(key)
            if val:
                result[key] = val
        return result

    def get_default_model_for_category(self, category: str) -> tuple[str, str] | None:
        """Get default (provider_type, model_id) for a tool category.

        Category mapping:
        - "vision" -> default_vision_provider / default_vision_model
        - "llm"    -> default_text_provider / default_text_model
        - "audio"  -> default_audio_provider / default_audio_model
        - "video"  -> default_video_provider / default_video_model

        Returns:
            Tuple of (provider_type, model_id) or None if not configured.
        """
        cat_map = {
            "vision": "vision",
            "llm": "text",
            "audio": "audio",
            "video": "video",
        }
        prefix = cat_map.get(category)
        if not prefix:
            return None
        provider = self.get_setting(f"default_{prefix}_provider")
        model = self.get_setting(f"default_{prefix}_model")
        if provider and model:
            return (provider, model)
        return None

    def reset_ai_defaults(self):
        """Delete all AI default settings."""
        keys = [
            "default_vision_provider",
            "default_vision_model",
            "default_text_provider",
            "default_text_model",
            "default_audio_provider",
            "default_audio_model",
            "default_video_provider",
            "default_video_model",
            "default_embeddings_provider",
            "default_embeddings_model",
            "default_temperature",
            "default_max_tokens",
            "default_prompt_prefix",
        ]
        for key in keys:
            self.delete_setting(key)

    def delete_model(self, model_id: str):
        """Delete a model."""
        self.conn.execute("DELETE FROM models WHERE id = ?", [model_id])
        self.conn.commit()

    def save_mcp_server(self, server):
        """Save or update an MCP server."""



        self.conn.execute(
            """
            INSERT INTO mcp_servers (
                id, name, description, transport, command, args, env,
                url, headers, tool_name_prefix, enabled, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                transport = excluded.transport,
                command = excluded.command,
                args = excluded.args,
                env = excluded.env,
                url = excluded.url,
                headers = excluded.headers,
                tool_name_prefix = excluded.tool_name_prefix,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
        """,
            [
                server.id,
                server.name,
                server.description,
                server.transport,
                server.command,
                json.dumps(server.args),
                json.dumps(server.env),
                server.url,
                json.dumps(server.headers),
                server.tool_name_prefix,
                server.enabled,
                datetime.now(),
            ],
        )
        self.conn.commit()
        return server

    def get_mcp_server(self, server_id: str):
        """Get an MCP server by ID."""

        from fichero.models import MCPServer

        result = self.conn.execute(
            "SELECT * FROM mcp_servers WHERE id = ?", [server_id]
        ).fetchone()

        if not result:
            return None

        return MCPServer(
            id=result[0],
            name=result[1],
            description=result[2],
            transport=result[3],
            command=result[4],
            args=json.loads(result[5]) if result[5] else [],
            env=json.loads(result[6]) if result[6] else {},
            url=result[7],
            headers=json.loads(result[8]) if result[8] else {},
            tool_name_prefix=result[9],
            enabled=result[10],
            created_at=result[11],
            updated_at=result[12],
        )

    def query_mcp_servers(self, **filters):
        """Query MCP servers with optional filters."""

        from fichero.models import MCPServer

        # Build WHERE clause from filters
        where_clauses = []
        params = []
        for key, value in filters.items():
            where_clauses.append(f"{key} = ?")
            params.append(value)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        results = self.conn.execute(
            f"SELECT * FROM mcp_servers {where_sql} ORDER BY name", params
        ).fetchall()

        servers = []
        for row in results:
            servers.append(
                MCPServer(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    transport=row[3],
                    command=row[4],
                    args=json.loads(row[5]) if row[5] else [],
                    env=json.loads(row[6]) if row[6] else {},
                    url=row[7],
                    headers=json.loads(row[8]) if row[8] else {},
                    tool_name_prefix=row[9],
                    enabled=row[10],
                    created_at=row[11],
                    updated_at=row[12],
                )
            )

        return servers

    def delete_mcp_server(self, server_id: str):
        """Delete an MCP server."""
        self.conn.execute("DELETE FROM mcp_servers WHERE id = ?", [server_id])
        self.conn.commit()

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("App database connection closed")


# Global app database instance
_app_db: AppDatabase | None = None


def get_app_db() -> AppDatabase:
    """Get or create the global app database instance."""
    global _app_db
    if _app_db is None:
        _app_db = AppDatabase()
    return _app_db
