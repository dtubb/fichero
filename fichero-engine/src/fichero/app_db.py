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
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from pydantic import BaseModel
from fichero.storage import settings
from fichero.models import (
    ActionAudit,
    AccountInvite,
    AccountSession,
    AccountUser,
    Device,
    LibraryAclOverride,
    LibraryRole,
    Model,
    Provider,
)
from fichero.model_profiles import (
    ModelProfile,
    ModelProfileParams,
    ModelProfilePrivacy,
    ModelProfileRole,
)

logger = logging.getLogger(__name__)


class AppSetting(BaseModel):
    """Typed row wrapper for settings-table write paths."""

    key: str
    value: str
    updated_at: datetime


def get_db_path() -> str:
    """Get the path to the app-wide database."""
    return str(settings.app_db_path)


class AppDatabase:
    """App-wide database for providers and settings."""
    _TABLE_BY_MODEL_NAME: dict[str, str] = {
        "ActionAudit": "actionaudits",
        "AccountInvite": "invites",
        "AccountUser": "users",
        "AccountSession": "sessions",
        "Device": "devices",
        "LibraryRole": "library_roles",
        "LibraryAclOverride": "library_acl_overrides",
        "Provider": "providers",
        "Model": "models",
        "ModelProfile": "model_profiles",
        "MCPServer": "mcp_servers",
        "AppSetting": "settings",
    }

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

    def commit(self) -> None:
        """Commit pending app-wide database work through the typed wrapper."""
        with self._lock:
            self.conn.commit()

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

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS actionaudits (
                id VARCHAR PRIMARY KEY,
                action_name VARCHAR NOT NULL,
                actor VARCHAR NOT NULL,
                target_ids JSON DEFAULT '[]',
                params JSON DEFAULT '{}',
                before JSON,
                after JSON,
                run_id VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                chain_seq BIGINT,
                undone BOOLEAN DEFAULT FALSE,
                inverse_of VARCHAR,
                prev_hash VARCHAR,
                row_hash VARCHAR DEFAULT ''
            )
        """)

        # Named AI model/provider profiles (app-wide)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS model_profiles (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL UNIQUE,
                provider VARCHAR NOT NULL,
                model VARCHAR NOT NULL,
                role VARCHAR NOT NULL DEFAULT 'text',
                privacy VARCHAR NOT NULL DEFAULT 'standard',
                local_only BOOLEAN DEFAULT FALSE,
                temperature DOUBLE,
                max_tokens INTEGER,
                timeout INTEGER,
                reasoning_effort VARCHAR,
                api_base VARCHAR,
                extra JSON DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Users table (app-wide identity directory)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR PRIMARY KEY,
                username VARCHAR NOT NULL UNIQUE,
                display_name VARCHAR NOT NULL,
                password_hash VARCHAR NOT NULL,
                is_owner BOOLEAN DEFAULT FALSE,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sessions table (app-wide session store)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                token_hash VARCHAR NOT NULL UNIQUE,
                device_label VARCHAR DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                revoked BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id VARCHAR PRIMARY KEY,
                username VARCHAR NOT NULL,
                display_name VARCHAR NOT NULL,
                token_hash VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                consumed_at TIMESTAMP,
                revoked BOOLEAN DEFAULT FALSE
            )
        """)

        # Devices table (app-wide paired-device token store)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                user_id VARCHAR NOT NULL,
                token_hash VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                revoked BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Migration: app.duckdb persists across versions, so `CREATE TABLE IF NOT
        # EXISTS` will NOT add a new column to a devices table created before
        # expires_at existed (#2173). Add it idempotently and backfill existing
        # paired devices with a finite TTL derived from their creation time so the
        # NOT-NULL invariant of fresh schemas is preserved for migrated rows.
        _device_cols = {
            row[1] for row in self.conn.execute("PRAGMA table_info(devices)").fetchall()
        }
        if "expires_at" not in _device_cols:
            self.conn.execute("ALTER TABLE devices ADD COLUMN expires_at TIMESTAMP")
            self.conn.execute(
                "UPDATE devices SET expires_at = created_at + INTERVAL 90 DAY "
                "WHERE expires_at IS NULL"
            )
            # Flush the DDL into the main DB file immediately. DuckDB cannot
            # REPLAY an ALTER ... ADD COLUMN from the WAL on recovery (internal
            # error "GetDefaultDatabase with no default database set"), so if the
            # process dies before the next checkpoint the WAL is poisoned and every
            # restart crashes natively. CHECKPOINT here keeps the migration durable
            # and out of the recovery WAL. See app-db migration incident 2026-06-12.
            self.conn.execute("CHECKPOINT")

        # Per-library ACL tables (global identity scope, not per-library DB).
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS library_roles (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                library_path VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, library_path),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS library_acl_overrides (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                library_path VARCHAR NOT NULL,
                target_id VARCHAR NOT NULL,
                effect VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, library_path, target_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
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
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actionaudits_created_at "
            "ON actionaudits(created_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_profiles_name ON model_profiles(name)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_owner ON users(is_owner, active)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invites_username ON invites(username)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invites_expires_at ON invites(expires_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_devices_token_hash ON devices(token_hash)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_devices_expires_at ON devices(expires_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_roles_user_library "
            "ON library_roles(user_id, library_path)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_roles_library "
            "ON library_roles(library_path)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_acl_overrides_user_library "
            "ON library_acl_overrides(user_id, library_path)"
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
            for model in self.list_models(provider_id=provider_id):
                self._delete_typed(model)

            provider = self.get_provider(provider_id)
            if provider:
                self._delete_typed(provider)
            self.conn.commit()

    def get_model(self, model_id: str) -> Model | None:
        """Get a model by ID."""
        from fichero.models import Model

        with self._lock:
            result = self.conn.execute(
                "SELECT * FROM models WHERE id = ?", [model_id]
            ).fetchone()

        if not result:
            return None

        return Model(
            id=result[0],
            provider_id=result[1],
            name=result[2],
            model_id=result[3],
            capabilities=json.loads(result[4]) if result[4] else [],
            is_default=result[5],
            enabled=result[6],
            sort_order=result[7],
            input_cost=result[8],
            output_cost=result[9],
            created_at=result[10],
            updated_at=result[11],
        )

    def reparent_model(self, model_id: str, new_provider_id: str) -> Model | None:
        """Re-parent a model to a different provider. Used during provider dedup collapse."""
        with self._lock:
            self.conn.execute(
                "UPDATE models SET provider_id = ? WHERE id = ?",
                [new_provider_id, model_id],
            )
            self.conn.commit()
        return self.get_model(model_id)

    def save_model(self, model: Model) -> Model:
        """Save or update a model.

        Idempotent on (provider_id, model_id) — adding a model whose
        model_id already exists on the same provider updates the
        existing row instead of inserting a duplicate. Pre-fix, the
        UI's '+ Add Model' button on Settings → Providers could add
        the same Apple Vision row N times because conflict resolution
        was only keyed on `id` (the row primary key, which is fresh
        per add). Daniel hit this in #937.
        """
        # Check (provider_id, model_id) for an existing row. If found
        # and it's NOT the same id we're trying to write, redirect the
        # write to update that existing id — preserving its history
        # (created_at, sort_order, etc.) while accepting the caller's
        # name + capabilities + flags. (#937)
        #
        # When the caller's capabilities list is empty but the existing
        # row has caps, preserve the existing caps. This guards against
        # a UI that calls save_model without setting capabilities
        # (e.g. the +Add Model button on Settings → Providers) wiping
        # the badges that the seeded row or a prior save established.
        # (#939 follow-up — the providers route now sets canonical caps
        # for known model_ids; this is the belt-and-braces.)
        with self._lock:
            existing_row = self.conn.execute(
                "SELECT id, capabilities FROM models WHERE provider_id = ? AND model_id = ?",
                [model.provider_id, model.model_id],
            ).fetchone()
            if existing_row and existing_row[0] != model.id:
                model = model.model_copy(update={"id": existing_row[0]})
            if existing_row and not (model.capabilities or []):
                # Preserve the existing caps when the incoming model
                # didn't carry any. \\\`capabilities\\\` is stored as a JSON
                # text column; decode it back to a list for the model
                # field. Falls back to [] on any decode error.
                try:
                    existing_caps = json.loads(existing_row[1] or "[]")
                    if isinstance(existing_caps, list) and existing_caps:
                        model = model.model_copy(update={"capabilities": existing_caps})
                except (json.JSONDecodeError, TypeError):
                    pass

            # Compute capabilities_json AFTER the preservation pass so
            # the JSON reflects the final model.capabilities (which may
            # have been re-hydrated from the existing row above).
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
        with self._lock:
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
        with self._lock:
            result = self.conn.execute(
                "SELECT value FROM settings WHERE key = ?", [key]
            ).fetchone()
        return result[0] if result else None

    def set_setting(self, key: str, value: str):
        """Set a setting value (upsert)."""


        now = datetime.now()
        with self._lock:
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
        value = self.get_setting(key)
        if value is None:
            return
        self._delete_typed(
            AppSetting(key=key, value=value, updated_at=datetime.now()),
            key_field="key",
            table_name="settings",
        )
        self.conn.commit()

    def get_ai_defaults(self) -> dict[str, str]:
        """Get all AI default settings as a dict.

        Use one set-based query rather than N per-key lookups so reads
        remain stable under concurrent workflow/API traffic.
        """
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
            "default_small_provider",
            "default_small_model",
            "default_medium_provider",
            "default_medium_model",
            "default_large_provider",
            "default_large_model",
            "default_vision_small_provider",
            "default_vision_small_model",
            "default_vision_medium_provider",
            "default_vision_medium_model",
            "default_vision_large_provider",
            "default_vision_large_model",
            "default_primary_language",
            "default_temperature",
            "default_max_tokens",
            "default_prompt_prefix",
        ]
        placeholders = ",".join(["?"] * len(keys))
        with self._lock:
            rows = self.conn.execute(
                f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
                keys,
            ).fetchall()
        return {key: value for key, value in rows if value}

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
        """Reset AI defaults to factory values.

        Pre-fix this just deleted every default_* key, leaving the user
        with blank AI Defaults until the next engine launch re-ran
        bootstrap. Between reset and restart the Catalogue workflow
        would fail with the first-run "no $small model" error (#932
        reprise). Now we delete the bag and immediately re-seed
        with the Apple Intelligence factory baseline, so 'Reset' really
        means 'back to defaults' rather than 'empty everything.'

        Scope guarantee (#933): touches ONLY the default_* setting keys.
        Never modifies the providers or models tables — those have
        their own reset surface (per-screen \"Reset Providers and
        Models\" button — separate feature when shipped).
        """
        keys_to_delete = [
            "default_vision_provider", "default_vision_model",
            "default_text_provider", "default_text_model",
            "default_audio_provider", "default_audio_model",
            "default_video_provider", "default_video_model",
            "default_embeddings_provider", "default_embeddings_model",
            "default_small_provider", "default_small_model",
            "default_medium_provider", "default_medium_model",
            "default_large_provider", "default_large_model",
            "default_vision_small_provider", "default_vision_small_model",
            "default_vision_medium_provider", "default_vision_medium_model",
            "default_vision_large_provider", "default_vision_large_model",
            "default_primary_language",
            "default_temperature", "default_max_tokens", "default_prompt_prefix",
        ]
        for key in keys_to_delete:
            self.delete_setting(key)

        # Re-seed with the factory baseline matching
        # what _ensure_default_ai_defaults() writes on first launch
        # (see api/main.py). Kept in lockstep with that bootstrap; if
        # bootstrap's pairs change, update both. $small stays free and
        # on-device; $medium is a capable low-cost OpenRouter cloud model
        # for structured fallback before any local $large retry (#1308).
        apple = "apple"
        factory_defaults = {
            "default_text_provider": apple, "default_text_model": "apple-intelligence",
            "default_small_provider": apple, "default_small_model": "apple-intelligence",
            "default_medium_provider": "openrouter", "default_medium_model": "openai/gpt-4o-mini",
            "default_large_provider": apple, "default_large_model": "apple-intelligence",
            "default_vision_provider": apple, "default_vision_model": "apple-vision",
            "default_vision_small_provider": apple, "default_vision_small_model": "apple-vision",
            "default_vision_medium_provider": apple, "default_vision_medium_model": "apple-vision",
            "default_vision_large_provider": apple, "default_vision_large_model": "apple-vision",
            "default_audio_provider": apple, "default_audio_model": "apple-speech",
        }
        for key, value in factory_defaults.items():
            self.set_setting(key, value)

    # =========================================================================
    # Model Profiles
    # =========================================================================

    def _row_to_model_profile(self, row) -> ModelProfile:
        params = ModelProfileParams(
            temperature=row[7],
            max_tokens=row[8],
            timeout=row[9],
            reasoning_effort=row[10],
        )
        try:
            extra = json.loads(row[12] or "{}")
        except (json.JSONDecodeError, TypeError):
            extra = {}
        if not isinstance(extra, dict):
            extra = {}
        return ModelProfile(
            id=row[0],
            name=row[1],
            provider=row[2],
            model=row[3],
            role=ModelProfileRole(row[4]),
            privacy=ModelProfilePrivacy(row[5]),
            local_only=bool(row[6]),
            params=params,
            api_base=row[11],
            extra=extra,
            created_at=row[13],
            updated_at=row[14],
        )

    def save_model_profile(self, profile: ModelProfile) -> ModelProfile:
        """Save or update a named model/provider profile."""
        now = datetime.now()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO model_profiles (
                    id, name, provider, model, role, privacy, local_only,
                    temperature, max_tokens, timeout, reasoning_effort,
                    api_base, extra, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name,
                    provider = excluded.provider,
                    model = excluded.model,
                    role = excluded.role,
                    privacy = excluded.privacy,
                    local_only = excluded.local_only,
                    temperature = excluded.temperature,
                    max_tokens = excluded.max_tokens,
                    timeout = excluded.timeout,
                    reasoning_effort = excluded.reasoning_effort,
                    api_base = excluded.api_base,
                    extra = excluded.extra,
                    updated_at = excluded.updated_at
            """,
                [
                    profile.id,
                    profile.name,
                    profile.provider,
                    profile.model,
                    profile.role.value,
                    profile.privacy.value,
                    profile.local_only,
                    profile.params.temperature,
                    profile.params.max_tokens,
                    profile.params.timeout,
                    profile.params.reasoning_effort,
                    profile.api_base,
                    json.dumps(profile.extra or {}),
                    now,
                ],
            )
            self.conn.commit()
        return profile.model_copy(update={"updated_at": now})

    def get_model_profile(self, profile_id: str) -> ModelProfile | None:
        """Get a model profile by id."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM model_profiles WHERE id = ?", [profile_id]
            ).fetchone()
        return self._row_to_model_profile(row) if row else None

    def get_model_profile_by_name(self, name: str) -> ModelProfile | None:
        """Get a model profile by exact display name."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM model_profiles WHERE name = ?", [name]
            ).fetchone()
        return self._row_to_model_profile(row) if row else None

    def list_model_profiles(self) -> list[ModelProfile]:
        """List named model profiles in stable display order."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM model_profiles ORDER BY name, created_at"
            ).fetchall()
        return [self._row_to_model_profile(row) for row in rows]

    def delete_model_profile(self, profile_id: str) -> ModelProfile | None:
        """Delete a model profile by id."""
        profile = self.get_model_profile(profile_id)
        if profile is None:
            return None
        with self._lock:
            self._delete_typed(profile)
            self.conn.commit()
        return profile

    # =========================================================================
    # Users and sessions
    # =========================================================================

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password_hash: str,
        is_owner: bool = False,
        active: bool = True,
    ) -> AccountUser:
        """Insert a new user row and return the typed record."""
        user = AccountUser(
            username=username.strip(),
            display_name=display_name.strip(),
            password_hash=password_hash,
            is_owner=is_owner,
            active=active,
        )
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO users (
                    id, username, display_name, password_hash,
                    is_owner, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    user.id,
                    user.username,
                    user.display_name,
                    user.password_hash,
                    user.is_owner,
                    user.active,
                    user.created_at,
                ],
            )
            self.conn.commit()
        return user

    def _row_to_user(self, row) -> AccountUser:
        return AccountUser(
            id=row[0],
            username=row[1],
            display_name=row[2],
            password_hash=row[3],
            is_owner=row[4],
            active=row[5],
            created_at=row[6],
        )

    def get_user_by_username(self, username: str) -> AccountUser | None:
        """Get a user row by username."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, username, display_name, password_hash,
                       is_owner, active, created_at
                FROM users
                WHERE username = ?
                """,
                [username.strip()],
            ).fetchone()
        return self._row_to_user(result) if result else None

    def get_user(self, user_id: str) -> AccountUser | None:
        """Get a user by ID."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, username, display_name, password_hash,
                       is_owner, active, created_at
                FROM users
                WHERE id = ?
                """,
                [user_id],
            ).fetchone()
        return self._row_to_user(result) if result else None

    def list_users(self) -> list[AccountUser]:
        """List all users, owner-first."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, username, display_name, password_hash,
                       is_owner, active, created_at
                FROM users
                ORDER BY is_owner DESC, created_at, username
                """
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def set_password(self, user_id: str, password_hash: str) -> AccountUser | None:
        """Update a user's password hash."""
        with self._lock:
            self.conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                [password_hash, user_id],
            )
            self.conn.commit()
        return self.get_user(user_id)

    def set_active(self, user_id: str, active: bool) -> AccountUser | None:
        """Enable or disable a user."""
        with self._lock:
            # DuckDB rejects UPDATEs to referenced user rows even when the
            # primary key stays the same, so temporarily drop ACL references
            # and restore them around the flag flip.
            role_rows = self.conn.execute(
                """
                SELECT id, user_id, library_path, role, created_at, updated_at
                FROM library_roles
                WHERE user_id = ?
                ORDER BY created_at, library_path
                """,
                [user_id],
            ).fetchall()
            override_rows = self.conn.execute(
                """
                SELECT id, user_id, library_path, target_id, effect, created_at, updated_at
                FROM library_acl_overrides
                WHERE user_id = ?
                ORDER BY created_at, library_path, target_id
                """,
                [user_id],
            ).fetchall()
            self.conn.execute(
                "DELETE FROM library_acl_overrides WHERE user_id = ?",
                [user_id],
            )
            self.conn.execute(
                "DELETE FROM library_roles WHERE user_id = ?",
                [user_id],
            )
            self.conn.execute(
                "UPDATE users SET active = ? WHERE id = ?",
                [active, user_id],
            )
            if role_rows:
                self.conn.executemany(
                    """
                    INSERT INTO library_roles (
                        id, user_id, library_path, role, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    role_rows,
                )
            if override_rows:
                self.conn.executemany(
                    """
                    INSERT INTO library_acl_overrides (
                        id, user_id, library_path, target_id, effect, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    override_rows,
                )
            self.conn.commit()
        return self.get_user(user_id)

    # =========================================================================
    # Library ACLs
    # =========================================================================

    def _row_to_library_role(self, row) -> LibraryRole:
        return LibraryRole(
            id=row[0],
            user_id=row[1],
            library_path=row[2],
            role=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def _row_to_library_acl_override(self, row) -> LibraryAclOverride:
        return LibraryAclOverride(
            id=row[0],
            user_id=row[1],
            library_path=row[2],
            target_id=row[3],
            effect=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    def set_library_role(
        self,
        *,
        user_id: str,
        library_path: str,
        role: str,
    ) -> LibraryRole:
        """Create or update a user's role for one library."""
        now = datetime.now()
        existing = self.get_library_role(user_id, library_path)
        row = LibraryRole(
            user_id=user_id,
            library_path=library_path,
            role=role,
            updated_at=now,
        )
        if existing:
            row.id = existing.id
            row.created_at = existing.created_at
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO library_roles (
                    id, user_id, library_path, role, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, library_path) DO UPDATE SET
                    role = excluded.role,
                    updated_at = excluded.updated_at
                """,
                [
                    row.id,
                    row.user_id,
                    row.library_path,
                    row.role,
                    row.created_at,
                    row.updated_at,
                ],
            )
            self.conn.commit()
        return self.get_library_role(user_id, library_path) or row

    def get_library_role(
        self, user_id: str, library_path: str
    ) -> LibraryRole | None:
        """Return a user's role for one library."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, user_id, library_path, role, created_at, updated_at
                FROM library_roles
                WHERE user_id = ? AND library_path = ?
                """,
                [user_id, library_path],
            ).fetchone()
        return self._row_to_library_role(result) if result else None

    def list_library_roles(self, library_path: str) -> list[LibraryRole]:
        """Return all roles for a library."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, user_id, library_path, role, created_at, updated_at
                FROM library_roles
                WHERE library_path = ?
                ORDER BY created_at, user_id
                """,
                [library_path],
            ).fetchall()
        return [self._row_to_library_role(row) for row in rows]

    def list_library_roles_for_user(self, user_id: str) -> list[LibraryRole]:
        """Return all whole-library roles for one user."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, user_id, library_path, role, created_at, updated_at
                FROM library_roles
                WHERE user_id = ?
                ORDER BY created_at, library_path
                """,
                [user_id],
            ).fetchall()
        return [self._row_to_library_role(row) for row in rows]

    def delete_library_role(self, user_id: str, library_path: str) -> None:
        """Remove a user's role for one library (revoke). Idempotent."""
        with self._lock:
            self.conn.execute(
                "DELETE FROM library_roles WHERE user_id = ? AND library_path = ?",
                [user_id, library_path],
            )
            self.conn.commit()

    def set_library_acl_override(
        self,
        *,
        user_id: str,
        library_path: str,
        target_id: str,
        effect: str,
    ) -> LibraryAclOverride:
        """Create or update a grant/deny override for one target subtree."""
        now = datetime.now()
        existing = self.get_library_acl_override(user_id, library_path, target_id)
        row = LibraryAclOverride(
            user_id=user_id,
            library_path=library_path,
            target_id=target_id,
            effect=effect,
            updated_at=now,
        )
        if existing:
            row.id = existing.id
            row.created_at = existing.created_at
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO library_acl_overrides (
                    id, user_id, library_path, target_id, effect, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, library_path, target_id) DO UPDATE SET
                    effect = excluded.effect,
                    updated_at = excluded.updated_at
                """,
                [
                    row.id,
                    row.user_id,
                    row.library_path,
                    row.target_id,
                    row.effect,
                    row.created_at,
                    row.updated_at,
                ],
            )
            self.conn.commit()
        return self.get_library_acl_override(user_id, library_path, target_id) or row

    def get_library_acl_override(
        self, user_id: str, library_path: str, target_id: str
    ) -> LibraryAclOverride | None:
        """Return one exact-target ACL override, if any."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, user_id, library_path, target_id, effect, created_at, updated_at
                FROM library_acl_overrides
                WHERE user_id = ? AND library_path = ? AND target_id = ?
                """,
                [user_id, library_path, target_id],
            ).fetchone()
        return self._row_to_library_acl_override(result) if result else None

    def list_library_acl_overrides(
        self, user_id: str, library_path: str
    ) -> list[LibraryAclOverride]:
        """Return a user's target overrides for one library."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, user_id, library_path, target_id, effect, created_at, updated_at
                FROM library_acl_overrides
                WHERE user_id = ? AND library_path = ?
                ORDER BY created_at, target_id
                """,
                [user_id, library_path],
            ).fetchall()
        return [self._row_to_library_acl_override(row) for row in rows]

    def create_session(
        self,
        user_id: str,
        token_hash: str,
        device_label: str | None,
        ttl: timedelta,
    ) -> AccountSession:
        """Insert a new session row and return the typed record."""
        now = datetime.now()
        session = AccountSession(
            user_id=user_id,
            token_hash=token_hash,
            device_label=(device_label or "").strip(),
            created_at=now,
            last_seen_at=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO sessions (
                    id, user_id, token_hash, device_label,
                    created_at, last_seen_at, expires_at, revoked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    session.id,
                    session.user_id,
                    session.token_hash,
                    session.device_label,
                    session.created_at,
                    session.last_seen_at,
                    session.expires_at,
                    session.revoked,
                ],
            )
            self.conn.commit()
        return session

    def _row_to_session(self, row) -> AccountSession:
        return AccountSession(
            id=row[0],
            user_id=row[1],
            token_hash=row[2],
            device_label=row[3] or "",
            created_at=row[4],
            last_seen_at=row[5],
            expires_at=row[6],
            revoked=row[7],
        )

    def get_session_by_token_hash(self, token_hash: str) -> AccountSession | None:
        """Get a session by its stored token hash."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, user_id, token_hash, device_label,
                       created_at, last_seen_at, expires_at, revoked
                FROM sessions
                WHERE token_hash = ?
                """,
                [token_hash],
            ).fetchone()
        return self._row_to_session(result) if result else None

    def get_session(self, session_id: str) -> AccountSession | None:
        """Get a session by its row id."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, user_id, token_hash, device_label,
                       created_at, last_seen_at, expires_at, revoked
                FROM sessions
                WHERE id = ?
                """,
                [session_id],
            ).fetchone()
        return self._row_to_session(result) if result else None

    def list_sessions(self, user_id: str | None = None) -> list[AccountSession]:
        """List active sessions, optionally scoped to one user."""
        now = datetime.now()
        with self._lock:
            if user_id is None:
                rows = self.conn.execute(
                    """
                    SELECT id, user_id, token_hash, device_label,
                           created_at, last_seen_at, expires_at, revoked
                    FROM sessions
                    WHERE revoked = FALSE AND expires_at > ?
                    ORDER BY last_seen_at DESC, created_at DESC
                    """,
                    [now],
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT id, user_id, token_hash, device_label,
                           created_at, last_seen_at, expires_at, revoked
                    FROM sessions
                    WHERE user_id = ? AND revoked = FALSE AND expires_at > ?
                    ORDER BY last_seen_at DESC, created_at DESC
                    """,
                    [user_id, now],
                ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def touch_session(
        self,
        token_hash: str,
        when: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        """Update the last-seen timestamp for a session."""
        now = when or datetime.now()
        with self._lock:
            if expires_at is None:
                self.conn.execute(
                    "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
                    [now, token_hash],
                )
            else:
                self.conn.execute(
                    "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
                    [now, expires_at, token_hash],
                )
            self.conn.commit()
        return None

    def revoke_session(self, token_hash: str) -> AccountSession | None:
        """Mark one session as revoked."""
        with self._lock:
            self.conn.execute(
                "UPDATE sessions SET revoked = TRUE WHERE token_hash = ?",
                [token_hash],
            )
            self.conn.commit()
        return self.get_session_by_token_hash(token_hash)

    def revoke_session_by_id(self, session_id: str) -> AccountSession | None:
        """Mark one session as revoked by row id."""
        with self._lock:
            self.conn.execute(
                "UPDATE sessions SET revoked = TRUE WHERE id = ?",
                [session_id],
            )
            self.conn.commit()
        return self.get_session(session_id)

    def revoke_all_for_user(self, user_id: str) -> None:
        """Drop all session rows for one user."""
        with self._lock:
            self.conn.execute(
                "DELETE FROM sessions WHERE user_id = ?",
                [user_id],
            )
            self.conn.commit()

    def revoke_all_devices_for_user(self, user_id: str) -> None:
        """Drop all paired-device rows for one user."""
        with self._lock:
            self.conn.execute(
                "DELETE FROM devices WHERE user_id = ?",
                [user_id],
            )
            self.conn.commit()

    # =========================================================================
    # Invites
    # =========================================================================

    def create_invite(
        self,
        *,
        username: str,
        display_name: str,
        token_hash: str,
        ttl: timedelta,
    ) -> AccountInvite:
        """Insert a new invite row and return the typed record."""
        now = datetime.now()
        invite = AccountInvite(
            username=username.strip(),
            display_name=display_name.strip(),
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO invites (
                    id, username, display_name, token_hash,
                    created_at, expires_at, consumed_at, revoked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    invite.id,
                    invite.username,
                    invite.display_name,
                    invite.token_hash,
                    invite.created_at,
                    invite.expires_at,
                    invite.consumed_at,
                    invite.revoked,
                ],
            )
            self.conn.commit()
        return invite

    def _row_to_invite(self, row) -> AccountInvite:
        return AccountInvite(
            id=row[0],
            username=row[1],
            display_name=row[2],
            token_hash=row[3],
            created_at=row[4],
            expires_at=row[5],
            consumed_at=row[6],
            revoked=row[7],
        )

    def get_invite(self, invite_id: str) -> AccountInvite | None:
        """Get an invite by row id."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, username, display_name, token_hash,
                       created_at, expires_at, consumed_at, revoked
                FROM invites
                WHERE id = ?
                """,
                [invite_id],
            ).fetchone()
        return self._row_to_invite(result) if result else None

    def get_invite_by_token_hash(self, token_hash: str) -> AccountInvite | None:
        """Get an invite by stored token hash."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, username, display_name, token_hash,
                       created_at, expires_at, consumed_at, revoked
                FROM invites
                WHERE token_hash = ?
                """,
                [token_hash],
            ).fetchone()
        return self._row_to_invite(result) if result else None

    def list_pending_invites(self) -> list[AccountInvite]:
        """List invites that are still redeemable."""
        now = datetime.now()
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, username, display_name, token_hash,
                       created_at, expires_at, consumed_at, revoked
                FROM invites
                WHERE revoked = FALSE AND consumed_at IS NULL AND expires_at > ?
                ORDER BY created_at DESC, username
                """,
                [now],
            ).fetchall()
        return [self._row_to_invite(row) for row in rows]

    def get_pending_invite_for_username(self, username: str) -> AccountInvite | None:
        """Get the latest redeemable invite for one username, if any."""
        now = datetime.now()
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, username, display_name, token_hash,
                       created_at, expires_at, consumed_at, revoked
                FROM invites
                WHERE username = ? AND revoked = FALSE AND consumed_at IS NULL AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [username.strip(), now],
            ).fetchone()
        return self._row_to_invite(result) if result else None

    def revoke_invite(self, invite_id: str) -> AccountInvite | None:
        """Mark one invite as revoked."""
        with self._lock:
            self.conn.execute(
                "UPDATE invites SET revoked = TRUE WHERE id = ?",
                [invite_id],
            )
            self.conn.commit()
        return self.get_invite(invite_id)

    def consume_invite(self, invite_id: str, *, when: datetime | None = None) -> AccountInvite | None:
        """Mark one invite as consumed."""
        consumed_at = when or datetime.now()
        with self._lock:
            self.conn.execute(
                "UPDATE invites SET consumed_at = ? WHERE id = ?",
                [consumed_at, invite_id],
            )
            self.conn.commit()
        return self.get_invite(invite_id)

    # =========================================================================
    # Devices
    # =========================================================================

    def create_device(
        self,
        *,
        name: str,
        user_id: str,
        token_hash: str,
        ttl: timedelta = timedelta(days=90),
    ) -> Device:
        """Insert a paired device credential and return the typed record."""
        now = datetime.now()
        device = Device(
            name=name.strip(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            last_seen=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO devices (
                    id, name, user_id, token_hash,
                    created_at, last_seen, expires_at, revoked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    device.id,
                    device.name,
                    device.user_id,
                    device.token_hash,
                    device.created_at,
                    device.last_seen,
                    device.expires_at,
                    device.revoked,
                ],
            )
            self.conn.commit()
        return device

    def _row_to_device(self, row) -> Device:
        return Device(
            id=row[0],
            name=row[1],
            user_id=row[2],
            token_hash=row[3],
            created_at=row[4],
            last_seen=row[5],
            expires_at=row[6],
            revoked=row[7],
        )

    def get_device(self, device_id: str) -> Device | None:
        """Return one paired device by id."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, name, user_id, token_hash,
                       created_at, last_seen, expires_at, revoked
                FROM devices
                WHERE id = ?
                """,
                [device_id],
            ).fetchone()
        return self._row_to_device(result) if result else None

    def get_device_by_token_hash(self, token_hash: str) -> Device | None:
        """Return one paired device by stored token hash."""
        with self._lock:
            result = self.conn.execute(
                """
                SELECT id, name, user_id, token_hash,
                       created_at, last_seen, expires_at, revoked
                FROM devices
                WHERE token_hash = ?
                """,
                [token_hash],
            ).fetchone()
        return self._row_to_device(result) if result else None

    def list_devices(self) -> list[Device]:
        """List all paired devices."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, name, user_id, token_hash,
                       created_at, last_seen, expires_at, revoked
                FROM devices
                ORDER BY revoked, created_at, name
                """
            ).fetchall()
        return [self._row_to_device(row) for row in rows]

    def touch_device(
        self,
        token_hash: str,
        when: datetime | None = None,
    ) -> None:
        """Update the last-seen timestamp for a device token."""
        now = when or datetime.now()
        with self._lock:
            self.conn.execute(
                "UPDATE devices SET last_seen = ? WHERE token_hash = ?",
                [now, token_hash],
            )
            self.conn.commit()
        return None

    def revoke_device(self, device_id: str) -> Device | None:
        """Mark one paired device as revoked."""
        with self._lock:
            self.conn.execute(
                "UPDATE devices SET revoked = TRUE WHERE id = ?",
                [device_id],
            )
            self.conn.commit()
        return self.get_device(device_id)

    def renew_device(
        self,
        device_id: str,
        *,
        token_hash: str,
        when: datetime | None = None,
        ttl: timedelta = timedelta(days=90),
    ) -> Device | None:
        """Rotate one paired device token and extend its expiry."""
        now = when or datetime.now()
        expires_at = now + ttl
        with self._lock:
            self.conn.execute(
                """
                UPDATE devices
                SET token_hash = ?, last_seen = ?, expires_at = ?
                WHERE id = ? AND revoked = FALSE
                """,
                [token_hash, now, expires_at, device_id],
            )
            self.conn.commit()
        return self.get_device(device_id)

    def delete_model(self, model_id: str):
        """Delete a model."""
        model = self.get_model(model_id)
        if model:
            self._delete_typed(model)
        self.conn.commit()

    def save_mcp_server(self, server):
        """Save or update an MCP server."""



        with self._lock:
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

        with self._lock:
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

        with self._lock:
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
        server = self.get_mcp_server(server_id)
        if server:
            self._delete_typed(server)
        self.conn.commit()

    def save_action_audit(self, audit: ActionAudit) -> ActionAudit:
        """Persist an app-scoped ActionAudit row."""
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO actionaudits (
                    id, action_name, actor, target_ids, params, before, after,
                    run_id, created_at, chain_seq, undone, inverse_of, prev_hash, row_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    action_name = excluded.action_name,
                    actor = excluded.actor,
                    target_ids = excluded.target_ids,
                    params = excluded.params,
                    before = excluded.before,
                    after = excluded.after,
                    run_id = excluded.run_id,
                    created_at = excluded.created_at,
                    chain_seq = excluded.chain_seq,
                    undone = excluded.undone,
                    inverse_of = excluded.inverse_of,
                    prev_hash = excluded.prev_hash,
                    row_hash = excluded.row_hash
                """,
                [
                    audit.id,
                    audit.action_name,
                    audit.actor,
                    json.dumps(audit.target_ids),
                    json.dumps(audit.params),
                    json.dumps(audit.before) if audit.before is not None else None,
                    json.dumps(audit.after) if audit.after is not None else None,
                    audit.run_id,
                    audit.created_at,
                    audit.chain_seq,
                    audit.undone,
                    audit.inverse_of,
                    audit.prev_hash,
                    audit.row_hash,
                ],
            )
            self.conn.commit()
        return audit

    def list_action_audits(self) -> list[ActionAudit]:
        """Return app-scoped ActionAudit rows in created order."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT
                    id, action_name, actor, target_ids, params, before, after,
                    run_id, created_at, chain_seq, undone, inverse_of, prev_hash, row_hash
                FROM actionaudits
                ORDER BY created_at, id
                """
            ).fetchall()
        return [
            ActionAudit(
                id=row[0],
                action_name=row[1],
                actor=row[2],
                target_ids=json.loads(row[3]) if row[3] else [],
                params=json.loads(row[4]) if row[4] else {},
                before=json.loads(row[5]) if row[5] else None,
                after=json.loads(row[6]) if row[6] else None,
                run_id=row[7],
                created_at=row[8],
                chain_seq=row[9],
                undone=row[10],
                inverse_of=row[11],
                prev_hash=row[12],
                row_hash=row[13] or "",
            )
            for row in rows
        ]

    def _delete_typed(
        self,
        obj: BaseModel,
        *,
        key_field: str = "id",
        table_name: str | None = None,
    ) -> None:
        """Delete using a typed row object instead of raw id-only SQL."""
        table = table_name or self._TABLE_BY_MODEL_NAME.get(
            obj.__class__.__name__,
            f"{obj.__class__.__name__.lower()}s",
        )
        value = getattr(obj, key_field, None)
        if value is None:
            return
        with self._lock:
            self.conn.execute(
                f"DELETE FROM {table} WHERE {key_field} = ?",
                [value],
            )

    def close(self):
        """Close the database connection."""
        with self._lock:
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
