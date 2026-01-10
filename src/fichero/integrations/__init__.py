"""
App Integrations Module.

Provides integrations with macOS applications:
- DEVONthink: Document management
- Bookends: Reference management
- Tinderbox: Note-taking and information management
"""

from fichero.integrations.devonthink import DEVONthinkIntegration
from fichero.integrations.bookends import BookendsIntegration
from fichero.integrations.tinderbox import TinderboxIntegration
from fichero.integrations.base import AppIntegration, IntegrationRegistry

__all__ = [
    "DEVONthinkIntegration",
    "BookendsIntegration",
    "TinderboxIntegration",
    "AppIntegration",
    "IntegrationRegistry",
]
