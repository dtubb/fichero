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
    from fichero.library.models import Collection, CollectionItem, ProcessingResult, ExternalPath, ThumbnailRecord
except ImportError:
    try:
        # Fallback for direct testing
        from .models import Collection, CollectionItem, ProcessingResult, ExternalPath, ThumbnailRecord
    except ImportError:
        # Direct import for testing
        import models
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        ExternalPath = models.ExternalPath
        ThumbnailRecord = models.ThumbnailRecord

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

                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_collection_items_collection_id ON collection_items(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_history_item_id ON processing_history(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_paths_collection_id ON external_paths(collection_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_thumbnails_source_hash ON thumbnails(source_file_hash, size)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_thumbnails_hash ON thumbnails(thumbnail_hash)")
                
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