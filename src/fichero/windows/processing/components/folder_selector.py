"""
Folder Selector Component

Handles folder selection, display with icons, and path rendering.
Clean, modular component that can be reused across desktop and mobile.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN, CENTER
from pathlib import Path
import logging
from typing import Optional, Callable

# Use the builtin _ function installed by translation.install()
# No need to import gettext or override _ - it's in builtins after app startup

logger = logging.getLogger(__name__)


class FolderSelector:
    """Folder selection component with icon display and path rendering"""
    
    def __init__(self, app, on_folder_selected: Optional[Callable] = None):
        """Initialize folder selector"""
        self.app = app
        self.on_folder_selected = on_folder_selected
        
        # State
        self.selected_folder: Optional[Path] = None
        
        # UI components (created in create())
        self.container: Optional[toga.Box] = None
        self.icon_container: Optional[toga.Box] = None
        self.path_container: Optional[toga.Box] = None
        self.choose_folder_btn: Optional[toga.Button] = None
        self.folder_canvas: Optional[toga.Canvas] = None
        
        # Icons
        self.question_icon: Optional[toga.Widget] = None
        self.folder_icon: Optional[toga.Widget] = None
        self.current_icon: Optional[toga.Widget] = None
    
    def create(self) -> toga.Box:
        """Create the folder selector UI"""
        # Create folder icons
        self._create_folder_icons()
        
        # Choose folder button
        button_text = _("choose_folder")
        logger.info(f"DEBUG: Translation result for 'choose_folder': '{button_text}'")
        
        self.choose_folder_btn = toga.Button(
            button_text,
            on_press=self._on_choose_folder,
            style=Pack()
        )
        
        # Button container with centering
        button_row = toga.Box(
            children=[
                toga.Box(style=Pack(flex=1)),  # Left spacer
                self.choose_folder_btn,
                toga.Box(style=Pack(flex=1))   # Right spacer
            ],
            style=Pack(direction=ROW, align_items=CENTER)
        )
        
        # Canvas for rounded background
        self.folder_canvas = toga.Canvas(
            style=Pack(flex=1, height=68),
            on_resize=self._draw_folder_background
        )
        
        # Path container (overlays on canvas)
        self.path_container = toga.Box(
            children=[button_row],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                flex=1,
                height=68,
            )
        )
        
        # Stack canvas and path container
        path_with_background = toga.Box(
            children=[self.folder_canvas],
            style=Pack(
                direction=COLUMN,
                margin_top=20,
                margin_right=20,
                margin_bottom=10,
                margin_left=10,
                flex=1,
            )
        )
        
        overlaid_container = toga.Box(
            children=[self.path_container],
            style=Pack(
                direction=COLUMN,
                margin_top=-78,
                margin_right=20,
                margin_left=10,
                flex=1,
            )
        )
        
        path_stack = toga.Box(
            children=[path_with_background, overlaid_container],
            style=Pack(direction=COLUMN, flex=1)
        )
        
        # Icon container
        self.icon_container = toga.Box(
            children=[self.current_icon],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                margin_top=20,
                margin_left=20,
                flex=0
            )
        )
        
        # Main container
        self.container = toga.Box(
            children=[self.icon_container, path_stack],
            style=Pack(direction=ROW, margin=(0, 20, 0, 20))
        )
        
        return self.container
    
    def _create_folder_icons(self):
        """Create different icons for different states"""
        # Question mark icon (default state)
        try:
            if hasattr(self.app, 'paths'):
                icon_path = self.app.paths.app / "resources" / "icons" / "folder_with_question_mark.png"
                if icon_path.exists():
                    question_image = toga.Image(str(icon_path))
                else:
                    question_image = toga.Image("resources/icons/folder_with_question_mark.png")
            else:
                question_image = toga.Image("resources/icons/folder_with_question_mark.png")
            
            self.question_icon = toga.ImageView(
                question_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.warning(f"Could not load question folder icon: {e}")
            self.question_icon = toga.Label(
                "📁?",
                style=Pack(font_size=32, text_align=CENTER, margin=8)
            )
        
        # Start with question mark icon
        self.current_icon = self.question_icon
    
    def _create_folder_icon_widget(self):
        """Create a folder icon widget for selected folder"""
        if self.selected_folder:
            folder_icon = self._get_folder_icon(self.selected_folder)
            if folder_icon:
                return folder_icon
        
        # Fall back to generic folder icon
        try:
            if hasattr(self.app, 'paths'):
                icon_path = self.app.paths.app / "resources" / "icons" / "folder.png"
                if icon_path.exists():
                    folder_image = toga.Image(str(icon_path))
                else:
                    folder_image = toga.Image("resources/icons/folder.png")
            else:
                folder_image = toga.Image("resources/icons/folder.png")
            
            return toga.ImageView(
                folder_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.debug(f"Could not load folder.png icon: {e}")
        
        # Fall back to emoji
        return toga.Label(
            "📁",
            style=Pack(font_size=32, text_align=CENTER, margin=8)
        )
    
    def _get_folder_icon(self, folder_path):
        """Get the actual icon for a specific folder"""
        try:
            from fichero.utils.path_icons import get_folder_icon_path
            
            icon_path = get_folder_icon_path(Path(folder_path), size=62)
            
            if icon_path and Path(icon_path).exists():
                try:
                    folder_image = toga.Image(icon_path)
                    return toga.ImageView(
                        folder_image,
                        style=Pack(width=62, height=62, margin=3)
                    )
                except Exception as e:
                    logger.debug(f"Could not load folder icon from {icon_path}: {e}")
            
            return self._get_default_folder_icon()
            
        except Exception as e:
            logger.debug(f"Could not get folder icon for {folder_path}: {e}")
            return self._get_default_folder_icon()
    
    def _get_default_folder_icon(self):
        """Get the default folder icon"""
        try:
            folder_image = toga.Image("resources/icons/folder.png")
            return toga.ImageView(
                folder_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.debug(f"Could not load folder.png icon: {e}")
        
        return toga.Label(
            "📁",
            style=Pack(font_size=32, text_align=CENTER, margin=8)
        )
    
    def _draw_folder_background(self, canvas=None, **kwargs):
        """Draw rounded gray background"""
        if canvas is None:
            canvas = self.folder_canvas
            
        canvas.context.clear()
        
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6
        
        with canvas.context.Fill(color='#E2DFDE') as background:
            background.begin_path()
            background.move_to(corner_radius, 0)
            background.line_to(width - corner_radius, 0)
            background.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            background.line_to(width, height - corner_radius)
            background.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            background.line_to(corner_radius, height)
            background.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            background.line_to(0, corner_radius)
            background.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            background.close_path()
    
    async def _on_choose_folder(self, widget):
        """Handle folder selection"""
        try:
            dialog = toga.SelectFolderDialog(
                title=_("select_folder_title")
            )
            
            folder_path = await self.app.dialog(dialog)
            
            if folder_path:
                self.selected_folder = Path(folder_path)
                
                # Update to folder icon
                self._switch_to_folder_icon()
                
                # Update path display
                self._show_folder_path()
                
                # Update button text
                self.choose_folder_btn.text = "Choose Different Folder"
                
                # Notify callback
                if self.on_folder_selected:
                    self.on_folder_selected(self.selected_folder)
                
                logger.info(f"Selected folder: {self.selected_folder}")
            
        except Exception as e:
            logger.error(f"Error selecting folder: {e}")
    
    def _switch_to_folder_icon(self):
        """Switch to folder icon"""
        self.folder_icon = self._create_folder_icon_widget()
        self.icon_container.clear()
        self.icon_container.add(self.folder_icon)
        self.current_icon = self.folder_icon
    
    def _switch_to_question_icon(self):
        """Switch to question mark icon"""
        self.icon_container.clear()
        self.icon_container.add(self.question_icon)
        self.current_icon = self.question_icon
    
    def _show_folder_path(self):
        """Show the selected folder path"""
        if not self.selected_folder:
            return
        
        folder_path = str(self.selected_folder)
        
        # Create path display with icons
        path_display = self._create_path_display(folder_path)
        
        # Replace button with path display
        self.path_container.clear()
        self.path_container.add(path_display)
    
    def _create_path_display(self, folder_path):
        """Create path display with icons and wrapping"""
        from fichero.utils.path_icons import PathBuilder, get_fallback_folder_icon, load_image
        
        # Create scrollable container with grey background
        path_display_container = toga.ScrollContainer(
            content=toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=8
                )
            ),
            horizontal=False,
            vertical=True,
            style=Pack(
                flex=1,
                height=68,
                margin=0,
                background_color='#E2DFDE'
            )
        )
        
        # Get path components
        components = PathBuilder.build_path_with_icons(folder_path)
        
        # Build rows with wrapping
        self._build_path_rows(path_display_container.content, components)
        
        return path_display_container
    
    def _build_path_rows(self, container, components):
        """Build path display rows with proper wrapping"""
        from fichero.utils.path_icons import get_fallback_folder_icon, load_image
        
        # Available width estimation
        try:
            canvas_width = self.folder_canvas.layout.content_width if self.folder_canvas else 400
            base_available_width = canvas_width - 32
        except:
            base_available_width = 400
        
        current_row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin_bottom=2))
        current_row_width = 0
        is_continuation_row = False
        
        for i, component in enumerate(components):
            # Calculate available width
            available_width = base_available_width - (15 if is_continuation_row else 0)
            
            # Estimate component width
            icon_width = 18
            if component["name"]:
                is_last_component = (i == len(components) - 1)
                char_count = len(component["name"])
                avg_char_width = 7 if is_last_component else 6
                name_width = char_count * avg_char_width + 8
            else:
                name_width = 0
                
            separator_width = 16 if i < len(components) - 1 else 0
            component_width = icon_width + name_width + separator_width
            
            # Check if we need a new row
            if current_row_width + component_width > available_width and current_row.children:
                container.add(current_row)
                current_row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin_bottom=2, margin_left=15))
                current_row_width = 0
                is_continuation_row = True
            
            # Add icon
            icon_image = None
            if component.get("icon_path"):
                icon_image = load_image(component["icon_path"])
            
            if not icon_image:
                fallback_icon_path = get_fallback_folder_icon()
                if fallback_icon_path:
                    icon_image = load_image(fallback_icon_path)
            
            if icon_image:
                try:
                    icon_widget = toga.ImageView(
                        image=icon_image,
                        style=Pack(width=16, height=16, margin_right=2)
                    )
                    current_row.add(icon_widget)
                except Exception as e:
                    logger.debug(f"Could not create ImageView: {e}")
            
            # Add folder name
            if component["name"]:
                is_last_component = (i == len(components) - 1)
                
                name_label = toga.Label(
                    component["name"],
                    style=Pack(
                        font_size=9,
                        font_weight='bold' if is_last_component else 'normal',
                        margin_right=4
                    )
                )
                current_row.add(name_label)
            
            # Add separator
            if i < len(components) - 1:
                separator_label = toga.Label(
                    "⟩",
                    style=Pack(
                        font_size=9,
                        color='#808080',
                        margin_left=4,
                        margin_right=4
                    )
                )
                current_row.add(separator_label)
            
            current_row_width += component_width
        
        # Add final row
        if current_row.children:
            container.add(current_row)
    
    def reset(self):
        """Reset to initial state"""
        self.selected_folder = None
        self.choose_folder_btn.text = _("choose_folder")
        self._switch_to_question_icon()
        
        # Reset to button
        button_row = toga.Box(
            children=[
                toga.Box(style=Pack(flex=1)),
                self.choose_folder_btn,
                toga.Box(style=Pack(flex=1))
            ],
            style=Pack(direction=ROW, align_items=CENTER)
        )
        self.path_container.clear()
        self.path_container.add(button_row)
    
    def get_selected_folder(self) -> Optional[Path]:
        """Get the currently selected folder"""
        return self.selected_folder 