"""Editor Protocol - Base class for all editors.

Defines the interface that all editors must implement.

Usage:
    from fichero.app.main_window.views.library.viewers.base import EditorProtocol

    class MyEditor(EditorProtocol):
        @property
        def native(self):
            return self._view

        def load(self, item):
            ...

        def clear(self):
            ...
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EditorProtocol(ABC):
    """Protocol for editor views.

    All editors must implement:
    - native: The NSView to display
    - load(item): Load content to display/edit
    - clear(): Clear the editor content
    """

    @property
    @abstractmethod
    def native(self) -> Any:
        """The native NSView to display."""
        pass

    @abstractmethod
    def load(self, item: Any) -> None:
        """Load content to display/edit.

        Args:
            item: Document, Artifact, path, or other content
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear the editor content."""
        pass
