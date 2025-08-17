"""
Fiche Preview Component

Preview component for processed fiche data, metadata, and processing results.
Shows transcription, metadata, processing status, and related files.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
import json
import datetime

logger = logging.getLogger(__name__)


class FichePreview:
    """Fiche data preview with metadata and processing information"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        self.presenter = presenter
        self.width = width
        self.is_mobile = is_mobile
        
        # Fiche state
        self.current_fiche_path: Optional[Path] = None
        self.fiche_data: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        
        # UI components
        self.container = None
        self.header = None
        self.scroll_container = None
        self.content_box = None
        self.toolbar = None
        self.refresh_button = None
        self.export_button = None
        
        # Callbacks
        self.on_fiche_refresh: Optional[Callable[[Path], None]] = None
        self.on_fiche_export: Optional[Callable[[Path], None]] = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create fiche preview UI"""
        # Main container
        style = Pack(direction=COLUMN, margin=10)
        if self.is_mobile:
            # Mobile: use specified width or full width
            if self.width is not None:
                style.width = self.width
            else:
                style.flex = 1  # Full width for mobile
        else:
            # Desktop: always use full width
            style.flex = 1
        self.container = toga.Box(style=style)
        
        # Header with fiche info
        self.header = toga.Label(
            "Fiche Preview",
            style=Pack(font_size=12, font_weight="bold", margin_bottom=5)
        )
        self.container.add(self.header)
        
        # Toolbar for actions
        self.toolbar = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
        
        self.refresh_button = toga.Button(
            "Refresh",
            on_press=self._refresh_fiche,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.refresh_button)
        
        self.export_button = toga.Button(
            "Export",
            on_press=self._export_fiche,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.export_button)
        
        self.container.add(self.toolbar)
        
        # Scrollable content area
        self.scroll_container = toga.ScrollContainer(style=Pack(flex=1))
        self.content_box = toga.Box(style=Pack(direction=COLUMN))
        self.scroll_container.content = self.content_box
        
        self.container.add(self.scroll_container)
        
        # Show placeholder
        self._show_placeholder()
    
    def _show_placeholder(self):
        """Show placeholder content"""
        self.header.text = "Fiche Preview"
        self.content_box.clear()
        self.content_box.add(toga.Label("Select a fiche to preview"))
        self.refresh_button.enabled = False
        self.export_button.enabled = False
    
    def show_fiche(self, fiche_path: Path):
        """Show fiche data and metadata"""
        try:
            self.current_fiche_path = fiche_path
            
            # Load fiche data
            self._load_fiche_data(fiche_path)
            
            # Update header
            self.header.text = f"Fiche: {fiche_path.name}"
            
            # Enable buttons
            self.refresh_button.enabled = True
            self.export_button.enabled = True
            
            # Display fiche content
            self._display_fiche_content()
            
            logger.info(f"Showing fiche: {fiche_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to show fiche: {e}")
            self._show_error(f"Failed to load fiche: {fiche_path.name}")
    
    def _load_fiche_data(self, fiche_path: Path):
        """Load fiche data and metadata"""
        try:
            # Look for fiche data files
            fiche_dir = fiche_path.parent
            fiche_name = fiche_path.stem
            
            # Common fiche data file patterns
            data_files = [
                fiche_dir / f"{fiche_name}.json",
                fiche_dir / f"{fiche_name}_metadata.json",
                fiche_dir / f"{fiche_name}_data.json",
                fiche_dir / "metadata.json",
                fiche_dir / "fiche_data.json"
            ]
            
            # Load the first available data file
            for data_file in data_files:
                if data_file.exists():
                    with open(data_file, 'r', encoding='utf-8') as f:
                        self.fiche_data = json.load(f)
                    logger.info(f"Loaded fiche data from: {data_file}")
                    break
            
            # Load metadata from various sources
            self._load_metadata(fiche_path)
            
        except Exception as e:
            logger.error(f"Failed to load fiche data: {e}")
            self.fiche_data = {}
            self.metadata = {}
    
    def _load_metadata(self, fiche_path: Path):
        """Load metadata from various sources"""
        try:
            # Basic file metadata
            stat = fiche_path.stat()
            self.metadata = {
                "filename": fiche_path.name,
                "size_bytes": stat.st_size,
                "created": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "file_type": fiche_path.suffix.lower()
            }
            
            # Look for additional metadata files
            fiche_dir = fiche_path.parent
            metadata_files = [
                fiche_dir / "metadata.json",
                fiche_dir / f"{fiche_path.stem}_metadata.json",
                fiche_dir / "processing_info.json"
            ]
            
            for metadata_file in metadata_files:
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        additional_metadata = json.load(f)
                        self.metadata.update(additional_metadata)
                    logger.info(f"Loaded additional metadata from: {metadata_file}")
                    break
            
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
    
    def _display_fiche_content(self):
        """Display fiche content in the UI"""
        try:
            self.content_box.clear()
            
            # File information section
            self._add_section_header("File Information")
            self._add_file_info()
            
            # Processing status section
            if "processing_status" in self.metadata:
                self._add_section_header("Processing Status")
                self._add_processing_status()
            
            # Transcription section
            if "transcription" in self.fiche_data or "text" in self.fiche_data:
                self._add_section_header("Transcription")
                self._add_transcription_content()
            
            # Metadata section
            if self.metadata:
                self._add_section_header("Metadata")
                self._add_metadata_content()
            
            # Related files section
            self._add_section_header("Related Files")
            self._add_related_files()
            
        except Exception as e:
            logger.error(f"Failed to display fiche content: {e}")
            self._show_error("Failed to display fiche content")
    
    def _add_section_header(self, title: str):
        """Add a section header"""
        header = toga.Label(
            title,
            style=Pack(font_size=11, font_weight="bold", margin_top=10, margin_bottom=5)
        )
        self.content_box.add(header)
    
    def _add_file_info(self):
        """Add file information"""
        try:
            if self.current_fiche_path:
                # File name
                name_label = toga.Label(
                    f"Name: {self.current_fiche_path.name}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(name_label)
                
                # File size
                size_mb = self.current_fiche_path.stat().st_size / (1024 * 1024)
                size_label = toga.Label(
                    f"Size: {size_mb:.1f} MB",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(size_label)
                
                # File type
                type_label = toga.Label(
                    f"Type: {self.current_fiche_path.suffix.upper()}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(type_label)
                
        except Exception as e:
            logger.error(f"Failed to add file info: {e}")
    
    def _add_processing_status(self):
        """Add processing status information"""
        try:
            status = self.metadata.get("processing_status", "Unknown")
            status_label = toga.Label(
                f"Status: {status}",
                style=Pack(font_size=10, margin_bottom=2)
            )
            self.content_box.add(status_label)
            
            # Processing date
            if "processed_date" in self.metadata:
                date_label = toga.Label(
                    f"Processed: {self.metadata['processed_date']}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(date_label)
            
            # Processing tool
            if "processing_tool" in self.metadata:
                tool_label = toga.Label(
                    f"Tool: {self.metadata['processing_tool']}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(tool_label)
                
        except Exception as e:
            logger.error(f"Failed to add processing status: {e}")
    
    def _add_transcription_content(self):
        """Add transcription content"""
        try:
            # Get transcription text
            transcription = ""
            if "transcription" in self.fiche_data:
                transcription = self.fiche_data["transcription"]
            elif "text" in self.fiche_data:
                transcription = self.fiche_data["text"]
            
            if transcription:
                # Truncate long transcriptions
                if len(transcription) > 500:
                    transcription = transcription[:500] + "..."
                
                # Create text widget
                text_widget = toga.MultilineTextInput(
                    value=transcription,
                    readonly=True,
                    style=Pack(height=100, font_size=10, margin_bottom=5)
                )
                self.content_box.add(text_widget)
                
                # Show full text button if truncated
                if len(self.fiche_data.get("transcription", "")) > 500:
                    show_full_button = toga.Button(
                        "Show Full Transcription",
                        on_press=self._show_full_transcription,
                        style=Pack(margin_bottom=5)
                    )
                    self.content_box.add(show_full_button)
            else:
                no_text_label = toga.Label(
                    "No transcription available",
                    style=Pack(font_size=10, color="#666", margin_bottom=5)
                )
                self.content_box.add(no_text_label)
                
        except Exception as e:
            logger.error(f"Failed to add transcription content: {e}")
    
    def _add_metadata_content(self):
        """Add metadata content"""
        try:
            # Display key metadata fields
            key_fields = [
                "collection", "date", "location", "description", 
                "tags", "category", "author", "source"
            ]
            
            for field in key_fields:
                if field in self.metadata:
                    value = self.metadata[field]
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    elif isinstance(value, dict):
                        value = json.dumps(value, indent=2)
                    
                    field_label = toga.Label(
                        f"{field.title()}: {value}",
                        style=Pack(font_size=10, margin_bottom=2)
                    )
                    self.content_box.add(field_label)
            
            # Show raw metadata button
            if len(self.metadata) > 5:
                show_raw_button = toga.Button(
                    "Show Raw Metadata",
                    on_press=self._show_raw_metadata,
                    style=Pack(margin_bottom=5)
                )
                self.content_box.add(show_raw_button)
                
        except Exception as e:
            logger.error(f"Failed to add metadata content: {e}")
    
    def _add_related_files(self):
        """Add related files information"""
        try:
            if self.current_fiche_path:
                fiche_dir = self.current_fiche_path.parent
                fiche_name = self.current_fiche_path.stem
                
                # Look for related files
                related_files = []
                for file_path in fiche_dir.iterdir():
                    if file_path.name.startswith(fiche_name) and file_path != self.current_fiche_path:
                        related_files.append(file_path)
                
                if related_files:
                    for file_path in related_files[:5]:  # Show first 5
                        file_label = toga.Label(
                            f"• {file_path.name}",
                            style=Pack(font_size=10, margin_bottom=2)
                        )
                        self.content_box.add(file_label)
                    
                    if len(related_files) > 5:
                        more_label = toga.Label(
                            f"... and {len(related_files) - 5} more files",
                            style=Pack(font_size=10, color="#666", margin_bottom=2)
                        )
                        self.content_box.add(more_label)
                else:
                    no_files_label = toga.Label(
                        "No related files found",
                        style=Pack(font_size=10, color="#666", margin_bottom=2)
                    )
                    self.content_box.add(no_files_label)
                    
        except Exception as e:
            logger.error(f"Failed to add related files: {e}")
    
    def _show_full_transcription(self, widget):
        """Show full transcription in a dialog"""
        try:
            transcription = self.fiche_data.get("transcription", "") or self.fiche_data.get("text", "")
            if transcription:
                # Create a simple dialog to show full text
                # Note: Toga doesn't have built-in text dialogs, so we'll use a basic approach
                logger.info("Showing full transcription (would open in dialog)")
                
        except Exception as e:
            logger.error(f"Failed to show full transcription: {e}")
    
    def _show_raw_metadata(self, widget):
        """Show raw metadata in a dialog"""
        try:
            if self.metadata:
                # Create a simple dialog to show raw metadata
                # Note: Toga doesn't have built-in text dialogs, so we'll use a basic approach
                logger.info("Showing raw metadata (would open in dialog)")
                
        except Exception as e:
            logger.error(f"Failed to show raw metadata: {e}")
    
    def _refresh_fiche(self, widget):
        """Refresh fiche data"""
        try:
            if self.current_fiche_path:
                # Reload fiche data
                self._load_fiche_data(self.current_fiche_path)
                self._display_fiche_content()
                
                # Notify callback
                if self.on_fiche_refresh:
                    self.on_fiche_refresh(self.current_fiche_path)
                
                logger.info(f"Refreshed fiche: {self.current_fiche_path.name}")
            else:
                logger.warning("No fiche to refresh")
                
        except Exception as e:
            logger.error(f"Failed to refresh fiche: {e}")
    
    def _export_fiche(self, widget):
        """Export fiche data"""
        try:
            if self.current_fiche_path:
                # Notify callback
                if self.on_fiche_export:
                    self.on_fiche_export(self.current_fiche_path)
                
                logger.info(f"Export requested for fiche: {self.current_fiche_path.name}")
            else:
                logger.warning("No fiche to export")
                
        except Exception as e:
            logger.error(f"Failed to export fiche: {e}")
    
    def _show_error(self, message: str):
        """Show error message"""
        self.header.text = "Error"
        self.content_box.clear()
        self.content_box.add(toga.Label(message))
        self.refresh_button.enabled = False
        self.export_button.enabled = False
    
    def clear(self):
        """Clear the preview"""
        self.current_fiche_path = None
        self.fiche_data = {}
        self.metadata = {}
        self._show_placeholder()
    
    def get_current_fiche(self) -> Optional[Path]:
        """Get current fiche path"""
        return self.current_fiche_path
    
    def get_fiche_data(self) -> Dict[str, Any]:
        """Get current fiche data"""
        return self.fiche_data.copy()
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get current metadata"""
        return self.metadata.copy() 