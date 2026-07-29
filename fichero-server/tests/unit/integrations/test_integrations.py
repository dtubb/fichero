"""
Unit tests for app integrations module.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fichero_server.integrations.base import (
    IntegrationRegistry,
    IntegrationStatus,
    AppInfo,
    ImportedItem,
    escape_applescript,
)
from fichero_server.integrations.devonthink import DEVONthinkIntegration
from fichero_server.integrations.bookends import BookendsIntegration
from fichero_server.integrations.tinderbox import TinderboxIntegration


class TestAppInfo:
    """Tests for AppInfo dataclass."""

    def test_create_app_info(self):
        """Test creating AppInfo with minimal fields."""
        info = AppInfo(
            name="TestApp",
            bundle_id="com.test.app"
        )
        assert info.name == "TestApp"
        assert info.bundle_id == "com.test.app"
        assert info.status == IntegrationStatus.UNAVAILABLE
        assert info.version is None

    def test_create_app_info_with_all_fields(self):
        """Test creating AppInfo with all fields."""
        info = AppInfo(
            name="TestApp",
            bundle_id="com.test.app",
            version="1.0.0",
            path=Path("/Applications/TestApp.app"),
            status=IntegrationStatus.AVAILABLE
        )
        assert info.version == "1.0.0"
        assert info.path == Path("/Applications/TestApp.app")
        assert info.status == IntegrationStatus.AVAILABLE


class TestImportedItem:
    """Tests for ImportedItem dataclass."""

    def test_create_imported_item(self):
        """Test creating ImportedItem with minimal fields."""
        item = ImportedItem(
            external_id="123",
            name="Test Item",
            source_app="TestApp",
            item_type="document"
        )
        assert item.external_id == "123"
        assert item.name == "Test Item"
        assert item.source_app == "TestApp"
        assert item.item_type == "document"
        assert item.metadata == {}

    def test_create_imported_item_with_metadata(self):
        """Test creating ImportedItem with metadata."""
        item = ImportedItem(
            external_id="123",
            name="Test Item",
            source_app="TestApp",
            item_type="document",
            metadata={"key": "value"}
        )
        assert item.metadata == {"key": "value"}


def test_integration_implementations_import_before_base() -> None:
    """Implementations remain importable before the package base contract."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import fichero_server.integrations.devonthink; import fichero_server.integrations.base",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


class TestIntegrationRegistry:
    """Tests for IntegrationRegistry."""

    def test_singleton_instance(self):
        """Test that registry is singleton."""
        registry1 = IntegrationRegistry.get_instance()
        registry2 = IntegrationRegistry.get_instance()
        assert registry1 is registry2

    def test_register_integration(self):
        """Test registering an integration."""
        registry = IntegrationRegistry()
        integration = DEVONthinkIntegration()

        # Mock availability check
        with patch.object(integration, 'check_availability', return_value=False):
            registry.register(integration)

        assert registry.get("devonthink") is integration

    def test_list_all(self):
        """Test listing all integrations."""
        registry = IntegrationRegistry()

        dt = DEVONthinkIntegration()
        be = BookendsIntegration()

        with patch.object(dt, 'check_availability', return_value=False):
            with patch.object(be, 'check_availability', return_value=False):
                registry.register(dt)
                registry.register(be)

        all_integrations = registry.list_all()
        assert len(all_integrations) == 2

    def test_initialize_registers_default_integrations_once(self):
        """Test initialization registers default integrations idempotently."""
        registry = IntegrationRegistry()

        registry.initialize()

        integrations_by_name = {
            integration.name: integration
            for integration in registry.list_all()
        }
        assert set(integrations_by_name) == {"DEVONthink", "Bookends", "Tinderbox"}
        assert registry.get("devonthink") is integrations_by_name["DEVONthink"]
        assert registry.get("bookends") is integrations_by_name["Bookends"]
        assert registry.get("tinderbox") is integrations_by_name["Tinderbox"]

        first_instances = {
            integration.name: id(integration)
            for integration in registry.list_all()
        }

        registry.initialize()

        assert {
            integration.name: id(integration)
            for integration in registry.list_all()
        } == first_instances


class TestDEVONthinkIntegration:
    """Tests for DEVONthink integration."""

    def test_properties(self):
        """Test basic properties."""
        integration = DEVONthinkIntegration()
        assert integration.name == "DEVONthink"
        assert integration.bundle_id == "com.devon-technologies.think3"

    def test_check_availability_not_installed(self):
        """Test availability check when app not installed."""
        integration = DEVONthinkIntegration()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = integration.check_availability()

        assert result is False
        assert integration.app_info.status == IntegrationStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_list_items_not_available(self):
        """Test list_items when app not available."""
        integration = DEVONthinkIntegration()

        with patch.object(integration, '_app_info', AppInfo(
            name="DEVONthink",
            bundle_id="com.devon-technologies.think3",
            status=IntegrationStatus.UNAVAILABLE
        )):
            items = await integration.list_items()

        assert items == []

    def test_parse_applescript_records_empty(self):
        """Test parsing empty AppleScript result."""
        integration = DEVONthinkIntegration()
        result = integration._parse_applescript_records("{}")
        assert result == []

    def test_parse_applescript_records_single(self):
        """Test parsing single AppleScript record."""
        integration = DEVONthinkIntegration()
        result = integration._parse_applescript_records('{|name|:"Test", |uuid|:"123"}')
        assert len(result) == 1
        assert result[0].get("name") == "Test"
        assert result[0].get("uuid") == "123"

    @pytest.mark.asyncio
    async def test_list_items_search_escapes_applescript_literal(self):
        """Adversarial search text stays inside the AppleScript string literal."""
        integration = DEVONthinkIntegration()
        payload = 'x" \nset y to do shell script "echo pwned'
        captured_script = ""

        def capture_script(script):
            nonlocal captured_script
            captured_script = script
            return True, "{}"

        with patch.object(
            integration,
            "_app_info",
            AppInfo(
                name="DEVONthink",
                bundle_id="com.devon-technologies.think3",
                status=IntegrationStatus.AVAILABLE,
            ),
        ):
            with patch.object(integration, "run_applescript", side_effect=capture_script):
                await integration.list_items(limit="3", search=payload)

        expected = 'search "x\\" \\nset y to do shell script \\"echo pwned"'
        assert expected in captured_script
        assert 'do shell script "echo pwned' not in captured_script
        assert 'search "x" \nset y' not in captured_script
        assert "if counter >= 3 then exit repeat" in captured_script


class TestAppleScriptEscaping:
    """Tests for shared AppleScript literal escaping."""

    def test_escape_applescript_neutralizes_quote_backslash_and_newline(self):
        value = 'quote" slash\\ newline\nend'

        assert escape_applescript(value) == 'quote\\" slash\\\\ newline\\nend'


class TestBookendsIntegration:
    """Tests for Bookends integration."""

    def test_properties(self):
        """Test basic properties."""
        integration = BookendsIntegration()
        assert integration.name == "Bookends"
        assert integration.bundle_id == "com.sonnysoftware.bookends2"

    @pytest.mark.asyncio
    async def test_list_items_not_available(self):
        """Test list_items when app not available."""
        integration = BookendsIntegration()

        with patch.object(integration, '_app_info', AppInfo(
            name="Bookends",
            bundle_id="com.sonnysoftware.bookends2",
            status=IntegrationStatus.UNAVAILABLE
        )):
            items = await integration.list_items()

        assert items == []

    @pytest.mark.asyncio
    async def test_get_citation_not_available(self):
        """Test get_citation when app not available."""
        integration = BookendsIntegration()

        with patch.object(integration, '_app_info', AppInfo(
            name="Bookends",
            bundle_id="com.sonnysoftware.bookends2",
            status=IntegrationStatus.UNAVAILABLE
        )):
            citation = await integration.get_citation("123")

        assert citation is None


class TestTinderboxIntegration:
    """Tests for Tinderbox integration."""

    def test_properties(self):
        """Test basic properties."""
        integration = TinderboxIntegration()
        assert integration.name == "Tinderbox"
        assert integration.bundle_id == "com.eastgate.Tinderbox"

    @pytest.mark.asyncio
    async def test_list_items_not_available(self):
        """Test list_items when app not available."""
        integration = TinderboxIntegration()

        with patch.object(integration, '_app_info', AppInfo(
            name="Tinderbox",
            bundle_id="com.eastgate.Tinderbox",
            status=IntegrationStatus.UNAVAILABLE
        )):
            items = await integration.list_items()

        assert items == []

    @pytest.mark.asyncio
    async def test_create_note_not_available(self):
        """Test create_note when app not available."""
        integration = TinderboxIntegration()

        with patch.object(integration, '_app_info', AppInfo(
            name="Tinderbox",
            bundle_id="com.eastgate.Tinderbox",
            status=IntegrationStatus.UNAVAILABLE
        )):
            note_id = await integration.create_note("Test Note")

        assert note_id is None

    def test_parse_date_invalid(self):
        """Test parsing invalid date."""
        integration = TinderboxIntegration()
        result = integration._parse_date("invalid date")
        assert result is None

    def test_parse_date_none(self):
        """Test parsing None date."""
        integration = TinderboxIntegration()
        result = integration._parse_date(None)
        assert result is None


class TestAppleScriptRunner:
    """Tests for AppleScript execution."""

    def test_run_applescript_success(self):
        """Test successful AppleScript execution."""
        integration = DEVONthinkIntegration()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="test result",
                stderr=""
            )
            success, result = integration.run_applescript('tell application "Finder" to beep')

        assert success is True
        assert result == "test result"

    def test_run_applescript_error(self):
        """Test AppleScript execution error."""
        integration = DEVONthinkIntegration()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Script error"
            )
            success, result = integration.run_applescript('invalid script')

        assert success is False
        assert "Script error" in result

    def test_run_applescript_timeout(self):
        """Test AppleScript timeout."""
        import subprocess
        integration = DEVONthinkIntegration()

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("osascript", 30)
            success, result = integration.run_applescript('slow script')

        assert success is False
        assert "timed out" in result.lower()
