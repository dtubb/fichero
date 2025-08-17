"""
Translation Preview Component

Preview component for translation results and workflows.
Shows original text, translated text, and translation metadata.
Supports side-by-side comparison and translation editing.
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


class TranslationPreview:
    """Translation results preview with comparison and editing"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        self.presenter = presenter
        self.width = width
        self.is_mobile = is_mobile
        
        # Translation state
        self.current_translation_path: Optional[Path] = None
        self.original_text: str = ""
        self.translated_text: str = ""
        self.translation_metadata: Dict[str, Any] = {}
        self.is_editable: bool = False
        self.is_modified: bool = False
        
        # UI components
        self.container = None
        self.header = None
        self.scroll_container = None
        self.content_box = None
        self.toolbar = None
        self.save_button = None
        self.copy_button = None
        self.compare_button = None
        
        # Text editors
        self.original_editor = None
        self.translated_editor = None
        
        # Callbacks
        self.on_translation_change: Optional[Callable[[str], None]] = None
        self.on_translation_save: Optional[Callable[[Path, str], None]] = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create translation preview UI"""
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
        
        # Header with translation info
        self.header = toga.Label(
            "Translation Preview",
            style=Pack(font_size=12, font_weight="bold", margin_bottom=5)
        )
        self.container.add(self.header)
        
        # Toolbar for actions
        self.toolbar = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
        
        self.copy_button = toga.Button(
            "Copy",
            on_press=self._copy_translation,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.copy_button)
        
        self.compare_button = toga.Button(
            "Compare",
            on_press=self._toggle_comparison,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.compare_button)
        
        self.save_button = toga.Button(
            "Save",
            on_press=self._save_translation,
            style=Pack(margin_right=5)
        )
        self.save_button.enabled = False  # Initially disabled
        self.toolbar.add(self.save_button)
        
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
        self.header.text = "Translation Preview"
        self.content_box.clear()
        self.content_box.add(toga.Label("Select a translation file to preview"))
        self.save_button.enabled = False
        self.copy_button.enabled = False
        self.compare_button.enabled = False
    
    def show_translation(self, translation_path: Path, editable: bool = True):
        """Show translation content"""
        try:
            self.current_translation_path = translation_path
            self.is_editable = editable
            
            # Load translation data
            self._load_translation_data(translation_path)
            
            # Update header
            self.header.text = f"Translation: {translation_path.name}"
            
            # Enable buttons
            self.save_button.enabled = False
            self.copy_button.enabled = True
            self.compare_button.enabled = True
            
            # Display translation content
            self._display_translation_content()
            
            logger.info(f"Showing translation: {translation_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to show translation: {e}")
            self._show_error(f"Failed to load translation: {translation_path.name}")
    
    def _load_translation_data(self, translation_path: Path):
        """Load translation data from file"""
        try:
            # Try to load as JSON first
            if translation_path.suffix.lower() == '.json':
                with open(translation_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract translation data
                self.original_text = data.get('original', '')
                self.translated_text = data.get('translated', '')
                self.translation_metadata = data.get('metadata', {})
                
            else:
                # Try to load as plain text
                with open(translation_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Simple parsing - assume first half is original, second half is translation
                lines = content.split('\n')
                mid_point = len(lines) // 2
                
                self.original_text = '\n'.join(lines[:mid_point])
                self.translated_text = '\n'.join(lines[mid_point:])
                self.translation_metadata = {
                    'source_file': translation_path.name,
                    'loaded_date': datetime.datetime.now().isoformat()
                }
            
            self.is_modified = False
            
        except Exception as e:
            logger.error(f"Failed to load translation data: {e}")
            self.original_text = ""
            self.translated_text = ""
            self.translation_metadata = {}
    
    def _display_translation_content(self):
        """Display translation content in the UI"""
        try:
            self.content_box.clear()
            
            # Translation metadata section
            if self.translation_metadata:
                self._add_section_header("Translation Info")
                self._add_translation_metadata()
            
            # Original text section
            if self.original_text:
                self._add_section_header("Original Text")
                self._add_original_text()
            
            # Translated text section
            if self.translated_text:
                self._add_section_header("Translated Text")
                self._add_translated_text()
            
            # Translation quality section
            if self.translation_metadata.get('quality_score'):
                self._add_section_header("Translation Quality")
                self._add_quality_info()
            
        except Exception as e:
            logger.error(f"Failed to display translation content: {e}")
            self._show_error("Failed to display translation content")
    
    def _add_section_header(self, title: str):
        """Add a section header"""
        header = toga.Label(
            title,
            style=Pack(font_size=11, font_weight="bold", margin_top=10, margin_bottom=5)
        )
        self.content_box.add(header)
    
    def _add_translation_metadata(self):
        """Add translation metadata information"""
        try:
            # Source language
            if 'source_language' in self.translation_metadata:
                source_label = toga.Label(
                    f"Source: {self.translation_metadata['source_language']}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(source_label)
            
            # Target language
            if 'target_language' in self.translation_metadata:
                target_label = toga.Label(
                    f"Target: {self.translation_metadata['target_language']}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(target_label)
            
            # Translation engine
            if 'engine' in self.translation_metadata:
                engine_label = toga.Label(
                    f"Engine: {self.translation_metadata['engine']}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(engine_label)
            
            # Translation date
            if 'translated_date' in self.translation_metadata:
                date_label = toga.Label(
                    f"Date: {self.translation_metadata['translated_date']}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(date_label)
                
        except Exception as e:
            logger.error(f"Failed to add translation metadata: {e}")
    
    def _add_original_text(self):
        """Add original text display"""
        try:
            # Truncate long text for display
            display_text = self.original_text
            if len(display_text) > 300:
                display_text = display_text[:300] + "..."
            
            # Create text widget (read-only)
            self.original_editor = toga.MultilineTextInput(
                value=display_text,
                readonly=True,
                style=Pack(height=80, font_size=10, margin_bottom=5)
            )
            self.content_box.add(self.original_editor)
            
            # Show full text button if truncated
            if len(self.original_text) > 300:
                show_full_button = toga.Button(
                    "Show Full Original",
                    on_press=self._show_full_original,
                    style=Pack(margin_bottom=5)
                )
                self.content_box.add(show_full_button)
                
        except Exception as e:
            logger.error(f"Failed to add original text: {e}")
    
    def _add_translated_text(self):
        """Add translated text display"""
        try:
            # Truncate long text for display
            display_text = self.translated_text
            if len(display_text) > 300:
                display_text = display_text[:300] + "..."
            
            # Create text widget (editable if enabled)
            self.translated_editor = toga.MultilineTextInput(
                value=display_text,
                readonly=not self.is_editable,
                style=Pack(height=80, font_size=10, margin_bottom=5)
            )
            self.content_box.add(self.translated_editor)
            
            # Set up change handler if editable
            if self.is_editable:
                self.translated_editor.on_change = self._on_translation_change
            
            # Show full text button if truncated
            if len(self.translated_text) > 300:
                show_full_button = toga.Button(
                    "Show Full Translation",
                    on_press=self._show_full_translation,
                    style=Pack(margin_bottom=5)
                )
                self.content_box.add(show_full_button)
                
        except Exception as e:
            logger.error(f"Failed to add translated text: {e}")
    
    def _add_quality_info(self):
        """Add translation quality information"""
        try:
            quality_score = self.translation_metadata.get('quality_score', 0)
            
            # Quality score
            score_label = toga.Label(
                f"Quality Score: {quality_score:.1f}/10",
                style=Pack(font_size=10, margin_bottom=2)
            )
            self.content_box.add(score_label)
            
            # Quality description
            if quality_score >= 8:
                quality_desc = "Excellent"
            elif quality_score >= 6:
                quality_desc = "Good"
            elif quality_score >= 4:
                quality_desc = "Fair"
            else:
                quality_desc = "Poor"
            
            desc_label = toga.Label(
                f"Quality: {quality_desc}",
                style=Pack(font_size=10, margin_bottom=2)
            )
            self.content_box.add(desc_label)
            
            # Confidence score if available
            if 'confidence' in self.translation_metadata:
                confidence = self.translation_metadata['confidence']
                confidence_label = toga.Label(
                    f"Confidence: {confidence:.1%}",
                    style=Pack(font_size=10, margin_bottom=2)
                )
                self.content_box.add(confidence_label)
                
        except Exception as e:
            logger.error(f"Failed to add quality info: {e}")
    
    def _on_translation_change(self, widget):
        """Handle translation text changes"""
        try:
            new_text = self.translated_editor.value
            if new_text != self.translated_text:
                self.is_modified = True
                self.save_button.enabled = True
                
                # Notify callback
                if self.on_translation_change:
                    self.on_translation_change(new_text)
                
                logger.debug("Translation text modified")
            
        except Exception as e:
            logger.error(f"Failed to handle translation change: {e}")
    
    def _show_full_original(self, widget):
        """Show full original text"""
        try:
            if self.original_text:
                # Update the editor with full text
                self.original_editor.value = self.original_text
                logger.info("Showing full original text")
                
        except Exception as e:
            logger.error(f"Failed to show full original: {e}")
    
    def _show_full_translation(self, widget):
        """Show full translated text"""
        try:
            if self.translated_text:
                # Update the editor with full text
                self.translated_editor.value = self.translated_text
                logger.info("Showing full translated text")
                
        except Exception as e:
            logger.error(f"Failed to show full translation: {e}")
    
    def _copy_translation(self, widget):
        """Copy translation to clipboard"""
        try:
            if self.translated_text:
                # Toga clipboard support
                app = toga.App.app
                if app and hasattr(app, 'clipboard'):
                    app.clipboard.set_text(self.translated_text)
                    logger.info("Translation copied to clipboard")
                else:
                    logger.warning("Clipboard not available")
            
        except Exception as e:
            logger.error(f"Failed to copy translation: {e}")
    
    def _toggle_comparison(self, widget):
        """Toggle side-by-side comparison view"""
        try:
            # This would switch between single view and side-by-side view
            # For now, just log the action
            logger.info("Toggle comparison view requested")
            
            # Future implementation would:
            # 1. Switch layout to side-by-side
            # 2. Show original and translation side by side
            # 3. Highlight differences
            
        except Exception as e:
            logger.error(f"Failed to toggle comparison: {e}")
    
    def _save_translation(self, widget):
        """Save modified translation"""
        try:
            if not self.is_modified:
                return
            
            new_text = self.translated_editor.value
            
            # Save to file if we have a file path
            if self.current_translation_path:
                # Update translation data
                self.translated_text = new_text
                self.translation_metadata['modified_date'] = datetime.datetime.now().isoformat()
                
                # Save as JSON
                if self.current_translation_path.suffix.lower() == '.json':
                    data = {
                        'original': self.original_text,
                        'translated': self.translated_text,
                        'metadata': self.translation_metadata
                    }
                    with open(self.current_translation_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    # Save as plain text
                    content = f"{self.original_text}\n\n---\n\n{self.translated_text}"
                    with open(self.current_translation_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                
                self.is_modified = False
                self.save_button.enabled = False
                
                logger.info(f"Translation saved to: {self.current_translation_path}")
                
                # Notify callback
                if self.on_translation_save:
                    self.on_translation_save(self.current_translation_path, new_text)
            else:
                logger.warning("No translation file path available for saving")
            
        except Exception as e:
            logger.error(f"Failed to save translation: {e}")
            self._show_error("Failed to save translation")
    
    def _show_error(self, message: str):
        """Show error message"""
        self.header.text = "Error"
        self.content_box.clear()
        self.content_box.add(toga.Label(message))
        self.save_button.enabled = False
        self.copy_button.enabled = False
        self.compare_button.enabled = False
    
    def clear(self):
        """Clear the preview"""
        self.current_translation_path = None
        self.original_text = ""
        self.translated_text = ""
        self.translation_metadata = {}
        self.is_editable = False
        self.is_modified = False
        self._show_placeholder()
    
    def make_editable(self, editable: bool = True):
        """Make the translation editable or read-only"""
        self.is_editable = editable
        if self.translated_editor:
            self.translated_editor.readonly = not editable
            
            if editable:
                self.translated_editor.on_change = self._on_translation_change
            else:
                self.translated_editor.on_change = None
                self.save_button.enabled = False
    
    def get_current_translation(self) -> Optional[Path]:
        """Get current translation path"""
        return self.current_translation_path
    
    def get_original_text(self) -> str:
        """Get original text"""
        return self.original_text
    
    def get_translated_text(self) -> str:
        """Get translated text"""
        return self.translated_text
    
    def get_translation_metadata(self) -> Dict[str, Any]:
        """Get translation metadata"""
        return self.translation_metadata.copy()
    
    def is_translation_modified(self) -> bool:
        """Check if translation has been modified"""
        return self.is_modified 