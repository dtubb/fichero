"""
SQLite Storage Backend for Fichero Library

Handles persistent storage of collections, items, and processing history.
"""

import sqlite3
import logging
import uuid
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

try:
    from fichero.library.models import (
        Collection, CollectionItem, ProcessingResult, ExternalPath,
        ThumbnailRecord, ProcessingOutput, ExtractedMetadata, StepFile
    )
except ImportError:
    try:
        # Fallback for direct testing
        from .models import (
            Collection, CollectionItem, ProcessingResult, ExternalPath,
            ThumbnailRecord, ProcessingOutput, ExtractedMetadata, StepFile
        )
    except ImportError:
        # Direct import for testing
        import models
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        ExternalPath = models.ExternalPath
        ThumbnailRecord = models.ThumbnailRecord
        ProcessingOutput = models.ProcessingOutput
        ExtractedMetadata = models.ExtractedMetadata
        StepFile = models.StepFile

logger = logging.getLogger(__name__)


class LibraryStorage:
    """SQLite-based storage for library data"""
    
    def __init__(self, db_path: Path):
        """Initialize storage with database path"""
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize the database schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Configure database for better performance and iOS compatibility
                conn.execute("PRAGMA journal_mode=WAL")  # Use Write-Ahead Logging
                conn.execute("PRAGMA synchronous=NORMAL")  # Better performance
                conn.execute("PRAGMA foreign_keys=ON")  # Ensure foreign key constraints
                
                cursor = conn.cursor()
                
                # Collections table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS collections (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        type TEXT NOT NULL,
                        source_path TEXT,
                        local_path TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        sort_order INTEGER DEFAULT 0,
                        metadata TEXT
                    )
                """)

                # Migration: Add sort_order column if it doesn't exist (for existing databases)
                try:
                    cursor.execute("SELECT sort_order FROM collections LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Adding sort_order column to existing collections table")
                    cursor.execute("ALTER TABLE collections ADD COLUMN sort_order INTEGER DEFAULT 0")

                # Collection items table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS collection_items (
                        id TEXT PRIMARY KEY,
                        collection_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        source_path TEXT,
                        local_path TEXT,
                        storage_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        parent_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY (collection_id) REFERENCES collections(id),
                        FOREIGN KEY (parent_id) REFERENCES collection_items(id)
                    )
                """)

                # Migration: Add parent_id column if it doesn't exist (for existing databases)
                try:
                    cursor.execute("SELECT parent_id FROM collection_items LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Adding parent_id column to existing collection_items table")
                    cursor.execute("ALTER TABLE collection_items ADD COLUMN parent_id TEXT")

                # Migration: Add indexes for storage_type and source_path (for URL lookups)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_collection_items_storage_type
                    ON collection_items(storage_type)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_collection_items_collection_storage
                    ON collection_items(collection_id, storage_type)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_collection_items_source_path
                    ON collection_items(source_path)
                """)
                logger.debug("Created indexes for collection_items table")

                # Processing history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processing_history (
                        id TEXT PRIMARY KEY,
                        item_id TEXT NOT NULL,
                        workflow TEXT NOT NULL,
                        prompt_config TEXT,
                        status TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        output_paths TEXT,
                        logs_path TEXT,
                        metadata TEXT,
                        llm_backend TEXT,
                        processing_time REAL,
                        FOREIGN KEY (item_id) REFERENCES collection_items(id)
                    )
                """)
                
                # External paths monitoring table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS external_paths (
                        id TEXT PRIMARY KEY,
                        collection_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        last_seen TEXT,
                        status TEXT DEFAULT 'available',
                        FOREIGN KEY (collection_id) REFERENCES collections(id)
                    )
                """)

                # Thumbnails tracking table for deduplication
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS thumbnails (
                        id TEXT PRIMARY KEY,
                        source_file_hash TEXT NOT NULL,
                        thumbnail_hash TEXT NOT NULL,
                        thumbnail_path TEXT NOT NULL,
                        size TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL
                    )
                """)

                # Processing outputs table for tracking individual output files
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processing_outputs (
                        id TEXT PRIMARY KEY,
                        processing_result_id TEXT NOT NULL,
                        collection_id TEXT NOT NULL,
                        item_id TEXT,
                        step_name TEXT NOT NULL,
                        source_file TEXT,
                        output_type TEXT NOT NULL,
                        output_path TEXT NOT NULL,
                        file_format TEXT NOT NULL,
                        file_size INTEGER,
                        file_modified TEXT,
                        created_at TEXT NOT NULL,
                        metadata_extracted INTEGER DEFAULT 0,
                        is_valid INTEGER DEFAULT 1,
                        depends_on_output_ids TEXT,
                        model_name TEXT,
                        provider_name TEXT,
                        model_version TEXT,
                        api_endpoint TEXT,
                        api_parameters TEXT,
                        usage_stats TEXT,
                        FOREIGN KEY (processing_result_id) REFERENCES processing_history(id),
                        FOREIGN KEY (collection_id) REFERENCES collections(id),
                        FOREIGN KEY (item_id) REFERENCES collection_items(id)
                    )
                """)

                # Extracted metadata table for searchable content with versioning
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS extracted_metadata (
                        id TEXT PRIMARY KEY,
                        processing_output_id TEXT NOT NULL,
                        collection_id TEXT NOT NULL,
                        item_id TEXT,
                        schema_type TEXT NOT NULL,
                        source_label TEXT NOT NULL,
                        version INTEGER DEFAULT 1,
                        schema_version INTEGER DEFAULT 1,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL,
                        context TEXT,
                        model_name TEXT,
                        provider_name TEXT,
                        edited_by TEXT,
                        custom_fields TEXT,
                        indexed INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (processing_output_id) REFERENCES processing_outputs(id),
                        FOREIGN KEY (collection_id) REFERENCES collections(id),
                        FOREIGN KEY (item_id) REFERENCES collection_items(id)
                    )
                """)

                # Migration: Add collection_level column if it doesn't exist (for existing databases)
                try:
                    cursor.execute("SELECT collection_level FROM extracted_metadata LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Adding collection_level column to existing extracted_metadata table")
                    cursor.execute("ALTER TABLE extracted_metadata ADD COLUMN collection_level INTEGER DEFAULT 0")

                # Step metadata versions table for version tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS step_metadata_versions (
                        id TEXT PRIMARY KEY,
                        item_id TEXT NOT NULL,
                        step_name TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        changed_at TEXT NOT NULL,
                        changed_by TEXT,
                        change_reason TEXT,
                        metadata_snapshot TEXT NOT NULL,
                        FOREIGN KEY (item_id) REFERENCES collection_items(id) ON DELETE CASCADE
                    )
                """)

                # Step files table for storing step output files in library
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS step_files (
                        id TEXT PRIMARY KEY,
                        item_id TEXT NOT NULL,
                        collection_id TEXT NOT NULL,
                        step_name TEXT NOT NULL,
                        source_label TEXT NOT NULL,
                        version INTEGER DEFAULT 1,
                        file_name TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_format TEXT NOT NULL,
                        file_size INTEGER,
                        file_hash TEXT,
                        mime_type TEXT,
                        metadata TEXT,
                        is_valid INTEGER DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (item_id) REFERENCES collection_items(id) ON DELETE CASCADE,
                        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
                    )
                """)

                # Metadata schemas table for validation
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS metadata_schemas (
                        id TEXT PRIMARY KEY,
                        schema_type TEXT NOT NULL UNIQUE,
                        schema_version INTEGER DEFAULT 1,
                        required_fields TEXT NOT NULL,
                        optional_fields TEXT,
                        field_types TEXT NOT NULL,
                        field_validators TEXT,
                        description TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Timeline events table for activity tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS timeline_events (
                        id TEXT PRIMARY KEY,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_category TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        description TEXT,
                        metadata TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)

                # Create indexes for timeline queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timeline_entity
                    ON timeline_events(entity_type, entity_id, timestamp DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timeline_type
                    ON timeline_events(event_type, timestamp DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timeline_category
                    ON timeline_events(event_category, timestamp DESC)
                """)

                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_collection_items_collection_id ON collection_items(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_history_item_id ON processing_history(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_paths_collection_id ON external_paths(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_thumbnails_source_hash ON thumbnails(source_file_hash, size)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_thumbnails_hash ON thumbnails(thumbnail_hash)")

                # Indexes for new tables
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_outputs_result_id ON processing_outputs(processing_result_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_outputs_collection_id ON processing_outputs(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_outputs_item_id ON processing_outputs(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_outputs_type ON processing_outputs(output_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_outputs_step ON processing_outputs(step_name)")

                # Indexes for extracted_metadata
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_output_id ON extracted_metadata(processing_output_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_collection_id ON extracted_metadata(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_schema_type ON extracted_metadata(schema_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_source_label ON extracted_metadata(source_label)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_version ON extracted_metadata(version)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_key ON extracted_metadata(key)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_value ON extracted_metadata(value)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_item_schema ON extracted_metadata(item_id, schema_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_metadata_source_version ON extracted_metadata(source_label, version)")

                # Indexes for step_metadata_versions
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_item_id ON step_metadata_versions(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_step_name ON step_metadata_versions(step_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_changed_at ON step_metadata_versions(changed_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_item_step ON step_metadata_versions(item_id, step_name)")
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_step_metadata_versions_unique ON step_metadata_versions(item_id, step_name, version)")

                # Indexes for step_files
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_item_id ON step_files(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_collection_id ON step_files(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_step_name ON step_files(step_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_source_label ON step_files(source_label)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_item_step ON step_files(item_id, step_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_source_version ON step_files(source_label, version)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_files_hash ON step_files(file_hash)")
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_step_files_unique ON step_files(item_id, step_name, source_label, version, file_name)")

                # Indexes for metadata_schemas
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_schemas_type ON metadata_schemas(schema_type)")

                # FTS5 virtual table for full-text search
                # Using porter stemming and unicode61 tokenizer for better search
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
                        metadata_id UNINDEXED,
                        collection_id UNINDEXED,
                        item_id UNINDEXED,
                        schema_type UNINDEXED,
                        source_label UNINDEXED,
                        version UNINDEXED,
                        content,
                        tokenize='porter unicode61 remove_diacritics 1'
                    )
                """)

                logger.debug("FTS5 search index table created")

                conn.commit()
                logger.info("Library database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def add_collection(self, collection: Collection) -> bool:
        """Add a collection to storage"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Configure connection
                conn.execute("PRAGMA foreign_keys=ON")
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO collections
                    (id, name, type, source_path, local_path, created_at, updated_at, sort_order, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    collection.id,
                    collection.name,
                    collection.type,
                    collection.source_path,
                    collection.local_path,
                    collection.created_at.isoformat(),
                    collection.updated_at.isoformat(),
                    collection.sort_order,
                    self._serialize_metadata(collection.metadata)
                ))

                conn.commit()
                logger.info(f"✅ Collection saved to database: {collection.name} (ID: {collection.id})")
                return True

        except Exception as e:
            logger.error(f"Failed to add collection: {e}")
            return False
    
    def update_collection(self, collection: Collection) -> bool:
        """Update an existing collection"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE collections
                    SET name = ?, type = ?, source_path = ?, local_path = ?,
                        updated_at = ?, sort_order = ?, metadata = ?
                    WHERE id = ?
                """, (
                    collection.name,
                    collection.type,
                    collection.source_path,
                    collection.local_path,
                    datetime.now().isoformat(),
                    collection.sort_order,
                    self._serialize_metadata(collection.metadata),
                    collection.id
                ))
                
                conn.commit()
                logger.debug(f"Collection updated in storage: {collection.name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update collection: {e}")
            return False
    
    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a collection by ID"""
        try:
            logger.debug(f"🔍 Looking up collection in database: {collection_id}")
            logger.debug(f"📂 Database path: {self.db_path}")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # First, list all collections to see what's in the database
                cursor.execute("SELECT id, name, type FROM collections")
                all_collections = cursor.fetchall()
                logger.debug(f"📋 Total collections in database: {len(all_collections)}")
                for coll_row in all_collections:
                    logger.debug(f"  - {coll_row[0]}: {coll_row[1]} ({coll_row[2]})")

                # Now try to find the specific collection
                cursor.execute("""
                    SELECT id, name, type, source_path, local_path, created_at, updated_at, sort_order, metadata
                    FROM collections WHERE id = ?
                """, (collection_id,))

                row = cursor.fetchone()
                if row:
                    logger.info(f"✅ Found collection in database: {row[1]} (ID: {row[0]}, Type: {row[2]})")
                    collection = Collection(
                        id=row[0],
                        name=row[1],
                        type=row[2],
                        source_path=row[3],
                        local_path=row[4],
                        created_at=datetime.fromisoformat(row[5]),
                        updated_at=datetime.fromisoformat(row[6]),
                        sort_order=row[7] if row[7] is not None else 0,
                        metadata=self._deserialize_metadata(row[8])
                    )
                    return collection
                else:
                    logger.warning(f"❌ Collection not found in database: {collection_id}")
                    return None

        except Exception as e:
            logger.error(f"Failed to get collection: {e}")
            return None
    
    def get_collection_by_name(self, name: str) -> Optional[Collection]:
        """Get a collection by name"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, name, type, source_path, local_path, created_at, updated_at, sort_order, metadata
                    FROM collections WHERE name = ?
                """, (name,))

                row = cursor.fetchone()
                if row:
                    collection = Collection(
                        id=row[0],
                        name=row[1],
                        type=row[2],
                        source_path=row[3],
                        local_path=row[4],
                        created_at=datetime.fromisoformat(row[5]),
                        updated_at=datetime.fromisoformat(row[6]),
                        sort_order=row[7] if row[7] is not None else 0,
                        metadata=self._deserialize_metadata(row[8])
                    )
                    return collection
                else:
                    return None
                
        except Exception as e:
            logger.error(f"Failed to get collection by name: {e}")
            return None
    
    def get_all_collections(self, sort_by: str = "manual") -> List[Collection]:
        """Get all collections with sorting

        Args:
            sort_by: Sort mode - "manual", "name", "date_created", "date_updated", "type"
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Configure connection for read operations
                conn.execute("PRAGMA foreign_keys=ON")
                conn.isolation_level = None  # Enable autocommit mode
                cursor = conn.cursor()

                # Start read transaction
                cursor.execute("BEGIN")

                # Determine sort order based on mode
                if sort_by == "manual":
                    # Manual sort: sort_order ASC (0 = auto), then by name for ties
                    order_clause = "ORDER BY CASE WHEN sort_order = 0 THEN 1 ELSE 0 END, sort_order ASC, name ASC"
                elif sort_by == "name":
                    order_clause = "ORDER BY name COLLATE NOCASE ASC"
                elif sort_by == "date_created":
                    order_clause = "ORDER BY created_at DESC"
                elif sort_by == "date_updated":
                    order_clause = "ORDER BY updated_at DESC"
                elif sort_by == "type":
                    order_clause = "ORDER BY type ASC, name ASC"
                else:
                    # Fallback to manual
                    order_clause = "ORDER BY CASE WHEN sort_order = 0 THEN 1 ELSE 0 END, sort_order ASC, name ASC"

                cursor.execute(f"""
                    SELECT id, name, type, source_path, local_path, created_at, updated_at, sort_order, metadata
                    FROM collections {order_clause}
                """)

                collections = []
                for row in cursor.fetchall():
                    collection = Collection(
                        id=row[0],
                        name=row[1],
                        type=row[2],
                        source_path=row[3],
                        local_path=row[4],
                        created_at=datetime.fromisoformat(row[5]),
                        updated_at=datetime.fromisoformat(row[6]),
                        sort_order=row[7] if row[7] is not None else 0,
                        metadata=self._deserialize_metadata(row[8])
                    )
                    collections.append(collection)

                return collections

        except Exception as e:
            logger.error(f"Failed to get all collections: {e}")
            return []
    
    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection and all related data"""
        try:
            logger.debug(f"Storage: Starting deletion of collection {collection_id}")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if collection exists first
                cursor.execute("SELECT id, name FROM collections WHERE id = ?", (collection_id,))
                collection_data = cursor.fetchone()
                if not collection_data:
                    logger.error(f"Storage: Collection {collection_id} not found in database")
                    return False

                logger.debug(f"Storage: Found collection to delete: {collection_data[1]} (ID: {collection_data[0]})")

                # Delete in order due to foreign key constraints
                logger.debug(f"Storage: Deleting processing_history for collection {collection_id}")
                cursor.execute("DELETE FROM processing_history WHERE item_id IN (SELECT id FROM collection_items WHERE collection_id = ?)", (collection_id,))

                logger.debug(f"Storage: Deleting extracted_metadata for collection {collection_id}")
                cursor.execute("DELETE FROM extracted_metadata WHERE collection_id = ?", (collection_id,))

                logger.debug(f"Storage: Deleting collection_items for collection {collection_id}")
                cursor.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection_id,))

                logger.debug(f"Storage: Deleting external_paths for collection {collection_id}")
                cursor.execute("DELETE FROM external_paths WHERE collection_id = ?", (collection_id,))

                logger.debug(f"Storage: Deleting collection record {collection_id}")
                cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))

                # Check if anything was actually deleted
                if cursor.rowcount == 0:
                    logger.warning(f"Storage: No collection record was deleted for ID {collection_id}")
                    return False

                conn.commit()
                logger.info(f"Storage: Successfully deleted collection {collection_data[1]} (ID: {collection_id})")
                return True

        except Exception as e:
            logger.error(f"Storage: Failed to delete collection {collection_id}: {e}")
            return False

    def delete_collection_item(self, item_id: str) -> bool:
        """Delete a collection item and its related data"""
        try:
            logger.debug(f"Storage: Starting deletion of item {item_id}")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if item exists first
                cursor.execute("SELECT id, name, type FROM collection_items WHERE id = ?", (item_id,))
                item_data = cursor.fetchone()
                if not item_data:
                    logger.error(f"Storage: Item {item_id} not found in database")
                    return False

                logger.debug(f"Storage: Found item to delete: {item_data[1]} (ID: {item_data[0]}, Type: {item_data[2]})")

                # Delete related processing history
                logger.debug(f"Storage: Deleting processing_history for item {item_id}")
                cursor.execute("DELETE FROM processing_history WHERE item_id = ?", (item_id,))

                # Delete related extracted metadata
                logger.debug(f"Storage: Deleting extracted_metadata for item {item_id}")
                cursor.execute("DELETE FROM extracted_metadata WHERE item_id = ?", (item_id,))

                # Delete the item
                logger.debug(f"Storage: Deleting collection_item record {item_id}")
                cursor.execute("DELETE FROM collection_items WHERE id = ?", (item_id,))

                # Check if anything was actually deleted
                if cursor.rowcount == 0:
                    logger.warning(f"Storage: No item record was deleted for ID {item_id}")
                    return False

                conn.commit()
                logger.info(f"Storage: Successfully deleted item {item_data[1]} (ID: {item_id})")
                return True

        except Exception as e:
            logger.error(f"Storage: Failed to delete item {item_id}: {e}")
            return False
    
    def add_collection_item(self, item: CollectionItem) -> bool:
        """Add an item to a collection"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO collection_items
                    (id, collection_id, type, source_path, local_path, storage_type, name, status, parent_id, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.id,
                    item.collection_id,
                    item.type,
                    item.source_path,
                    item.local_path,
                    item.storage_type,
                    item.name,
                    item.status,
                    item.parent_id,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                    self._serialize_metadata(item.metadata)
                ))
                
                conn.commit()
                logger.debug(f"Collection item added: {item.name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add collection item: {e}")
            return False

    def update_item(self, item: CollectionItem) -> bool:
        """Update an existing collection item"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE collection_items
                    SET type = ?, source_path = ?, local_path = ?, storage_type = ?,
                        name = ?, status = ?, parent_id = ?, updated_at = ?, metadata = ?
                    WHERE id = ?
                """, (
                    item.type,
                    item.source_path,
                    item.local_path,
                    item.storage_type,
                    item.name,
                    item.status,
                    item.parent_id,
                    datetime.now().isoformat(),
                    self._serialize_metadata(item.metadata),
                    item.id
                ))

                conn.commit()
                logger.debug(f"Collection item updated: {item.name}")
                return True

        except Exception as e:
            logger.error(f"Failed to update collection item: {e}")
            return False

    def get_collection_items(self, collection_id: str) -> List[CollectionItem]:
        """Get all items in a collection

        Sorting logic:
        - If items have manifest_position in metadata, sort by that (ASC) - preserves IIIF manifest order
        - Otherwise sort by created_at (ASC) - order added to collection
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Note: SQLite doesn't support JSON extraction natively, so we'll sort in Python
                cursor.execute("""
                    SELECT id, collection_id, type, source_path, local_path, storage_type, name, status, parent_id, created_at, updated_at, metadata
                    FROM collection_items WHERE collection_id = ?
                """, (collection_id,))

                items = []
                for row in cursor.fetchall():
                    item = CollectionItem(
                        id=row[0],
                        collection_id=row[1],
                        type=row[2],
                        source_path=row[3],
                        local_path=row[4],
                        storage_type=row[5],
                        name=row[6],
                        status=row[7],
                        parent_id=row[8],
                        created_at=datetime.fromisoformat(row[9]),
                        updated_at=datetime.fromisoformat(row[10]),
                        metadata=self._deserialize_metadata(row[11])
                    )
                    items.append(item)

                # Smart sorting: use manifest_position if available, otherwise created_at
                def sort_key(item):
                    manifest_pos = item.metadata.get('manifest_position')
                    if manifest_pos is not None:
                        # Has manifest position - use it (with type prefix for folders first)
                        type_order = 0 if item.type == 'folder' else 1
                        return (type_order, manifest_pos, item.created_at)
                    else:
                        # No manifest position - sort by type then creation time
                        type_order = 0 if item.type == 'folder' else 1
                        return (type_order, 999999, item.created_at)

                items.sort(key=sort_key)

                return items

        except Exception as e:
            logger.error(f"Failed to get collection items: {e}")
            return []

    def get_item(self, item_id: str) -> Optional[CollectionItem]:
        """Get a single item by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, collection_id, type, source_path, local_path, storage_type, name, status, parent_id, created_at, updated_at, metadata
                    FROM collection_items WHERE id = ?
                """, (item_id,))

                row = cursor.fetchone()
                if row:
                    item = CollectionItem(
                        id=row[0],
                        collection_id=row[1],
                        type=row[2],
                        source_path=row[3],
                        local_path=row[4],
                        storage_type=row[5],
                        name=row[6],
                        status=row[7],
                        parent_id=row[8],
                        created_at=datetime.fromisoformat(row[9]),
                        updated_at=datetime.fromisoformat(row[10]),
                        metadata=self._deserialize_metadata(row[11])
                    )
                    return item
                return None

        except Exception as e:
            logger.error(f"Failed to get item: {e}")
            return None

    def get_file_items_by_parent(self, collection_id: str, parent_id: str) -> List[CollectionItem]:
        """
        Get file items in a collection filtered by parent_id.

        This is optimized for building item_maps during folder processing.
        Uses database-level filtering instead of querying all items.

        Args:
            collection_id: Collection ID
            parent_id: Parent folder item_id

        Returns:
            List of CollectionItem objects with type='file' and matching parent_id
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, collection_id, type, source_path, local_path, storage_type, name, status, parent_id, created_at, updated_at, metadata
                    FROM collection_items
                    WHERE collection_id = ? AND parent_id = ? AND type = 'file'
                    ORDER BY name ASC
                """, (collection_id, parent_id))

                items = []
                for row in cursor.fetchall():
                    item = CollectionItem(
                        id=row[0],
                        collection_id=row[1],
                        type=row[2],
                        source_path=row[3],
                        local_path=row[4],
                        storage_type=row[5],
                        name=row[6],
                        status=row[7],
                        parent_id=row[8],
                        created_at=datetime.fromisoformat(row[9]),
                        updated_at=datetime.fromisoformat(row[10]),
                        metadata=self._deserialize_metadata(row[11])
                    )
                    items.append(item)

                return items

        except Exception as e:
            logger.error(f"Failed to get file items by parent: {e}")
            return []

    def add_processing_result(self, result: ProcessingResult) -> bool:
        """Add a processing result"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO processing_history 
                    (id, item_id, workflow, prompt_config, status, started_at, completed_at, output_paths, logs_path, metadata, llm_backend, processing_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.id,
                    result.item_id,
                    result.workflow,
                    result.prompt_config,
                    result.status,
                    result.started_at.isoformat() if result.started_at else None,
                    result.completed_at.isoformat() if result.completed_at else None,
                    self._serialize_list(result.output_paths),
                    result.logs_path,
                    self._serialize_metadata(result.metadata),
                    result.llm_backend,
                    result.processing_time
                ))
                
                conn.commit()
                logger.debug(f"Processing result added: {result.workflow}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add processing result: {e}")
            return False
    
    def get_processing_history(self, item_id: str) -> List[ProcessingResult]:
        """Get processing history for an item"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, item_id, workflow, prompt_config, status, started_at, completed_at, output_paths, logs_path, metadata, llm_backend, processing_time
                    FROM processing_history WHERE item_id = ? ORDER BY started_at DESC
                """, (item_id,))
                
                results = []
                for row in cursor.fetchall():
                    result = ProcessingResult(
                        id=row[0],
                        item_id=row[1],
                        workflow=row[2],
                        prompt_config=row[3],
                        status=row[4],
                        started_at=datetime.fromisoformat(row[5]) if row[5] else None,
                        completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                        output_paths=self._deserialize_list(row[7]),
                        logs_path=row[8],
                        metadata=self._deserialize_metadata(row[9]),
                        llm_backend=row[10],
                        processing_time=row[11]
                    )
                    results.append(result)
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get processing history: {e}")
            return []

    def get_processing_results_by_collection(self, collection_id: str) -> List[ProcessingResult]:
        """Get all processing results for items in a collection"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT ph.id, ph.item_id, ph.workflow, ph.prompt_config, ph.status,
                           ph.started_at, ph.completed_at, ph.output_paths, ph.logs_path,
                           ph.metadata, ph.llm_backend, ph.processing_time
                    FROM processing_history ph
                    JOIN collection_items ci ON ph.item_id = ci.id
                    WHERE ci.collection_id = ?
                    ORDER BY ph.started_at DESC
                """, (collection_id,))

                results = []
                for row in cursor.fetchall():
                    result = ProcessingResult(
                        id=row[0],
                        item_id=row[1],
                        workflow=row[2],
                        prompt_config=row[3],
                        status=row[4],
                        started_at=datetime.fromisoformat(row[5]) if row[5] else None,
                        completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                        output_paths=self._deserialize_list(row[7]),
                        logs_path=row[8],
                        metadata=self._deserialize_metadata(row[9]),
                        llm_backend=row[10],
                        processing_time=row[11]
                    )
                    results.append(result)

                return results

        except Exception as e:
            logger.error(f"Failed to get processing results for collection: {e}")
            return []

    def get_processing_results_before_date(self, before_date: datetime) -> List[ProcessingResult]:
        """Get all processing results completed before a specific date"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, item_id, workflow, prompt_config, status, started_at,
                           completed_at, output_paths, logs_path, metadata, llm_backend, processing_time
                    FROM processing_history
                    WHERE completed_at < ?
                    ORDER BY completed_at DESC
                """, (before_date.isoformat(),))

                results = []
                for row in cursor.fetchall():
                    result = ProcessingResult(
                        id=row[0],
                        item_id=row[1],
                        workflow=row[2],
                        prompt_config=row[3],
                        status=row[4],
                        started_at=datetime.fromisoformat(row[5]) if row[5] else None,
                        completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                        output_paths=self._deserialize_list(row[7]),
                        logs_path=row[8],
                        metadata=self._deserialize_metadata(row[9]),
                        llm_backend=row[10],
                        processing_time=row[11]
                    )
                    results.append(result)

                return results

        except Exception as e:
            logger.error(f"Failed to get processing results before date: {e}")
            return []

    def get_processing_result(self, result_id: str) -> Optional[ProcessingResult]:
        """Get a single processing result by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, item_id, workflow, prompt_config, status, started_at,
                           completed_at, output_paths, logs_path, metadata, llm_backend, processing_time
                    FROM processing_history
                    WHERE id = ?
                """, (result_id,))

                row = cursor.fetchone()
                if not row:
                    return None

                result = ProcessingResult(
                    id=row[0],
                    item_id=row[1],
                    workflow=row[2],
                    prompt_config=row[3],
                    status=row[4],
                    started_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    output_paths=self._deserialize_list(row[7]),
                    logs_path=row[8],
                    metadata=self._deserialize_metadata(row[9]),
                    llm_backend=row[10],
                    processing_time=row[11]
                )

                return result

        except Exception as e:
            logger.error(f"Failed to get processing result {result_id}: {e}")
            return None

    def delete_processing_result(self, result_id: str) -> bool:
        """
        Delete a processing result and all related data (outputs, metadata)

        Args:
            result_id: ID of the ProcessingResult to delete

        Returns:
            True if deletion was successful
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Delete extracted metadata first (FK constraint)
                cursor.execute("""
                    DELETE FROM extracted_metadata
                    WHERE processing_output_id IN (
                        SELECT id FROM processing_outputs WHERE processing_result_id = ?
                    )
                """, (result_id,))

                # Delete processing outputs
                cursor.execute("DELETE FROM processing_outputs WHERE processing_result_id = ?", (result_id,))

                # Delete the processing result itself
                cursor.execute("DELETE FROM processing_history WHERE id = ?", (result_id,))

                conn.commit()
                logger.info(f"Deleted processing result {result_id} from database")
                return True

        except Exception as e:
            logger.error(f"Failed to delete processing result {result_id}: {e}")
            return False

    # Processing output tracking methods

    # Column list for processing_outputs SELECT queries
    _PROCESSING_OUTPUT_COLUMNS = """
        id, processing_result_id, collection_id, item_id, step_name, source_file,
        output_type, output_path, file_format, file_size, file_modified, created_at,
        metadata_extracted, is_valid, depends_on_output_ids,
        model_name, provider_name, model_version, api_endpoint, api_parameters, usage_stats
    """

    def _row_to_processing_output(self, row) -> ProcessingOutput:
        """Convert a database row to ProcessingOutput object"""
        return ProcessingOutput(
            id=row[0],
            processing_result_id=row[1],
            collection_id=row[2],
            item_id=row[3],
            step_name=row[4],
            source_file=row[5],
            output_type=row[6],
            output_path=row[7],
            file_format=row[8],
            file_size=row[9],
            file_modified=datetime.fromisoformat(row[10]) if row[10] else None,
            created_at=datetime.fromisoformat(row[11]),
            metadata_extracted=bool(row[12]),
            is_valid=bool(row[13]),
            depends_on_output_ids=self._deserialize_list(row[14]),
            model_name=row[15] if len(row) > 15 else None,
            provider_name=row[16] if len(row) > 16 else None,
            model_version=row[17] if len(row) > 17 else None,
            api_endpoint=row[18] if len(row) > 18 else None,
            api_parameters=row[19] if len(row) > 19 else None,
            usage_stats=row[20] if len(row) > 20 else None,
        )

    def add_processing_output(self, output: ProcessingOutput) -> bool:
        """Add a processing output record"""
        try:
            logger.debug(f"Adding processing output: id={output.id}, type={output.output_type}")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO processing_outputs
                    (id, processing_result_id, collection_id, item_id, step_name, source_file,
                     output_type, output_path, file_format, file_size, file_modified, created_at,
                     metadata_extracted, is_valid, depends_on_output_ids,
                     model_name, provider_name, model_version, api_endpoint, api_parameters, usage_stats)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    output.id,
                    output.processing_result_id,
                    output.collection_id,
                    output.item_id,
                    output.step_name,
                    output.source_file,
                    output.output_type,
                    output.output_path,
                    output.file_format,
                    output.file_size,
                    output.file_modified.isoformat() if output.file_modified else None,
                    output.created_at.isoformat(),
                    1 if output.metadata_extracted else 0,
                    1 if output.is_valid else 0,
                    self._serialize_list(output.depends_on_output_ids),
                    output.model_name,
                    output.provider_name,
                    output.model_version,
                    output.api_endpoint,
                    output.api_parameters,
                    output.usage_stats
                ))

                conn.commit()
                logger.debug(f"Processing output added: {output.output_type} - {output.output_path}")
                return True

        except Exception as e:
            logger.error(f"Failed to add processing output: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_processing_outputs(self, processing_result_id: str) -> List[ProcessingOutput]:
        """Get all outputs for a processing result"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(f"""
                    SELECT {self._PROCESSING_OUTPUT_COLUMNS}
                    FROM processing_outputs
                    WHERE processing_result_id = ?
                    ORDER BY created_at ASC
                """, (processing_result_id,))

                return [self._row_to_processing_output(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get processing outputs: {e}")
            return []

    def get_outputs_by_collection(self, collection_id: str, output_type: str = None) -> List[ProcessingOutput]:
        """Get all outputs for a collection, optionally filtered by type"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if output_type:
                    cursor.execute(f"""
                        SELECT {self._PROCESSING_OUTPUT_COLUMNS}
                        FROM processing_outputs
                        WHERE collection_id = ? AND output_type = ?
                        ORDER BY created_at DESC
                    """, (collection_id, output_type))
                else:
                    cursor.execute(f"""
                        SELECT {self._PROCESSING_OUTPUT_COLUMNS}
                        FROM processing_outputs
                        WHERE collection_id = ?
                        ORDER BY created_at DESC
                    """, (collection_id,))

                return [self._row_to_processing_output(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get outputs by collection: {e}")
            return []

    def get_outputs_by_item(self, item_id: str, output_type: str = None) -> List[ProcessingOutput]:
        """Get outputs for a specific item, optionally filtered by type"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if output_type:
                    cursor.execute(f"""
                        SELECT {self._PROCESSING_OUTPUT_COLUMNS}
                        FROM processing_outputs
                        WHERE item_id = ? AND output_type = ?
                        ORDER BY created_at DESC
                    """, (item_id, output_type))
                else:
                    cursor.execute(f"""
                        SELECT {self._PROCESSING_OUTPUT_COLUMNS}
                        FROM processing_outputs
                        WHERE item_id = ?
                        ORDER BY created_at DESC
                    """, (item_id,))

                return [self._row_to_processing_output(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get outputs by item: {e}")
            return []

    def update_processing_output(self, output: ProcessingOutput) -> bool:
        """Update a processing output record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE processing_outputs
                    SET metadata_extracted = ?, is_valid = ?, file_modified = ?, file_size = ?
                    WHERE id = ?
                """, (
                    1 if output.metadata_extracted else 0,
                    1 if output.is_valid else 0,
                    output.file_modified.isoformat() if output.file_modified else None,
                    output.file_size,
                    output.id
                ))

                conn.commit()
                logger.debug(f"Processing output updated: {output.id}")
                return True

        except Exception as e:
            logger.error(f"Failed to update processing output: {e}")
            return False

    # Extracted metadata methods

    # Column list for extracted_metadata SELECT queries
    _EXTRACTED_METADATA_COLUMNS = """
        id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
        version, schema_version, key, value, confidence, context,
        model_name, provider_name, edited_by, custom_fields, indexed, created_at
    """

    def _row_to_extracted_metadata(self, row) -> ExtractedMetadata:
        """Convert a database row to ExtractedMetadata object"""
        return ExtractedMetadata(
            id=row[0],
            processing_output_id=row[1],
            collection_id=row[2],
            item_id=row[3],
            collection_level=bool(row[4]),
            schema_type=row[5],
            source_label=row[6],
            version=row[7],
            schema_version=row[8],
            key=row[9],
            value=row[10],
            confidence=row[11],
            context=row[12],
            model_name=row[13] if len(row) > 13 else None,
            provider_name=row[14] if len(row) > 14 else None,
            edited_by=row[15] if len(row) > 15 else None,
            custom_fields=self._deserialize_metadata(row[16]) if len(row) > 16 else {},
            indexed=bool(row[17]) if len(row) > 17 else False,
            created_at=datetime.fromisoformat(row[18]) if len(row) > 18 else datetime.now(),
        )

    def add_extracted_metadata(self, metadata: ExtractedMetadata) -> bool:
        """Add extracted metadata record with versioning support"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO extracted_metadata
                    (id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
                     version, schema_version, key, value, confidence, context,
                     model_name, provider_name, edited_by, custom_fields, indexed, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metadata.id,
                    metadata.processing_output_id,
                    metadata.collection_id,
                    metadata.item_id,
                    1 if metadata.collection_level else 0,
                    metadata.schema_type,
                    metadata.source_label,
                    metadata.version,
                    metadata.schema_version,
                    metadata.key,
                    metadata.value,
                    metadata.confidence,
                    metadata.context,
                    metadata.model_name,
                    metadata.provider_name,
                    metadata.edited_by,
                    self._serialize_metadata(metadata.custom_fields),
                    1 if metadata.indexed else 0,
                    metadata.created_at.isoformat()
                ))

                conn.commit()
                logger.debug(f"Extracted metadata added: {metadata.schema_type} - {metadata.source_label}_v{metadata.version} - {metadata.key}")
                return True

        except Exception as e:
            logger.error(f"Failed to add extracted metadata: {e}")
            return False

    def get_extracted_metadata(self, processing_output_id: str) -> List[ExtractedMetadata]:
        """Get all extracted metadata for a processing output"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(f"""
                    SELECT {self._EXTRACTED_METADATA_COLUMNS}
                    FROM extracted_metadata
                    WHERE processing_output_id = ?
                    ORDER BY created_at ASC
                """, (processing_output_id,))

                return [self._row_to_extracted_metadata(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get extracted metadata: {e}")
            return []

    def get_extracted_metadata_by_item(self, item_id: str,
                                       schema_type: str = None,
                                       key: str = None,
                                       collection_level: bool = None) -> List[ExtractedMetadata]:
        """Get extracted metadata directly by item_id

        This is the preferred method for views to load metadata, as it queries
        directly using the item_id without needing processing_output_id from manifests.

        Args:
            item_id: The item ID to query
            schema_type: Optional filter by schema_type (e.g., 'transcription')
            key: Optional filter by key (e.g., 'text')
            collection_level: Optional filter by collection level (True/False/None for all)

        Returns:
            List of ExtractedMetadata records matching the filters, ordered newest first
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = f"""
                    SELECT {self._EXTRACTED_METADATA_COLUMNS}
                    FROM extracted_metadata
                    WHERE item_id = ?
                """
                params = [item_id]

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                if key:
                    sql += " AND key = ?"
                    params.append(key)

                if collection_level is not None:
                    sql += " AND collection_level = ?"
                    params.append(1 if collection_level else 0)

                sql += " ORDER BY version DESC, created_at DESC"  # Newest first

                cursor.execute(sql, params)

                return [self._row_to_extracted_metadata(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get extracted metadata by item: {e}")
            return []

    def get_max_metadata_version(self, item_id: str, schema_type: str,
                                  source_label: str = None) -> int:
        """Get the highest version number for a specific item/schema/source combination.

        This is an efficient single-query method used for atomic version incrementing
        during metadata extraction.

        Args:
            item_id: The item ID
            schema_type: Schema type (e.g., 'transcription', 'catalogue')
            source_label: Optional source label filter (e.g., 'ai_qwen', 'user_edit')

        Returns:
            Max version number (0 if no records exist)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if source_label:
                    cursor.execute("""
                        SELECT COALESCE(MAX(version), 0)
                        FROM extracted_metadata
                        WHERE item_id = ? AND schema_type = ? AND source_label = ?
                    """, (item_id, schema_type, source_label))
                else:
                    cursor.execute("""
                        SELECT COALESCE(MAX(version), 0)
                        FROM extracted_metadata
                        WHERE item_id = ? AND schema_type = ?
                    """, (item_id, schema_type))

                result = cursor.fetchone()
                return result[0] if result else 0

        except Exception as e:
            logger.error(f"Failed to get max metadata version: {e}")
            return 0

    def get_field_versions(self, item_id: str, schema_type: str,
                           key: str) -> List[ExtractedMetadata]:
        """Get all versions of a specific metadata field for an item.

        Returns list ordered by version DESC (newest first).

        Args:
            item_id: Item ID
            schema_type: Schema type (e.g., 'transcription', 'catalogue')
            key: Field key (e.g., 'text', 'title')

        Returns:
            List of ExtractedMetadata records, newest first
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT {self._EXTRACTED_METADATA_COLUMNS}
                    FROM extracted_metadata
                    WHERE item_id = ? AND schema_type = ? AND key = ?
                    ORDER BY version DESC, created_at DESC
                """, (item_id, schema_type, key))
                return [self._row_to_extracted_metadata(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get field versions: {e}")
            return []

    def get_item_metadata_with_versions(self, item_id: str,
                                        schema_type: str = None) -> Dict[str, List[ExtractedMetadata]]:
        """Get all metadata for an item, grouped by key with all versions.

        Args:
            item_id: Item ID
            schema_type: Optional filter by schema type

        Returns:
            Dict mapping key -> list of ExtractedMetadata (newest first per key)
        """
        try:
            metadata_list = self.get_extracted_metadata_by_item(
                item_id=item_id,
                schema_type=schema_type
            )

            # Group by key
            grouped: Dict[str, List[ExtractedMetadata]] = {}
            for metadata in metadata_list:
                if metadata.key not in grouped:
                    grouped[metadata.key] = []
                grouped[metadata.key].append(metadata)

            return grouped
        except Exception as e:
            logger.error(f"Failed to get metadata with versions: {e}")
            return {}

    def get_model_versions_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        """Get all AI model versions for an item, grouped by source_label.

        Returns a list of model version summaries, each containing:
        - source_label: The source identifier (e.g., 'ai_qwen', 'ai_gpt')
        - model_name: Model name if available
        - provider_name: Provider name if available
        - created_at: When this version was created
        - schema_types: List of schema types this source has data for
        - record_count: Number of metadata records from this source

        Args:
            item_id: Item ID

        Returns:
            List of model version summary dicts, newest first
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get distinct source versions with their metadata
                cursor.execute("""
                    SELECT
                        source_label,
                        model_name,
                        provider_name,
                        MAX(created_at) as latest_created,
                        GROUP_CONCAT(DISTINCT schema_type) as schema_types,
                        COUNT(*) as record_count
                    FROM extracted_metadata
                    WHERE item_id = ? AND source_label != 'user_edit'
                    GROUP BY source_label, model_name, provider_name
                    ORDER BY latest_created DESC
                """, (item_id,))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'source_label': row[0],
                        'model_name': row[1],
                        'provider_name': row[2],
                        'created_at': row[3],
                        'schema_types': row[4].split(',') if row[4] else [],
                        'record_count': row[5]
                    })

                return results
        except Exception as e:
            logger.error(f"Failed to get model versions for item: {e}")
            return []

    # Sentinel value to distinguish between "not provided" and "explicitly None"
    _MODEL_NAME_NOT_PROVIDED = object()

    def get_metadata_by_source(self, item_id: str, source_label: str,
                               model_name: str = _MODEL_NAME_NOT_PROVIDED) -> List[ExtractedMetadata]:
        """Get all metadata for an item from a specific source/model.

        Args:
            item_id: Item ID
            source_label: Source label (e.g., 'ai_qwen', 'ai_gpt')
            model_name: Model name filter. If provided (including None), filters by exact match.
                       If not provided, returns all records for the source_label.

        Returns:
            List of ExtractedMetadata records from this source
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if model_name is self._MODEL_NAME_NOT_PROVIDED:
                    # No model_name filter - return all records for this source
                    cursor.execute(f"""
                        SELECT {self._EXTRACTED_METADATA_COLUMNS}
                        FROM extracted_metadata
                        WHERE item_id = ? AND source_label = ?
                        ORDER BY schema_type, key, version DESC
                    """, (item_id, source_label))
                elif model_name is None:
                    # Explicitly filter for records where model_name IS NULL
                    cursor.execute(f"""
                        SELECT {self._EXTRACTED_METADATA_COLUMNS}
                        FROM extracted_metadata
                        WHERE item_id = ? AND source_label = ? AND model_name IS NULL
                        ORDER BY schema_type, key, version DESC
                    """, (item_id, source_label))
                else:
                    # Filter by specific model_name
                    cursor.execute(f"""
                        SELECT {self._EXTRACTED_METADATA_COLUMNS}
                        FROM extracted_metadata
                        WHERE item_id = ? AND source_label = ? AND model_name = ?
                        ORDER BY schema_type, key, version DESC
                    """, (item_id, source_label, model_name))

                return [self._row_to_extracted_metadata(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get metadata by source: {e}")
            return []

    # =========================================================================
    # Metadata Update Methods (for editable metadata pane)
    # =========================================================================

    def update_extracted_metadata(
        self, item_id: str, schema_type: str, key: str, value: str
    ) -> bool:
        """
        Update or insert metadata record (UPSERT logic).

        Updates most recent record if exists, otherwise creates new.
        Uses source_label='user_edit' for user-created edits.

        Args:
            item_id: Item ID
            schema_type: Schema type (e.g., 'transcription', 'catalogue')
            key: Field key (e.g., 'text', 'title')
            value: New value

        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if record exists
                cursor.execute("""
                    SELECT id, collection_id FROM extracted_metadata
                    WHERE item_id = ? AND schema_type = ? AND key = ?
                    ORDER BY version DESC, created_at DESC
                    LIMIT 1
                """, (item_id, schema_type, key))

                row = cursor.fetchone()

                if row:
                    # Update existing
                    record_id = row[0]
                    cursor.execute("""
                        UPDATE extracted_metadata
                        SET value = ?, created_at = ?, source_label = 'user_edit'
                        WHERE id = ?
                    """, (value, datetime.now().isoformat(), record_id))
                    logger.debug(f"Updated metadata record {record_id}")
                else:
                    # Get collection_id from item
                    cursor.execute(
                        "SELECT collection_id FROM collection_items WHERE id = ?",
                        (item_id,)
                    )
                    item_row = cursor.fetchone()
                    collection_id = item_row[0] if item_row else ''

                    # Insert new
                    new_id = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO extracted_metadata
                        (id, processing_output_id, collection_id, item_id, collection_level,
                         schema_type, source_label, version, schema_version, key, value,
                         confidence, context, custom_fields, indexed, created_at)
                        VALUES (?, '', ?, ?, 0, ?, 'user_edit', 1, 1, ?, ?, NULL, NULL, '{}', 0, ?)
                    """, (new_id, collection_id, item_id, schema_type, key, value,
                          datetime.now().isoformat()))
                    logger.debug(f"Inserted new metadata record {new_id}")

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to update metadata: {e}")
            return False

    def update_extracted_metadata_batch(
        self, updates: List[Tuple[str, str, str, str]]
    ) -> bool:
        """
        Batch update metadata records.

        Args:
            updates: List of (item_id, schema_type, key, value) tuples

        Returns:
            True if all updates successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                for item_id, schema_type, key, value in updates:
                    # Check if exists
                    cursor.execute("""
                        SELECT id FROM extracted_metadata
                        WHERE item_id = ? AND schema_type = ? AND key = ?
                        ORDER BY version DESC LIMIT 1
                    """, (item_id, schema_type, key))

                    row = cursor.fetchone()
                    if row:
                        cursor.execute("""
                            UPDATE extracted_metadata
                            SET value = ?, created_at = ?, source_label = 'user_edit'
                            WHERE id = ?
                        """, (value, datetime.now().isoformat(), row[0]))
                    else:
                        # Get collection_id from item
                        cursor.execute(
                            "SELECT collection_id FROM collection_items WHERE id = ?",
                            (item_id,)
                        )
                        item_row = cursor.fetchone()
                        collection_id = item_row[0] if item_row else ''

                        new_id = str(uuid.uuid4())
                        cursor.execute("""
                            INSERT INTO extracted_metadata
                            (id, processing_output_id, collection_id, item_id, collection_level,
                             schema_type, source_label, version, schema_version, key, value,
                             confidence, context, custom_fields, indexed, created_at)
                            VALUES (?, '', ?, ?, 0, ?, 'user_edit', 1, 1, ?, ?, NULL, NULL, '{}', 0, ?)
                        """, (new_id, collection_id, item_id, schema_type, key, value,
                              datetime.now().isoformat()))

                conn.commit()
                logger.debug(f"Batch updated {len(updates)} metadata records")
                return True

        except Exception as e:
            logger.error(f"Failed to batch update metadata: {e}")
            return False

    def get_collection_level_metadata(self, collection_id: str,
                                      schema_type: str = None,
                                      key: str = None) -> List[ExtractedMetadata]:
        """Get extracted metadata for collection-level records (node-level metadata)

        This method queries metadata where collection_level=True and item_id=NULL,
        representing collection-wide metadata like catalogues, summaries, or other
        aggregate data that applies to the entire collection rather than specific files.

        Args:
            collection_id: The collection ID to query
            schema_type: Optional filter by schema_type (e.g., 'catalogue', 'collection_summary')
            key: Optional filter by key (e.g., 'text', 'description')

        Returns:
            List of ExtractedMetadata records for collection-level metadata, ordered newest first
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
                           version, schema_version, key, value, confidence, context, custom_fields,
                           indexed, created_at
                    FROM extracted_metadata
                    WHERE collection_id = ? AND collection_level = 1 AND item_id IS NULL
                """
                params = [collection_id]

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                if key:
                    sql += " AND key = ?"
                    params.append(key)

                sql += " ORDER BY version DESC, created_at DESC"  # Newest first
                cursor.execute(sql, params)

                metadata_list = []
                for row in cursor.fetchall():
                    metadata = ExtractedMetadata(
                        id=row[0],
                        processing_output_id=row[1],
                        collection_id=row[2],
                        item_id=row[3],
                        collection_level=bool(row[4]),
                        schema_type=row[5],
                        source_label=row[6],
                        version=row[7],
                        schema_version=row[8],
                        key=row[9],
                        value=row[10],
                        confidence=row[11],
                        context=row[12],
                        custom_fields=self._deserialize_metadata(row[13]),
                        indexed=bool(row[14]),
                        created_at=datetime.fromisoformat(row[15])
                    )
                    metadata_list.append(metadata)

                return metadata_list

        except Exception as e:
            logger.error(f"Failed to get collection-level metadata: {e}")
            return []

    def get_leaf_level_metadata(self, collection_id: str = None, item_id: str = None,
                               schema_type: str = None, key: str = None) -> List[ExtractedMetadata]:
        """Get extracted metadata for file-level records (leaf-level metadata)

        This method queries metadata where collection_level=False and item_id is NOT NULL,
        representing file-specific metadata like transcriptions, enhanced images, or other
        data that applies to individual files rather than the entire collection.

        Args:
            collection_id: Optional collection ID filter
            item_id: Optional specific item ID filter
            schema_type: Optional filter by schema_type (e.g., 'transcription', 'prepared_image')
            key: Optional filter by key (e.g., 'text', 'file_path')

        Returns:
            List of ExtractedMetadata records for file-level data, ordered newest first
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
                           version, schema_version, key, value, confidence, context, custom_fields,
                           indexed, created_at
                    FROM extracted_metadata
                    WHERE collection_level = 0 AND item_id IS NOT NULL
                """
                params = []

                if collection_id:
                    sql += " AND collection_id = ?"
                    params.append(collection_id)

                if item_id:
                    sql += " AND item_id = ?"
                    params.append(item_id)

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                if key:
                    sql += " AND key = ?"
                    params.append(key)

                sql += " ORDER BY version DESC, created_at DESC"  # Newest first

                cursor.execute(sql, params)
                rows = cursor.fetchall()

                metadata_list = []
                for row in rows:
                    metadata = ExtractedMetadata(
                        id=row[0],
                        processing_output_id=row[1],
                        collection_id=row[2],
                        item_id=row[3],
                        collection_level=bool(row[4]),
                        schema_type=row[5],
                        source_label=row[6],
                        version=row[7],
                        schema_version=row[8],
                        key=row[9],
                        value=row[10],
                        confidence=row[11],
                        context=row[12],
                        custom_fields=self._deserialize_metadata(row[13]),
                        indexed=bool(row[14]),
                        created_at=datetime.fromisoformat(row[15])
                    )
                    metadata_list.append(metadata)

                return metadata_list

        except Exception as e:
            logger.error(f"Failed to get leaf-level metadata: {e}")
            return []

    def search_metadata(self, collection_id: str, query: str,
                       schema_type: str = None, source_label: str = None, key: str = None) -> List[ExtractedMetadata]:
        """Search metadata by value (case-insensitive LIKE search)

        Args:
            collection_id: Collection to search within
            query: Search query string
            schema_type: Optional filter by schema type
            source_label: Optional filter by source label
            key: Optional filter by key
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Build query with optional filters
                sql = """
                    SELECT id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
                           version, schema_version, key, value, confidence, context, custom_fields,
                           indexed, created_at
                    FROM extracted_metadata
                    WHERE collection_id = ? AND value LIKE ?
                """
                params = [collection_id, f"%{query}%"]

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                if source_label:
                    sql += " AND source_label = ?"
                    params.append(source_label)

                if key:
                    sql += " AND key = ?"
                    params.append(key)

                sql += " ORDER BY created_at DESC"

                cursor.execute(sql, params)

                metadata_list = []
                for row in cursor.fetchall():
                    metadata = ExtractedMetadata(
                        id=row[0],
                        processing_output_id=row[1],
                        collection_id=row[2],
                        item_id=row[3],
                        collection_level=bool(row[4]),
                        schema_type=row[5],
                        source_label=row[6],
                        version=row[7],
                        schema_version=row[8],
                        key=row[9],
                        value=row[10],
                        confidence=row[11],
                        context=row[12],
                        custom_fields=self._deserialize_metadata(row[13]),
                        indexed=bool(row[14]),
                        created_at=datetime.fromisoformat(row[15])
                    )
                    metadata_list.append(metadata)

                return metadata_list

        except Exception as e:
            logger.error(f"Failed to search metadata: {e}")
            return []

    def get_metadata_by_collection(self, collection_id: str,
                                   schema_type: str = None, source_label: str = None) -> List[ExtractedMetadata]:
        """Get all metadata for a collection, optionally filtered by schema type and source"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
                           version, schema_version, key, value, confidence, context, custom_fields,
                           indexed, created_at
                    FROM extracted_metadata
                    WHERE collection_id = ?
                """
                params = [collection_id]

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                if source_label:
                    sql += " AND source_label = ?"
                    params.append(source_label)

                sql += " ORDER BY created_at DESC"

                cursor.execute(sql, params)

                metadata_list = []
                for row in cursor.fetchall():
                    metadata = ExtractedMetadata(
                        id=row[0],
                        processing_output_id=row[1],
                        collection_id=row[2],
                        item_id=row[3],
                        collection_level=bool(row[4]),
                        schema_type=row[5],
                        source_label=row[6],
                        version=row[7],
                        schema_version=row[8],
                        key=row[9],
                        value=row[10],
                        confidence=row[11],
                        context=row[12],
                        custom_fields=self._deserialize_metadata(row[13]),
                        indexed=bool(row[14]),
                        created_at=datetime.fromisoformat(row[15])
                    )
                    metadata_list.append(metadata)

                return metadata_list

        except Exception as e:
            logger.error(f"Failed to get metadata by collection: {e}")
            return []

    def get_extracted_metadata_by_collection(self, collection_id: str,
                                             schema_type: str = None,
                                             collection_level: bool = None) -> List[ExtractedMetadata]:
        """Get extracted metadata for a collection with optional collection_level filtering

        Args:
            collection_id: The collection ID to query
            schema_type: Optional filter by schema type
            collection_level: Optional filter by collection level (True/False/None for all)

        Returns:
            List of ExtractedMetadata records
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT id, processing_output_id, collection_id, item_id, collection_level, schema_type, source_label,
                           version, schema_version, key, value, confidence, context, custom_fields,
                           indexed, created_at
                    FROM extracted_metadata
                    WHERE collection_id = ?
                """
                params = [collection_id]

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                if collection_level is not None:
                    sql += " AND collection_level = ?"
                    params.append(1 if collection_level else 0)

                sql += " ORDER BY created_at DESC"

                cursor.execute(sql, params)

                metadata_list = []
                for row in cursor.fetchall():
                    metadata = ExtractedMetadata(
                        id=row[0],
                        processing_output_id=row[1],
                        collection_id=row[2],
                        item_id=row[3],
                        collection_level=bool(row[4]),
                        schema_type=row[5],
                        source_label=row[6],
                        version=row[7],
                        schema_version=row[8],
                        key=row[9],
                        value=row[10],
                        confidence=row[11],
                        context=row[12],
                        custom_fields=self._deserialize_metadata(row[13]),
                        indexed=bool(row[14]),
                        created_at=datetime.fromisoformat(row[15])
                    )
                    metadata_list.append(metadata)

                return metadata_list
        except Exception as e:
            logger.error(f"Failed to get extracted metadata by collection: {e}")
            return []

    def get_metadata_keys_for_item(self, item_id: str, schema_type: str = None) -> List[str]:
        """Get all unique metadata keys stored for an item.

        This is used to discover dynamic fields that were extracted by
        processing tools but are not in the predefined schemas.

        Args:
            item_id: The item ID to query
            schema_type: Optional filter by schema type (catalogue, transcription, etc.)

        Returns:
            List of unique metadata keys sorted alphabetically
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT DISTINCT key, schema_type
                    FROM extracted_metadata
                    WHERE item_id = ?
                """
                params = [item_id]

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                sql += " ORDER BY schema_type, key"

                cursor.execute(sql, params)

                return [row[0] for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get metadata keys for item {item_id}: {e}")
            return []

    def get_all_metadata_keys(self, collection_id: str = None, schema_type: str = None) -> List[Dict[str, str]]:
        """Get all unique metadata keys across the library or collection.

        Returns keys with their schema type for dynamic field discovery.

        Args:
            collection_id: Optional filter by collection
            schema_type: Optional filter by schema type

        Returns:
            List of dicts with 'key' and 'schema_type' fields
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT DISTINCT key, schema_type
                    FROM extracted_metadata
                    WHERE 1=1
                """
                params = []

                if collection_id:
                    sql += " AND collection_id = ?"
                    params.append(collection_id)

                if schema_type:
                    sql += " AND schema_type = ?"
                    params.append(schema_type)

                sql += " ORDER BY schema_type, key"

                cursor.execute(sql, params)

                return [{"key": row[0], "schema_type": row[1]} for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get all metadata keys: {e}")
            return []

    def cleanup_processing_outputs(self, item_id: str = None,
                                   collection_id: str = None,
                                   before_date: datetime = None,
                                   dry_run: bool = False) -> Dict[str, Any]:
        """
        Delete processing outputs from filesystem AND database

        Args:
            item_id: Clean up specific item's outputs
            collection_id: Clean up all outputs for a collection
            before_date: Clean up outputs completed before this date
            dry_run: If True, report what would be deleted without actually deleting

        Returns:
            Dict with cleanup stats: {
                'files_deleted': int,
                'dirs_deleted': int,
                'bytes_freed': int,
                'records_deleted': int,
                'errors': List[str],
                'deleted_paths': List[str]
            }
        """
        import shutil

        stats = {
            'files_deleted': 0,
            'dirs_deleted': 0,
            'bytes_freed': 0,
            'records_deleted': 0,
            'errors': [],
            'deleted_paths': []
        }

        try:
            # Get processing results to clean up
            if item_id:
                results = self.get_processing_history(item_id)
                logger.info(f"Cleanup: Found {len(results)} processing results for item {item_id}")
            elif collection_id:
                results = self.get_processing_results_by_collection(collection_id)
                logger.info(f"Cleanup: Found {len(results)} processing results for collection {collection_id}")
            elif before_date:
                results = self.get_processing_results_before_date(before_date)
                logger.info(f"Cleanup: Found {len(results)} processing results before {before_date.isoformat()}")
            else:
                logger.error("Cleanup: Must specify item_id, collection_id, or before_date")
                stats['errors'].append("Must specify item_id, collection_id, or before_date")
                return stats

            if not results:
                logger.info("Cleanup: No processing results found to clean up")
                return stats

            # Delete filesystem outputs
            for result in results:
                for output_path_str in result.output_paths:
                    output_path = Path(output_path_str)

                    if not output_path.exists():
                        logger.debug(f"Cleanup: Output path does not exist, skipping: {output_path}")
                        continue

                    # Calculate size before deletion
                    try:
                        size = sum(f.stat().st_size for f in output_path.rglob('*') if f.is_file())
                    except Exception as e:
                        logger.warning(f"Cleanup: Failed to calculate size for {output_path}: {e}")
                        size = 0

                    # Count files and directories
                    try:
                        file_count = sum(1 for _ in output_path.rglob('*') if _.is_file())
                        dir_count = sum(1 for _ in output_path.rglob('*') if _.is_dir())
                    except Exception as e:
                        logger.warning(f"Cleanup: Failed to count files for {output_path}: {e}")
                        file_count = 0
                        dir_count = 0

                    # Delete the directory
                    if not dry_run:
                        try:
                            shutil.rmtree(output_path)
                            logger.info(f"Cleanup: Deleted output directory: {output_path}")
                            stats['files_deleted'] += file_count
                            stats['dirs_deleted'] += dir_count + 1  # +1 for the output_path itself
                            stats['bytes_freed'] += size
                            stats['deleted_paths'].append(str(output_path))
                        except Exception as e:
                            error_msg = f"Failed to delete {output_path}: {e}"
                            logger.error(f"Cleanup: {error_msg}")
                            stats['errors'].append(error_msg)
                    else:
                        logger.info(f"Cleanup (dry run): Would delete {output_path} ({file_count} files, {size} bytes)")
                        stats['files_deleted'] += file_count
                        stats['dirs_deleted'] += dir_count + 1
                        stats['bytes_freed'] += size
                        stats['deleted_paths'].append(str(output_path))

            # Delete database records
            if not dry_run:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    result_ids = [result.id for result in results]
                    placeholders = ','.join('?' * len(result_ids))

                    cursor.execute(f"""
                        DELETE FROM processing_history
                        WHERE id IN ({placeholders})
                    """, result_ids)

                    stats['records_deleted'] = cursor.rowcount
                    conn.commit()
                    logger.info(f"Cleanup: Deleted {stats['records_deleted']} processing_history records")
            else:
                stats['records_deleted'] = len(results)
                logger.info(f"Cleanup (dry run): Would delete {len(results)} processing_history records")

            return stats

        except Exception as e:
            error_msg = f"Failed to cleanup processing outputs: {e}"
            logger.error(f"Cleanup: {error_msg}")
            stats['errors'].append(error_msg)
            return stats

    def _serialize_metadata(self, metadata: Dict[str, Any]) -> str:
        """Serialize metadata to JSON string"""
        try:
            import json
            return json.dumps(metadata, ensure_ascii=False)
        except Exception:
            return "{}"
    
    def _deserialize_metadata(self, metadata_str: str) -> Dict[str, Any]:
        """Deserialize metadata from JSON string"""
        try:
            import json
            if metadata_str:
                return json.loads(metadata_str)
            return {}
        except Exception:
            return {}
    
    def _serialize_list(self, items: List[str]) -> str:
        """Serialize list to JSON string"""
        try:
            import json
            return json.dumps(items, ensure_ascii=False)
        except Exception:
            return "[]"
    
    def _deserialize_list(self, items_str: str) -> List[str]:
        """Deserialize list from JSON string"""
        try:
            import json
            if items_str:
                return json.loads(items_str)
            return []
        except Exception:
            return []

    # Thumbnail tracking methods

    def add_thumbnail(self, thumbnail: ThumbnailRecord) -> bool:
        """Add a thumbnail record to storage"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO thumbnails
                    (id, source_file_hash, thumbnail_hash, thumbnail_path, size, created_at, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    thumbnail.id,
                    thumbnail.source_file_hash,
                    thumbnail.thumbnail_hash,
                    thumbnail.thumbnail_path,
                    thumbnail.size,
                    thumbnail.created_at.isoformat(),
                    thumbnail.last_accessed.isoformat()
                ))

                conn.commit()
                logger.debug(f"Thumbnail record added: {thumbnail.thumbnail_path}")
                return True

        except Exception as e:
            logger.error(f"Failed to add thumbnail record: {e}")
            return False

    def get_thumbnail(self, source_file_hash: str, size: str) -> Optional[ThumbnailRecord]:
        """Get thumbnail record by source file hash and size"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, source_file_hash, thumbnail_hash, thumbnail_path, size, created_at, last_accessed
                    FROM thumbnails WHERE source_file_hash = ? AND size = ?
                """, (source_file_hash, size))

                row = cursor.fetchone()
                if row:
                    thumbnail = ThumbnailRecord(
                        id=row[0],
                        source_file_hash=row[1],
                        thumbnail_hash=row[2],
                        thumbnail_path=row[3],
                        size=row[4],
                        created_at=datetime.fromisoformat(row[5]),
                        last_accessed=datetime.fromisoformat(row[6])
                    )
                    return thumbnail
                return None

        except Exception as e:
            logger.error(f"Failed to get thumbnail record: {e}")
            return None

    def get_thumbnail_by_id(self, thumbnail_id: str) -> Optional[ThumbnailRecord]:
        """Get thumbnail record by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, source_file_hash, thumbnail_hash, thumbnail_path, size, created_at, last_accessed
                    FROM thumbnails WHERE id = ?
                """, (thumbnail_id,))

                row = cursor.fetchone()
                if row:
                    thumbnail = ThumbnailRecord(
                        id=row[0],
                        source_file_hash=row[1],
                        thumbnail_hash=row[2],
                        thumbnail_path=row[3],
                        size=row[4],
                        created_at=datetime.fromisoformat(row[5]),
                        last_accessed=datetime.fromisoformat(row[6])
                    )
                    return thumbnail
                return None

        except Exception as e:
            logger.error(f"Failed to get thumbnail by ID: {e}")
            return None

    def update_thumbnail_access(self, thumbnail_id: str) -> bool:
        """Update thumbnail last_accessed timestamp"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE thumbnails SET last_accessed = ? WHERE id = ?
                """, (datetime.now().isoformat(), thumbnail_id))

                conn.commit()
                logger.debug(f"Thumbnail access updated: {thumbnail_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to update thumbnail access: {e}")
            return False

    def delete_thumbnail(self, thumbnail_id: str) -> bool:
        """Delete a thumbnail record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("DELETE FROM thumbnails WHERE id = ?", (thumbnail_id,))

                conn.commit()
                logger.debug(f"Thumbnail record deleted: {thumbnail_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete thumbnail record: {e}")
            return False

    def get_thumbnails_by_file_hash(self, source_file_hash: str) -> List[ThumbnailRecord]:
        """Get all thumbnail records for a source file (all sizes)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, source_file_hash, thumbnail_hash, thumbnail_path, size, created_at, last_accessed
                    FROM thumbnails WHERE source_file_hash = ?
                """, (source_file_hash,))

                thumbnails = []
                for row in cursor.fetchall():
                    thumbnail = ThumbnailRecord(
                        id=row[0],
                        source_file_hash=row[1],
                        thumbnail_hash=row[2],
                        thumbnail_path=row[3],
                        size=row[4],
                        created_at=datetime.fromisoformat(row[5]),
                        last_accessed=datetime.fromisoformat(row[6])
                    )
                    thumbnails.append(thumbnail)

                return thumbnails

        except Exception as e:
            logger.error(f"Failed to get thumbnails by file hash: {e}")
            return []

    def count_items_with_file_hash(self, file_hash: str, exclude_collection_id: str = None) -> int:
        """Count how many collection items reference this file_hash

        Args:
            file_hash: The SHA256 hash of the file
            exclude_collection_id: Optional collection ID to exclude from count

        Returns:
            Number of items that reference this file_hash
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if exclude_collection_id:
                    # Count items with this hash EXCLUDING items from specified collection
                    cursor.execute("""
                        SELECT COUNT(*) FROM collection_items
                        WHERE json_extract(metadata, '$.file_hash') = ?
                        AND collection_id != ?
                    """, (file_hash, exclude_collection_id))
                else:
                    # Count all items with this hash
                    cursor.execute("""
                        SELECT COUNT(*) FROM collection_items
                        WHERE json_extract(metadata, '$.file_hash') = ?
                    """, (file_hash,))

                count = cursor.fetchone()[0]
                logger.debug(f"Found {count} items with file_hash {file_hash[:8]}...")
                return count

        except Exception as e:
            logger.error(f"Failed to count items with file hash: {e}")
            return 0

    # Step metadata version tracking methods

    def add_metadata_version(
        self,
        item_id: str,
        step_name: str,
        version: int,
        metadata_snapshot: Dict[str, Any],
        changed_by: str = "tool",
        change_reason: str = "processing_step"
    ) -> bool:
        """Add a metadata version snapshot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                version_id = str(uuid.uuid4())

                cursor.execute("""
                    INSERT INTO step_metadata_versions
                    (id, item_id, step_name, version, changed_at, changed_by, change_reason, metadata_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    version_id,
                    item_id,
                    step_name,
                    version,
                    datetime.now().isoformat(),
                    changed_by,
                    change_reason,
                    self._serialize_metadata(metadata_snapshot)
                ))

                conn.commit()
                logger.debug(f"Added metadata version v{version} for {step_name} on item {item_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to add metadata version: {e}")
            return False

    def get_metadata_versions(
        self,
        item_id: str,
        step_name: str
    ) -> List[Dict[str, Any]]:
        """Get all version snapshots for a step on an item"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, version, changed_at, changed_by, change_reason, metadata_snapshot
                    FROM step_metadata_versions
                    WHERE item_id = ? AND step_name = ?
                    ORDER BY version ASC
                """, (item_id, step_name))

                versions = []
                for row in cursor.fetchall():
                    versions.append({
                        'id': row[0],
                        'version': row[1],
                        'changed_at': row[2],
                        'changed_by': row[3],
                        'change_reason': row[4],
                        'metadata': self._deserialize_metadata(row[5])
                    })

                return versions

        except Exception as e:
            logger.error(f"Failed to get metadata versions: {e}")
            return []

    def get_metadata_version(
        self,
        item_id: str,
        step_name: str,
        version: int
    ) -> Optional[Dict[str, Any]]:
        """Get a specific version snapshot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, version, changed_at, changed_by, change_reason, metadata_snapshot
                    FROM step_metadata_versions
                    WHERE item_id = ? AND step_name = ? AND version = ?
                """, (item_id, step_name, version))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'version': row[1],
                        'changed_at': row[2],
                        'changed_by': row[3],
                        'change_reason': row[4],
                        'metadata': self._deserialize_metadata(row[5])
                    }

                return None

        except Exception as e:
            logger.error(f"Failed to get metadata version: {e}")
            return None

    def get_latest_version_number(
        self,
        item_id: str,
        step_name: str
    ) -> int:
        """Get the latest version number for a step (returns 0 if no versions exist)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT MAX(version)
                    FROM step_metadata_versions
                    WHERE item_id = ? AND step_name = ?
                """, (item_id, step_name))

                result = cursor.fetchone()[0]
                return result if result is not None else 0

        except Exception as e:
            logger.error(f"Failed to get latest version number: {e}")
            return 0

    # Step files methods - for storing step output files in library

    def add_step_file(self, step_file: StepFile) -> bool:
        """Add a step file record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO step_files
                    (id, item_id, collection_id, step_name, source_label, version,
                     file_name, file_path, file_format, file_size, file_hash, mime_type,
                     metadata, is_valid, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    step_file.id,
                    step_file.item_id,
                    step_file.collection_id,
                    step_file.step_name,
                    step_file.source_label,
                    step_file.version,
                    step_file.file_name,
                    step_file.file_path,
                    step_file.file_format,
                    step_file.file_size,
                    step_file.file_hash,
                    step_file.mime_type,
                    self._serialize_metadata(step_file.metadata),
                    1 if step_file.is_valid else 0,
                    step_file.created_at.isoformat(),
                    step_file.updated_at.isoformat()
                ))

                conn.commit()
                logger.debug(f"Step file added: {step_file.step_name} - {step_file.source_label}_v{step_file.version} - {step_file.file_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to add step file: {e}")
            return False

    def get_step_files(self, item_id: str, step_name: str = None,
                       source_label: str = None, version: int = None) -> List[StepFile]:
        """Get step files for an item, optionally filtered by step, source, and version"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                sql = """
                    SELECT id, item_id, collection_id, step_name, source_label, version,
                           file_name, file_path, file_format, file_size, file_hash, mime_type,
                           metadata, is_valid, created_at, updated_at
                    FROM step_files
                    WHERE item_id = ?
                """
                params = [item_id]

                if step_name:
                    sql += " AND step_name = ?"
                    params.append(step_name)

                if source_label:
                    sql += " AND source_label = ?"
                    params.append(source_label)

                if version is not None:
                    sql += " AND version = ?"
                    params.append(version)

                sql += " ORDER BY created_at ASC"

                cursor.execute(sql, params)

                step_files = []
                for row in cursor.fetchall():
                    step_file = StepFile(
                        id=row[0],
                        item_id=row[1],
                        collection_id=row[2],
                        step_name=row[3],
                        source_label=row[4],
                        version=row[5],
                        file_name=row[6],
                        file_path=row[7],
                        file_format=row[8],
                        file_size=row[9],
                        file_hash=row[10],
                        mime_type=row[11],
                        metadata=self._deserialize_metadata(row[12]),
                        is_valid=bool(row[13]),
                        created_at=datetime.fromisoformat(row[14]),
                        updated_at=datetime.fromisoformat(row[15])
                    )
                    step_files.append(step_file)

                return step_files

        except Exception as e:
            logger.error(f"Failed to get step files: {e}")
            return []

    def get_step_file_by_id(self, file_id: str) -> Optional[StepFile]:
        """Get a specific step file by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, item_id, collection_id, step_name, source_label, version,
                           file_name, file_path, file_format, file_size, file_hash, mime_type,
                           metadata, is_valid, created_at, updated_at
                    FROM step_files
                    WHERE id = ?
                """, (file_id,))

                row = cursor.fetchone()
                if not row:
                    return None

                step_file = StepFile(
                    id=row[0],
                    item_id=row[1],
                    collection_id=row[2],
                    step_name=row[3],
                    source_label=row[4],
                    version=row[5],
                    file_name=row[6],
                    file_path=row[7],
                    file_format=row[8],
                    file_size=row[9],
                    file_hash=row[10],
                    mime_type=row[11],
                    metadata=self._deserialize_metadata(row[12]),
                    is_valid=bool(row[13]),
                    created_at=datetime.fromisoformat(row[14]),
                    updated_at=datetime.fromisoformat(row[15])
                )

                return step_file

        except Exception as e:
            logger.error(f"Failed to get step file by ID: {e}")
            return None

    def get_latest_step_file_version(self, item_id: str, step_name: str, source_label: str) -> int:
        """Get the latest version number for a step file (returns 0 if no versions exist)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT MAX(version)
                    FROM step_files
                    WHERE item_id = ? AND step_name = ? AND source_label = ?
                """, (item_id, step_name, source_label))

                result = cursor.fetchone()[0]
                return result if result is not None else 0

        except Exception as e:
            logger.error(f"Failed to get latest step file version: {e}")
            return 0

    def update_step_file(self, step_file: StepFile) -> bool:
        """Update a step file record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                step_file.updated_at = datetime.now()

                cursor.execute("""
                    UPDATE step_files
                    SET file_size = ?, file_hash = ?, mime_type = ?, metadata = ?,
                        is_valid = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    step_file.file_size,
                    step_file.file_hash,
                    step_file.mime_type,
                    self._serialize_metadata(step_file.metadata),
                    1 if step_file.is_valid else 0,
                    step_file.updated_at.isoformat(),
                    step_file.id
                ))

                conn.commit()
                logger.debug(f"Step file updated: {step_file.id}")
                return True

        except Exception as e:
            logger.error(f"Failed to update step file: {e}")
            return False

    def delete_step_file(self, file_id: str) -> bool:
        """Delete a step file record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("DELETE FROM step_files WHERE id = ?", (file_id,))

                conn.commit()
                logger.debug(f"Step file deleted: {file_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete step file: {e}")
            return False

    def get_step_files_by_collection(self, collection_id: str) -> List[StepFile]:
        """Get all step files for a collection"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, item_id, collection_id, step_name, source_label, version,
                           file_name, file_path, file_format, file_size, file_hash, mime_type,
                           metadata, is_valid, created_at, updated_at
                    FROM step_files
                    WHERE collection_id = ?
                    ORDER BY created_at DESC
                """, (collection_id,))

                step_files = []
                for row in cursor.fetchall():
                    step_file = StepFile(
                        id=row[0],
                        item_id=row[1],
                        collection_id=row[2],
                        step_name=row[3],
                        source_label=row[4],
                        version=row[5],
                        file_name=row[6],
                        file_path=row[7],
                        file_format=row[8],
                        file_size=row[9],
                        file_hash=row[10],
                        mime_type=row[11],
                        metadata=self._deserialize_metadata(row[12]),
                        is_valid=bool(row[13]),
                        created_at=datetime.fromisoformat(row[14]),
                        updated_at=datetime.fromisoformat(row[15])
                    )
                    step_files.append(step_file)

                return step_files

        except Exception as e:
            logger.error(f"Failed to get step files by collection: {e}")
            return []

    # FTS5 Search Index methods

    def index_metadata_for_search(self, metadata: ExtractedMetadata) -> bool:
        """Add metadata content to FTS5 search index"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Only index if not already indexed and value contains text
                if metadata.indexed or not metadata.value:
                    return True

                cursor.execute("""
                    INSERT INTO search_index
                    (metadata_id, collection_id, item_id, schema_type, source_label, version, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    metadata.id,
                    metadata.collection_id,
                    metadata.item_id,
                    metadata.schema_type,
                    metadata.source_label,
                    metadata.version,
                    metadata.value
                ))

                # Mark as indexed in extracted_metadata table
                cursor.execute("""
                    UPDATE extracted_metadata SET indexed = 1 WHERE id = ?
                """, (metadata.id,))

                conn.commit()
                logger.debug(f"Metadata indexed for search: {metadata.id}")
                return True

        except Exception as e:
            logger.error(f"Failed to index metadata for search: {e}")
            return False

    def remove_metadata_from_index(self, metadata_id: str) -> bool:
        """Remove metadata from FTS5 search index"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    DELETE FROM search_index WHERE metadata_id = ?
                """, (metadata_id,))

                # Mark as not indexed
                cursor.execute("""
                    UPDATE extracted_metadata SET indexed = 0 WHERE id = ?
                """, (metadata_id,))

                conn.commit()
                logger.debug(f"Metadata removed from search index: {metadata_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to remove metadata from search index: {e}")
            return False

    def rebuild_search_index(self, collection_id: str = None) -> bool:
        """Rebuild FTS5 search index for all or specific collection

        Args:
            collection_id: If provided, only rebuild for this collection
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Clear existing index
                if collection_id:
                    cursor.execute("DELETE FROM search_index WHERE collection_id = ?", (collection_id,))
                    cursor.execute("UPDATE extracted_metadata SET indexed = 0 WHERE collection_id = ?", (collection_id,))
                else:
                    cursor.execute("DELETE FROM search_index")
                    cursor.execute("UPDATE extracted_metadata SET indexed = 0")

                # Get all searchable metadata (transcriptions, translations, catalogues)
                searchable_types = ['transcription', 'translation', 'catalogue', 'named_entities']

                if collection_id:
                    placeholders = ','.join('?' * len(searchable_types))
                    cursor.execute(f"""
                        SELECT id, collection_id, item_id, schema_type, source_label, version, value
                        FROM extracted_metadata
                        WHERE collection_id = ? AND schema_type IN ({placeholders}) AND value IS NOT NULL AND value != ''
                    """, (collection_id, *searchable_types))
                else:
                    placeholders = ','.join('?' * len(searchable_types))
                    cursor.execute(f"""
                        SELECT id, collection_id, item_id, schema_type, source_label, version, value
                        FROM extracted_metadata
                        WHERE schema_type IN ({placeholders}) AND value IS NOT NULL AND value != ''
                    """, searchable_types)

                # Batch insert into FTS5 index
                rows = cursor.fetchall()
                if rows:
                    cursor.executemany("""
                        INSERT INTO search_index
                        (metadata_id, collection_id, item_id, schema_type, source_label, version, content)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, rows)

                    # Mark all as indexed
                    metadata_ids = [row[0] for row in rows]
                    placeholders = ','.join('?' * len(metadata_ids))
                    cursor.execute(f"""
                        UPDATE extracted_metadata SET indexed = 1 WHERE id IN ({placeholders})
                    """, metadata_ids)

                conn.commit()
                logger.info(f"Search index rebuilt: {len(rows)} metadata records indexed" +
                           (f" for collection {collection_id}" if collection_id else ""))
                return True

        except Exception as e:
            logger.error(f"Failed to rebuild search index: {e}")
            return False

    def get_search_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the search index"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                stats = {}

                # Total indexed items
                cursor.execute("SELECT COUNT(*) FROM search_index")
                stats['total_indexed'] = cursor.fetchone()[0]

                # By schema type
                cursor.execute("""
                    SELECT schema_type, COUNT(*)
                    FROM search_index
                    GROUP BY schema_type
                """)
                stats['by_schema_type'] = dict(cursor.fetchall())

                # By collection
                cursor.execute("""
                    SELECT collection_id, COUNT(*)
                    FROM search_index
                    GROUP BY collection_id
                """)
                stats['by_collection'] = dict(cursor.fetchall())

                # Unindexed count
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM extracted_metadata
                    WHERE indexed = 0 AND schema_type IN ('transcription', 'translation', 'catalogue', 'named_entities')
                """)
                stats['unindexed_count'] = cursor.fetchone()[0]

                return stats

        except Exception as e:
            logger.error(f"Failed to get search index stats: {e}")
            return {}

    # ===== TIMELINE EVENT METHODS =====

    def add_timeline_event(self, event: 'TimelineEvent') -> bool:
        """Add a timeline event"""
        try:
            from fichero.library.models import TimelineEvent

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO timeline_events
                    (id, entity_type, entity_id, event_type, event_category, actor, description, metadata, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.id,
                    event.entity_type,
                    event.entity_id,
                    event.event_type,
                    event.event_category,
                    event.actor,
                    event.description,
                    json.dumps(event.metadata),
                    event.timestamp.isoformat()
                ))
                conn.commit()
                logger.debug(f"Added timeline event {event.event_type} for {event.entity_type}:{event.entity_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to add timeline event: {e}")
            return False

    def get_timeline_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_type: Optional[str] = None,
        event_category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List['TimelineEvent']:
        """Get timeline events with optional filters"""
        try:
            from fichero.library.models import TimelineEvent

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Build query
                where_clauses = []
                params = []

                if entity_type:
                    where_clauses.append("entity_type = ?")
                    params.append(entity_type)
                if entity_id:
                    where_clauses.append("entity_id = ?")
                    params.append(entity_id)
                if event_type:
                    where_clauses.append("event_type = ?")
                    params.append(event_type)
                if event_category:
                    where_clauses.append("event_category = ?")
                    params.append(event_category)

                where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

                cursor.execute(f"""
                    SELECT id, entity_type, entity_id, event_type, event_category,
                           actor, description, metadata, timestamp
                    FROM timeline_events
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])

                events = []
                for row in cursor.fetchall():
                    event = TimelineEvent(
                        id=row[0],
                        entity_type=row[1],
                        entity_id=row[2],
                        event_type=row[3],
                        event_category=row[4],
                        actor=row[5],
                        description=row[6],
                        metadata=json.loads(row[7]) if row[7] else {},
                        timestamp=datetime.fromisoformat(row[8])
                    )
                    events.append(event)

                return events

        except Exception as e:
            logger.error(f"Failed to get timeline events: {e}")
            return []

    def get_item_timeline(self, item_id: str, limit: int = 50) -> List['TimelineEvent']:
        """Get timeline events for a specific item"""
        return self.get_timeline_events(
            entity_type="item",
            entity_id=item_id,
            limit=limit
        )

    def get_collection_timeline(self, collection_id: str, limit: int = 50) -> List['TimelineEvent']:
        """Get timeline events for a specific collection"""
        return self.get_timeline_events(
            entity_type="collection",
            entity_id=collection_id,
            limit=limit
        )

    def delete_timeline_events(self, entity_type: str, entity_id: str) -> bool:
        """Delete all timeline events for an entity"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM timeline_events
                    WHERE entity_type = ? AND entity_id = ?
                """, (entity_type, entity_id))
                conn.commit()
                logger.info(f"Deleted timeline events for {entity_type}:{entity_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete timeline events: {e}")
            return False 