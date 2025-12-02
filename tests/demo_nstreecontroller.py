#!/usr/bin/env python3
"""
Minimal NSTreeController + NSOutlineView Demo using Toga

Tests if NSTreeController.moveNodes:toIndexPath: works with Rubicon-ObjC.

Run: PYTHONPATH=src python tests/demo_nstreecontroller.py
"""

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

# Global storage
_node_storage = {}
_delegate_storage = {
    'treeController': None,
    'outlineView': None,
    'dragNodesArray': None,
}

DRAG_TYPE = "com.demo.node"


def _get_ptr(obj):
    return int(obj.ptr.value) if hasattr(obj, 'ptr') else id(obj)


def setup_objc_classes():
    """Import ObjC classes after Toga has loaded AppKit."""
    from rubicon.objc import ObjCClass, ObjCInstance, objc_method, send_super
    from rubicon.objc.types import NSRect, NSPoint, NSSize

    NSObject = ObjCClass("NSObject")
    NSScrollView = ObjCClass("NSScrollView")
    NSOutlineView = ObjCClass("NSOutlineView")
    NSTableColumn = ObjCClass("NSTableColumn")
    NSTreeController = ObjCClass("NSTreeController")
    NSMutableArray = ObjCClass("NSMutableArray")
    NSIndexPath = ObjCClass("NSIndexPath")
    NSTableCellView = ObjCClass("NSTableCellView")
    NSTextField = ObjCClass("NSTextField")
    NSArray = ObjCClass("NSArray")

    # SimpleNode class
    class SimpleNode(NSObject):
        @objc_method
        def init(self) -> ObjCInstance:
            self = ObjCInstance(send_super(__class__, self, 'init'))
            if self is None:
                return None
            ptr = _get_ptr(self)
            _node_storage[ptr] = {
                'nodeTitle': "Untitled",
                'children': NSMutableArray.alloc().init(),
                'isLeaf': False,
            }
            return self

        @objc_method
        def nodeTitle(self):
            return _node_storage.get(_get_ptr(self), {}).get('nodeTitle', "")

        @objc_method
        def setNodeTitle_(self, value) -> None:
            ptr = _get_ptr(self)
            if ptr in _node_storage:
                _node_storage[ptr]['nodeTitle'] = str(value) if value else ""

        @objc_method
        def children(self):
            return _node_storage.get(_get_ptr(self), {}).get('children')

        @objc_method
        def setChildren_(self, value) -> None:
            ptr = _get_ptr(self)
            if ptr not in _node_storage:
                return
            storage = _node_storage[ptr]
            existing = storage['children']
            if existing is None:
                existing = NSMutableArray.alloc().init()
                storage['children'] = existing
            existing.removeAllObjects()
            if value:
                for i in range(len(value)):
                    try:
                        existing.addObject_(value.objectAtIndex_(i))
                    except:
                        pass

        @objc_method
        def isLeaf(self):
            return _node_storage.get(_get_ptr(self), {}).get('isLeaf', False)

        @objc_method
        def setIsLeaf_(self, value) -> None:
            ptr = _get_ptr(self)
            if ptr in _node_storage:
                _node_storage[ptr]['isLeaf'] = bool(value)

        @objc_method
        def countOfChildren(self):
            children = self.children
            return len(children) if children else 0

        @objc_method
        def objectInChildrenAtIndex_(self, index):
            children = self.children
            if children and 0 <= index < len(children):
                return children.objectAtIndex_(index)
            return None

        @objc_method
        def insertObject_inChildrenAtIndex_(self, obj, index) -> None:
            children = self.children
            if children:
                children.insertObject_atIndex_(obj, int(index))

        @objc_method
        def removeObjectFromChildrenAtIndex_(self, index) -> None:
            children = self.children
            if children and 0 <= index < len(children):
                children.removeObjectAtIndex_(int(index))

    # OutlineDelegate class
    class OutlineDelegate(NSObject):
        @objc_method
        def init(self) -> ObjCInstance:
            return ObjCInstance(send_super(__class__, self, 'init'))

        @objc_method
        def outlineView_numberOfChildrenOfItem_(self, outlineView, item) -> int:
            if item is None:
                tc = _delegate_storage['treeController']
                if tc:
                    arranged = tc.arrangedObjects
                    if arranged:
                        children = arranged.childNodes
                        count = len(children) if children else 0
                        logger.info(f"numberOfChildren(root): {count}")
                        return count
                return 0
            children = item.childNodes
            count = len(children) if children else 0
            logger.info(f"numberOfChildren(item): {count}")
            return count

        @objc_method
        def outlineView_isItemExpandable_(self, outlineView, item):
            logger.info(f"isItemExpandable: item={item}")
            try:
                if item is None:
                    logger.info("  returning True (root)")
                    return True
                children = item.childNodes
                result = len(children) > 0 if children else False
                logger.info(f"  result={result}")
                return result
            except Exception as e:
                logger.error(f"isItemExpandable ERROR: {e}")
                return False

        @objc_method
        def outlineView_child_ofItem_(self, outlineView, index, item):
            idx = int(index) if index is not None else 0
            logger.info(f"child_ofItem: index={idx}, item={item}")
            if item is None:
                tc = _delegate_storage['treeController']
                if tc:
                    arranged = tc.arrangedObjects
                    logger.info(f"  arranged={arranged}")
                    if arranged:
                        children = arranged.childNodes
                        logger.info(f"  children={children}, count={len(children) if children else 0}")
                        if children and 0 <= idx < len(children):
                            child = children.objectAtIndex_(idx)
                            logger.info(f"  returning child: {child}")
                            return child
                return None
            children = item.childNodes
            if children and 0 <= idx < len(children):
                return children.objectAtIndex_(idx)
            return None

        @objc_method
        def outlineView_objectValueForTableColumn_byItem_(self, outlineView, column, item):
            logger.info(f"objectValueForTableColumn: item={item}")
            try:
                if item is None:
                    return "?"
                node = item.representedObject
                logger.info(f"  node={node}")
                title = node.nodeTitle if node else "?"
                logger.info(f"  returning title={title}")
                return str(title)
            except Exception as e:
                logger.error(f"objectValueForTableColumn ERROR: {e}")
                return "ERROR"

        # NOTE: Using objectValueForTableColumn instead of viewForTableColumn
        # because viewForTableColumn crashes with Rubicon-ObjC

        @objc_method
        def outlineView_writeItems_toPasteboard_(self, outlineView, items, pboard) -> bool:
            logger.info(f"DRAG START: {len(items)} items")
            _delegate_storage['dragNodesArray'] = items
            pboard.declareTypes_owner_([DRAG_TYPE], self)
            pboard.setString_forType_("drag", DRAG_TYPE)
            return True

        @objc_method
        def outlineView_validateDrop_proposedItem_proposedChildIndex_(
            self, outlineView, info, item, index
        ) -> int:
            if index == -1:
                return 0
            return 16

        @objc_method
        def outlineView_acceptDrop_item_childIndex_(
            self, outlineView, info, targetItem, index
        ) -> bool:
            logger.info(f"DROP: targetItem={targetItem}, index={index}")

            tc = _delegate_storage['treeController']
            dragNodes = _delegate_storage['dragNodesArray']

            if not tc or not dragNodes:
                logger.error("Missing treeController or dragNodesArray")
                return False

            if targetItem is not None:
                indexPath = targetItem.indexPath.indexPathByAddingIndex_(index)
            else:
                indexPath = NSIndexPath.indexPathWithIndex_(index)

            logger.info(f"Calling moveNodes_toIndexPath_...")

            try:
                nodes_array = NSArray.arrayWithArray_(dragNodes)
                tc.moveNodes_toIndexPath_(nodes_array, indexPath)
                logger.info("SUCCESS! moveNodes_toIndexPath_ completed!")
                outlineView.reloadData()
                outlineView.expandItem_expandChildren_(None, True)
                return True
            except Exception as e:
                logger.error(f"EXCEPTION: {e}")
                import traceback
                traceback.print_exc()
                return False

    return {
        'SimpleNode': SimpleNode,
        'OutlineDelegate': OutlineDelegate,
        'NSScrollView': NSScrollView,
        'NSOutlineView': NSOutlineView,
        'NSTableColumn': NSTableColumn,
        'NSTreeController': NSTreeController,
        'NSMutableArray': NSMutableArray,
        'NSRect': NSRect,
        'NSPoint': NSPoint,
        'NSSize': NSSize,
    }


class TreeControllerDemo(toga.App):
    def startup(self):
        logger.info("=" * 60)
        logger.info("NSTreeController moveNodes:toIndexPath: Test")
        logger.info("=" * 60)
        logger.info("Drag items to test!")

        # Setup ObjC classes (now that AppKit is loaded)
        self.objc = setup_objc_classes()

        # Create main box
        main_box = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Create native outline view
        self.setup_outline_view()

        self.main_window = toga.MainWindow(title="NSTreeController Demo - Drag to Test!")
        self.main_window.content = main_box
        self.main_window.show()

        # Add native scroll view to window
        content_view = self.main_window._impl.native.contentView
        self.scroll_view.frame = content_view.bounds
        self.scroll_view.setAutoresizingMask_(18)
        content_view.addSubview_(self.scroll_view)

        logger.info("")
        logger.info("Window ready! Drag items between folders.")
        logger.info("Watch console for SUCCESS or CRASH messages.")
        logger.info("")

    def setup_outline_view(self):
        objc = self.objc

        # Tree controller
        tc = objc['NSTreeController'].alloc().init()
        tc.setChildrenKeyPath_("children")
        tc.setLeafKeyPath_("isLeaf")
        tc.setPreservesSelection_(False)
        tc.setAvoidsEmptySelection_(False)
        _delegate_storage['treeController'] = tc

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
        self._delegate = delegate

        # Drag types
        ov.registerForDraggedTypes_([DRAG_TYPE])

        # Scroll view
        sv = objc['NSScrollView'].alloc().initWithFrame_(
            objc['NSRect'](objc['NSPoint'](0, 0), objc['NSSize'](400, 300))
        )
        sv.setDocumentView_(ov)
        sv.setHasVerticalScroller_(True)
        sv.setHasHorizontalScroller_(True)
        self.scroll_view = sv

        # Create tree
        def create_node(title, is_leaf=False):
            node = objc['SimpleNode'].alloc().init()
            node.setNodeTitle_(title)
            node.setIsLeaf_(is_leaf)
            return node

        folder_a = create_node("Folder A", is_leaf=False)
        folder_b = create_node("Folder B", is_leaf=False)
        item_1 = create_node("Item 1", is_leaf=True)
        item_2 = create_node("Item 2", is_leaf=True)
        item_3 = create_node("Item 3", is_leaf=True)

        folder_a.children.addObject_(item_1)
        folder_a.children.addObject_(item_2)
        folder_b.children.addObject_(item_3)

        content = objc['NSMutableArray'].alloc().init()
        content.addObject_(folder_a)
        content.addObject_(folder_b)

        logger.info(f"Setting content: 2 root nodes")
        tc.setContent_(content)

        ov.reloadData()
        ov.expandItem_expandChildren_(None, True)


def main():
    return TreeControllerDemo("NSTreeController Demo", "com.demo.treecontroller")


if __name__ == "__main__":
    main().main_loop()
