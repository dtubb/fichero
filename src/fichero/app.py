"""
Fichero - Document Processing and Transcription GUI
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW


class FicheroUnified(toga.App):
    def startup(self):
        """Initialize the app when it starts up."""
        print("🚀 App starting up...")
        
        # Create the sidebar content
        sidebar = toga.Box(style=Pack(
            direction=COLUMN,
            flex=1, 
            margin=10,
            background_color='#f0f0f0'
        ))
        sidebar_button = toga.Button("Sidebar Button", on_press=self.button_handler)
        sidebar_label = toga.Label("Sidebar", style=Pack(font_weight='bold', margin_bottom=5))
        sidebar.add(sidebar_label)
        sidebar.add(sidebar_button)
        
        # Create the main content area
        main_content = toga.Box(style=Pack(
            direction=COLUMN,
            flex=3, 
            margin=10
        ))
        content_button = toga.Button("Content Button", on_press=self.button_handler)
        content_label = toga.Label("Main Content", style=Pack(font_weight='bold', margin_bottom=5))
        main_content.add(content_label)
        main_content.add(content_button)
        
        # Create a split container (modern replacement for NavigationView)
        split_container = toga.SplitContainer(
            content=[sidebar, main_content],
            style=Pack(flex=1)
        )
        
        print("🖼️ Creating main window...")
        # Create main window explicitly (like the working example)
        self.main_window = toga.MainWindow(title="Fichero", size=(800, 600))
        self.main_window.content = split_container
        
        print("✨ Showing window...")
        self.main_window.show()
        print("🎉 Window should now be visible!")

    def button_handler(self, widget):
        """Handle button clicks."""
        print(f"🔘 Button clicked: {widget.text}")


def main():
    """Main entry point for the app."""
    return FicheroUnified("Fichero", "org.beeware.toga.examples.tutorial")


if __name__ == "__main__":
    app = main()
    app.main_loop() 