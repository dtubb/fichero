import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
import srsly
from pathlib import Path
from ..i18n import _
import os

class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.settings = self.load_settings()
        self.window = None
        
    def load_settings(self) -> dict:
        """Load app settings from user data directory"""
        settings_path = self.app.paths.data / "app_settings.json"
        
        if not settings_path.exists():
            # Copy default settings from resources
            default_settings_path = self.app.paths.app / "resources" / "default_app_settings.json"
            default_settings = srsly.read_json(default_settings_path)
            
            # Ensure data directory exists
            if not self.app.paths.data.exists():
                self.app.paths.data.mkdir(parents=True, exist_ok=True)
            
            # Save default settings
            srsly.write_json(settings_path, default_settings)
            return default_settings
        
        return srsly.read_json(settings_path)
    
    def save_settings(self):
        """Save current settings to user data directory"""
        from ..app_settings import get_app_settings
        settings = get_app_settings(self.app)
        settings.save_settings(self.settings)
    
    def show(self):
        """Show the settings window"""
        if self.window:
            self.window.show()
            return
            
        self.window = toga.Window(
            title=_("app_preferences"),
            size=(430, 520),
            resizable=False
        )
        
        # Create tab bar style selector
        self.current_tab = "api_servers"
        
        # Tab buttons
        self.api_tab_btn = toga.Button(
            "🔑 " + _("api_servers"),
            on_press=lambda w: self.switch_tab("api_servers"),
            style=Pack(
                width=150,
                height=40,
                margin_right=10,
                font_size=12
            )
        )
        
        self.advanced_tab_btn = toga.Button(
            "⚙️ " + _("advanced"),
            on_press=lambda w: self.switch_tab("advanced"),
            style=Pack(
                width=150,
                height=40,
                font_size=12
            )
        )
        
        # Center the tab buttons
        tab_spacer_left = toga.Box(style=Pack(flex=1))
        tab_spacer_right = toga.Box(style=Pack(flex=1))
        
        tab_bar = toga.Box(
            children=[
                tab_spacer_left,
                self.api_tab_btn,
                self.advanced_tab_btn,
                tab_spacer_right
            ],
            style=Pack(
                direction=ROW,
                margin=(20, 20, 20, 20)
            )
        )
        
        # Content area
        self.content_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=(0, 20, 20, 20)
            )
        )
        
        # Main layout
        main_box = toga.Box(
            children=[tab_bar, self.content_box],
            style=Pack(direction=COLUMN, flex=1)
        )
        
        self.window.content = main_box
        
        # Initialize all UI elements
        self._initialize_all_ui_elements()
        
        # Show initial tab
        self.switch_tab("api_servers")
        
        # Set up auto-save on window close
        self.window.on_close = self._auto_save_and_close
        
        self.window.show()
    
    def _initialize_all_ui_elements(self):
        """Initialize all UI elements so they exist for saving"""
        # API Servers elements
        self.openai_enabled = toga.Switch("Enabled", value=self.settings["api_servers"]["openai"]["enabled"])
        self.openai_key = toga.PasswordInput(value=self.settings["api_servers"]["openai"]["api_key"], placeholder="sk-...")
        self.qwen_enabled = toga.Switch("Enabled", value=self.settings["api_servers"]["qwen"]["enabled"])
        self.qwen_key = toga.PasswordInput(value=self.settings["api_servers"]["qwen"]["api_key"], placeholder="sk-...")
        
        # Advanced elements
        self.cpu_workers = toga.NumberInput(value=self.settings["workers"]["cpu_workers"])
        self.io_workers = toga.NumberInput(value=self.settings["workers"]["io_workers"])
        self.memory_per_worker = toga.NumberInput(value=self.settings["workers"]["memory_per_worker_mb"])
    
    def switch_tab(self, tab_name):
        """Switch between tabs"""
        self.current_tab = tab_name
        
        # Update button styles
        if tab_name == "api_servers":
            self.api_tab_btn.style.background_color = "#007AFF"
            self.api_tab_btn.style.color = "#FFFFFF"
            # Reset other button style
            if hasattr(self.advanced_tab_btn.style, 'background_color'):
                del self.advanced_tab_btn.style.background_color
            if hasattr(self.advanced_tab_btn.style, 'color'):
                del self.advanced_tab_btn.style.color
        else:
            self.advanced_tab_btn.style.background_color = "#007AFF"
            self.advanced_tab_btn.style.color = "#FFFFFF"
            # Reset other button style
            if hasattr(self.api_tab_btn.style, 'background_color'):
                del self.api_tab_btn.style.background_color
            if hasattr(self.api_tab_btn.style, 'color'):
                del self.api_tab_btn.style.color
        
        # Clear and rebuild content
        self.content_box.clear()
        
        if tab_name == "api_servers":
            self._build_api_servers_tab()
        else:
            self._build_advanced_tab()
    
    def _build_api_servers_tab(self):
        """Build the API Servers tab content"""
        
        # OpenAI
        self.content_box.add(toga.Label("OpenAI", style=Pack(font_size=12, margin_bottom=5)))
        self.content_box.add(self.openai_enabled)
        self.content_box.add(toga.Label("API Key:", style=Pack(font_size=12, margin_top=10)))
        self.openai_key.style = Pack(margin=(10, 0, 20, 0))
        self.content_box.add(self.openai_key)
        
        # Qwen
        self.content_box.add(toga.Label("Qwen", style=Pack(font_size=12, margin_bottom=5, margin_top=20)))
        self.content_box.add(self.qwen_enabled)
        self.content_box.add(toga.Label("API Key:", style=Pack(font_size=12, margin_top=10)))
        self.qwen_key.style = Pack(margin=(10, 0, 20, 0))
        self.content_box.add(self.qwen_key)
    
    def _build_advanced_tab(self):
        """Build the Advanced tab content"""
        
        # Worker Performance
        self.content_box.add(toga.Label("Worker Performance", style=Pack(font_size=12, margin_bottom=10)))
        
        # CPU Workers
        self.content_box.add(toga.Label("CPU Workers:", style=Pack(font_size=12, margin_bottom=5)))
        self.cpu_workers.style = Pack(margin_bottom=20)
        self.content_box.add(self.cpu_workers)
        
        # IO Workers
        self.content_box.add(toga.Label("I/O Workers:", style=Pack(font_size=12, margin_bottom=5)))
        self.io_workers.style = Pack(margin_bottom=20)
        self.content_box.add(self.io_workers)
        
        # Memory per Worker
        self.content_box.add(toga.Label("Memory per Worker (MB):", style=Pack(font_size=12, margin_bottom=5)))
        self.memory_per_worker.style = Pack(margin_bottom=20)
        self.content_box.add(self.memory_per_worker)
    
    def _auto_save_and_close(self, widget):
        """Auto-save settings when window closes"""
        # Update settings from UI
        self.settings["api_servers"]["openai"]["enabled"] = self.openai_enabled.value
        self.settings["api_servers"]["openai"]["api_key"] = self.openai_key.value
        
        self.settings["api_servers"]["qwen"]["enabled"] = self.qwen_enabled.value
        self.settings["api_servers"]["qwen"]["api_key"] = self.qwen_key.value
        
        self.settings["workers"]["cpu_workers"] = int(self.cpu_workers.value)
        self.settings["workers"]["io_workers"] = int(self.io_workers.value)
        self.settings["workers"]["memory_per_worker_mb"] = int(self.memory_per_worker.value)
        
        # Set environment variables for API keys
        if self.settings["api_servers"]["openai"]["api_key"]:
            os.environ["OPENAI_API_KEY"] = self.settings["api_servers"]["openai"]["api_key"]
        if self.settings["api_servers"]["qwen"]["api_key"]:
            os.environ["DASHSCOPE_API_KEY"] = self.settings["api_servers"]["qwen"]["api_key"]
        
        # Save to file
        self.save_settings()
        
        # Reload the app settings to reflect changes
        from ..app_settings import reload_settings
        reload_settings(self.app)
        
        # Reset window
        self.window = None
        
        print("Settings auto-saved and reloaded!")
        
        # Return True to allow the window to close
        return True