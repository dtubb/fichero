"""
Tinderbox Integration.

Provides integration with Tinderbox for note-taking and information management:
- List documents and notes
- Import notes from Tinderbox
- Export notes to Tinderbox
- Search within Tinderbox documents

Uses AppleScript for communication with Tinderbox.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fichero_server.integrations.base import AppIntegration, ImportedItem, escape_applescript

logger = logging.getLogger(__name__)


class TinderboxIntegration(AppIntegration):
    """Integration with Tinderbox note-taking application."""

    @property
    def name(self) -> str:
        return "Tinderbox"

    @property
    def bundle_id(self) -> str:
        return "com.eastgate.Tinderbox"

    async def list_documents(self) -> list[dict]:
        """List open Tinderbox documents."""
        if not self.is_available:
            return []

        script = """
        tell application "Tinderbox 9"
            set docList to {}
            repeat with doc in documents
                set docInfo to {|name|:name of doc, |path|:path of doc}
                set end of docList to docInfo
            end repeat
            return docList
        end tell
        """

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to list Tinderbox documents: {result}")
            return []

        return self._parse_applescript_records(result)

    async def list_items(
        self,
        limit: int = 100,
        search: Optional[str] = None,
        item_type: Optional[str] = None,
        container: Optional[str] = None,
    ) -> list[ImportedItem]:
        """
        List notes from Tinderbox.

        Args:
            limit: Maximum number of items to return
            search: Optional search query (searches name and text)
            item_type: Filter by prototype name
            container: Specific container path to list from
        """
        if not self.is_available:
            return []

        limit = int(limit)

        if search:
            # Search for notes matching query
            search_escaped = escape_applescript(search)
            script = f'''
            tell application "Tinderbox 9"
                set resultList to {{}}
                set counter to 0
                repeat with doc in documents
                    set matchingNotes to find doc query "$Name.contains(\\"{search_escaped}\\") | $Text.contains(\\"{search_escaped}\\")"
                    repeat with n in matchingNotes
                        if counter >= {limit} then exit repeat
                        set noteInfo to {{|id|:id of n, |name|:name of n, |path|:path of n, |prototype|:name of prototype of n, |created|:created of n as string, |modified|:modified of n as string}}
                        set end of resultList to noteInfo
                        set counter to counter + 1
                    end repeat
                    if counter >= {limit} then exit repeat
                end repeat
                return resultList
            end tell
            '''
        elif container:
            # List notes in specific container
            container_escaped = escape_applescript(container)
            script = f'''
            tell application "Tinderbox 9"
                set resultList to {{}}
                set counter to 0
                set frontDoc to front document
                set containerNote to find frontDoc query "$Path==\\"{container_escaped}\\""
                if containerNote is not {{}} then
                    set containerNote to item 1 of containerNote
                    repeat with n in children of containerNote
                        if counter >= {limit} then exit repeat
                        set noteInfo to {{|id|:id of n, |name|:name of n, |path|:path of n, |prototype|:name of prototype of n, |created|:created of n as string, |modified|:modified of n as string}}
                        set end of resultList to noteInfo
                        set counter to counter + 1
                    end repeat
                end if
                return resultList
            end tell
            '''
        else:
            # List all notes from front document
            script = f"""
            tell application "Tinderbox 9"
                set resultList to {{}}
                set counter to 0
                set frontDoc to front document
                repeat with n in notes of frontDoc
                    if counter >= {limit} then exit repeat
                    set noteInfo to {{|id|:id of n, |name|:name of n, |path|:path of n, |prototype|:name of prototype of n, |created|:created of n as string, |modified|:modified of n as string}}
                    set end of resultList to noteInfo
                    set counter to counter + 1
                end repeat
                return resultList
            end tell
            """

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to list Tinderbox items: {result}")
            return []

        items = []
        try:
            records = self._parse_applescript_records(result)
            for record in records:
                prototype = record.get("prototype", "")
                item_type_str = f"note:{prototype}" if prototype else "note"

                items.append(
                    ImportedItem(
                        external_id=record.get("id", ""),
                        name=record.get("name", "Untitled"),
                        source_app="Tinderbox",
                        item_type=item_type_str,
                        metadata={
                            "path": record.get("path", ""),
                            "prototype": prototype,
                        },
                        created_at=self._parse_date(record.get("created")),
                        modified_at=self._parse_date(record.get("modified")),
                    )
                )
        except Exception as e:
            logger.error(f"Error parsing Tinderbox items: {e}")

        return items

    async def get_item(self, external_id: str) -> Optional[ImportedItem]:
        """Get a specific note by ID."""
        if not self.is_available:
            return None

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Tinderbox 9"
            set frontDoc to front document
            set n to note id "{external_id_escaped}" of frontDoc
            if n is not missing value then
                return {{|id|:id of n, |name|:name of n, |path|:path of n, |text|:text of n, |prototype|:name of prototype of n, |created|:created of n as string, |modified|:modified of n as string, |url|:URL of n, |color|:color of n}}
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to get Tinderbox item {external_id}: {result}")
            return None

        try:
            records = self._parse_applescript_records(result)
            if records:
                record = records[0]
                prototype = record.get("prototype", "")
                item_type_str = f"note:{prototype}" if prototype else "note"

                return ImportedItem(
                    external_id=record.get("id", external_id),
                    name=record.get("name", "Untitled"),
                    source_app="Tinderbox",
                    item_type=item_type_str,
                    url=record.get("url"),
                    content=record.get("text"),
                    metadata={
                        "path": record.get("path", ""),
                        "prototype": prototype,
                        "color": record.get("color"),
                    },
                    created_at=self._parse_date(record.get("created")),
                    modified_at=self._parse_date(record.get("modified")),
                )
        except Exception as e:
            logger.error(f"Error parsing Tinderbox item: {e}")

        return None

    async def import_item(
        self, external_id: str, target_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Import a note from Tinderbox.

        Exports the note text to a markdown file.
        """
        if not self.is_available:
            return None

        item = await self.get_item(external_id)
        if not item:
            return None

        # If no target path, create one based on note name
        if not target_path:
            safe_name = "".join(
                c if c.isalnum() or c in "._- " else "_" for c in item.name
            )
            target_path = Path.cwd() / f"{safe_name}.md"

        # Write content to file
        content = item.content or ""

        # Add metadata header
        md_content = f"""---
title: {item.name}
source: Tinderbox
external_id: {external_id}
prototype: {item.metadata.get("prototype", "")}
path: {item.metadata.get("path", "")}
created: {item.created_at.isoformat() if item.created_at else ""}
modified: {item.modified_at.isoformat() if item.modified_at else ""}
---

{content}
"""

        try:
            target_path.write_text(md_content)
            logger.info(f"Exported Tinderbox note to {target_path}")
            return target_path
        except Exception as e:
            logger.error(f"Failed to write Tinderbox export: {e}")
            return None

    async def export_item(
        self,
        file_path: Path,
        metadata: Optional[dict] = None,
        container: Optional[str] = None,
        prototype: Optional[str] = None,
    ) -> Optional[str]:
        """
        Export a file to Tinderbox as a new note.

        Args:
            file_path: Path to the file (text/markdown content will be imported)
            metadata: Optional metadata (name, attributes, etc.)
            container: Target container path in Tinderbox
            prototype: Prototype to assign to the new note

        Returns:
            ID of the created note, or None if failed
        """
        if not self.is_available:
            return None

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Read file content
        try:
            content = file_path.read_text()
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return None

        name = metadata.get("name", file_path.stem) if metadata else file_path.stem

        # Escape content for AppleScript
        content_escaped = escape_applescript(content)
        name_escaped = escape_applescript(str(name))

        # Build script based on options
        if container:
            container_escaped = escape_applescript(container)
            container_clause = f'''
            set containerNote to find frontDoc query "$Path==\\"{container_escaped}\\""
            if containerNote is not {{}} then
                set newNote to make new note in item 1 of containerNote
            else
                set newNote to make new note in frontDoc
            end if
            '''
        else:
            container_clause = "set newNote to make new note in frontDoc"

        prototype_clause = ""
        if prototype:
            prototype_escaped = escape_applescript(prototype)
            prototype_clause = (
                f'set prototype of newNote to prototype "{prototype_escaped}" of frontDoc'
            )

        script = f'''
        tell application "Tinderbox 9"
            set frontDoc to front document
            {container_clause}
            set name of newNote to "{name_escaped}"
            set text of newNote to "{content_escaped}"
            {prototype_clause}
            return id of newNote
        end tell
        '''

        success, result = self.run_applescript(script)
        if success and result:
            logger.info(f"Exported {file_path.name} to Tinderbox: {result}")
            return result

        logger.error(f"Failed to export to Tinderbox: {result}")
        return None

    async def create_note(
        self,
        name: str,
        text: str = "",
        container: Optional[str] = None,
        prototype: Optional[str] = None,
        attributes: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Create a new note in Tinderbox.

        Args:
            name: Note name
            text: Note text content
            container: Container path (optional)
            prototype: Prototype name (optional)
            attributes: Additional attributes to set (optional)

        Returns:
            ID of created note, or None if failed
        """
        if not self.is_available:
            return None

        name_escaped = escape_applescript(name)
        text_escaped = escape_applescript(text)

        if container:
            container_escaped = escape_applescript(container)
            container_clause = f'''
            set containerNote to find frontDoc query "$Path==\\"{container_escaped}\\""
            if containerNote is not {{}} then
                set newNote to make new note in item 1 of containerNote
            else
                set newNote to make new note in frontDoc
            end if
            '''
        else:
            container_clause = "set newNote to make new note in frontDoc"

        prototype_clause = ""
        if prototype:
            prototype_escaped = escape_applescript(prototype)
            prototype_clause = (
                f'set prototype of newNote to prototype "{prototype_escaped}" of frontDoc'
            )

        # Build attribute setting commands
        attr_commands = []
        if attributes:
            for key, value in attributes.items():
                key_escaped = escape_applescript(str(key))
                value_escaped = escape_applescript(str(value))
                attr_commands.append(
                    f'set value of attribute "{key_escaped}" of newNote to "{value_escaped}"'
                )

        attr_clause = "\n".join(attr_commands)

        script = f'''
        tell application "Tinderbox 9"
            set frontDoc to front document
            {container_clause}
            set name of newNote to "{name_escaped}"
            set text of newNote to "{text_escaped}"
            {prototype_clause}
            {attr_clause}
            return id of newNote
        end tell
        '''

        success, result = self.run_applescript(script)
        if success and result:
            logger.info(f"Created Tinderbox note: {name} ({result})")
            return result

        logger.error(f"Failed to create Tinderbox note: {result}")
        return None

    async def open_item(self, external_id: str) -> bool:
        """Open a note in Tinderbox."""
        if not self.is_available:
            return False

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Tinderbox 9"
            set frontDoc to front document
            set n to note id "{external_id_escaped}" of frontDoc
            if n is not missing value then
                select n
                activate
                return "success"
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        return success and result == "success"

    async def get_attributes(
        self, external_id: str, attribute_names: list[str]
    ) -> dict:
        """Get specific attribute values for a note."""
        if not self.is_available:
            return {}

        # Build attribute query
        attr_list = ", ".join(
            f'|{escape_applescript(a)}|:value of attribute "{escape_applescript(a)}" of n'
            for a in attribute_names
        )

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Tinderbox 9"
            set frontDoc to front document
            set n to note id "{external_id_escaped}" of frontDoc
            if n is not missing value then
                return {{{attr_list}}}
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        if not success:
            logger.error(f"Failed to get Tinderbox attributes: {result}")
            return {}

        try:
            records = self._parse_applescript_records(result)
            if records:
                return records[0]
        except Exception as e:
            logger.error(f"Error parsing Tinderbox attributes: {e}")

        return {}

    async def set_attributes(self, external_id: str, attributes: dict) -> bool:
        """Set attribute values for a note."""
        if not self.is_available:
            return False

        # Build attribute setting commands
        attr_commands = []
        for key, value in attributes.items():
            key_escaped = escape_applescript(str(key))
            value_escaped = escape_applescript(str(value))
            attr_commands.append(
                f'set value of attribute "{key_escaped}" of n to "{value_escaped}"'
            )

        attr_clause = "\n".join(attr_commands)

        external_id_escaped = escape_applescript(external_id)
        script = f'''
        tell application "Tinderbox 9"
            set frontDoc to front document
            set n to note id "{external_id_escaped}" of frontDoc
            if n is not missing value then
                {attr_clause}
                return "success"
            end if
        end tell
        '''

        success, result = self.run_applescript(script)
        return success and result == "success"

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

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse a date string from AppleScript."""
        if not date_str:
            return None
        try:
            for fmt in ["%A, %B %d, %Y at %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None
