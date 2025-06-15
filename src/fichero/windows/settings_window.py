"""
Settings window for Fichero application
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
from ..i18n import _, translator


class SettingsWindow:
    """Settings window for configuring Fichero options"""
    
    def __init__(self, app):
        """Initialize the settings window"""
        self.app = app
        self.window = toga.Window(
            title=_("settings_title") if hasattr(_, '__call__') else "Settings",
            size=(500, 600),
            resizable=False
        )
        
        # Initialize settings storage
        self.settings = self._load_settings()
        
        # Create the UI
        self._create_ui()
    
    def _load_settings(self):
        """Load settings from storage (placeholder for now)"""
        # TODO: Implement actual settings persistence
        return {
            'language': 'en',
            'theme': 'system',
            'auto_open_output': True,
            'max_workers': 4,
            'notification_enabled': True
        }
    
    def _save_settings(self):
        """Save settings to storage (placeholder for now)"""
        # TODO: Implement actual settings persistence
        print(f"Saving settings: {self.settings}")
    
    def _create_ui(self):
        """Create the settings UI"""
        # Main container
        main_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=20
            )
        )
        
        # Language section
        main_container.add(self._create_section_header("Language"))
        main_container.add(self._create_language_section())
        main_container.add(self._create_horizontal_separator())
        
        # Processing section
        main_container.add(self._create_section_header("Processing"))
        main_container.add(self._create_processing_section())
        main_container.add(self._create_horizontal_separator())
        
        # Output section
        main_container.add(self._create_section_header("Output"))
        main_container.add(self._create_output_section())
        main_container.add(self._create_horizontal_separator())
        
        # Notification section
        main_container.add(self._create_section_header("Notifications"))
        main_container.add(self._create_notification_section())
        
        # Spacer to push buttons to bottom
        main_container.add(toga.Box(style=Pack(flex=1)))
        
        # Buttons section
        main_container.add(self._create_buttons_section())
        
        # Set window content
        self.window.content = main_container
    
    def show(self):
        """Show the window"""
        self.window.show()
    
    def hide(self):
        """Hide the window"""
        self.window.hide()
    
    def _create_section_header(self, text):
        """Create a section header label"""
        return toga.Label(
            text,
            style=Pack(
                font_size=14,
                font_weight='bold',
                margin=(15, 5, 5, 5)
            )
        )
    
    def _create_horizontal_separator(self):
        """Create a horizontal separator line"""
        return toga.Box(
            style=Pack(
                height=1,
                background_color='rgb(200, 200, 200)',
                margin=(10, 20)
            )
        )
    
    def _create_language_section(self):
        """Create language selection section"""
        section = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 0, 20)
            )
        )
        
        # Language selection
        language_box = toga.Box(
            style=Pack(
                direction=ROW,
                align_items='start',
                margin=(5, 0)
            )
        )
        
        language_label = toga.Label(
            "Language:", 
            style=Pack(margin_right=10)
        )
        
        # Language dropdown
        self.language_selection = toga.Selection(
            items=[
                ("English", "en"),
                ("Español", "es"),
                ("Français", "fr")
            ],
            style=Pack(width=150),
            on_change=self._on_language_change
        )
        
        # Set current language
        current_lang = self.settings.get('language', 'en')
        for item in self.language_selection.items:
            if item.value == current_lang:
                self.language_selection.value = item
                break
        
        language_box.add(language_label)
        language_box.add(self.language_selection)
        section.add(language_box)
        
        return section
    
    def _create_processing_section(self):
        """Create processing configuration section"""
        section = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 0, 20)
            )
        )
        
        # Max workers setting
        workers_box = toga.Box(
            style=Pack(
                direction=ROW,
                align_items='start',
                margin=(5, 0)
            )
        )
        
        workers_label = toga.Label(
            "Max Workers:", 
            style=Pack(margin_right=10)
        )
        
        self.workers_input = toga.NumberInput(
            value=self.settings.get('max_workers', 4),
            style=Pack(width=80),
            on_change=self._on_workers_change
        )
        
        workers_help = toga.Label(
            "(1-16, higher = faster but uses more CPU)",
            style=Pack(
                font_size=10,
                color='rgb(100, 100, 100)',
                margin_left=10
            )
        )
        
        workers_box.add(workers_label)
        workers_box.add(self.workers_input)
        workers_box.add(workers_help)
        section.add(workers_box)
        
        return section
    
    def _create_output_section(self):
        """Create output configuration section"""
        section = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 0, 20)
            )
        )
        
        # Auto-open output folder checkbox
        self.auto_open_switch = toga.Switch(
            text="Automatically open output folder when complete",
            value=self.settings.get('auto_open_output', True),
            style=Pack(margin=(5, 0)),
            on_change=self._on_auto_open_change
        )
        
        section.add(self.auto_open_switch)
        
        return section
    
    def _create_notification_section(self):
        """Create notification configuration section"""
        section = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 0, 20)
            )
        )
        
        # Notification enabled checkbox
        self.notification_switch = toga.Switch(
            text="Enable notifications when processing completes",
            value=self.settings.get('notification_enabled', True),
            style=Pack(margin=(5, 0)),
            on_change=self._on_notification_change
        )
        
        section.add(self.notification_switch)
        
        return section
    
    def _create_buttons_section(self):
        """Create buttons section"""
        buttons_box = toga.Box(
            style=Pack(
                direction=ROW,
                align_items=CENTER,
                margin=(20, 0, 0, 0)
            )
        )
        
        # Reset to defaults button
        reset_btn = toga.Button(
            "Reset to Defaults",
            on_press=self._on_reset_defaults,
            style=Pack(margin_right=10)
        )
        
        # Cancel button
        cancel_btn = toga.Button(
            "Cancel",
            on_press=self._on_cancel,
            style=Pack(margin_right=10)
        )
        
        # Save button (primary)
        save_btn = toga.Button(
            "Save",
            on_press=self._on_save,
            style=Pack(font_weight='bold')
        )
        
        buttons_box.add(reset_btn)
        buttons_box.add(cancel_btn)
        buttons_box.add(save_btn)
        
        return buttons_box
    
    def _on_language_change(self, widget, **kwargs):
        """Handle language selection change"""
        if widget.value:
            self.settings['language'] = widget.value.value
    
    def _on_workers_change(self, widget, **kwargs):
        """Handle max workers change"""
        self.settings['max_workers'] = int(widget.value)
    
    def _on_auto_open_change(self, widget, **kwargs):
        """Handle auto-open output folder change"""
        self.settings['auto_open_output'] = widget.value
    
    def _on_notification_change(self, widget, **kwargs):
        """Handle notification setting change"""
        self.settings['notification_enabled'] = widget.value
    
    def _on_reset_defaults(self, widget, **kwargs):
        """Reset settings to defaults"""
        self.settings = {
            'language': 'en',
            'theme': 'system',
            'auto_open_output': True,
            'max_workers': 4,
            'notification_enabled': True
        }
        
        # Update UI with default values
        self._update_ui_from_settings()
    
    def _on_cancel(self, widget, **kwargs):
        """Cancel settings changes and close window"""
        # Reload original settings
        self.settings = self._load_settings()
        self.hide()
    
    def _on_save(self, widget, **kwargs):
        """Save settings and close window"""
        self._save_settings()
        
        # Apply language change if needed
        if hasattr(translator, 'set_language'):
            translator.set_language(self.settings['language'])
            # Could trigger a UI refresh in main app here
        
        self.hide()
    
    def _update_ui_from_settings(self):
        """Update UI elements to match current settings"""
        # Update language selection
        current_lang = self.settings.get('language', 'en')
        for item in self.language_selection.items:
            if item.value == current_lang:
                self.language_selection.value = item
                break
        
        # Update other controls
        self.workers_input.value = self.settings.get('max_workers', 4)
        self.auto_open_switch.value = self.settings.get('auto_open_output', True)
        self.notification_switch.value = self.settings.get('notification_enabled', True) 