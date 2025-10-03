"""
Simple View Integration for Fichero

Minimal replacement for NavigationManager that creates NavigationController
and integrates with the event-driven system.
"""

import logging
from typing import Optional

from .navigation_controller import NavigationController

logger = logging.getLogger(__name__)


class ViewIntegration:
    """Simple view integration that provides NavigationController"""

    def __init__(self, app):
        """Initialize with app reference"""
        self.app = app
        self.navigation_controller: Optional[NavigationController] = None

        logger.info("ViewIntegration initialized")

    def initialize(self) -> bool:
        """Initialize the navigation controller"""
        try:
            # Get library service from app
            library_service = getattr(self.app, 'library_service', None)
            if not library_service:
                logger.error("Cannot initialize: no library service found in app")
                return False

            # Detect mobile platform
            is_mobile = self._detect_mobile_platform()
            logger.info(f"ViewIntegration: Detected platform is_mobile={is_mobile}")

            # Create navigation controller
            self.navigation_controller = NavigationController(
                library_service=library_service,
                app=self.app,
                is_mobile=is_mobile
            )

            logger.info("Navigation controller initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ViewIntegration: {e}")
            return False

    def get_navigation_controller(self) -> Optional[NavigationController]:
        """Get the navigation controller"""
        return self.navigation_controller

    def _detect_mobile_platform(self) -> bool:
        """Detect if we're running on a mobile platform"""
        try:
            # Check environment variable first
            import os
            env_mobile = os.environ.get('FORCE_MOBILE_UI')
            if env_mobile is not None:
                is_mobile = env_mobile.lower() in ('true', '1', 'yes', 'on')
                logger.info(f"ViewIntegration: Using environment variable FORCE_MOBILE_UI: {is_mobile}")
                return is_mobile

            # Use Toga's platform detection
            import toga.platform
            current_platform = toga.platform.current_platform
            is_mobile = current_platform in ['iOS', 'android']

            logger.info(f"ViewIntegration: Platform detection: {current_platform} -> mobile={is_mobile}")
            return is_mobile

        except Exception as e:
            logger.warning(f"ViewIntegration: Failed to detect platform, defaulting to desktop: {e}")
            return False