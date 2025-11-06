"""
Unit tests for MetadataViewer component

Tests for:
- Metadata loading and display
- Nested dictionary handling
- Different data types
- Clear functionality
- Empty state handling
"""

import pytest
from fichero.shared.components import MetadataViewer


class TestMetadataViewer:
    """Test MetadataViewer component"""

    def test_create_metadata_viewer(self):
        """Test creating a MetadataViewer"""
        viewer = MetadataViewer("Test Title")

        assert viewer.title == "Test Title"
        assert viewer._metadata == {}
        assert viewer._container is not None

    def test_create_with_default_title(self):
        """Test creating MetadataViewer with default title"""
        viewer = MetadataViewer()

        assert viewer.title == "Metadata"

    def test_set_simple_metadata(self):
        """Test loading simple key-value metadata"""
        viewer = MetadataViewer()
        metadata = {
            'Step Name': 'prepare_images',
            'File Type': 'image',
            'Status': 'completed'
        }

        viewer.set_metadata(metadata)

        assert viewer._metadata == metadata

    def test_set_nested_metadata(self):
        """Test loading nested metadata"""
        viewer = MetadataViewer()
        metadata = {
            'Step Name': 'prepare_images',
            'Processing Details': {
                'Time': '1.23s',
                'Status': 'completed',
                'Tool Version': '2.1.0'
            }
        }

        viewer.set_metadata(metadata)

        assert viewer._metadata == metadata
        assert 'Processing Details' in viewer._metadata
        assert isinstance(viewer._metadata['Processing Details'], dict)

    def test_set_metadata_with_list(self):
        """Test loading metadata with list values"""
        viewer = MetadataViewer()
        metadata = {
            'Files': ['file1.jpg', 'file2.jpg', 'file3.jpg'],
            'Tags': ['document', 'historical', 'archive']
        }

        viewer.set_metadata(metadata)

        assert 'Files' in viewer._metadata
        assert len(viewer._metadata['Files']) == 3

    def test_set_metadata_with_different_types(self):
        """Test loading metadata with different data types"""
        viewer = MetadataViewer()
        metadata = {
            'String': 'test value',
            'Integer': 42,
            'Float': 3.14,
            'Boolean': True,
            'None': None
        }

        viewer.set_metadata(metadata)

        assert viewer._metadata['String'] == 'test value'
        assert viewer._metadata['Integer'] == 42
        assert viewer._metadata['Float'] == 3.14
        assert viewer._metadata['Boolean'] is True
        assert viewer._metadata['None'] is None

    def test_clear_metadata(self):
        """Test clearing metadata"""
        viewer = MetadataViewer()
        metadata = {'key': 'value'}

        viewer.set_metadata(metadata)
        assert viewer._metadata == metadata

        viewer.clear()
        assert viewer._metadata == {}

    def test_set_empty_metadata(self):
        """Test setting empty metadata"""
        viewer = MetadataViewer()

        viewer.set_metadata({})

        assert viewer._metadata == {}

    def test_set_none_metadata(self):
        """Test setting None as metadata"""
        viewer = MetadataViewer()

        viewer.set_metadata(None)

        assert viewer._metadata == {}

    def test_as_box_returns_container(self):
        """Test that as_box returns a Toga Box"""
        viewer = MetadataViewer()

        box = viewer.as_box()

        assert box is not None
        assert box == viewer._container

    def test_format_value_handles_long_strings(self):
        """Test that long strings are truncated"""
        viewer = MetadataViewer()

        long_string = 'a' * 150
        formatted = viewer._format_value(long_string)

        assert len(formatted) <= 104  # 100 + "..."
        assert formatted.endswith('...')

    def test_format_value_handles_none(self):
        """Test formatting None values"""
        viewer = MetadataViewer()

        formatted = viewer._format_value(None)

        assert formatted == "(None)"

    def test_format_value_handles_booleans(self):
        """Test formatting boolean values"""
        viewer = MetadataViewer()

        assert viewer._format_value(True) == "Yes"
        assert viewer._format_value(False) == "No"

    def test_format_value_handles_numbers(self):
        """Test formatting numbers"""
        viewer = MetadataViewer()

        assert viewer._format_value(42) == "42"
        assert viewer._format_value(3.14) == "3.14"

    def test_deeply_nested_metadata(self):
        """Test loading deeply nested metadata"""
        viewer = MetadataViewer()
        metadata = {
            'Level 1': {
                'Level 2': {
                    'Level 3': {
                        'Value': 'deep value'
                    }
                }
            }
        }

        viewer.set_metadata(metadata)

        assert 'Level 1' in viewer._metadata
        assert 'Level 2' in viewer._metadata['Level 1']
        assert 'Level 3' in viewer._metadata['Level 1']['Level 2']

    def test_mixed_nested_and_flat_metadata(self):
        """Test loading mixed nested and flat metadata"""
        viewer = MetadataViewer()
        metadata = {
            'Simple': 'value',
            'Nested': {
                'Key1': 'value1',
                'Key2': 'value2'
            },
            'Another Simple': 123,
            'List': ['a', 'b', 'c']
        }

        viewer.set_metadata(metadata)

        assert viewer._metadata['Simple'] == 'value'
        assert isinstance(viewer._metadata['Nested'], dict)
        assert viewer._metadata['Another Simple'] == 123
        assert isinstance(viewer._metadata['List'], list)

    def test_update_metadata_multiple_times(self):
        """Test updating metadata multiple times"""
        viewer = MetadataViewer()

        # First update
        viewer.set_metadata({'Key1': 'Value1'})
        assert viewer._metadata == {'Key1': 'Value1'}

        # Second update (replace)
        viewer.set_metadata({'Key2': 'Value2'})
        assert viewer._metadata == {'Key2': 'Value2'}
        assert 'Key1' not in viewer._metadata


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
