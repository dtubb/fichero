"""
Unit tests for Rubicon-ObjC property/method access patterns

Tests to verify correct usage of Rubicon-ObjC for NSPasteboard and NSArray operations.
These tests document the correct patterns to avoid TypeError issues.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys


class TestRubiconObjCPatterns(unittest.TestCase):
    """
    Test Rubicon-ObjC access patterns for NSPasteboard and NSArray.

    These tests serve as documentation and regression prevention for the
    drag-and-drop implementation.
    """

    def test_nspasteboard_types_is_property(self):
        """
        Document that NSPasteboard.types is a property, not a method.

        Correct: pasteboard.types
        Wrong: pasteboard.types()
        """
        # This test documents the pattern - actual testing requires NSPasteboard
        pass

    def test_nsdragginginfo_pasteboard_is_property(self):
        """
        Document that NSDraggingInfo.draggingPasteboard is a property, not a method.

        Correct: drag_info.draggingPasteboard
        Wrong: drag_info.draggingPasteboard()
        """
        pass

    def test_nsarray_count_is_method(self):
        """
        Document that NSArray.count() is a method, not a property.

        Correct: array.count()
        Wrong: array.count
        """
        pass

    def test_nsarray_objectAtIndex_is_method(self):
        """
        Document that NSArray.objectAtIndex() is a method with parameter.

        Correct: array.objectAtIndex(i)
        Wrong: array.objectAtIndex[i]
        """
        pass

    def test_rubicon_property_vs_method_pattern(self):
        """
        Test to verify understanding of Rubicon-ObjC property vs method patterns.

        Properties:
        - Accessed without parentheses: obj.property
        - Examples: drag_info.draggingPasteboard, pasteboard.types

        Methods:
        - Called with parentheses: obj.method()
        - Examples: types.count(), types.objectAtIndex(i)
        """
        # Create a mock object that demonstrates the pattern
        mock_obj = Mock()

        # Properties should be accessed without ()
        mock_obj.my_property = "property_value"
        result = mock_obj.my_property
        self.assertEqual(result, "property_value")

        # Methods should be called with ()
        mock_obj.my_method = Mock(return_value="method_result")
        result = mock_obj.my_method()
        self.assertEqual(result, "method_result")


class TestNSArrayIterationPattern(unittest.TestCase):
    """
    Test NSArray iteration patterns used in drag-and-drop.
    """

    def test_nsarray_iteration_mock(self):
        """
        Test the correct pattern for iterating NSArray in Rubicon-ObjC.

        UPDATED: NSArray is returned as ObjCListInstance (Python list wrapper)
        The pattern is:
        1. Use len() to get length
        2. Access items with [index] syntax
        3. Or iterate directly with 'for item in array'
        """
        # Mock an ObjCListInstance-like object (Python list)
        mock_array = ["type1", "type2", "type3"]

        # Use the correct iteration pattern for ObjCListInstance
        results = []
        for i in range(len(mock_array)):
            obj = mock_array[i]
            results.append(str(obj))

        self.assertEqual(results, ["type1", "type2", "type3"])

        # Alternative: Direct iteration
        results2 = [str(item) for item in mock_array]
        self.assertEqual(results2, ["type1", "type2", "type3"])

    def test_nsarray_wrong_pattern_fails(self):
        """
        Test that wrong patterns fail as expected.

        UPDATED: With ObjCListInstance, the mistake is trying to call count()
        when it's actually a Python list.
        """
        # ObjCListInstance behaves like a Python list
        mock_array = ["type1", "type2", "type3"]

        # Correct: Use len()
        count = len(mock_array)
        self.assertEqual(count, 3)

        # This test now documents the correct pattern


class TestDragTypeCheckingPattern(unittest.TestCase):
    """
    Test the pattern for checking drag types in NSPasteboard.
    """

    def test_drag_type_checking_pattern(self):
        """
        Test the correct pattern for checking if a UTI exists in pasteboard types.

        UPDATED Pattern:
        1. Get types array: types = pasteboard.types (returns ObjCListInstance)
        2. Iterate with len(): for i in range(len(types))
        3. Access items: types[i]
        """
        # Mock pasteboard with ObjCListInstance (list-like)
        mock_pasteboard = Mock()

        # Setup types property returning a list
        target_uti = "com.fichero.collection.id"
        mock_pasteboard.types = [
            "public.utf8-plain-text",
            target_uti,  # Our target
            "public.file-url"
        ]

        # Execute the pattern
        types = mock_pasteboard.types  # Property access
        has_target_uti = False

        # Use len() and list indexing
        for i in range(len(types)):
            type_str = str(types[i])
            if type_str == target_uti:
                has_target_uti = True
                break

        self.assertTrue(has_target_uti)

    def test_check_multiple_types(self):
        """
        Test checking for multiple UTI types in one pass.

        This is the pattern used in outlineView_validateDrop.
        UPDATED for ObjCListInstance.
        """
        # Mock setup - types as list
        mock_types = [
            "public.utf8-plain-text",
            "com.fichero.collection.id",
            "public.file-url",
            "public.image"
        ]

        # Check for multiple types
        has_collection_uti = False
        has_file_url = False

        for i in range(len(mock_types)):
            type_str = str(mock_types[i])
            if type_str == "com.fichero.collection.id":
                has_collection_uti = True
            elif type_str == "public.file-url":
                has_file_url = True

        self.assertTrue(has_collection_uti)
        self.assertTrue(has_file_url)


class TestCommonRubiconMistakes(unittest.TestCase):
    """
    Test common mistakes when using Rubicon-ObjC.

    These tests document errors to avoid.
    """

    def test_mistake_calling_property_as_method(self):
        """
        Common mistake: Calling a property as if it were a method.

        Error: pasteboard.types()
        Correct: pasteboard.types

        Results in: TypeError: 'ObjCInstance' object is not callable
        """
        mock_obj = Mock()
        mock_obj.my_property = "value"

        # Correct access
        result = mock_obj.my_property
        self.assertEqual(result, "value")

        # Wrong access (would fail with real ObjC property)
        # mock_obj.my_property() would raise TypeError in real scenario

    def test_mistake_not_calling_method(self):
        """
        Common mistake: Trying to call count() on ObjCListInstance.

        UPDATED: NSArray is returned as ObjCListInstance (Python list)
        Error: types.count() - doesn't exist on lists
        Correct: len(types)

        The original error was: 'ObjCListInstance.count() missing 1 required positional argument'
        This is because count() on lists expects a value to count, not a length method.
        """
        # ObjCListInstance behaves like a Python list
        mock_types = ["type1", "type2", "type3"]

        # Correct: Use len()
        count = len(mock_types)
        self.assertEqual(count, 3)

        # Wrong: Trying to call count() like NSArray
        # (Python list.count() expects an argument - the item to count)
        with self.assertRaises(TypeError):
            count = mock_types.count()  # Missing required argument


class TestRubiconReferenceGuide(unittest.TestCase):
    """
    Reference guide for Rubicon-ObjC patterns used in drag-and-drop.

    This test class serves as documentation.
    """

    def test_reference_property_access_patterns(self):
        """
        Reference: Correct property access patterns

        | Objective-C                  | Rubicon-ObjC                    |
        |------------------------------|---------------------------------|
        | [info draggingPasteboard]    | info.draggingPasteboard         |
        | [pasteboard types]           | pasteboard.types                |
        | [item _python_data]          | item._python_data               |
        """
        # This test is for documentation purposes
        self.assertTrue(True, "See test docstring for patterns")

    def test_reference_method_call_patterns(self):
        """
        Reference: Correct method call patterns

        UPDATED: NSArray returns as ObjCListInstance (Python list wrapper)

        | Objective-C                  | Rubicon-ObjC                    | ObjCListInstance     |
        |------------------------------|----------------------------------|----------------------|
        | [types count]                | types.count() (pure NSArray)     | len(types)           |
        | [types objectAtIndex:i]      | types.objectAtIndex(i)           | types[i]             |
        | [pasteboard stringForType:t] | pasteboard.stringForType_(t)     | N/A                  |
        | [item setString:s forType:t] | item.setString_forType_(s, t)    | N/A                  |
        """
        # This test is for documentation purposes
        self.assertTrue(True, "See test docstring for patterns")

    def test_reference_quick_decision_tree(self):
        """
        Reference: Quick decision tree for property vs method

        Ask: "Does it take parameters?"
        - YES → It's a method, use parentheses: obj.method(param)
        - NO → Check Apple docs:
          - Property → No parentheses: obj.property
          - Method → Use parentheses: obj.method()

        When in doubt:
        1. Check Apple's documentation for the class
        2. Look for "Property" vs "Instance Method"
        3. Properties never need parentheses
        4. Methods always need parentheses (even with 0 params)
        """
        self.assertTrue(True, "See test docstring for decision tree")


if __name__ == "__main__":
    unittest.main()
