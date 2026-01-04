"""
App-Wide Database

Stores app-level configuration that is shared across all libraries:
- Provider configurations (Anthropic, OpenAI, etc.)
- API keys (stored in Keychain, referenced here)
- App preferences
- User settings

Location: ~/Library/Application Support/ca.tubb.fichero/app.duckdb

This is separate from library databases which store:
- Documents, workflows, conversations
- Provider references (which providers this library uses)
"""

from pathlib import Path
import logging
import duckdb
from fichero.storage import settings
from fichero.models import Provider, Model

logger = logging.getLogger(__name__)


class AppDatabase:
    """App-wide database for providers and settings."""

    def __init__(self, path: str | Path | None = None):
        """
        Initialize app-wide database connection.

        Args:
            path: Path to app database file. Defaults to ~/Library/Application Support/ca.tubb.fichero/app.duckdb
        """
        if path is None:
            path = settings.app_db_path
        else:
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = duckdb.connect(str(path))

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

        # Create indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_providers_type ON providers(provider_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_id)")

        logger.info("App database schema initialized")

    def save_provider(self, provider: Provider) -> Provider:
        """Save or update a provider."""
        from datetime import datetime

        self.conn.execute("""
            INSERT INTO providers (id, name, provider_type, api_base, enabled, sort_order, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                provider_type = excluded.provider_type,
                api_base = excluded.api_base,
                enabled = excluded.enabled,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
        """, [
            provider.id,
            provider.name,
            provider.provider_type.value if hasattr(provider.provider_type, 'value') else provider.provider_type,
            provider.api_base,
            provider.enabled,
            provider.sort_order,
            datetime.now()
        ])
        self.conn.commit()
        return provider

    def get_provider(self, provider_id: str) -> Provider | None:
        """Get a provider by ID."""
        from fichero.models import ProviderType

        result = self.conn.execute(
            "SELECT * FROM providers WHERE id = ?",
            [provider_id]
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
            updated_at=result[7]
        )

    def list_providers(self) -> list[Provider]:
        """List all providers."""
        from fichero.models import ProviderType

        results = self.conn.execute("SELECT * FROM providers ORDER BY sort_order, created_at").fetchall()

        return [
            Provider(
                id=row[0],
                name=row[1],
                provider_type=ProviderType(row[2]),
                api_base=row[3],
                enabled=row[4],
                sort_order=row[5],
                created_at=row[6],
                updated_at=row[7]
            )
            for row in results
        ]

    def delete_provider(self, provider_id: str):
        """Delete a provider and its associated models."""
        # First delete all models for this provider
        self.conn.execute("DELETE FROM models WHERE provider_id = ?", [provider_id])
        # Then delete the provider
        self.conn.execute("DELETE FROM providers WHERE id = ?", [provider_id])
        self.conn.commit()

    def save_model(self, model: Model) -> Model:
        """Save or update a model."""
        from datetime import datetime
        import json

        capabilities_json = json.dumps(model.capabilities) if model.capabilities else "[]"

        self.conn.execute("""
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
        """, [
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
            datetime.now()
        ])
        self.conn.commit()
        return model

    def list_models(self, provider_id: str | None = None) -> list[Model]:
        """List models, optionally filtered by provider."""
        import json

        if provider_id:
            results = self.conn.execute(
                "SELECT * FROM models WHERE provider_id = ? ORDER BY sort_order, name",
                [provider_id]
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
                updated_at=row[11]
            )
            for row in results
        ]

    def delete_model(self, model_id: str):
        """Delete a model."""
        self.conn.execute("DELETE FROM models WHERE id = ?", [model_id])
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
