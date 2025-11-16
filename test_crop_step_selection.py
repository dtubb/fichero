"""
Integration test for crop step selection fix.

Tests that StepBrowser correctly extracts data from ListWidget Row objects.
"""

import sys
sys.path.insert(0, 'src')

from fichero.windows.main.views.preview.step_browser import StepBrowser


class MockRow:
    """Mock Row object as returned by ListWidget"""
    def __init__(self, item_id, collection_data):
        self._item_id = item_id
        self._collection_data = collection_data


def test_step_browser_row_extraction():
    """Test that StepBrowser correctly extracts data from Row objects"""

    # Track callback invocations
    callback_invoked = []

    def mock_callback(index):
        callback_invoked.append(index)

    # Create StepBrowser with callback
    browser = StepBrowser(on_step_selected=mock_callback)

    # Simulate ListWidget calling _on_step_selected with a Row object
    mock_row = MockRow(
        item_id=1,
        collection_data={'_item_id': 1, 'step_name': 'crop', 'tool_name': 'crop'}
    )

    # This should extract _collection_data from the Row and call the callback
    browser._on_step_selected(mock_row)

    # Verify callback was invoked with correct index
    assert len(callback_invoked) == 1, "Callback should be invoked once"
    assert callback_invoked[0] == 1, f"Callback should receive index 1, got {callback_invoked[0]}"

    print("✅ Test passed: StepBrowser correctly extracts data from Row objects")
    print(f"   - Row._item_id extracted: {mock_row._item_id}")
    print(f"   - Callback invoked with index: {callback_invoked[0]}")


def test_step_browser_dict_extraction():
    """Test that StepBrowser still works with dict format (backward compatibility)"""

    callback_invoked = []

    def mock_callback(index):
        callback_invoked.append(index)

    browser = StepBrowser(on_step_selected=mock_callback)

    # Simulate custom renderer passing dict directly
    mock_dict = {'_item_id': 2, 'step_name': 'transcribe'}

    browser._on_step_selected(mock_dict)

    assert len(callback_invoked) == 1, "Callback should be invoked once"
    assert callback_invoked[0] == 2, f"Callback should receive index 2, got {callback_invoked[0]}"

    print("✅ Test passed: StepBrowser still works with dict format")
    print(f"   - Dict extracted correctly")
    print(f"   - Callback invoked with index: {callback_invoked[0]}")


def test_step_browser_no_data():
    """Test that StepBrowser handles missing data gracefully"""

    callback_invoked = []

    def mock_callback(index):
        callback_invoked.append(index)

    browser = StepBrowser(on_step_selected=mock_callback)

    # Simulate selection with no data (deselection)
    class EmptyRow:
        pass

    browser._on_step_selected(EmptyRow())

    assert len(callback_invoked) == 0, "Callback should not be invoked for empty data"

    print("✅ Test passed: StepBrowser handles missing data gracefully")
    print("   - No callback invoked (deselection)")


if __name__ == '__main__':
    print("=" * 60)
    print("Testing StepBrowser Row extraction fix")
    print("=" * 60)
    print()

    test_step_browser_row_extraction()
    print()
    test_step_browser_dict_extraction()
    print()
    test_step_browser_no_data()
    print()

    print("=" * 60)
    print("All tests passed! ✅")
    print("=" * 60)
    print()
    print("The fix is ready for GUI testing with:")
    print("  briefcase dev")
