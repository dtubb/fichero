"""
Unit tests for workflow node caching.

Tests the NodeCache class and cache key computation.
"""

import os
import tempfile
from pathlib import Path

import pytest

from fichero_server.workflows.cache import (
    NodeCache,
    compute_cache_key,
    _get_file_identity,
    CACHEABLE_TOOLS,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db():
    """Create a temporary DuckDB database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        yield db_path


@pytest.fixture
def cache(temp_db):
    """Create a NodeCache instance."""
    cache = NodeCache(temp_db)
    yield cache
    cache.close()


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content")
        f.flush()
        yield f.name
    os.unlink(f.name)


# =============================================================================
# NodeCache Tests
# =============================================================================


class TestNodeCache:
    """Tests for NodeCache class."""

    def test_create_cache(self, temp_db):
        """Test that cache can be created and schema is initialized."""
        cache = NodeCache(temp_db)

        # Verify table exists
        result = cache.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='node_cache'"
        ).fetchone()
        assert result is not None

        cache.close()

    def test_get_miss(self, cache):
        """Test that get returns None for missing key."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        cache_key = "test_key_123"
        result_data = {"output": "test result", "score": 0.95}

        cache.set(
            cache_key=cache_key,
            result=result_data,
            workflow_id="wf_001",
            node_id="node_001",
            tool="describe",
            file_path="/path/to/file.jpg",
        )

        # Retrieve
        retrieved = cache.get(cache_key)
        assert retrieved is not None
        assert retrieved.result["output"] == "test result"
        assert retrieved.result["score"] == 0.95

    def test_set_overwrites(self, cache):
        """Test that set overwrites existing entries."""
        cache_key = "test_key_456"

        # First set
        cache.set(
            cache_key=cache_key,
            result={"version": 1},
            workflow_id="wf_001",
            node_id="node_001",
            tool="describe",
        )

        # Overwrite
        cache.set(
            cache_key=cache_key,
            result={"version": 2},
            workflow_id="wf_001",
            node_id="node_001",
            tool="describe",
        )

        # Should get latest
        retrieved = cache.get(cache_key)
        assert retrieved.result["version"] == 2

    def test_clear_workflow(self, cache):
        """Test clearing cache for a specific workflow."""
        # Add entries for two workflows
        cache.set("key1", {"data": 1}, "wf_A", "n1", "describe")
        cache.set("key2", {"data": 2}, "wf_A", "n2", "transcribe")
        cache.set("key3", {"data": 3}, "wf_B", "n1", "describe")

        # Clear workflow A
        count = cache.clear_workflow("wf_A")
        assert count == 2

        # wf_A entries gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None

        # wf_B entry still exists
        assert cache.get("key3") is not None

    def test_clear_node(self, cache):
        """Test clearing cache for a specific node."""
        # Add entries for same workflow, different nodes
        cache.set("key1", {"data": 1}, "wf_A", "node_1", "describe")
        cache.set("key2", {"data": 2}, "wf_A", "node_1", "describe")
        cache.set("key3", {"data": 3}, "wf_A", "node_2", "describe")

        # Clear node_1
        count = cache.clear_node("wf_A", "node_1")
        assert count == 2

        # node_1 entries gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None

        # node_2 entry still exists
        assert cache.get("key3") is not None

    def test_clear_all(self, cache):
        """Test clearing entire cache."""
        # Add entries
        cache.set("key1", {"data": 1}, "wf_A", "n1", "describe")
        cache.set("key2", {"data": 2}, "wf_B", "n2", "transcribe")

        # Clear all
        count = cache.clear_all()
        assert count == 2

        # All gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_get_stats_empty(self, cache):
        """Test stats for empty cache."""
        stats = cache.get_stats()
        assert stats["total_entries"] == 0
        assert stats["tools_cached"] == 0

    def test_get_stats_with_data(self, cache):
        """Test stats with cached data."""
        cache.set("key1", {"data": 1}, "wf_A", "n1", "describe")
        cache.set("key2", {"data": 2}, "wf_A", "n2", "transcribe")
        cache.set("key3", {"data": 3}, "wf_B", "n3", "describe")

        # Overall stats
        stats = cache.get_stats()
        assert stats["total_entries"] == 3
        assert stats["workflows_cached"] == 2
        assert stats["tools_cached"] == 2  # describe, transcribe

        # Workflow-specific stats
        stats_a = cache.get_stats(workflow_id="wf_A")
        assert stats_a["total_entries"] == 2
        assert stats_a["nodes_cached"] == 2

    def test_complex_result_data(self, cache):
        """Test caching complex nested data structures."""
        complex_result = {
            "text": "A detailed description",
            "entities": [
                {"name": "Person A", "type": "PERSON"},
                {"name": "Place B", "type": "LOCATION"},
            ],
            "metadata": {
                "confidence": 0.87,
                "model": "gpt-4",
                "tokens_used": 150,
            },
            "tags": ["tag1", "tag2", "tag3"],
        }

        cache.set("complex_key", complex_result, "wf", "n", "describe")

        retrieved = cache.get("complex_key")
        assert retrieved.result["text"] == complex_result["text"]
        assert len(retrieved.result["entities"]) == 2
        assert retrieved.result["entities"][0]["name"] == "Person A"
        assert retrieved.result["metadata"]["confidence"] == 0.87


# =============================================================================
# Cache Key Tests
# =============================================================================


class TestCacheKey:
    """Tests for cache key computation."""

    def test_compute_cache_key_basic(self, temp_file):
        """Test basic cache key computation."""
        key = compute_cache_key(
            workflow_id="wf_123",
            node_id="node_456",
            tool="describe",
            config={"prompt": "Describe this image"},
            provider="openai",
            model="gpt-4-vision",
            file_path=temp_file,
        )

        # Key should be 32-char hex string
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    def test_same_inputs_same_key(self, temp_file):
        """Test that identical inputs produce same key."""
        kwargs = {
            "workflow_id": "wf_123",
            "node_id": "node_456",
            "tool": "describe",
            "config": {"prompt": "Describe this"},
            "provider": "openai",
            "model": "gpt-4",
            "file_path": temp_file,
        }

        key1 = compute_cache_key(**kwargs)
        key2 = compute_cache_key(**kwargs)

        assert key1 == key2

    def test_different_workflow_different_key(self, temp_file):
        """Test that different workflow_id produces different key."""
        base_kwargs = {
            "node_id": "node_456",
            "tool": "describe",
            "config": {},
            "provider": "openai",
            "model": "gpt-4",
            "file_path": temp_file,
        }

        key1 = compute_cache_key(workflow_id="wf_A", **base_kwargs)
        key2 = compute_cache_key(workflow_id="wf_B", **base_kwargs)

        assert key1 != key2

    def test_different_config_different_key(self, temp_file):
        """Test that different config produces different key."""
        base_kwargs = {
            "workflow_id": "wf_123",
            "node_id": "node_456",
            "tool": "describe",
            "provider": "openai",
            "model": "gpt-4",
            "file_path": temp_file,
        }

        key1 = compute_cache_key(config={"prompt": "Describe A"}, **base_kwargs)
        key2 = compute_cache_key(config={"prompt": "Describe B"}, **base_kwargs)

        assert key1 != key2

    def test_different_model_different_key(self, temp_file):
        """Test that different model produces different key."""
        base_kwargs = {
            "workflow_id": "wf_123",
            "node_id": "node_456",
            "tool": "describe",
            "config": {},
            "provider": "openai",
            "file_path": temp_file,
        }

        key1 = compute_cache_key(model="gpt-4", **base_kwargs)
        key2 = compute_cache_key(model="gpt-3.5-turbo", **base_kwargs)

        assert key1 != key2

    def test_config_order_independent(self, temp_file):
        """Test that config dict order doesn't affect key."""
        base_kwargs = {
            "workflow_id": "wf_123",
            "node_id": "node_456",
            "tool": "describe",
            "provider": "openai",
            "model": "gpt-4",
            "file_path": temp_file,
        }

        # Same config, different order
        key1 = compute_cache_key(config={"a": 1, "b": 2, "c": 3}, **base_kwargs)
        key2 = compute_cache_key(config={"c": 3, "a": 1, "b": 2}, **base_kwargs)

        assert key1 == key2

    def test_document_id_disambiguates_shared_path(self, temp_file):
        """Regression test for #896 — PDF page children share their
        parent PDF's on-disk path. Without document_id in the key,
        all six page docs collide and the cache returns page 1's
        result for pages 2-6, producing Davidson ×6.
        """
        base_kwargs = {
            "workflow_id": "wf_123",
            "node_id": "node_456",
            "tool": "extract_all",
            "config": {},
            "provider": "apple",
            "model": "fm-bridge",
            "file_path": temp_file,
        }
        key_page_1 = compute_cache_key(document_id="page-doc-1", **base_kwargs)
        key_page_2 = compute_cache_key(document_id="page-doc-2", **base_kwargs)
        assert key_page_1 != key_page_2, (
            "Page Documents sharing a parent PDF path must get distinct cache keys"
        )

    def test_document_id_default_is_backward_compatible(self, temp_file):
        """Omitting document_id keeps the historical key (before
        #896 fix). Non-page inputs that have no shared-path
        ambiguity continue to hit cache the way they did pre-fix.
        """
        kwargs = {
            "workflow_id": "wf_123",
            "node_id": "node_456",
            "tool": "describe",
            "config": {},
            "provider": "openai",
            "model": "gpt-4",
            "file_path": temp_file,
        }
        key_without = compute_cache_key(**kwargs)
        key_with_empty = compute_cache_key(**kwargs, document_id=None)
        assert key_without == key_with_empty


# =============================================================================
# File Identity Tests
# =============================================================================


class TestFileIdentity:
    """Tests for file identity computation."""

    def test_file_identity_includes_path(self, temp_file):
        """Test that file identity includes the path."""
        identity = _get_file_identity(temp_file)
        assert temp_file in identity

    def test_file_identity_includes_mtime_and_size(self, temp_file):
        """Test that file identity includes mtime and size."""
        identity = _get_file_identity(temp_file)
        parts = identity.split(":")

        # Should have path:mtime:size format
        assert len(parts) == 3
        assert parts[0] == temp_file
        # mtime and size should be numeric
        assert float(parts[1]) > 0  # mtime
        assert int(parts[2]) > 0    # size

    def test_file_identity_changes_on_modify(self, temp_file):
        """Test that file identity changes when file is modified."""
        identity1 = _get_file_identity(temp_file)

        # Modify the file
        with open(temp_file, "a") as f:
            f.write(" more content")

        identity2 = _get_file_identity(temp_file)

        # Should be different (mtime and/or size changed)
        assert identity1 != identity2

    def test_file_identity_nonexistent_file(self):
        """Test file identity for non-existent file."""
        identity = _get_file_identity("/nonexistent/path/file.txt")
        assert "unknown" in identity


# =============================================================================
# Cacheable Tools Tests
# =============================================================================


class TestCacheableTools:
    """Tests for cacheable tools configuration."""

    def test_expensive_tools_are_cacheable(self):
        """Test that expensive LLM tools are in CACHEABLE_TOOLS."""
        expected_tools = {
            "describe",
            "transcribe",
            "summarize",
            "entities",
            "handwriting",
            "caption",
        }

        for tool in expected_tools:
            assert tool in CACHEABLE_TOOLS, f"{tool} should be cacheable"

    def test_cheap_tools_not_cacheable(self):
        """Test that cheap tools are not in CACHEABLE_TOOLS."""
        cheap_tools = {"files", "collection", "folder", "filter", "sort"}

        for tool in cheap_tools:
            assert tool not in CACHEABLE_TOOLS, f"{tool} should not be cacheable"

    def test_extract_all_is_cacheable(self):
        """extract_all is the combined extractor the default Catalogue
        preset uses — it MUST be cacheable, or every re-run pays the full
        extraction cost again while transcribe cache-hits (#1065)."""
        assert "extract_all" in CACHEABLE_TOOLS


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestCacheIntegration:
    """Integration-style tests for cache workflow."""

    def test_cache_workflow_scenario(self, cache, temp_file):
        """Test a realistic caching scenario."""
        workflow_id = "wf_photo_processing"
        node_id = "describe_node"
        tool = "describe"
        config = {"prompt": "Describe this photo", "detail": "high"}
        provider = "openai"
        model = "gpt-4-vision"

        # Compute cache key
        cache_key = compute_cache_key(
            workflow_id=workflow_id,
            node_id=node_id,
            tool=tool,
            config=config,
            provider=provider,
            model=model,
            file_path=temp_file,
        )

        # First run: cache miss
        result = cache.get(cache_key)
        assert result is None

        # Simulate tool execution
        tool_result = {
            "description": "A beautiful sunset over the ocean",
            "objects": ["sun", "ocean", "clouds"],
            "colors": ["orange", "blue", "pink"],
        }

        # Cache the result
        cache.set(
            cache_key=cache_key,
            result=tool_result,
            workflow_id=workflow_id,
            node_id=node_id,
            tool=tool,
            file_path=temp_file,
        )

        # Second run: cache hit
        cached_result = cache.get(cache_key)
        assert cached_result is not None
        assert cached_result.result["description"] == tool_result["description"]

        # Different config: cache miss
        new_config = {"prompt": "List objects in this photo", "detail": "low"}
        new_cache_key = compute_cache_key(
            workflow_id=workflow_id,
            node_id=node_id,
            tool=tool,
            config=new_config,
            provider=provider,
            model=model,
            file_path=temp_file,
        )

        assert cache.get(new_cache_key) is None

    def test_multiple_files_caching(self, cache):
        """Test caching multiple files in a batch."""
        workflow_id = "wf_batch"
        node_id = "process_node"
        tool = "describe"
        config = {}
        provider = "anthropic"
        model = "claude-3"

        # Create multiple temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(5):
                file_path = Path(tmpdir) / f"file_{i}.txt"
                file_path.write_text(f"Content {i}")
                files.append(str(file_path))

            # Process each file
            for i, file_path in enumerate(files):
                cache_key = compute_cache_key(
                    workflow_id=workflow_id,
                    node_id=node_id,
                    tool=tool,
                    config=config,
                    provider=provider,
                    model=model,
                    file_path=file_path,
                )

                cache.set(
                    cache_key=cache_key,
                    result={"file_index": i, "processed": True},
                    workflow_id=workflow_id,
                    node_id=node_id,
                    tool=tool,
                    file_path=file_path,
                )

            # Verify all cached
            stats = cache.get_stats(workflow_id=workflow_id)
            assert stats["total_entries"] == 5
