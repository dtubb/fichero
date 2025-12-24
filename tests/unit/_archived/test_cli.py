"""Tests for CLI commands."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from fichero.cli import app


runner = CliRunner()


class TestIngestCommand:
    """Test the ingest command."""

    def test_ingest_file_not_found(self):
        """Ingest fails for missing file."""
        result = runner.invoke(app, ["ingest", "/nonexistent/file.txt"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_ingest_single_file(self, tmp_path):
        """Ingest a single file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content for ingestion")

        with patch("fichero.ingest.ingest_file") as mock_ingest:
            mock_doc = MagicMock()
            mock_doc.name = "test.txt"
            mock_ingest.return_value = mock_doc

            result = runner.invoke(app, ["ingest", str(test_file)])

        assert result.exit_code == 0
        assert "Ingested: test.txt" in result.output
        mock_ingest.assert_called_once()

    def test_ingest_folder(self, tmp_path):
        """Ingest a folder."""
        (tmp_path / "doc1.txt").write_text("Document 1")
        (tmp_path / "doc2.txt").write_text("Document 2")

        with patch("fichero.ingest.ingest_folder") as mock_ingest:
            mock_ingest.return_value = [MagicMock(), MagicMock()]

            result = runner.invoke(app, ["ingest", str(tmp_path)])

        assert result.exit_code == 0
        assert "Ingested 2 files" in result.output

    def test_ingest_copy_flag(self, tmp_path):
        """Ingest with --copy flag."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        with patch("fichero.ingest.ingest_file") as mock_ingest:
            mock_doc = MagicMock()
            mock_doc.name = "test.txt"
            mock_ingest.return_value = mock_doc

            result = runner.invoke(app, ["ingest", "--copy", str(test_file)])

        assert result.exit_code == 0
        call_kwargs = mock_ingest.call_args.kwargs
        from fichero.ingest import IngestMode
        assert call_kwargs.get("mode") == IngestMode.COPY

    def test_ingest_no_extract(self, tmp_path):
        """Ingest with --no-extract flag."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        with patch("fichero.ingest.ingest_file") as mock_ingest:
            mock_doc = MagicMock()
            mock_doc.name = "test.txt"
            mock_ingest.return_value = mock_doc

            result = runner.invoke(app, ["ingest", "--no-extract", str(test_file)])

        assert result.exit_code == 0
        call_kwargs = mock_ingest.call_args.kwargs
        assert call_kwargs.get("extract_text") is False

    def test_ingest_no_index(self, tmp_path):
        """Ingest with --no-index flag."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        with patch("fichero.ingest.ingest_file") as mock_ingest:
            mock_doc = MagicMock()
            mock_doc.name = "test.txt"
            mock_ingest.return_value = mock_doc

            result = runner.invoke(app, ["ingest", "--no-index", str(test_file)])

        assert result.exit_code == 0
        call_kwargs = mock_ingest.call_args.kwargs
        assert call_kwargs.get("auto_embed") is False


class TestSearchCommand:
    """Test the search command."""

    def test_search_no_results(self):
        """Search with no results."""
        with patch("fichero.db.db") as mock_db:
            mock_db.search.return_value = []

            result = runner.invoke(app, ["search", "nonexistent query"])

        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_search_with_results(self):
        """Search returns results."""
        from fichero.db import SearchResult

        mock_results = [
            SearchResult(
                document_id="doc1",
                score=0.95,
                content_preview="This is a preview of the document",
                metadata={"name": "letter.pdf"},
            ),
            SearchResult(
                document_id="doc2",
                score=0.80,
                content_preview="Another document preview",
                metadata={"name": "invoice.pdf"},
            ),
        ]

        with patch("fichero.db.db") as mock_db:
            mock_db.search.return_value = mock_results

            result = runner.invoke(app, ["search", "test query"])

        assert result.exit_code == 0
        assert "Found 2 results" in result.output
        assert "letter.pdf" in result.output
        assert "0.95" in result.output

    def test_search_limit_option(self):
        """Search respects --limit option."""
        with patch("fichero.db.db") as mock_db:
            mock_db.search.return_value = []

            result = runner.invoke(app, ["search", "--limit", "5", "query"])

        mock_db.search.assert_called_once_with("query", limit=5)


class TestStatsCommand:
    """Test the stats command."""

    def test_stats_output(self):
        """Stats shows document count and indexed count."""
        with patch("fichero.db.db") as mock_db:
            mock_db.count.return_value = 42
            mock_db.embedding_stats.return_value = {"indexed_count": 35}

            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "Documents: 42" in result.output
        assert "Indexed:   35" in result.output


class TestReindexCommand:
    """Test the reindex command."""

    def test_reindex(self):
        """Reindex rebuilds search index."""
        with patch("fichero.db.db") as mock_db:
            mock_db.reindex_all.return_value = 10

            result = runner.invoke(app, ["reindex"])

        assert result.exit_code == 0
        assert "Indexed 10 documents" in result.output


class TestQueryCommand:
    """Test the query (RAG) command."""

    def test_query_no_results(self):
        """Query with no matching documents."""
        with patch("fichero.db.db") as mock_db:
            mock_db.search.return_value = []

            result = runner.invoke(app, ["query", "What is in these documents?"])

        assert result.exit_code == 1
        assert "No relevant documents found" in result.output

    def test_query_with_context(self):
        """Query uses document context for RAG."""
        from fichero.db import SearchResult

        mock_results = [
            SearchResult(
                document_id="doc1",
                score=0.95,
                content_preview="The letter discusses property sale in 1923.",
                metadata={"name": "letter1.pdf"},
            ),
        ]

        with patch("fichero.db.db") as mock_db:
            mock_db.search.return_value = mock_results

            with patch("openai.OpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_openai.return_value = mock_client
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = "The document discusses a property sale."
                mock_client.chat.completions.create.return_value = mock_response

                result = runner.invoke(app, ["query", "What does the letter discuss?"])

        assert result.exit_code == 0
        assert "Answer:" in result.output
        assert "Sources:" in result.output

    def test_query_context_limit_option(self):
        """Query respects --context option."""
        with patch("fichero.db.db") as mock_db:
            mock_db.search.return_value = []

            result = runner.invoke(app, ["query", "--context", "3", "test"])

        mock_db.search.assert_called_once_with("test", limit=3)

    def test_query_help(self):
        """Query help shows options."""
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "--context" in result.output
        assert "--model" in result.output


class TestHelpOutput:
    """Test help output for all commands."""

    def test_main_help(self):
        """Main help shows all commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ingest" in result.output
        assert "search" in result.output
        assert "stats" in result.output
        assert "reindex" in result.output
        assert "query" in result.output

    def test_ingest_help(self):
        """Ingest help shows options."""
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--copy" in result.output
        assert "--extract" in result.output
        assert "--index" in result.output

    def test_search_help(self):
        """Search help shows options."""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output
