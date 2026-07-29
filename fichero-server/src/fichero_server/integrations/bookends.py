"""
Bookends Integration.

Provides integration with Bookends reference manager:
- List references and attachments
- Import references from Bookends
- Export references to Bookends
- Search within Bookends library

Uses AppleScript for communication with Bookends.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from fichero_server.integrations.base import AppIntegration, ImportedItem, escape_applescript

logger = logging.getLogger(__name__)


class BookendsIntegration(AppIntegration):
    """Integration with Bookends reference manager."""

    @property
    def name(self) -> str:
        return "Bookends"

    @property
    def bundle_id(self) -> str:
        return "com.sonnysoftware.bookends2"

    async def list_libraries(self) -> list[dict]:
        """List open Bookends libraries."""
        if not self.is_available:
            return []

        script = """
        tell application "Bookends"
            set libList to {}
            repeat with lib in library windows
                set libInfo to {|name|:name of lib, |path|:path of lib}
                set end of libList to libInfo
            end repeat
            return libList
        end tell
        """

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to list Bookends libraries: {result}")
            return []

        return self._parse_applescript_records(result)

    async def list_items(
        self,
        limit: int = 100,
        search: Optional[str] = None,
        item_type: Optional[str] = None,
    ) -> list[ImportedItem]:
        """
        List references from Bookends.

        Args:
            limit: Maximum number of items to return
            search: Optional search query (searches all fields)
            item_type: Filter by reference type (article, book, etc.)
        """
        if not self.is_available:
            return []

        limit = int(limit)

        if search:
            # Search for references
            search_escaped = escape_applescript(search)
            script = f'''
            tell application "Bookends"
                set refIDs to «event ToySRFLD» "{search_escaped}" given «class TEFN»:"any"
                set resultList to {{}}
                set counter to 0
                repeat with refID in refIDs
                    if counter >= {limit} then exit repeat
                    set refData to «event ToySGUID» refID
                    set refInfo to {{|id|:refID as string, |title|:«event ToySRFLD» refID given «class TEFN»:"title", |authors|:«event ToySRFLD» refID given «class TEFN»:"authors", |type|:«event ToySRFLD» refID given «class TEFN»:"type", |year|:«event ToySRFLD» refID given «class TEFN»:"date"}}
                    set end of resultList to refInfo
                    set counter to counter + 1
                end repeat
                return resultList
            end tell
            '''
        else:
            # Get recent references
            script = f"""
            tell application "Bookends"
                set refIDs to «event ToySRFLD» "*" given «class TEFN»:"any"
                set resultList to {{}}
                set counter to 0
                repeat with refID in refIDs
                    if counter >= {limit} then exit repeat
                    set refInfo to {{|id|:refID as string, |title|:«event ToySRFLD» refID given «class TEFN»:"title", |authors|:«event ToySRFLD» refID given «class TEFN»:"authors", |type|:«event ToySRFLD» refID given «class TEFN»:"type", |year|:«event ToySRFLD» refID given «class TEFN»:"date"}}
                    set end of resultList to refInfo
                    set counter to counter + 1
                end repeat
                return resultList
            end tell
            """

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to list Bookends items: {result}")
            return []

        items = []
        try:
            records = self._parse_applescript_records(result)
            for record in records:
                # Format author list for display
                authors = record.get("authors", "Unknown")
                title = record.get("title", "Untitled")
                year = record.get("year", "")

                display_name = (
                    f"{authors} ({year}) - {title}" if year else f"{authors} - {title}"
                )

                items.append(
                    ImportedItem(
                        external_id=record.get("id", ""),
                        name=display_name,
                        source_app="Bookends",
                        item_type=f"reference:{record.get('type', 'unknown')}",
                        metadata={
                            "title": title,
                            "authors": authors,
                            "year": year,
                            "reference_type": record.get("type", "unknown"),
                        },
                    )
                )
        except Exception as e:
            logger.error(f"Error parsing Bookends items: {e}")

        return items

    async def get_item(self, external_id: str) -> Optional[ImportedItem]:
        """Get a specific reference by ID."""
        if not self.is_available:
            return None

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Bookends"
            set refID to "{external_id_escaped}"
            set refInfo to {{|id|:refID, |title|:«event ToySRFLD» refID given «class TEFN»:"title", |authors|:«event ToySRFLD» refID given «class TEFN»:"authors", |type|:«event ToySRFLD» refID given «class TEFN»:"type", |year|:«event ToySRFLD» refID given «class TEFN»:"date", |abstract|:«event ToySRFLD» refID given «class TEFN»:"abstract", |journal|:«event ToySRFLD» refID given «class TEFN»:"journal", |volume|:«event ToySRFLD» refID given «class TEFN»:"volume", |pages|:«event ToySRFLD» refID given «class TEFN»:"pages", |doi|:«event ToySRFLD» refID given «class TEFN»:"doi", |url|:«event ToySRFLD» refID given «class TEFN»:"url", |attachments|:«event ToySRFLD» refID given «class TEFN»:"attachments"}}
            return refInfo
        end tell
        '''

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to get Bookends item {external_id}: {result}")
            return None

        try:
            records = self._parse_applescript_records(result)
            if records:
                record = records[0]
                authors = record.get("authors", "Unknown")
                title = record.get("title", "Untitled")
                year = record.get("year", "")

                display_name = (
                    f"{authors} ({year}) - {title}" if year else f"{authors} - {title}"
                )

                # Parse attachment path if present
                attachment_path = None
                if record.get("attachments"):
                    # Bookends returns colon-separated paths
                    attachments = record["attachments"].split(":")
                    if attachments:
                        # Convert HFS path to POSIX
                        attachment_path = Path(attachments[0].replace(":", "/"))

                return ImportedItem(
                    external_id=external_id,
                    name=display_name,
                    source_app="Bookends",
                    item_type=f"reference:{record.get('type', 'unknown')}",
                    file_path=attachment_path,
                    url=record.get("url") or record.get("doi"),
                    content=record.get("abstract"),
                    metadata={
                        "title": title,
                        "authors": authors,
                        "year": year,
                        "reference_type": record.get("type", "unknown"),
                        "journal": record.get("journal"),
                        "volume": record.get("volume"),
                        "pages": record.get("pages"),
                        "doi": record.get("doi"),
                        "abstract": record.get("abstract"),
                    },
                )
        except Exception as e:
            logger.error(f"Error parsing Bookends item: {e}")

        return None

    async def import_item(
        self, external_id: str, target_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Import a reference's attachment from Bookends.

        Returns the path to the PDF or other attachment file.
        """
        if not self.is_available:
            return None

        item = await self.get_item(external_id)
        if not item:
            return None

        # If item has an attachment, copy it
        if item.file_path and item.file_path.exists():
            if target_path:
                shutil.copy2(item.file_path, target_path)
                return target_path
            return item.file_path

        # Try to get the attachment path via AppleScript
        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Bookends"
            set attachPath to «event ToySRFLD» "{external_id_escaped}" given «class TEFN»:"attachments"
            return attachPath
        end tell
        '''

        success, result = self.run_applescript(script)
        if success and result:
            # Convert HFS path to POSIX if needed
            source_path = Path(result.replace(":", "/"))
            if source_path.exists():
                if target_path:
                    shutil.copy2(source_path, target_path)
                    return target_path
                return source_path

        return None

    async def export_item(
        self, file_path: Path, metadata: Optional[dict] = None
    ) -> Optional[str]:
        """
        Export a file to Bookends as a new reference.

        The file will be added as an attachment to a new reference.
        Metadata should include reference fields like title, authors, etc.
        """
        if not self.is_available:
            return None

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Build the reference data
        title = metadata.get("title", file_path.stem) if metadata else file_path.stem
        authors = metadata.get("authors", "") if metadata else ""
        ref_type = metadata.get("type", "0") if metadata else "0"  # 0 = Generic
        title_escaped = escape_applescript(str(title))
        authors_escaped = escape_applescript(str(authors))
        ref_type_escaped = escape_applescript(str(ref_type))
        file_path_escaped = escape_applescript(str(file_path))

        # Create reference and attach file
        script = f'''
        tell application "Bookends"
            set newRef to «event ToySADDA» {{«class TEFN»:"title", «class TEVA»:"{title_escaped}"}}
            if "{authors_escaped}" is not "" then
                «event ToySRFLD» newRef given «class TEFN»:"authors", «class TEVA»:"{authors_escaped}"
            end if
            «event ToySRFLD» newRef given «class TEFN»:"type", «class TEVA»:"{ref_type_escaped}"
            «event ToySATTA» newRef given «class DEST»:POSIX file "{file_path_escaped}"
            return newRef as string
        end tell
        '''

        success, result = self.run_applescript(script)
        if success and result:
            logger.info(f"Exported {file_path.name} to Bookends: {result}")
            return result

        logger.error(f"Failed to export to Bookends: {result}")
        return None

    async def get_citation(self, external_id: str, style: str = "APA") -> Optional[str]:
        """Get a formatted citation for a reference."""
        if not self.is_available:
            return None

        external_id_escaped = escape_applescript(external_id)
        style_escaped = escape_applescript(style)
        script = f'''
        tell application "Bookends"
            set citation to «event ToySFCIT» "{external_id_escaped}" given «class STYL»:"{style_escaped}"
            return citation
        end tell
        '''

        success, result = self.run_applescript(script)
        if success:
            return result
        return None

    async def open_item(self, external_id: str) -> bool:
        """Open a reference in Bookends."""
        if not self.is_available:
            return False

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Bookends"
            «event ToySGOTO» "{external_id_escaped}"
            activate
        end tell
        '''

        success, _ = self.run_applescript(script)
        return success

    def _parse_applescript_records(self, result: str) -> list[dict]:
        """Parse AppleScript record list output."""
        records = []

        if not result or result == "{}":
            return records

        result = result.strip()
        if result.startswith("{{"):
            result = result[1:-1]

        try:
            parts = result.split("}, {")
            for part in parts:
                part = part.strip("{} ")
                record = {}
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
