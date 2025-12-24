"""
AdjustView - AI Model Outputs Viewer

Shows AI model outputs (versions) for the currently selected item.
Users can view, compare, and copy AI-generated metadata to their user pane.

Architecture:
- Single Versions tab showing AI model outputs
- List view: Cards for each AI model that processed the item
- Detail view: Inspector-style display of transcription + catalogue from a model
- Compare view: Side-by-side comparison of two selected versions
- Copy to User Pane: Copy AI data to user's editable metadata
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path
from datetime import datetime

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from fichero.shared.widgets.token_field import TokenFieldWidget, parse_metadata_value

if TYPE_CHECKING:
    from fichero.library.models import ExtractedMetadata

logger = logging.getLogger(__name__)


class AdjustView(BaseView):
    """
    AI Model Outputs Viewer.

    Shows AI model outputs (versions) for the currently selected item.
    Users can view, compare, and copy AI-generated metadata to their user pane.
    """

    def __init__(self, app, is_mobile: bool = False):
        """Initialize AI outputs viewer"""
        logger.info("Initializing AdjustView (AI Model Outputs)")

        # Current item and collection
        self.current_item_id: Optional[str] = None
        self.current_collection_id: Optional[str] = None
        self.current_collection_name: Optional[str] = None
        self.library_manager = None  # Set by main_window
        self.main_window = None  # Set by main_window for dialogs

        # UI components - simplified to just versions
        self.tab_container = None
        self.versions_box = None  # Main container for AI model outputs

        # Versions tab state
        self.model_versions: List[Dict[str, Any]] = []  # AI model version summaries
        self.selected_versions: List[Dict[str, Any]] = []  # Selected for comparison (max 2)
        self.current_version_view: str = 'list'  # 'list', 'detail', 'compare'
        self.current_detail_version: Optional[Dict[str, Any]] = None

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("AdjustView (AI Model Outputs) initialized")

    def _create_view_structure(self):
        """
        Override BaseView's structure to use OptionContainer as root.

        OptionContainer MUST be the root container (cannot be nested in Box)
        because it's a special Toga widget that manages its own layout.
        """
        try:
            # Create content first (creates tab_container as OptionContainer)
            self._create_content()

            # Use OptionContainer directly as the main container
            # (OptionContainer cannot be added to a Box - it must be the root)
            self.container = self.tab_container

            logger.debug("AdjustView structure created (OptionContainer as root)")

        except Exception as e:
            logger.error(f"Failed to create AdjustView structure: {e}")
            import traceback
            traceback.print_exc()
            # Create fallback container
            self.container = toga.Box(style=Pack(direction=COLUMN))
            self.tab_container = None

    def _create_content(self):
        """Create AI model outputs viewer (single Versions view)"""
        # Create the versions content directly as the container
        # No tabs needed - just the versions view
        self._create_versions_view()

        # Use versions_box as the tab_container (for compatibility)
        self.tab_container = self.versions_box

        logger.debug("AdjustView created with Versions view")

    def _create_versions_view(self):
        """Create the AI Model Outputs viewer.

        Shows:
        - List of all AI model versions that processed this item
        - Detail view for a specific model's outputs (Inspector-style)
        - Comparison view for side-by-side comparison of two versions
        - Copy to User Pane functionality
        """
        # Main container for versions content
        # Note: No flex=1 on width to prevent horizontal expansion
        versions_content = toga.Box(style=Pack(direction=COLUMN, margin=10))

        # Header with back button (hidden initially)
        self.versions_header = toga.Box(style=Pack(direction=ROW, margin_bottom=10))

        self.versions_back_button = toga.Button(
            "< Back",
            on_press=self._on_versions_back,
            style=Pack(margin_right=5, width=60)
        )
        self.versions_back_button.style.visibility = 'hidden'
        self.versions_header.add(self.versions_back_button)

        self.versions_title = toga.Label(
            "AI Model Outputs",
            style=Pack(font_weight='bold', font_size=13)
        )
        self.versions_header.add(self.versions_title)

        # Compare button (enabled when 2 versions selected)
        self.versions_compare_button = toga.Button(
            "Compare",
            on_press=self._on_compare_versions,
            enabled=False,
            style=Pack(margin_left=5, width=70)
        )
        self.versions_header.add(self.versions_compare_button)

        versions_content.add(self.versions_header)

        # Divider
        divider = toga.Box(style=Pack(
            height=1,
            background_color='#D0D0D0',
            margin=(5, 0, 10, 0)
        ))
        versions_content.add(divider)

        # Content area (will hold list, detail, or comparison views)
        # Note: No flex=1 to prevent horizontal expansion - content should wrap/clip
        self.versions_content_area = toga.Box(style=Pack(direction=COLUMN))
        self._add_placeholder(self.versions_content_area, "Select an item to view AI model outputs")
        versions_content.add(self.versions_content_area)

        # Wrap in ScrollContainer with vertical-only scrolling
        # horizontal=False prevents horizontal scrollbar in the sidebar pane
        self.versions_box = toga.ScrollContainer(
            content=versions_content,
            horizontal=False,
            style=Pack(flex=1)
        )

        logger.debug("Versions view created")

    def _on_versions_back(self, widget):
        """Handle back button press in versions tab"""
        if self.current_version_view == 'detail':
            # Go back to list view
            self.current_version_view = 'list'
            self.current_detail_version = None
            self._show_versions_list()
        elif self.current_version_view == 'compare':
            # Go back to list view
            self.current_version_view = 'list'
            self._show_versions_list()

    def _on_compare_versions(self, widget):
        """Handle compare button press"""
        if len(self.selected_versions) == 2:
            self.current_version_view = 'compare'
            self._show_comparison_view()

    def _show_versions_list(self):
        """Show the list of model versions"""
        self.versions_content_area.clear()
        self.versions_back_button.style.visibility = 'hidden'
        self.versions_title.text = "AI Model Versions"

        if not self.model_versions:
            self._add_placeholder(self.versions_content_area, "No AI model versions available")
            return

        # Create a card for each model version
        for version in self.model_versions:
            card = self._create_version_card(version)
            self.versions_content_area.add(card)

        # Update compare button state
        self._update_compare_button()

    def _create_version_card(self, version: Dict[str, Any]) -> toga.Box:
        """Create a card for a model version.

        Args:
            version: Dict with source_label, model_name, provider_name, created_at, schema_types, record_count
        """
        # Card container - no flex to prevent horizontal expansion
        card = toga.Box(style=Pack(
            direction=COLUMN,
            margin=(0, 0, 10, 0),
            background_color='#F5F5F5'
        ))

        # Card content with margin
        card_content = toga.Box(style=Pack(direction=COLUMN, margin=10))

        # Header row: checkbox + model name
        header_row = toga.Box(style=Pack(direction=ROW, margin_bottom=5))

        # Checkbox for comparison selection
        is_selected = version in self.selected_versions
        checkbox = toga.Switch(
            "",
            value=is_selected,
            on_change=lambda w, v=version: self._on_version_checkbox_change(v, w.value),
            style=Pack(margin_right=10, width=40)
        )
        header_row.add(checkbox)

        # Model name with icon (handle None values explicitly)
        source_label = version.get('source_label') or 'unknown'
        model_name = version.get('model_name') or 'Unknown Model'
        provider = version.get('provider_name') or ''

        # Icon based on source type
        if source_label.startswith('ai_') or 'ai' in source_label.lower():
            icon = "🤖"
        elif source_label == 'user_edit':
            icon = "👤"
        else:
            icon = "📄"

        # Truncate long model names to prevent horizontal overflow
        display_name = model_name if len(model_name) <= 25 else model_name[:22] + "..."
        model_label = toga.Label(
            f"{icon} {display_name}",
            style=Pack(font_weight='bold', font_size=12)
        )
        header_row.add(model_label)

        card_content.add(header_row)

        # Details row: provider, date, record count - use COLUMN layout to prevent overflow
        details_row = toga.Box(style=Pack(direction=COLUMN, margin_bottom=5))

        # First line: provider and date
        meta_line = []
        if provider and len(provider) > 0:
            # Truncate long provider names
            display_provider = provider if len(provider) <= 20 else provider[:17] + "..."
            meta_line.append(f"Provider: {display_provider}")

        created_at = version.get('created_at')
        if created_at:
            if isinstance(created_at, str):
                date_str = created_at[:10]  # Just date portion
            else:
                date_str = created_at.strftime("%Y-%m-%d")
            meta_line.append(f"Date: {date_str}")

        record_count = version.get('record_count', 0)
        meta_line.append(f"Records: {record_count}")

        # Combine into single label to prevent overflow
        meta_label = toga.Label(
            " | ".join(meta_line),
            style=Pack(font_size=10, color='#666')
        )
        details_row.add(meta_label)

        card_content.add(details_row)

        # Schema types row
        schema_types = version.get('schema_types', [])
        if schema_types:
            schemas_label = toga.Label(
                f"Data: {', '.join(schema_types)}",
                style=Pack(font_size=10, color='#888', margin_bottom=5)
            )
            card_content.add(schemas_label)

        # Action buttons row - use smaller buttons to fit in narrow pane
        actions_row = toga.Box(style=Pack(direction=ROW, margin_top=5))

        # View Details button
        view_button = toga.Button(
            "View",
            on_press=lambda w, v=version: self._on_view_version_details(v),
            style=Pack(margin_right=5, width=60)
        )
        actions_row.add(view_button)

        # Copy to User Pane button
        copy_button = toga.Button(
            "Copy to User",
            on_press=lambda w, v=version: self._on_copy_to_user_pane(v),
            style=Pack(width=100)
        )
        actions_row.add(copy_button)

        card_content.add(actions_row)

        card.add(card_content)
        return card

    def _on_version_checkbox_change(self, version: Dict[str, Any], selected: bool):
        """Handle version selection checkbox change"""
        if selected:
            # Add to selection (max 2)
            if version not in self.selected_versions:
                if len(self.selected_versions) >= 2:
                    # Remove oldest selection
                    self.selected_versions.pop(0)
                self.selected_versions.append(version)
        else:
            # Remove from selection
            if version in self.selected_versions:
                self.selected_versions.remove(version)

        self._update_compare_button()

    def _update_compare_button(self):
        """Update compare button enabled state"""
        if hasattr(self, 'versions_compare_button') and self.versions_compare_button:
            self.versions_compare_button.enabled = len(self.selected_versions) == 2

    def _on_view_version_details(self, version: Dict[str, Any]):
        """Handle View Details button press"""
        self.current_version_view = 'detail'
        self.current_detail_version = version
        self._show_version_detail(version)

    def _on_copy_to_user_pane(self, version: Dict[str, Any]):
        """Handle Copy to User Pane button press"""
        asyncio.create_task(self._copy_version_to_user_pane(version))

    async def _copy_version_to_user_pane(self, version: Dict[str, Any]):
        """Copy metadata from an AI version to the user's working copy"""
        if not self.library_manager or not self.current_item_id:
            logger.warning("Cannot copy: missing library manager or item")
            return

        try:
            source_label = version.get('source_label', '')
            model_name = version.get('model_name')

            # Get all metadata from this source/model
            metadata_records = await self.library_manager.get_metadata_by_source(
                item_id=self.current_item_id,
                source_label=source_label,
                model_name=model_name
            )

            if not metadata_records:
                logger.warning(f"No metadata found for {source_label}/{model_name}")
                return

            # Copy to user pane
            success = await self.library_manager.copy_metadata_to_user_pane(
                item_id=self.current_item_id,
                metadata_records=metadata_records
            )

            if success:
                logger.info(f"Copied {len(metadata_records)} records from {source_label} to user pane")
                # Show feedback to user
                if hasattr(self, 'versions_title'):
                    self.versions_title.text = f"Copied {len(metadata_records)} records to User Pane"
                    # Reset title after 2 seconds
                    await asyncio.sleep(2)
                    self.versions_title.text = "AI Model Versions"
            else:
                logger.error("Failed to copy metadata to user pane")

        except Exception as e:
            logger.error(f"Error copying to user pane: {e}")
            import traceback
            traceback.print_exc()

    def _show_version_detail(self, version: Dict[str, Any]):
        """Show detail view for a specific model version"""
        self.versions_content_area.clear()
        self.versions_back_button.style.visibility = 'visible'

        source_label = version.get('source_label', 'unknown')
        model_name = version.get('model_name', 'Unknown Model')
        self.versions_title.text = f"{model_name}"

        # Load metadata for this version
        asyncio.create_task(self._load_version_detail(version))

    async def _load_version_detail(self, version: Dict[str, Any]):
        """Load and display detail view for a model version"""
        if not self.library_manager or not self.current_item_id:
            self._add_placeholder(self.versions_content_area, "Cannot load: missing data")
            return

        try:
            source_label = version.get('source_label', '')
            model_name = version.get('model_name')

            # Get all metadata from this source
            metadata_records = await self.library_manager.get_metadata_by_source(
                item_id=self.current_item_id,
                source_label=source_label,
                model_name=model_name
            )

            if not metadata_records:
                self._add_placeholder(self.versions_content_area, "No data found for this version")
                return

            # Group by schema_type
            by_schema: Dict[str, List] = {}
            for record in metadata_records:
                schema = record.schema_type
                if schema not in by_schema:
                    by_schema[schema] = []
                by_schema[schema].append(record)

            # Display transcription first if present
            if 'transcription' in by_schema:
                self._add_detail_section("Transcription", by_schema['transcription'])

            # Then catalogue
            if 'catalogue' in by_schema:
                self._add_detail_section("Catalogue", by_schema['catalogue'])

            # Then any other schema types
            for schema, records in by_schema.items():
                if schema not in ['transcription', 'catalogue']:
                    self._add_detail_section(schema.title(), records)

            # Copy button at bottom
            copy_row = toga.Box(style=Pack(direction=ROW, margin_top=15))
            copy_button = toga.Button(
                "Copy All to User Pane",
                on_press=lambda w, v=version: self._on_copy_to_user_pane(v),
                style=Pack(width=160)
            )
            copy_row.add(copy_button)
            self.versions_content_area.add(copy_row)

        except Exception as e:
            logger.error(f"Error loading version detail: {e}")
            self._add_placeholder(self.versions_content_area, f"Error: {e}")

    def _add_detail_section(self, title: str, records: List):
        """Add a section to the detail view using Inspector-style layout"""
        # Section header
        header = toga.Label(
            title,
            style=Pack(font_weight='bold', font_size=12, margin_top=10, margin_bottom=5)
        )
        self.versions_content_area.add(header)

        # Check if this is transcription (show as text block)
        if title.lower() == 'transcription':
            for record in records:
                if record.key == 'text' and record.value:
                    text_box = toga.MultilineTextInput(
                        value=record.value,
                        readonly=True,
                        style=Pack(flex=1, height=200, font_family='monospace', font_size=11)
                    )
                    self.versions_content_area.add(text_box)
        else:
            # Show as Inspector-style key-value pairs (label on left, value on right)
            for record in records:
                if record.value:
                    self._add_inspector_row(
                        record.key.replace('_', ' ').title(),
                        str(record.value)
                    )

    def _add_inspector_row(self, label: str, value: str):
        """Add an Inspector-style row (label: value) to the content area.

        Values are displayed as native macOS token pills (NSTokenField) only when
        there are multiple items (list-like data).
        Single values are shown as plain text.
        Long prose text (>100 chars) is shown in a multiline text field.
        Empty values are not shown.
        """
        # Skip empty values entirely
        if not value or value.strip() == "":
            return

        # Parse value to extract data from JSON, lists, etc.
        tags = parse_metadata_value(value)

        # If parsing resulted in no tags, skip this row
        if not tags:
            return

        # Use COLUMN layout for narrow pane - label on top, value below
        row = toga.Box(style=Pack(direction=COLUMN, margin_bottom=6))

        # Label
        label_widget = toga.Label(
            f"{label}:",
            style=Pack(
                font_size=9,
                color='#666',
                margin_bottom=2
            )
        )
        row.add(label_widget)

        # Only use token pills when there are MULTIPLE values
        # Single values should be plain text
        if len(tags) > 1:
            # Display as native macOS token pills (NSTokenField)
            token_field = TokenFieldWidget(
                values=tags,
                on_token_click=self._on_tag_clicked,
                placeholder="",
                width=200,
                height=24
            )
            # Add the appropriate widget based on platform
            if token_field.native:
                # Wrap native view in a Toga Box for embedding
                native_wrapper = toga.Box(style=Pack(height=26))
                try:
                    native_wrapper._impl.native.addSubview_(token_field.native)
                except Exception:
                    # Fallback if native embedding fails
                    native_wrapper = token_field.container
                row.add(native_wrapper)
            else:
                row.add(token_field.container)
        elif len(tags[0]) > 100:
            # Long text: use multiline with limited height
            value_widget = toga.MultilineTextInput(
                value=tags[0],
                readonly=True,
                style=Pack(height=60, font_size=9)
            )
            row.add(value_widget)
        else:
            # Simple short value - plain text
            value_widget = toga.Label(
                tags[0],
                style=Pack(font_size=9)
            )
            row.add(value_widget)

        self.versions_content_area.add(row)

    def _on_tag_clicked(self, tag_text: str):
        """Handle click on a metadata tag - could trigger search."""
        logger.info(f"Tag clicked: {tag_text}")
        # Future: trigger search for items with this tag value
        # For now, just log it

    def _show_comparison_view(self):
        """Show side-by-side comparison of two versions"""
        self.versions_content_area.clear()
        self.versions_back_button.style.visibility = 'visible'
        self.versions_title.text = "Compare Versions"

        if len(self.selected_versions) != 2:
            self._add_placeholder(self.versions_content_area, "Select exactly 2 versions to compare")
            return

        # Load and display comparison
        asyncio.create_task(self._load_comparison_view())

    async def _load_comparison_view(self):
        """Load and display comparison of two versions"""
        if not self.library_manager or not self.current_item_id:
            self._add_placeholder(self.versions_content_area, "Cannot load: missing data")
            return

        try:
            version1 = self.selected_versions[0]
            version2 = self.selected_versions[1]

            # Get metadata for both versions
            metadata1 = await self.library_manager.get_metadata_by_source(
                item_id=self.current_item_id,
                source_label=version1.get('source_label', ''),
                model_name=version1.get('model_name')
            )
            metadata2 = await self.library_manager.get_metadata_by_source(
                item_id=self.current_item_id,
                source_label=version2.get('source_label', ''),
                model_name=version2.get('model_name')
            )

            # Header - show version names stacked (narrow pane)
            model1_name = version1.get('model_name', 'Version 1')
            model2_name = version2.get('model_name', 'Version 2')
            # Truncate long model names
            if len(model1_name) > 20:
                model1_name = model1_name[:17] + "..."
            if len(model2_name) > 20:
                model2_name = model2_name[:17] + "..."

            header = toga.Label(
                f"Comparing:",
                style=Pack(font_weight='bold', font_size=11, margin_bottom=5)
            )
            self.versions_content_area.add(header)

            v1_label = toga.Label(
                f"1: 🤖 {model1_name}",
                style=Pack(font_size=10, margin_bottom=2)
            )
            self.versions_content_area.add(v1_label)

            v2_label = toga.Label(
                f"2: 🤖 {model2_name}",
                style=Pack(font_size=10, margin_bottom=10)
            )
            self.versions_content_area.add(v2_label)

            # Group both by schema type
            by_schema1 = self._group_by_schema(metadata1)
            by_schema2 = self._group_by_schema(metadata2)

            # Get all schema types
            all_schemas = set(by_schema1.keys()) | set(by_schema2.keys())

            # Display each schema type side by side
            priority_order = ['transcription', 'catalogue']
            for schema in priority_order:
                if schema in all_schemas:
                    self._add_comparison_section(
                        schema.title(),
                        by_schema1.get(schema, []),
                        by_schema2.get(schema, [])
                    )
                    all_schemas.discard(schema)

            # Remaining schemas
            for schema in sorted(all_schemas):
                self._add_comparison_section(
                    schema.title(),
                    by_schema1.get(schema, []),
                    by_schema2.get(schema, [])
                )

            # Copy buttons - stacked for narrow pane
            copy_box = toga.Box(style=Pack(direction=COLUMN, margin_top=15))
            copy1_btn = toga.Button(
                f"Copy Version 1",
                on_press=lambda w: self._on_copy_to_user_pane(version1),
                style=Pack(margin_bottom=5, width=120)
            )
            copy_box.add(copy1_btn)
            copy2_btn = toga.Button(
                f"Copy Version 2",
                on_press=lambda w: self._on_copy_to_user_pane(version2),
                style=Pack(width=120)
            )
            copy_box.add(copy2_btn)
            self.versions_content_area.add(copy_box)

        except Exception as e:
            logger.error(f"Error loading comparison: {e}")
            self._add_placeholder(self.versions_content_area, f"Error: {e}")

    def _group_by_schema(self, metadata_records: List) -> Dict[str, List]:
        """Group metadata records by schema_type"""
        by_schema: Dict[str, List] = {}
        for record in metadata_records:
            schema = record.schema_type
            if schema not in by_schema:
                by_schema[schema] = []
            by_schema[schema].append(record)
        return by_schema

    def _add_comparison_section(self, title: str, records1: List, records2: List):
        """Add a comparison section showing two versions stacked vertically (for narrow pane)"""
        # Section header
        header = toga.Label(
            title,
            style=Pack(font_weight='bold', font_size=12, margin_top=15, margin_bottom=5)
        )
        self.versions_content_area.add(header)

        # Version 1 content (stacked vertically, not side-by-side for narrow pane)
        v1_header = toga.Label(
            "Version 1:",
            style=Pack(font_size=10, color='#666', margin_bottom=3)
        )
        self.versions_content_area.add(v1_header)

        if records1:
            if title.lower() == 'transcription':
                text = next((r.value for r in records1 if r.key == 'text'), '')
                text_box = toga.MultilineTextInput(
                    value=text,
                    readonly=True,
                    style=Pack(height=100, font_family='monospace', font_size=9)
                )
                self.versions_content_area.add(text_box)
            else:
                for record in records1:
                    if record.value:
                        # Truncate values for narrow pane
                        display_value = str(record.value)[:40]
                        if len(str(record.value)) > 40:
                            display_value += "..."
                        value_label = toga.Label(
                            f"{record.key.replace('_', ' ').title()}: {display_value}",
                            style=Pack(font_size=9, margin_bottom=2)
                        )
                        self.versions_content_area.add(value_label)
        else:
            no_data = toga.Label("No data", style=Pack(font_size=9, color='#999'))
            self.versions_content_area.add(no_data)

        # Divider between versions
        divider = toga.Box(style=Pack(
            height=1,
            background_color='#D0D0D0',
            margin=(8, 0, 8, 0)
        ))
        self.versions_content_area.add(divider)

        # Version 2 content
        v2_header = toga.Label(
            "Version 2:",
            style=Pack(font_size=10, color='#666', margin_bottom=3)
        )
        self.versions_content_area.add(v2_header)

        if records2:
            if title.lower() == 'transcription':
                text = next((r.value for r in records2 if r.key == 'text'), '')
                text_box = toga.MultilineTextInput(
                    value=text,
                    readonly=True,
                    style=Pack(height=100, font_family='monospace', font_size=9)
                )
                self.versions_content_area.add(text_box)
            else:
                for record in records2:
                    if record.value:
                        # Truncate values for narrow pane
                        display_value = str(record.value)[:40]
                        if len(str(record.value)) > 40:
                            display_value += "..."
                        value_label = toga.Label(
                            f"{record.key.replace('_', ' ').title()}: {display_value}",
                            style=Pack(font_size=9, margin_bottom=2)
                        )
                        self.versions_content_area.add(value_label)
        else:
            no_data = toga.Label("No data", style=Pack(font_size=9, color='#999'))
            self.versions_content_area.add(no_data)

    async def _load_versions_tab(self, item_id: str):
        """Load the versions tab with AI model versions for this item"""
        if not self.library_manager:
            return

        try:
            # Get all model versions for this item
            versions = await self.library_manager.get_model_versions_for_item(item_id)
            self.model_versions = versions if versions else []
            self.selected_versions = []  # Reset selection
            self.current_version_view = 'list'
            self.current_detail_version = None

            # Show the list view
            self._show_versions_list()

            logger.debug(f"Loaded {len(self.model_versions)} model versions for item {item_id}")

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            logger.error(f"Failed to load versions tab: {e}\n{tb_str}")
            self.model_versions = []
            self.versions_content_area.clear()
            self._add_placeholder(self.versions_content_area, f"Error loading versions: {e}")

    def _add_placeholder(self, container: toga.Box, text: str):
        """Add placeholder text to a container"""
        label = toga.Label(
            text,
            style=Pack(margin=20, color='#999', font_size=12)
        )
        container.add(label)

    def set_library_manager(self, library_manager):
        """Set library manager reference"""
        self.library_manager = library_manager
        logger.debug("Library manager set in AdjustView")

    def set_main_window(self, main_window):
        """Set main window reference for dialogs"""
        self.main_window = main_window
        logger.debug("Main window set in AdjustView")

    def set_collection(self, collection_id: str, collection_name: str):
        """Set current collection context"""
        self.current_collection_id = collection_id
        self.current_collection_name = collection_name
        logger.debug(f"Collection set in AdjustView: {collection_name} ({collection_id})")

    async def load_item(self, item_id: str, output_data: Optional[Dict] = None):
        """
        Load and display item details (AI Model Outputs).

        Shows AI model versions for the selected item.

        Args:
            item_id: ID of the item to load
            output_data: Optional pre-fetched output data (not used - kept for API compatibility)
        """
        # ALWAYS reload - no deduplication to ensure content updates properly
        logger.info(f"Loading AI model outputs for item: {item_id}")

        try:
            self.current_item_id = item_id

            if not self.library_manager:
                logger.warning("No library manager available")
                return

            # Get item
            item = self.library_manager.storage.get_item(item_id)
            if not item:
                logger.warning(f"Item not found: {item_id}")
                return

            # Load versions (AI model outputs)
            await self._load_versions_tab(item_id)

            logger.info("AI model outputs loaded")

        except Exception as e:
            logger.error(f"Failed to load AI model outputs: {e}")
            import traceback
            traceback.print_exc()

    def clear(self):
        """Clear all content"""
        self.current_item_id = None

        # Clear versions view
        self.model_versions = []
        self.selected_versions = []
        self.current_version_view = 'list'
        self.current_detail_version = None
        if hasattr(self, 'versions_content_area') and self.versions_content_area:
            self.versions_content_area.clear()
            self._add_placeholder(self.versions_content_area, "Select an item to view AI model outputs")
        if hasattr(self, 'versions_back_button') and self.versions_back_button:
            self.versions_back_button.style.visibility = 'hidden'
        if hasattr(self, 'versions_title') and self.versions_title:
            self.versions_title.text = "AI Model Outputs"

        logger.debug("Cleared AI model outputs view")
