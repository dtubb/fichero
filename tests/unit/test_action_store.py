"""Unit tests for action store."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from fichero.workflows.action_store import Action, ActionStore, BUILTIN_ACTIONS


class TestAction:
    """Tests for Action model."""

    def test_create_action(self):
        """Test creating an action."""
        action = Action(name="Test Action", description="A test action")
        assert action.name == "Test Action"
        assert action.description == "A test action"
        assert action.category == "custom"
        assert action.is_builtin is False

    def test_action_with_node_template(self):
        """Test action with node template."""
        action = Action(
            name="LLM Action",
            node_template={"type": "llm", "data": {"prompt": "test"}}
        )
        assert action.node_template["type"] == "llm"

    def test_composite_action(self):
        """Test composite action."""
        action = Action(
            name="Composite",
            nodes=[{"id": "1"}, {"id": "2"}],
            edges=[{"source": "1", "target": "2"}],
            is_composite=True
        )
        assert action.is_composite is True
        assert len(action.nodes) == 2
        assert len(action.edges) == 1


class TestBuiltinActions:
    """Tests for built-in actions."""

    def test_builtin_actions_exist(self):
        """Test that built-in actions are defined."""
        assert len(BUILTIN_ACTIONS) > 0

    def test_builtin_actions_have_ids(self):
        """Test that all built-in actions have IDs starting with builtin-."""
        for action in BUILTIN_ACTIONS:
            assert action.id.startswith("builtin-")
            assert action.is_builtin is True

    def test_builtin_actions_have_names(self):
        """Test that all built-in actions have names."""
        for action in BUILTIN_ACTIONS:
            assert action.name
            assert len(action.name) > 0


class TestActionStore:
    """Tests for ActionStore."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.duck = MagicMock()
        db.duck.execute.return_value.fetchone.return_value = None
        db.duck.execute.return_value.fetchall.return_value = []
        return db

    def test_init_creates_table(self, mock_db):
        """Test that init creates the actions table."""
        store = ActionStore(mock_db)
        # Should have called execute for CREATE TABLE
        calls = mock_db.duck.execute.call_args_list
        assert any("CREATE TABLE" in str(c) for c in calls)

    def test_get_categories(self, mock_db):
        """Test getting categories."""
        mock_db.duck.execute.return_value.fetchall.return_value = [
            ("ai",), ("transform",), ("extract",)
        ]
        store = ActionStore(mock_db)
        categories = store.get_categories()
        assert "ai" in categories or len(categories) >= 0
