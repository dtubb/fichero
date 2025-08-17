"""
Refactored Collection View

Clean modular collection view system organized by UI components.
Desktop = Current Level + Preview columns (simplified, no tree)
Mobile = Single DetailedList using shared middle column logic
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging

from .collection.presenter import CollectionPresenter
# Removed TreeNavigationColumn import
from .collection.middle_column import CurrentLevelColumn
from .collection.right_column import PreviewColumn
from .collection.mobile_view import MobileCollectionView

logger = logging.getLogger(__name__)


class DesktopCollectionView:
    """Desktop collection view with two-column layout (no tree)"""
    
    def __init__(self, app):
        self.app = app
        
        # Single presenter handles all logic
        self.presenter = CollectionPresenter(app)
        
        # Two column components (removed tree)
        self.middle_column = CurrentLevelColumn(self.presenter, include_header=True, width=600)
        self.right_column = PreviewColumn(self.presenter, width=300)
        
        # Create main container
        self.container = toga.Box(style=Pack(direction=ROW, flex=1))
        self.container.add(self.middle_column.container)
        self.container.add(self.right_column.container)
        
        logger.info("Created desktop collection view with two-column layout (no tree)")
    
    async def initialize(self):
        """Initialize the view"""
        logger.info("Initializing desktop collection view...")
        result = await self.presenter.initialize()
        logger.info(f"Desktop collection view initialized: {result}")
        return result
    
    def create(self) -> toga.Widget:
        """Create method for view manager compatibility"""
        return self.container
    
    def get_container(self) -> toga.Widget:
        """Get container method for backward compatibility"""
        return self.container
    
    async def refresh(self):
        """Refresh the view"""
        try:
            await self.presenter.nav_logic.load_collections()
        except Exception as e:
            logger.error(f"Failed to refresh: {e}")


class CollectionView:
    """
    Main collection view that creates platform-appropriate UI.
    
    Factory that returns either desktop (3-column) or mobile (1-column) view.
    """
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize collection view with platform detection"""
        self.app = app
        self.is_mobile = is_mobile
        
        if is_mobile:
            # Mobile: Single DetailedList using shared middle column logic
            self.presenter = CollectionPresenter(app)
            self.view = MobileCollectionView(self.presenter)
            self.container = self.view.container
        else:
            # Desktop: Two-column layout (List + Preview, no tree)
            self.view = DesktopCollectionView(app)
            self.presenter = self.view.presenter
            self.container = self.view.container
        
        logger.info(f"Created collection view (mobile: {is_mobile})")
    
    async def initialize(self):
        """Initialize the view"""
        if self.is_mobile:
            logger.info("Initializing mobile collection view...")
            result = await self.presenter.initialize()
            logger.info(f"Mobile collection view initialized: {result}")
            return result
        else:
            return await self.view.initialize()
    
    def create(self) -> toga.Widget:
        """Create method for view manager compatibility"""
        return self.container
    
    def get_container(self) -> toga.Widget:
        """Get container method for backward compatibility"""
        return self.container
    
    async def refresh(self):
        """Refresh the view"""
        if self.is_mobile:
            try:
                await self.presenter.nav_logic.load_collections()
            except Exception as e:
                logger.error(f"Failed to refresh: {e}")
        else:
            await self.view.refresh() 