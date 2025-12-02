#!/usr/bin/env python3
"""
NSOutlineView Demo with Drag-Drop (Toga pattern, NO NSTreeController)

This demo follows Toga's tree.py pattern:
- Custom NodeData class wraps Python nodes
- Direct dataSource methods return NodeData wrappers
- No NSTreeController (manages tree manually)
- Uses pasteboardWriterForItem (modern API) for drag-drop

Run: PYTHONPATH=src python tests/demo_toga_pattern.py
"""

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

# Global storage for node implementations
_node_impls = {}  # Maps ObjC ptr to {'node': PythonNode}

DRAG_TYPE = "com.demo.node"
FILE_URL_TYPE = "public.file-url"


class TreeNode:
    """Simple Python tree node."""
    def __init__(self, title, children=None, is_leaf=False):
        self.title = title
        self.children = children or []
        self.is_leaf = is_leaf
        self._impl = None  # Will hold ObjC wrapper
        self.parent = None  # Track parent for move operations

        # Set parent on children
        for child in self.children:
            child.parent = self


# Global storage for delegate data
_delegate_storage = {
    'data': None,
    'outlineView': None,
}


def setup_objc_classes():
    """Import ObjC classes after Toga has loaded AppKit."""
    from rubicon.objc import ObjCClass, ObjCInstance, objc_method, send_super
    from rubicon.objc.types import NSRect, NSPoint, NSSize

    NSObject = ObjCClass("NSObject")
    NSScrollView = ObjCClass("NSScrollView")
    NSOutlineView = ObjCClass("NSOutlineView")
    NSTableColumn = ObjCClass("NSTableColumn")
    NSTableCellView = ObjCClass("NSTableCellView")
    NSTextField = ObjCClass("NSTextField")
    NSPasteboardItem = ObjCClass("NSPasteboardItem")
    NSMenu = ObjCClass("NSMenu")
    NSMenuItem = ObjCClass("NSMenuItem")

    # NodeData class - wraps Python objects for ObjC (like Toga's TogaData)
    class NodeData(NSObject):
        """Wrapper class that stores a reference to a Python object."""

        @objc_method
        def init(self) -> ObjCInstance:
            self = ObjCInstance(send_super(__class__, self, 'init'))
            if self is None:
                return None
            ptr = int(self.ptr.value)
            _node_impls[ptr] = {'node': None}
            return self

        @objc_method
        def dealloc(self) -> None:
            ptr = int(self.ptr.value)
            if ptr in _node_impls:
                del _node_impls[ptr]

    def get_node(node_data):
        """Get Python node from NodeData wrapper."""
        if node_data is None:
            return None
        ptr = int(node_data.ptr.value)
        return _node_impls.get(ptr, {}).get('node')

    def set_node(node_data, node):
        """Set Python node on NodeData wrapper."""
        ptr = int(node_data.ptr.value)
        if ptr in _node_impls:
            _node_impls[ptr]['node'] = node

    def node_impl(node):
        """Get or create NodeData wrapper for a Python node."""
        if node._impl is None:
            impl = NodeData.alloc().init()
            set_node(impl, node)
            node._impl = impl
        return node._impl

    # OutlineDelegate class - following Toga's pattern
    class OutlineDelegate(NSObject):
        @objc_method
        def init(self) -> ObjCInstance:
            self = ObjCInstance(send_super(__class__, self, 'init'))
            return self

        # =================================================================
        # DATA SOURCE METHODS
        # =================================================================

        @objc_method
        def outlineView_numberOfChildrenOfItem_(self, outlineView, item) -> int:
            if item is None:
                data = _delegate_storage.get('data', [])
                count = len(data)
                logger.info(f"numberOfChildren(root): {count}")
                return count
            node = get_node(item)
            if node is None:
                return 0
            count = len(node.children)
            logger.info(f"numberOfChildren({node.title}): {count}")
            return count

        @objc_method
        def outlineView_isItemExpandable_(self, outlineView, item) -> bool:
            if item is None:
                return True
            node = get_node(item)
            if node is None:
                return False
            result = not node.is_leaf and len(node.children) > 0
            logger.info(f"isItemExpandable({node.title}): {result}")
            return result

        @objc_method
        def outlineView_child_ofItem_(self, outlineView, index: int, item):
            idx = int(index)
            if item is None:
                data = _delegate_storage.get('data', [])
                if 0 <= idx < len(data):
                    child = data[idx]
                    impl = node_impl(child)
                    logger.info(f"child(root, {idx}): {child.title}")
                    return impl
                return None
            node = get_node(item)
            if node is None or idx >= len(node.children):
                return None
            child = node.children[idx]
            impl = node_impl(child)
            logger.info(f"child({node.title}, {idx}): {child.title}")
            return impl

        @objc_method
        def outlineView_viewForTableColumn_item_(self, outlineView, tableColumn, item):
            node = get_node(item)
            title = node.title if node else "?"
            logger.info(f"viewForTableColumn: {title}")

            cell = NSTableCellView.alloc().init()
            text_field = NSTextField.labelWithString_(str(title))
            text_field.frame = NSRect(NSPoint(0, 0), NSSize(350, 17))
            cell.addSubview_(text_field)
            cell.textField = text_field
            return cell

        # =================================================================
        # DRAG-DROP METHODS (modern API like existing sidebar)
        # =================================================================

        @objc_method
        def outlineView_pasteboardWriterForItem_(self, outlineView, item):
            """Start drag - provide pasteboard writer (modern API)."""
            node = get_node(item)
            if node is None:
                return None

            logger.info(f"DRAG START: {node.title}")

            # Create pasteboard item with node title as ID
            pb_item = NSPasteboardItem.alloc().init()
            pb_item.setString_forType_(node.title, DRAG_TYPE)
            return pb_item

        @objc_method
        def outlineView_validateDrop_proposedItem_proposedChildIndex_(
            self, outlineView, drag_info, item, index: int
        ) -> int:
            """Validate drop location."""
            target_node = get_node(item) if item else None
            target_name = target_node.title if target_node else "root"
            idx = int(index)

            # Check what types are being dragged
            pasteboard = drag_info.draggingPasteboard
            types = pasteboard.types

            has_internal = False
            has_file_url = False
            for i in range(len(types)):
                type_str = str(types.objectAtIndex_(i))
                if type_str == DRAG_TYPE:
                    has_internal = True
                elif type_str == FILE_URL_TYPE:
                    has_file_url = True

            logger.info(f"validateDrop: target={target_name}, index={idx}, internal={has_internal}, file_url={has_file_url}")

            # Accept file URL drops (from Finder)
            if has_file_url:
                # Accept drops into folders or at root level
                if idx == -1:
                    # Dropping ON an item - only folders
                    if target_node and target_node.is_leaf:
                        return 0  # NSDragOperationNone
                    return 1  # NSDragOperationCopy
                return 1  # NSDragOperationCopy (between items)

            # Internal drag-drop
            if has_internal:
                # Get source node from pasteboard
                source_title = str(pasteboard.stringForType_(DRAG_TYPE) or "")
                source_node = find_node_by_title(source_title) if source_title else None

                # Prevent dropping on self or descendants
                if source_node and target_node:
                    if source_node == target_node:
                        logger.info(f"  REJECT: Can't drop on self")
                        return 0  # NSDragOperationNone
                    if is_descendant_of(target_node, source_node):
                        logger.info(f"  REJECT: Can't drop on descendant")
                        return 0  # NSDragOperationNone

                # index=-1 means dropping ON the item
                # index>=0 means dropping BETWEEN children at that index
                if idx == -1:
                    # Accept drops ON any item (leaf will be converted to folder)
                    return 1  # NSDragOperationGeneric
                else:
                    # Accept drops BETWEEN items
                    return 1  # NSDragOperationGeneric

            return 0  # NSDragOperationNone

        @objc_method
        def outlineView_acceptDrop_item_childIndex_(
            self, outlineView, drag_info, targetItem, index: int
        ) -> bool:
            """Accept and handle drop."""
            target_node = get_node(targetItem) if targetItem else None
            target_name = target_node.title if target_node else "root"
            idx = int(index)

            logger.info(f"DROP: target={target_name}, index={idx}")

            pasteboard = drag_info.draggingPasteboard
            types = pasteboard.types

            # Check for file URL drops (from Finder)
            has_file_url = False
            for i in range(len(types)):
                if str(types.objectAtIndex_(i)) == FILE_URL_TYPE:
                    has_file_url = True
                    break

            if has_file_url:
                # Handle file drop from Finder
                return handle_file_drop(outlineView, pasteboard, target_node, idx)

            # Handle internal drag-drop
            source_title = str(pasteboard.stringForType_(DRAG_TYPE) or "")

            if not source_title:
                logger.error("No source title in pasteboard")
                return False

            logger.info(f"Moving '{source_title}' to '{target_name}' at index {idx}")

            # Find source node in tree
            source_node = find_node_by_title(source_title)
            if source_node is None:
                logger.error(f"Source node '{source_title}' not found")
                return False

            # Remove from old parent
            old_parent = source_node.parent
            if old_parent:
                old_parent.children.remove(source_node)
            else:
                # Was at root level
                _delegate_storage['data'].remove(source_node)

            # Insert at new location
            if idx == -1:
                # Dropping ON target - add to end of target's children
                if target_node:
                    # Convert leaf to folder if needed
                    if target_node.is_leaf:
                        target_node.is_leaf = False
                        logger.info(f"Converted '{target_node.title}' from leaf to folder")
                    target_node.children.append(source_node)
                    source_node.parent = target_node
                else:
                    # Dropping on root
                    _delegate_storage['data'].append(source_node)
                    source_node.parent = None
            else:
                # Dropping BETWEEN - insert at index
                if target_node:
                    target_node.children.insert(idx, source_node)
                    source_node.parent = target_node
                else:
                    # Root level
                    _delegate_storage['data'].insert(idx, source_node)
                    source_node.parent = None

            # Reload to show changes
            outlineView.reloadData()
            outlineView.expandItem_expandChildren_(None, True)

            logger.info(f"Move completed!")
            return True

        # =================================================================
        # CONTEXTUAL MENU
        # =================================================================

        @objc_method
        def outlineView_menuForEvent_(self, outlineView, event):
            """Provide contextual menu for right-click."""
            # Get click location and find clicked row
            point = outlineView.convertPoint_fromView_(event.locationInWindow, None)
            row = outlineView.rowAtPoint_(point)

            if row < 0:
                # Clicked on empty area - show "New Folder" option
                menu = NSMenu.alloc().init()
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "New Folder", "menuNewFolder:", ""
                )
                item.setTarget_(self)
                menu.addItem_(item)
                return menu

            # Select the clicked row
            outlineView.selectRowIndexes_byExtendingSelection_(
                ObjCClass("NSIndexSet").indexSetWithIndex_(row), False
            )

            # Get the node
            item = outlineView.itemAtRow_(row)
            node = get_node(item)
            if node is None:
                return None

            logger.info(f"Context menu for: {node.title}")

            # Create menu
            menu = NSMenu.alloc().init()

            # Rename
            rename_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Rename", "menuRename:", ""
            )
            rename_item.setTarget_(self)
            menu.addItem_(rename_item)

            # Delete
            delete_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Delete", "menuDelete:", ""
            )
            delete_item.setTarget_(self)
            menu.addItem_(delete_item)

            menu.addItem_(NSMenuItem.separatorItem())

            # Convert to folder (only for leaf items)
            if node.is_leaf:
                folder_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Convert to Folder", "menuConvertToFolder:", ""
                )
                folder_item.setTarget_(self)
                menu.addItem_(folder_item)

            # New Folder (add subfolder)
            if not node.is_leaf:
                new_folder_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "New Subfolder", "menuNewSubfolder:", ""
                )
                new_folder_item.setTarget_(self)
                menu.addItem_(new_folder_item)

            return menu

        @objc_method
        def menuRename_(self, sender) -> None:
            """Handle Rename menu action."""
            ov = _delegate_storage['outlineView']
            row = ov.selectedRow
            if row < 0:
                return
            item = ov.itemAtRow_(row)
            node = get_node(item)
            if node:
                # In real app, show input dialog. For demo, just rename.
                node.title = node.title + " (renamed)"
                logger.info(f"Renamed to: {node.title}")
                ov.reloadData()
                ov.expandItem_expandChildren_(None, True)

        @objc_method
        def menuDelete_(self, sender) -> None:
            """Handle Delete menu action."""
            ov = _delegate_storage['outlineView']
            row = ov.selectedRow
            if row < 0:
                return
            item = ov.itemAtRow_(row)
            node = get_node(item)
            if node:
                logger.info(f"Deleting: {node.title}")
                # Remove from parent
                if node.parent:
                    node.parent.children.remove(node)
                else:
                    _delegate_storage['data'].remove(node)
                ov.reloadData()
                ov.expandItem_expandChildren_(None, True)

        @objc_method
        def menuConvertToFolder_(self, sender) -> None:
            """Handle Convert to Folder menu action."""
            ov = _delegate_storage['outlineView']
            row = ov.selectedRow
            if row < 0:
                return
            item = ov.itemAtRow_(row)
            node = get_node(item)
            if node and node.is_leaf:
                node.is_leaf = False
                logger.info(f"Converted '{node.title}' to folder")
                ov.reloadData()
                ov.expandItem_expandChildren_(None, True)

        @objc_method
        def menuNewFolder_(self, sender) -> None:
            """Handle New Folder menu action (at root)."""
            new_node = TreeNode("New Folder", is_leaf=False)
            _delegate_storage['data'].append(new_node)
            logger.info("Created new folder at root")
            ov = _delegate_storage['outlineView']
            ov.reloadData()
            ov.expandItem_expandChildren_(None, True)

        @objc_method
        def menuNewSubfolder_(self, sender) -> None:
            """Handle New Subfolder menu action."""
            ov = _delegate_storage['outlineView']
            row = ov.selectedRow
            if row < 0:
                return
            item = ov.itemAtRow_(row)
            node = get_node(item)
            if node and not node.is_leaf:
                new_node = TreeNode("New Subfolder", is_leaf=False)
                new_node.parent = node
                node.children.append(new_node)
                logger.info(f"Created new subfolder in '{node.title}'")
                ov.reloadData()
                ov.expandItem_expandChildren_(None, True)

    def handle_file_drop(outlineView, pasteboard, target_node, idx):
        """Handle file drop from Finder."""
        NSURL = ObjCClass("NSURL")

        # Read file URLs from pasteboard
        urls = pasteboard.readObjectsForClasses_options_(
            [NSURL], None
        )

        if not urls or len(urls) == 0:
            logger.error("No URLs in pasteboard")
            return False

        logger.info(f"FILE DROP: {len(urls)} files")

        # Create new nodes for each dropped file
        for i in range(len(urls)):
            url = urls.objectAtIndex_(i)
            path = str(url.path)
            filename = path.split("/")[-1] if "/" in path else path

            logger.info(f"  - {filename}")

            # Create new leaf node for the file
            new_node = TreeNode(filename, is_leaf=True)

            # Insert at appropriate location
            if idx == -1:
                # Dropping ON target folder
                if target_node:
                    target_node.children.append(new_node)
                    new_node.parent = target_node
                else:
                    # Dropping on root
                    _delegate_storage['data'].append(new_node)
                    new_node.parent = None
            else:
                # Dropping BETWEEN items
                if target_node:
                    target_node.children.insert(idx, new_node)
                    new_node.parent = target_node
                else:
                    # Root level
                    _delegate_storage['data'].insert(idx, new_node)
                    new_node.parent = None
                idx += 1  # Increment for next file

        # Reload to show changes
        outlineView.reloadData()
        outlineView.expandItem_expandChildren_(None, True)

        logger.info(f"File drop completed!")
        return True

    def find_node_by_title(title):
        """Find a node by title in the tree."""
        def search(nodes):
            for node in nodes:
                if node.title == title:
                    return node
                if node.children:
                    found = search(node.children)
                    if found:
                        return found
            return None
        return search(_delegate_storage.get('data', []))

    def is_descendant_of(node, potential_ancestor):
        """Check if node is a descendant of potential_ancestor."""
        current = node
        while current is not None:
            if current == potential_ancestor:
                return True
            current = current.parent
        return False

    return {
        'OutlineDelegate': OutlineDelegate,
        'NodeData': NodeData,
        'node_impl': node_impl,
        'get_node': get_node,
        'NSScrollView': NSScrollView,
        'NSOutlineView': NSOutlineView,
        'NSTableColumn': NSTableColumn,
        'NSRect': NSRect,
        'NSPoint': NSPoint,
        'NSSize': NSSize,
    }


class TreeDemo(toga.App):
    def startup(self):
        logger.info("=" * 60)
        logger.info("NSOutlineView Demo (Toga pattern, no NSTreeController)")
        logger.info("=" * 60)

        # Setup ObjC classes (now that AppKit is loaded)
        self.objc = setup_objc_classes()

        # Create tree data
        self.create_tree_data()

        # Create main box
        main_box = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Create native outline view
        self.setup_outline_view()

        self.main_window = toga.MainWindow(title="Sidebar Demo - Right-click for Menu!")
        self.main_window.content = main_box
        self.main_window.show()

        # Add native scroll view to window
        content_view = self.main_window._impl.native.contentView
        self.scroll_view.frame = content_view.bounds
        self.scroll_view.setAutoresizingMask_(18)
        content_view.addSubview_(self.scroll_view)

        logger.info("")
        logger.info("Window ready! Features:")
        logger.info("  - Drag items between folders")
        logger.info("  - Drop files from Finder")
        logger.info("  - Drop onto an item to convert it to a folder")
        logger.info("  - Right-click for context menu (Rename, Delete, Convert to Folder)")
        logger.info("")

    def create_tree_data(self):
        """Create sample tree structure."""
        folder_a = TreeNode("Folder A", children=[
            TreeNode("Item 1", is_leaf=True),
            TreeNode("Item 2", is_leaf=True),
        ])
        folder_b = TreeNode("Folder B", children=[
            TreeNode("Item 3", is_leaf=True),
        ])

        _delegate_storage['data'] = [folder_a, folder_b]
        logger.info(f"Created tree with {len(_delegate_storage['data'])} root nodes")

    def setup_outline_view(self):
        objc = self.objc

        # Outline view
        ov = objc['NSOutlineView'].alloc().initWithFrame_(
            objc['NSRect'](objc['NSPoint'](0, 0), objc['NSSize'](380, 260))
        )
        col = objc['NSTableColumn'].alloc().initWithIdentifier_("Title")
        col.setWidth_(350)
        ov.addTableColumn_(col)
        ov.setOutlineTableColumn_(col)

        # Delegate
        delegate = objc['OutlineDelegate'].alloc().init()
        ov.setDelegate_(delegate)
        ov.setDataSource_(delegate)
        _delegate_storage['outlineView'] = ov
        self._delegate = delegate  # Keep reference

        # Register drag types (internal + file URLs from Finder)
        ov.registerForDraggedTypes_([DRAG_TYPE, FILE_URL_TYPE])

        # Scroll view
        sv = objc['NSScrollView'].alloc().initWithFrame_(
            objc['NSRect'](objc['NSPoint'](0, 0), objc['NSSize'](400, 300))
        )
        sv.setDocumentView_(ov)
        sv.setHasVerticalScroller_(True)
        sv.setHasHorizontalScroller_(True)
        self.scroll_view = sv

        # Reload and expand
        ov.reloadData()
        ov.expandItem_expandChildren_(None, True)


def main():
    return TreeDemo("Sidebar Demo", "com.demo.sidebar")


if __name__ == "__main__":
    main().main_loop()
