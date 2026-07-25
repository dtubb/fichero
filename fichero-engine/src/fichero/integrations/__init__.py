"""
App Integrations Module.

Provides integrations with macOS applications:
- DEVONthink: Document management
- Bookends: Reference management
- Tinderbox: Note-taking and information management
"""

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "DEVONthinkIntegration": ("devonthink", "DEVONthinkIntegration"),
    "BookendsIntegration": ("bookends", "BookendsIntegration"),
    "TinderboxIntegration": ("tinderbox", "TinderboxIntegration"),
    "AppIntegration": ("base", "AppIntegration"),
    "IntegrationRegistry": ("base", "IntegrationRegistry"),
}


def __getattr__(name: str) -> Any:
    """Resolve public integration exports without package import cycles."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "DEVONthinkIntegration",
    "BookendsIntegration",
    "TinderboxIntegration",
    "AppIntegration",
    "IntegrationRegistry",
]
