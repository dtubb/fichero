"""
DEVONthink Integration.

Provides integration with DEVONthink Pro for document management:
- List databases and documents
- Import documents from DEVONthink
- Export documents to DEVONthink
- Search within DEVONthink

Uses AppleScript for communication with DEVONthink.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fichero_server.integrations.base import AppIntegration, ImportedItem, escape_applescript

logger = logging.getLogger(__name__)


class DEVONthinkIntegration(AppIntegration):
    """Integration with DEVONthink Pro."""

    @property
    def name(self) -> str:
        return "DEVONthink"

    @property
    def bundle_id(self) -> str:
        return "com.devon-technologies.think3"

    async def list_databases(self) -> list[dict]:
        """List all open DEVONthink databases."""
        if not self.is_available:
            return []

        script = """
        tell application "DEVONthink 3"
            set dbList to {}
            repeat with db in databases
                set dbInfo to {|name|:name of db, |uuid|:uuid of db, |path|:path of db}
                set end of dbList to dbInfo
            end repeat
            return dbList
        end tell
        """

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to list DEVONthink databases: {result}")
            return []

        # Parse AppleScript result (simplified - real implementation would parse properly)
        databases = []
        try:
            # Result format: {{name:"DB1", uuid:"xxx", path:"/path"}, ...}
            # This is a simplified parser
            if result:
                databases = self._parse_applescript_records(result)
        except Exception as e:
            logger.error(f"Error parsing DEVONthink databases: {e}")

        return databases

    async def list_items(
        self,
        limit: int = 100,
        search: Optional[str] = None,
        item_type: Optional[str] = None,
        database: Optional[str] = None,
    ) -> list[ImportedItem]:
        """
        List documents from DEVONthink.

        Args:
            limit: Maximum number of items to return
            search: Optional search query
            item_type: Filter by type (pdf, markdown, html, etc.)
            database: Specific database to search in
        """
        if not self.is_available:
            return []

        limit = int(limit)

        if search:
            # Search query
            search_escaped = escape_applescript(search)
            script = f'''
            tell application "DEVONthink 3"
                set searchResults to search "{search_escaped}" in databases
                set resultList to {{}}
                set counter to 0
                repeat with doc in searchResults
                    if counter >= {limit} then exit repeat
                    set docInfo to {{|uuid|:uuid of doc, |name|:name of doc, |type|:type of doc as string, |path|:path of doc, |url|:reference URL of doc}}
                    set end of resultList to docInfo
                    set counter to counter + 1
                end repeat
                return resultList
            end tell
            '''
        else:
            # List recent items
            db_clause = (
                f'database "{escape_applescript(database)}"'
                if database
                else "current database"
            )
            script = f"""
            tell application "DEVONthink 3"
                set docs to contents of {db_clause}
                set resultList to {{}}
                set counter to 0
                repeat with doc in docs
                    if counter >= {limit} then exit repeat
                    set docInfo to {{|uuid|:uuid of doc, |name|:name of doc, |type|:type of doc as string, |path|:path of doc, |url|:reference URL of doc}}
                    set end of resultList to docInfo
                    set counter to counter + 1
                end repeat
                return resultList
            end tell
            """

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to list DEVONthink items: {result}")
            return []

        items = []
        try:
            records = self._parse_applescript_records(result)
            for record in records:
                items.append(
                    ImportedItem(
                        external_id=record.get("uuid", ""),
                        name=record.get("name", "Untitled"),
                        source_app="DEVONthink",
                        item_type=record.get("type", "unknown"),
                        file_path=Path(record["path"]) if record.get("path") else None,
                        url=record.get("url"),
                        metadata={"devonthink_type": record.get("type")},
                    )
                )
        except Exception as e:
            logger.error(f"Error parsing DEVONthink items: {e}")

        return items

    async def get_item(self, external_id: str) -> Optional[ImportedItem]:
        """Get a specific document by UUID."""
        if not self.is_available:
            return None

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "DEVONthink 3"
            set doc to get record with uuid "{external_id_escaped}"
            if doc is not missing value then
                return {{|uuid|:uuid of doc, |name|:name of doc, |type|:type of doc as string, |path|:path of doc, |url|:reference URL of doc, |content|:plain text of doc, |created|:creation date of doc as string, |modified|:modification date of doc as string}}
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to get DEVONthink item {external_id}: {result}")
            return None

        try:
            records = self._parse_applescript_records(result)
            if records:
                record = records[0]
                return ImportedItem(
                    external_id=record.get("uuid", external_id),
                    name=record.get("name", "Untitled"),
                    source_app="DEVONthink",
                    item_type=record.get("type", "unknown"),
                    file_path=Path(record["path"]) if record.get("path") else None,
                    url=record.get("url"),
                    content=record.get("content"),
                    metadata={"devonthink_type": record.get("type")},
                    created_at=self._parse_date(record.get("created")),
                    modified_at=self._parse_date(record.get("modified")),
                )
        except Exception as e:
            logger.error(f"Error parsing DEVONthink item: {e}")

        return None

    async def import_item(
        self, external_id: str, target_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Import a document from DEVONthink.

        Exports the document from DEVONthink to the specified path.
        """
        if not self.is_available:
            return None

        item = await self.get_item(external_id)
        if not item:
            return None

        # If item has a file path, we can copy it directly
        if item.file_path and item.file_path.exists():
            if target_path:
                shutil.copy2(item.file_path, target_path)
                return target_path
            return item.file_path

        # Otherwise, export via AppleScript
        if target_path:
            external_id_escaped = escape_applescript(external_id)
            target_path_escaped = escape_applescript(str(target_path))
            script = f'''
            tell application "DEVONthink 3"
                set doc to get record with uuid "{external_id_escaped}"
                if doc is not missing value then
                    export record doc to POSIX file "{target_path_escaped}"
                    return "success"
                end if
            end tell
            '''

            success, result = self.run_applescript(script)
            if success and result == "success":
                return target_path

        return None

    async def export_item(
        self,
        file_path: Path,
        metadata: Optional[dict] = None,
        database: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Optional[str]:
        """
        Export a file to DEVONthink.

        Args:
            file_path: Path to the file to import
            metadata: Optional metadata (name, tags, etc.)
            database: Target database name
            group: Target group/folder path

        Returns:
            UUID of the created record, or None if failed
        """
        if not self.is_available:
            return None

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Build import script
        db_clause = (
            f'database "{escape_applescript(database)}"'
            if database
            else "current database"
        )
        group_clause = ""
        if group:
            group_clause = f"to incoming group of {db_clause}"
        else:
            group_clause = f"to incoming group of {db_clause}"

        name = metadata.get("name", file_path.name) if metadata else file_path.name
        file_path_escaped = escape_applescript(str(file_path))
        name_escaped = escape_applescript(str(name))

        script = f'''
        tell application "DEVONthink 3"
            set importedDoc to import POSIX file "{file_path_escaped}" {group_clause}
            if importedDoc is not missing value then
                set name of importedDoc to "{name_escaped}"
                return uuid of importedDoc
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        if success and result:
            logger.info(f"Exported {file_path.name} to DEVONthink: {result}")
            return result

        logger.error(f"Failed to export to DEVONthink: {result}")
        return None

    async def open_item(self, external_id: str) -> bool:
        """Open an item in DEVONthink."""
        if not self.is_available:
            return False

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "DEVONthink 3"
            set doc to get record with uuid "{external_id_escaped}"
            if doc is not missing value then
                open window for record doc
                activate
                return "success"
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        return success and result == "success"

    def _parse_applescript_records(self, result: str) -> list[dict]:
        """Parse AppleScript record list output."""
        # This is a simplified parser - real implementation would be more robust
        records = []

        if not result or result == "{}":
            return records

        # Handle single record vs list
        result = result.strip()
        if result.startswith("{{"):
            # List of records
            result = result[1:-1]  # Remove outer braces

        # Very basic parsing - production code would use proper parsing
        try:
            # Split by record boundaries
            parts = result.split("}, {")
            for part in parts:
                part = part.strip("{} ")
                record = {}
                # Parse key:value pairs
                for item in part.split(", "):
                    if ":" in item:
                        key, value = item.split(":", 1)
                        key = key.strip("|").strip()
                        value = value.strip().strip('"')
                        record[key] = value
                if record:
                    records.append(record)
        except Exception as e:
            logger.error(f"Error parsing AppleScript result: {e}")

        return records

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse a date string from AppleScript."""
        if not date_str:
            return None
        try:
            # AppleScript date format varies, try common formats
            for fmt in ["%A, %B %d, %Y at %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None
