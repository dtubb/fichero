"""
SQLite Storage Backend for Fichero Library

Handles persistent storage of collections, items, and processing history.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

try:
    from fichero.library.models import Collection, CollectionItem, ProcessingResult, ExternalPath
except ImportError:
    try:
        # Fallback for direct testing
        from .models import Collection, CollectionItem, ProcessingResult, ExternalPath
    except ImportError:
        # Direct import for testing
        import models
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        ExternalPath = models.ExternalPath

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
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY (collection_id) REFERENCES collections(id)
                    )
                """)
                
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
                
                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_collection_items_collection_id ON collection_items(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_history_item_id ON processing_history(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_paths_collection_id ON external_paths(collection_id)")
                
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
                conn.isolation_level = None  # Enable autocommit mode
                cursor = conn.cursor()
                
                # Start transaction
                cursor.execute("BEGIN IMMEDIATE")
                
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
                logger.debug(f"Collection added to storage: {collection.name}")
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, name, type, source_path, local_path, created_at, updated_at, sort_order, metadata
                    FROM collections WHERE id = ?
                """, (collection_id,))

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
    
    def add_collection_item(self, item: CollectionItem) -> bool:
        """Add an item to a collection"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO collection_items 
                    (id, collection_id, type, source_path, local_path, storage_type, name, status, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.id,
                    item.collection_id,
                    item.type,
                    item.source_path,
                    item.local_path,
                    item.storage_type,
                    item.name,
                    item.status,
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
    
    def get_collection_items(self, collection_id: str) -> List[CollectionItem]:
        """Get all items in a collection"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, collection_id, type, source_path, local_path, storage_type, name, status, created_at, updated_at, metadata
                    FROM collection_items WHERE collection_id = ? ORDER BY created_at DESC
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
                        created_at=datetime.fromisoformat(row[8]),
                        updated_at=datetime.fromisoformat(row[9]),
                        metadata=self._deserialize_metadata(row[10])
                    )
                    items.append(item)
                
                return items
                
        except Exception as e:
            logger.error(f"Failed to get collection items: {e}")
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