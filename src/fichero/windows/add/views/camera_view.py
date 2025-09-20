"""
Camera Add View

BaseView for taking photos to add to the library.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
import logging
from typing import Optional, Callable
from pathlib import Path

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class CameraAddView(BaseView):
    """View for adding camera photos to the library"""
    
    def __init__(self, app: toga.App, on_back: Callable, on_content_added: Callable):
        """Initialize camera add view"""
        self.on_back = on_back
        self.on_content_added = on_content_added
        self.last_photo_path: Optional[Path] = None
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("Camera Add View initialized")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for camera add view"""
        try:
            from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using automatic navigation
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Add Picture",
                on_back=self.on_back,
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class CameraAddBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Camera-specific actions could go here
            
            self.bottom_toolbar = CameraAddBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Camera add view toolbars created with automatic navigation")            
        except Exception as e:
            logger.error(f"Failed to create camera add toolbars: {e}")
    
    def _create_content(self):
        """Create the view content"""
        # Title
        title = toga.Label(
            _("Take Picture"),
            style=Pack(
                font_size=20,
                font_weight="bold",
                text_align=CENTER,
                margin=20,
                color="#1a1a1a"
            )
        )
        self.content_container.add(title)
        
        # Description
        description = toga.Label(
            _("Use your device's camera to take a photo and add it to your library."),
            style=Pack(
                font_size=14,
                text_align=CENTER,
                margin=20,
                color="#666666"
            )
        )
        self.content_container.add(description)
        
        # Camera button
        self.camera_button = toga.Button(
            _("📷 Take Photo"),
            on_press=self._on_camera_capture,
            style=Pack(margin=10)
        )
        self.content_container.add(self.camera_button)
        
        # Status label
        self.status_label = toga.Label(
            _("Ready to take photo"),
            style=Pack(margin=10)
        )
        self.content_container.add(self.status_label)
        
        # Photo preview area (placeholder)
        self.preview_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=20,
                height=200
            )
        )
        
        preview_placeholder = toga.Label(
            _("Photo preview will appear here"),
            style=Pack(
                text_align=CENTER,
                margin=50,
                color="#666666"
            )
        )
        self.preview_container.add(preview_placeholder)
        self.content_container.add(self.preview_container)
        
        # Add to library button (initially disabled)
        self.add_button = toga.Button(
            _("Add Photo to Library"),
            on_press=self._on_add_to_library,
            enabled=False,
            style=Pack(margin=10)
        )
        self.content_container.add(self.add_button)
        
        # Instructions
        instructions = toga.Label(
            _("Instructions:\n1. Click 'Take Photo' to open camera\n2. Take your photo\n3. Click 'Add Photo to Library' to save"),
            style=Pack(
                text_align=CENTER,
                margin=20,
                font_size=12,
                color="#666666"
            )
        )
        self.content_container.add(instructions)
    
    async def _on_camera_capture(self, widget):
        """Handle camera capture button press"""
        try:
            self.status_label.text = _("Opening camera...")
            self.camera_button.enabled = False
            
            # Check if camera is available
            if not hasattr(self.app, 'camera') or not self.app.camera:
                self.status_label.text = _("Camera not available on this platform")
                self.camera_button.enabled = True
                return
            
            # Check camera permission
            if not self.app.camera.has_permission:
                logger.info("Requesting camera permission")
                permission_granted = await self.app.camera.request_permission()
                if not permission_granted:
                    self.status_label.text = _("Camera permission denied")
                    self.camera_button.enabled = True
                    return
            
            self.status_label.text = _("Taking photo...")
            
            # Take photo
            photo = await self.app.camera.take_photo()
            
            if photo:
                # Save photo to temporary location
                import tempfile
                import time
                
                # Create temporary file with timestamp
                timestamp = int(time.time())
                temp_dir = Path(tempfile.gettempdir()) / "fichero_camera"
                temp_dir.mkdir(exist_ok=True)
                
                photo_path = temp_dir / f"photo_{timestamp}.jpg"
                
                # Save the photo
                if hasattr(photo, 'save'):
                    photo.save(str(photo_path))
                    self.last_photo_path = photo_path
                    self.status_label.text = _("Photo captured successfully")
                    self.add_button.enabled = True
                    
                    # Update preview area
                    self.preview_container.clear()
                    success_label = toga.Label(
                        _("✓ Photo captured successfully"),
                        style=Pack(
                            text_align=CENTER,
                            margin=50,
                            color="#28a745"
                        )
                    )
                    self.preview_container.add(success_label)
                    
                    logger.info(f"Photo saved to: {photo_path}")
                else:
                    self.status_label.text = _("Failed to save photo")
            else:
                self.status_label.text = _("Photo capture cancelled")
            
            self.camera_button.enabled = True
                
        except Exception as e:
            logger.error(f"Failed to capture photo: {e}")
            self.status_label.text = _("Error capturing photo. Please try again.")
            self.camera_button.enabled = True
    
    async def _on_add_to_library(self, widget):
        """Add captured photo to library"""
        try:
            if not self.last_photo_path:
                self.status_label.text = _("No photo to add")
                return
            
            self.status_label.text = _("Adding photo to library...")
            self.add_button.enabled = False
            
            # Call the callback with the photo
            if self.on_content_added:
                self.on_content_added({'option_id': 'camera', 'photo_path': self.last_photo_path, 'action': 'added'})
                self.status_label.text = _("Photo added successfully!")
                logger.info(f"Successfully added photo to library: {self.last_photo_path}")
            
        except Exception as e:
            logger.error(f"Failed to add photo to library: {e}")
            self.status_label.text = _("Error adding photo. Please try again.")
            self.add_button.enabled = True 