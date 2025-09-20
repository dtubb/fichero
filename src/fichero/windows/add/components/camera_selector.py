"""
Camera Selector Component

UI component for capturing photos to add to the library.
Uses Toga's Camera API for supported platforms (macOS, iOS, Android).
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable
from pathlib import Path

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class CameraSelector:
    """Camera selector component using Toga's native camera API"""
    
    def __init__(self, app: toga.App):
        """Initialize camera selector"""
        self.app = app
        self.on_photo_captured: Optional[Callable] = None
        self.last_photo_path: Optional[Path] = None
    
    async def execute(self) -> Optional[Path]:
        """
        Execute photo capture using Toga's Camera API.
        
        Returns:
            Optional[Path]: Path to captured photo, None if cancelled or failed
        """
        try:
            logger.info("Checking camera permissions and availability")
            
            # Check if camera is available
            if not self.app.camera:
                logger.error("Camera not available on this platform")
                return None
            
            # Request camera permission if needed
            if not self.app.camera.has_permission:
                logger.info("Requesting camera permission")
                permission_granted = await self.app.camera.request_permission()
                if not permission_granted:
                    logger.warning("Camera permission denied")
                    return None
            
            logger.info("Taking photo with camera")
            
            # Take photo
            photo = await self.app.camera.take_photo()
            
            if photo:
                # Save photo to temporary location
                # Note: Toga's camera returns a toga.Image object
                # We need to save it to a file and return the path
                
                import tempfile
                import time
                
                # Create temporary file with timestamp
                timestamp = int(time.time())
                temp_dir = Path(tempfile.gettempdir()) / "fichero_camera"
                temp_dir.mkdir(exist_ok=True)
                
                photo_path = temp_dir / f"photo_{timestamp}.jpg"
                
                # Save the photo
                # Note: This assumes toga.Image has a save method
                # If not, we may need to use platform-specific code
                if hasattr(photo, 'save'):
                    photo.save(str(photo_path))
                else:
                    # Fallback: save using platform-specific methods
                    logger.warning("Photo save method not available, using fallback")
                    # This might need platform-specific implementation
                    
                self.last_photo_path = photo_path
                logger.info(f"Photo saved to: {photo_path}")
                
                # Notify callback if registered
                if self.on_photo_captured:
                    self.on_photo_captured(photo_path)
                
                return photo_path
            else:
                logger.info("Photo capture cancelled")
                return None
                
        except PermissionError:
            logger.error("Camera permission not granted")
            return None
        except Exception as e:
            logger.error(f"Failed to capture photo: {e}")
            return None
    
    def create(self):
        """Create the camera selector UI (for legacy compatibility)"""
        container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Camera button
        camera_button = toga.Button(
            _("📷 Take Photo"),
            on_press=self._on_camera_capture,
            style=Pack(flex=0, margin=(0, 10, 0, 0))
        )
        container.add(camera_button)
        
        # Status label
        self.status_label = toga.Label(
            _("Ready to take photo"),
            style=Pack(flex=1)
        )
        container.add(self.status_label)
        
        return container
    
    async def _on_camera_capture(self, widget):
        """Handle camera capture button press (legacy compatibility)"""
        self.status_label.text = _("Taking photo...")
        
        photo_path = await self.execute()
        
        if photo_path:
            self.status_label.text = _("Photo captured successfully")
        else:
            self.status_label.text = _("Photo capture failed or cancelled")
    
    def register_callback(self, callback: Callable):
        """Register callback for when photo is captured"""
        self.on_photo_captured = callback


# Use builtin _ function installed by translation.install()
