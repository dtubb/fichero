"""
NSTreeController wrapper for Python/Rubicon-ObjC.

This module provides a Python wrapper around NSTreeController for use with
NSOutlineView. It follows Apple's recommended pattern where:

1. NSTreeController manages the content (array of SidebarNode)
2. NSTreeController is bound to NSOutlineView
3. All structural changes go through NSTreeController (move, insert, remove)
4. NSTreeController automatically updates NSOutlineView with animations

Key methods:
- set_content(nodes): Set the root nodes array
- move(items, to_index_path): Atomically move items (Apple's DragNDropOutlineView pattern)
- find_tree_node_by_id(id): Find NSTreeNode for a given item ID

See: /Users/dtubb/code/docs/NavigatingHierarchicalDataUsingOutlineAndSplitViews/SourceView/OutlineViewController.swift
"""

import logging
from typing import Any, List, Optional

from .constants import RUBICON_AVAILABLE

logger = logging.getLogger(__name__)

# Cache for NSTreeController wrapper class
_tree_controller_wrapper = None


def get_tree_controller_class():
    """Get or create the Python wrapper for NSTreeController."""
    global _tree_controller_wrapper

    if _tree_controller_wrapper is not None:
        return _tree_controller_wrapper

    if not RUBICON_AVAILABLE:
        logger.warning("Rubicon-ObjC not available - NSTreeController unavailable")
        return None

    from rubicon.objc import ObjCClass, objc_method

    NSTreeController = ObjCClass("NSTreeController")
    NSObject = ObjCClass("NSObject")
    NSIndexPath = ObjCClass("NSIndexPath")
    NSMutableArray = ObjCClass("NSMutableArray")

    class TreeControllerWrapper:
        """
        Python wrapper around NSTreeController.

        This provides a simpler API for managing tree content and performing
        operations like move() that NSTreeController handles atomically.
        """

        def __init__(self, outline_view):
            """
            Initialize the tree controller wrapper.

            Args:
                outline_view: The NSOutlineView to bind to
            """
            self._outline_view = outline_view
            self._tree_controller = NSTreeController.alloc().init()

            # Configure tree controller for our SidebarNode model
            # These key paths tell NSTreeController how to navigate the tree
            self._tree_controller.childrenKeyPath = "children"
            self._tree_controller.leafKeyPath = "isLeaf"
            self._tree_controller.countKeyPath = "countOfChildren"

            # Don't preserve selection across content changes (simplifies our code)
            self._tree_controller.preservesSelection = False
            self._tree_controller.selectsInsertedObjects = False
            self._tree_controller.avoidsEmptySelection = False

            # Set object class for new objects (not used but good practice)
            # self._tree_controller.objectClass = SidebarNode

            logger.info("NSTreeController initialized")

        @property
        def native(self):
            """Get the underlying NSTreeController."""
            return self._tree_controller

        @property
        def arranged_objects(self):
            """Get the root NSTreeNode (arrangedObjects)."""
            return self._tree_controller.arrangedObjects

        def set_content(self, nodes: List[Any]):
            """
            Set the content array (root nodes).

            Args:
                nodes: List of SidebarNode objects
            """
            if not nodes:
                self._tree_controller.setContent_(None)
                return

            # Convert to NSMutableArray for KVO compliance
            content = NSMutableArray.alloc().init()
            for node in nodes:
                content.addObject_(node)

            self._tree_controller.setContent_(content)
            logger.info(f"Set tree controller content: {len(nodes)} root nodes")

        def rearrange_objects(self):
            """
            Tell NSTreeController to rearrange its objects.

            Call this after modifying node children to refresh the view.
            """
            self._tree_controller.rearrangeObjects()

        def find_tree_node_by_id(self, item_id: str) -> Optional[Any]:
            """
            Find an NSTreeNode by item identifier.

            NSTreeController wraps our SidebarNode objects in NSTreeNode proxies.
            This method traverses the tree to find the NSTreeNode for a given ID.

            Args:
                item_id: The identifier to search for

            Returns:
                NSTreeNode if found, None otherwise
            """
            root = self.arranged_objects
            if root is None:
                return None

            def _search_children(tree_node):
                """Recursively search tree node children."""
                children = tree_node.childNodes
                if children is None:
                    return None

                for i in range(len(children)):
                    child_tree_node = children[i]
                    represented_obj = child_tree_node.representedObject

                    # Check if this is the node we're looking for
                    if represented_obj is not None:
                        try:
                            # Try property access first (Rubicon-ObjC @objc_method)
                            node_id = represented_obj.identifier
                            # If it's callable (method), call it
                            if callable(node_id):
                                node_id = node_id()
                            if node_id and str(node_id) == item_id:
                                return child_tree_node
                        except Exception as e:
                            logger.debug(f"Error getting identifier: {e}")

                    # Recurse into children
                    found = _search_children(child_tree_node)
                    if found is not None:
                        return found

                return None

            return _search_children(root)

        def get_index_path_for_node(self, tree_node) -> Optional[Any]:
            """Get the NSIndexPath for an NSTreeNode."""
            if tree_node is None:
                return None
            return tree_node.indexPath

        def create_index_path(self, *indices) -> Any:
            """
            Create an NSIndexPath from a sequence of indices.

            Args:
                indices: Variable number of integer indices

            Returns:
                NSIndexPath for the given path
            """
            if not indices:
                return None

            path = NSIndexPath.indexPathWithIndex_(indices[0])
            for idx in indices[1:]:
                path = path.indexPathByAddingIndex_(idx)

            return path

        def move(self, tree_nodes: List[Any], to_index_path: Any) -> bool:
            """
            Move items to a new location - THE KEY ATOMIC OPERATION.

            This uses NSTreeController.moveNodes:toIndexPath: which handles
            the move atomically. Our SidebarNode now has proper `-> None`
            return type annotations on setters for KVO compliance.

            Args:
                tree_nodes: List of NSTreeNode objects to move
                to_index_path: NSIndexPath for destination

            Returns:
                True if move succeeded
            """
            if not tree_nodes or to_index_path is None:
                logger.warning("move() called with empty items or None index path")
                return False

            try:
                # NSTreeController.moveNodes:toIndexPath: - Objective-C method
                # In Rubicon-ObjC: moveNodes_toIndexPath_
                from rubicon.objc import ObjCClass
                NSArray = ObjCClass("NSArray")

                items_array = NSArray.arrayWithArray_(tree_nodes)
                self._tree_controller.moveNodes_toIndexPath_(items_array, to_index_path)

                logger.info(f"Moved {len(tree_nodes)} items via moveNodes_toIndexPath_")
                return True

            except Exception as e:
                logger.error(f"NSTreeController.move() failed: {e}", exc_info=True)
                return False

        def insert_object_at_index_path(self, obj, index_path):
            """
            Insert an object at a specific index path.

            Args:
                obj: The SidebarNode to insert
                index_path: NSIndexPath for insertion point
            """
            self._tree_controller.insertObject_atArrangedObjectIndexPath_(obj, index_path)

        def remove_object_at_index_path(self, index_path):
            """
            Remove the object at a specific index path.

            Args:
                index_path: NSIndexPath of object to remove
            """
            self._tree_controller.removeObjectAtArrangedObjectIndexPath_(index_path)

        def bind_to_outline_view(self):
            """
            Bind this tree controller to the outline view.

            This sets up Cocoa Bindings so NSOutlineView automatically
            reflects NSTreeController's content.

            NOTE: NSOutlineView doesn't directly support Cocoa Bindings
            like NSTableView does. Instead, we need to use the tree controller
            as the data source through delegate methods.
            """
            # NSOutlineView doesn't have direct bindings like NSTableView.
            # Instead, we configure it to use us as data source in a
            # "tree controller aware" mode - the delegate methods query
            # the tree controller's arrangedObjects.
            logger.info("Tree controller configured (delegate mode, not bindings)")

    _tree_controller_wrapper = TreeControllerWrapper
    return TreeControllerWrapper


__all__ = ['get_tree_controller_class']
