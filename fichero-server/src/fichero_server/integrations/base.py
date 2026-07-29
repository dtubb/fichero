"""
Base classes for app integrations.

Provides abstract base class and registry for managing integrations.
"""

import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def escape_applescript(value: str) -> str:
    """Escape a Python string for interpolation into an AppleScript string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class IntegrationStatus(str, Enum):
    """Status of an app integration."""

    AVAILABLE = "available"  # App is installed and accessible
    UNAVAILABLE = "unavailable"  # App is not installed
    ERROR = "error"  # Error connecting to app
    DISABLED = "disabled"  # Integration is disabled by user


@dataclass
class AppInfo:
    """Information about an integrated application."""

    name: str
    bundle_id: str
    version: Optional[str] = None
    path: Optional[Path] = None
    status: IntegrationStatus = IntegrationStatus.UNAVAILABLE
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class ImportedItem:
    """An item imported from an external app."""

    external_id: str  # ID in the source app
    name: str  # Display name
    source_app: str  # Source application name
    item_type: str  # Type of item (document, reference, note, etc.)
    file_path: Optional[Path] = None  # Path to associated file
    url: Optional[str] = None  # URL in source app
    metadata: dict = field(default_factory=dict)  # Additional metadata
    content: Optional[str] = None  # Text content if available
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None


class AppIntegration(ABC):
    """Abstract base class for app integrations."""

    def __init__(self):
        self._app_info: Optional[AppInfo] = None
        self._last_error: Optional[str] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the integration."""
        pass

    @property
    @abstractmethod
    def bundle_id(self) -> str:
        """macOS bundle identifier for the app."""
        pass

    @property
    def app_info(self) -> AppInfo:
        """Get current app info, checking availability if needed."""
        if self._app_info is None:
            self.check_availability()
        return self._app_info

    @property
    def is_available(self) -> bool:
        """Check if the app is available."""
        return self.app_info.status == IntegrationStatus.AVAILABLE

    def check_availability(self) -> bool:
        """Check if the application is installed and accessible."""
        try:
            # Use mdfind to check if app with bundle ID exists
            result = subprocess.run(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{self.bundle_id}'"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            paths = result.stdout.strip().split("\n")
            app_path = paths[0] if paths and paths[0] else None

            if app_path and Path(app_path).exists():
                # Get version info
                version = self._get_app_version(Path(app_path))

                self._app_info = AppInfo(
                    name=self.name,
                    bundle_id=self.bundle_id,
                    version=version,
                    path=Path(app_path),
                    status=IntegrationStatus.AVAILABLE,
                    last_checked=datetime.now(),
                )
                logger.info(f"{self.name} found at {app_path} (version {version})")
                return True
            else:
                self._app_info = AppInfo(
                    name=self.name,
                    bundle_id=self.bundle_id,
                    status=IntegrationStatus.UNAVAILABLE,
                    last_checked=datetime.now(),
                )
                logger.info(f"{self.name} not found")
                return False

        except subprocess.TimeoutExpired:
            self._app_info = AppInfo(
                name=self.name,
                bundle_id=self.bundle_id,
                status=IntegrationStatus.ERROR,
                error_message="Timeout checking app availability",
                last_checked=datetime.now(),
            )
            return False
        except Exception as e:
            self._app_info = AppInfo(
                name=self.name,
                bundle_id=self.bundle_id,
                status=IntegrationStatus.ERROR,
                error_message=str(e),
                last_checked=datetime.now(),
            )
            logger.error(f"Error checking {self.name} availability: {e}")
            return False

    def _get_app_version(self, app_path: Path) -> Optional[str]:
        """Get version from app's Info.plist."""
        try:
            plist_path = app_path / "Contents" / "Info.plist"
            if plist_path.exists():
                result = subprocess.run(
                    ["defaults", "read", str(plist_path), "CFBundleShortVersionString"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
        except Exception:
            pass
        return None

    def run_applescript(self, script: str) -> tuple[bool, str]:
        """
        Run an AppleScript and return the result.

        Returns:
            Tuple of (success, result_or_error)
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                error = result.stderr.strip() or "Unknown AppleScript error"
                self._last_error = error
                return False, error

        except subprocess.TimeoutExpired:
            self._last_error = "AppleScript timeout"
            return False, "AppleScript execution timed out"
        except Exception as e:
            self._last_error = str(e)
            return False, str(e)

    @abstractmethod
    async def list_items(
        self,
        limit: int = 100,
        search: Optional[str] = None,
        item_type: Optional[str] = None,
    ) -> list[ImportedItem]:
        """List items from the application."""
        pass

    @abstractmethod
    async def get_item(self, external_id: str) -> Optional[ImportedItem]:
        """Get a specific item by its external ID."""
        pass

    @abstractmethod
    async def import_item(
        self, external_id: str, target_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Import an item from the application.

        Args:
            external_id: The item's ID in the source app
            target_path: Where to save the imported file

        Returns:
            Path to the imported file, or None if import failed
        """
        pass

    async def export_item(
        self, file_path: Path, metadata: Optional[dict] = None
    ) -> Optional[str]:
        """
        Export a file to the application.

        Args:
            file_path: Path to the file to export
            metadata: Optional metadata to include

        Returns:
            External ID of the created item, or None if export failed
        """
        raise NotImplementedError(f"{self.name} does not support export")


class IntegrationRegistry:
    """Registry of available app integrations."""

    _instance: Optional["IntegrationRegistry"] = None

    def __init__(self):
        self._integrations: dict[str, AppIntegration] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "IntegrationRegistry":
        """Get the singleton registry instance."""
        if cls._instance is None:
            cls._instance = IntegrationRegistry()
        return cls._instance

    def register(self, integration: AppIntegration) -> None:
        """Register an integration."""
        self._integrations[integration.name.lower()] = integration
        logger.info(f"Registered integration: {integration.name}")

    def get(self, name: str) -> Optional[AppIntegration]:
        """Get an integration by name."""
        return self._integrations.get(name.lower())

    def list_all(self) -> list[AppIntegration]:
        """List all registered integrations."""
        return list(self._integrations.values())

    def list_available(self) -> list[AppIntegration]:
        """List only available integrations."""
        return [i for i in self._integrations.values() if i.is_available]

    def initialize(self) -> None:
        """Initialize all registered integrations."""
        if self._initialized:
            return

        # Import and register default integrations
        from fichero_server.integrations.devonthink import DEVONthinkIntegration
        from fichero_server.integrations.bookends import BookendsIntegration
        from fichero_server.integrations.tinderbox import TinderboxIntegration

        self.register(DEVONthinkIntegration())
        self.register(BookendsIntegration())
        self.register(TinderboxIntegration())

        self._initialized = True
        logger.info(f"Initialized {len(self._integrations)} app integrations")

    def get_status(self) -> dict[str, Any]:
        """Get status of all integrations."""
        return {
            name: {
                "status": integration.app_info.status.value,
                "version": integration.app_info.version,
                "path": str(integration.app_info.path)
                if integration.app_info.path
                else None,
                "last_checked": integration.app_info.last_checked.isoformat()
                if integration.app_info.last_checked
                else None,
                "error": integration.app_info.error_message,
            }
            for name, integration in self._integrations.items()
        }


# Convenience function to get the registry
def get_integration_registry() -> IntegrationRegistry:
    """Get the global integration registry."""
    registry = IntegrationRegistry.get_instance()
    registry.initialize()
    return registry
