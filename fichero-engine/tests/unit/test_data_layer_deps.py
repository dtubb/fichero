"""
Tests for data layer dependencies.

This module validates that all data layer dependencies work correctly:
- DuckDB (embedded analytics database)
- Pydantic (data validation)
- LanceDB (vector database with Pydantic support)
- LangGraph/LangChain (AI workflow)
- Parquet (via DuckDB and PyArrow)
"""

import pytest
import tempfile
import os
from datetime import datetime


class TestDuckDB:
    """Test DuckDB functionality."""

    def test_import(self):
        """Test DuckDB imports correctly."""
        import duckdb
        assert hasattr(duckdb, 'connect')
        assert hasattr(duckdb, '__version__')

    def test_basic_query(self):
        """Test basic SQL query."""
        import duckdb
        conn = duckdb.connect()
        result = conn.execute("SELECT 1 + 1 AS answer").fetchone()
        assert result[0] == 2

    def test_create_table(self):
        """Test creating and querying a table."""
        import duckdb
        conn = duckdb.connect()
        conn.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
        conn.execute("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')")
        result = conn.execute("SELECT * FROM test ORDER BY id").fetchall()
        assert len(result) == 2
        assert result[0] == (1, 'Alice')
        assert result[1] == (2, 'Bob')

    def test_parquet_write_and_read(self):
        """Test writing and reading Parquet files with DuckDB."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = os.path.join(tmpdir, 'test.parquet')

            # Write to Parquet
            conn = duckdb.connect()
            conn.execute("CREATE TABLE test AS SELECT 1 AS id, 'Hello' AS text")
            conn.execute(f"COPY test TO '{parquet_path}' (FORMAT PARQUET)")

            # Verify file exists
            assert os.path.exists(parquet_path)

            # Read from Parquet
            result = conn.execute(f"SELECT * FROM read_parquet('{parquet_path}')").fetchall()
            assert result == [(1, 'Hello')]

    def test_parquet_with_schema(self):
        """Test Parquet with complex schema."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = os.path.join(tmpdir, 'complex.parquet')

            conn = duckdb.connect()
            conn.execute("""
                CREATE TABLE complex AS SELECT
                    1 AS id,
                    'test' AS name,
                    3.14159::DOUBLE AS value,
                    TIMESTAMP '2024-01-15 10:30:00' AS created_at,
                    ['a', 'b', 'c'] AS tags
            """)
            conn.execute(f"COPY complex TO '{parquet_path}' (FORMAT PARQUET)")

            # Read back and verify
            result = conn.execute(f"SELECT id, name, value FROM read_parquet('{parquet_path}')").fetchone()
            assert result[0] == 1
            assert result[1] == 'test'
            assert abs(float(result[2]) - 3.14159) < 0.0001


class TestPydantic:
    """Test Pydantic functionality."""

    def test_import(self):
        """Test Pydantic imports correctly."""
        from pydantic import BaseModel, Field
        assert BaseModel is not None
        assert Field is not None

    def test_basic_model(self):
        """Test basic Pydantic model."""
        from pydantic import BaseModel

        class Item(BaseModel):
            id: str
            name: str
            value: float

        item = Item(id='123', name='Test', value=42.0)
        assert item.id == '123'
        assert item.name == 'Test'
        assert item.value == 42.0

    def test_model_validation(self):
        """Test Pydantic validation."""
        from pydantic import BaseModel, ValidationError

        class Item(BaseModel):
            count: int

        # Valid
        item = Item(count=5)
        assert item.count == 5

        # Invalid
        with pytest.raises(ValidationError):
            Item(count='not a number')

    def test_model_dump(self):
        """Test Pydantic model serialization."""
        from pydantic import BaseModel, Field

        class Collection(BaseModel):
            id: str
            name: str
            created_at: datetime = Field(default_factory=datetime.now)

        collection = Collection(id='abc', name='My Collection')
        data = collection.model_dump()

        assert data['id'] == 'abc'
        assert data['name'] == 'My Collection'
        assert 'created_at' in data


class TestPyArrow:
    """Test PyArrow functionality (used by LanceDB and Parquet)."""

    def test_import(self):
        """Test PyArrow imports correctly."""
        import pyarrow
        assert hasattr(pyarrow, '__version__')

    def test_create_table(self):
        """Test creating PyArrow table."""
        import pyarrow as pa

        data = {
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie']
        }
        table = pa.table(data)
        assert table.num_rows == 3
        assert table.num_columns == 2

    def test_parquet_roundtrip(self):
        """Test PyArrow Parquet write/read."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test.parquet')

            # Create and write
            data = {'id': [1, 2], 'value': [10.0, 20.0]}
            table = pa.table(data)
            pq.write_table(table, path)

            # Read back
            result = pq.read_table(path)
            assert result.num_rows == 2
            assert result.column('id').to_pylist() == [1, 2]


class TestLanceDB:
    """Test LanceDB functionality."""

    def test_import(self):
        """Test LanceDB imports correctly."""
        import lancedb
        assert hasattr(lancedb, 'connect')
        assert hasattr(lancedb, '__version__')

    def test_create_database(self):
        """Test creating a LanceDB database."""
        import lancedb

        with tempfile.TemporaryDirectory() as tmpdir:
            db = lancedb.connect(os.path.join(tmpdir, 'test.lancedb'))
            assert db is not None

    def test_create_and_query_table(self):
        """Test creating and querying a table."""
        import lancedb

        with tempfile.TemporaryDirectory() as tmpdir:
            db = lancedb.connect(os.path.join(tmpdir, 'test.lancedb'))

            # Create table
            data = [
                {'id': 1, 'name': 'Alice', 'score': 0.9},
                {'id': 2, 'name': 'Bob', 'score': 0.8}
            ]
            table = db.create_table('users', data)

            # Verify
            assert table.count_rows() == 2

            # Query
            results = table.search().limit(10).to_list()
            assert len(results) == 2

    def test_pydantic_integration(self):
        """Test LanceDB with Pydantic models."""
        import lancedb
        from pydantic import BaseModel

        class Item(BaseModel):
            id: int
            name: str
            value: float

        with tempfile.TemporaryDirectory() as tmpdir:
            db = lancedb.connect(os.path.join(tmpdir, 'test.lancedb'))

            # Create items
            items = [
                Item(id=1, name='Test1', value=1.0),
                Item(id=2, name='Test2', value=2.0)
            ]

            # Create table from Pydantic models
            data = [item.model_dump() for item in items]
            table = db.create_table('items', data)

            assert table.count_rows() == 2


class TestLangGraph:
    """Test LangGraph functionality."""

    def test_import(self):
        """Test LangGraph imports correctly."""
        from langgraph.graph import StateGraph
        assert StateGraph is not None

    def test_state_graph_creation(self):
        """Test creating a basic StateGraph."""
        from langgraph.graph import StateGraph
        from typing import TypedDict

        class State(TypedDict):
            value: int

        graph = StateGraph(State)
        assert graph is not None


class TestLangChain:
    """Test LangChain functionality."""

    def test_import(self):
        """Test LangChain core imports correctly."""
        # Note: We use langchain_core, not langchain base package
        import langchain_core
        assert hasattr(langchain_core, '__version__')

    def test_core_messages(self):
        """Test LangChain core message types."""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        human = HumanMessage(content='Hello')
        ai = AIMessage(content='Hi there!')
        system = SystemMessage(content='You are helpful.')

        assert human.content == 'Hello'
        assert ai.content == 'Hi there!'
        assert system.content == 'You are helpful.'

class TestIntegration:
    """Integration tests for the data layer."""

    def test_pydantic_to_duckdb(self):
        """Test storing Pydantic models in DuckDB."""
        import duckdb
        from pydantic import BaseModel, Field

        class Item(BaseModel):
            id: str
            name: str
            created_at: datetime = Field(default_factory=datetime.now)

        # Create items
        items = [
            Item(id='1', name='First'),
            Item(id='2', name='Second')
        ]

        # Store in DuckDB
        conn = duckdb.connect()
        conn.execute("""
            CREATE TABLE items (
                id VARCHAR,
                name VARCHAR,
                created_at TIMESTAMP
            )
        """)

        for item in items:
            data = item.model_dump()
            conn.execute(
                "INSERT INTO items VALUES (?, ?, ?)",
                [data['id'], data['name'], data['created_at']]
            )

        # Query back
        result = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        assert result[0] == 2

    def test_duckdb_parquet_lancedb(self):
        """Test data flow: DuckDB -> Parquet -> LanceDB."""
        import duckdb
        import lancedb
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = os.path.join(tmpdir, 'data.parquet')
            lance_path = os.path.join(tmpdir, 'data.lancedb')

            # 1. Create data in DuckDB and export to Parquet
            conn = duckdb.connect()
            conn.execute("""
                CREATE TABLE source AS SELECT
                    1 AS id, 'Document 1' AS title, 0.5 AS score
                UNION ALL SELECT
                    2, 'Document 2', 0.7
            """)
            conn.execute(f"COPY source TO '{parquet_path}' (FORMAT PARQUET)")

            # 2. Read Parquet and load into LanceDB
            parquet_table = pq.read_table(parquet_path)

            db = lancedb.connect(lance_path)
            lance_table = db.create_table('documents', parquet_table)

            # 3. Verify data in LanceDB
            assert lance_table.count_rows() == 2
            results = lance_table.search().limit(10).to_list()
            assert len(results) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
