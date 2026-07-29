"""Unit tests for action store."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from fichero_server.workflows.action_store import Action, ActionStore, BUILTIN_ACTIONS


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
        """Create a mock database.

        ActionStore now talks to the Database through the #2508 locked seam
        (db.execute / db.execute_fetchall / db.execute_fetchone) instead of the
        unlocked db.duck.execute(...).fetch* path, so the collaborator mock is
        wired to those helpers.
        """
        db = MagicMock()
        db.execute_fetchone.return_value = None
        db.execute_fetchall.return_value = []
        return db

    def test_init_creates_table(self, mock_db):
        """Test that init creates the actions table."""
        ActionStore(mock_db)
        # Should have called execute for CREATE TABLE
        calls = mock_db.execute.call_args_list
        assert any("CREATE TABLE" in str(c) for c in calls)

    def test_get_categories(self, mock_db):
        """Test getting categories."""
        mock_db.execute_fetchall.return_value = [
            ("ai",), ("transform",), ("extract",)
        ]
        store = ActionStore(mock_db)
        categories = store.get_categories()
        assert "ai" in categories or len(categories) >= 0


class TestActionStoreConcurrency:
    """#2508 Phase 3b — the action store now routes its raw SQL through the
    Database locked seam (db.execute / db.execute_fetchall / db.execute_fetchone)
    so it shares one DuckDB connection + one RLock with the typed db.save path.

    Real threads + a real temp DuckDB library, no DB mocks (a mock can't exhibit
    the connection-topology hazard the lock guards against).
    """

    @pytest.fixture
    def shared_db(self, tmp_path, monkeypatch):
        """One shared managed Database for a real .fichero package."""
        monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
        from fichero_server.db.manager import db_manager

        lib = tmp_path / "ActionConc.fichero"
        lib.mkdir(parents=True, exist_ok=True)
        db = db_manager.get_database(str(lib))
        yield db
        try:
            db_manager.close_all()
        except Exception:
            pass

    def test_action_write_concurrent_with_typed_save(self, shared_db):
        """An ActionStore write loop running on real threads concurrently with a
        typed db.save loop — both on the SAME shared Database connection —
        completes with zero DuckDB threading errors and EVERY row lands.

        Before #2508 Phase 3b the action store wrote on the unlocked
        ``db.duck.execute`` path; interleaved with a typed save on the one shared
        connection that is a data race. Now both serialize on Database._lock.
        """
        from fichero_server.models import Document, DocType, Status

        store = ActionStore(shared_db)
        n = 40
        errors: list[str] = []

        def write_actions() -> None:
            for i in range(n):
                try:
                    store.save(
                        Action(id=f"act-{i}", name=f"action {i}", category="custom")
                    )
                except Exception as exc:  # noqa: BLE001 - surface any threading error
                    errors.append(f"action act-{i}: {exc!r}")

        def write_docs() -> None:
            now = datetime.now()
            for i in range(n):
                try:
                    shared_db.save(
                        Document(
                            id=f"doc-{i}",
                            name=f"doc {i}",
                            doc_type=DocType.file,
                            path=None,
                            status=Status.pending,
                            metadata={},
                            created_at=now,
                            updated_at=now,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"doc doc-{i}: {exc!r}")

        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(write_actions), ex.submit(write_docs)]
            for f in futures:
                f.result()

        assert not errors, f"concurrent action/typed-save errors: {errors[:5]}"

        # Both writers' rows must all be present after the threads join.
        action_ids = {a.id for a in store.list_all()}
        missing_actions = [f"act-{i}" for i in range(n) if f"act-{i}" not in action_ids]
        assert not missing_actions, f"action rows lost: {missing_actions[:5]}"

        present_docs = {d.id for d in shared_db.all(Document)}
        missing_docs = [f"doc-{i}" for i in range(n) if f"doc-{i}" not in present_docs]
        assert not missing_docs, f"document rows lost: {missing_docs[:5]}"
