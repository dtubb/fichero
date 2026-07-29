"""Unit tests for the write_file tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fichero_server.workflows.tools.write_file import (
    _extract_records,
    _render_template,
    _safe_filename,
    _unique_path,
    write_file,
)


class TestSafeFilename:
    def test_preserves_safe_chars(self):
        assert _safe_filename("hello_world-42.txt") == "hello_world-42.txt"

    def test_strips_path_separators(self):
        assert "/" not in _safe_filename("../etc/passwd")
        assert "\\" not in _safe_filename("..\\windows\\system32")

    def test_rejects_bare_dotdot(self):
        # After sanitization ".." should never survive
        result = _safe_filename("..")
        assert ".." not in result
        assert result == "file"  # fallback

    def test_rejects_bare_dot(self):
        assert _safe_filename(".") == "file"

    def test_empty_falls_back(self):
        assert _safe_filename("") == "file"
        assert _safe_filename("   ") == "file"

    def test_clips_long(self):
        long_name = "a" * 500
        assert len(_safe_filename(long_name)) <= 200

    def test_non_ascii_replaced(self):
        # Spanish characters aren't in the safe set; they get replaced.
        # The important thing is no path separators survive.
        result = _safe_filename("café/día")
        assert "/" not in result


class TestRenderTemplate:
    def test_substitutes_placeholders(self):
        result = _render_template(
            "{doc_name}-{tool}-{model}.{ext}",
            doc_name="photo1",
            tool="transcribe",
            model="qwen-vl-3.5",
            provider="qwen",
            ext="txt",
            index=0,
        )
        # Dots are preserved within the safe set
        assert "photo1" in result
        assert "transcribe" in result
        assert "qwen-vl-3.5" in result
        assert result.endswith("txt")

    def test_malicious_doc_name_sanitized(self):
        # A doc name containing path traversal must not escape
        result = _render_template(
            "{doc_name}.{ext}",
            doc_name="../../etc/passwd",
            tool="transcribe",
            model="m",
            provider="p",
            ext="txt",
            index=0,
        )
        assert "/" not in result
        assert ".." not in result

    def test_index_substitution(self):
        result = _render_template(
            "item-{index}.{ext}",
            doc_name="x",
            tool="t",
            model="m",
            provider="p",
            ext="md",
            index=7,
        )
        assert "7" in result


class TestUniquePath:
    def test_returns_unused_as_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            p = _unique_path(d, "new.txt")
            assert p == d / "new.txt"

    def test_suffixes_on_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "dup.txt").touch()
            p = _unique_path(d, "dup.txt")
            assert p.name == "dup-2.txt"

    def test_chains_multiple_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "c.txt").touch()
            (d / "c-2.txt").touch()
            (d / "c-3.txt").touch()
            p = _unique_path(d, "c.txt")
            assert p.name == "c-4.txt"


class TestExtractRecords:
    def test_empty_inputs_returns_empty(self):
        assert _extract_records({}) == []
        assert _extract_records({"text": None}) == []

    def test_single_string(self):
        records = _extract_records({"text": "hello"})
        assert len(records) == 1
        assert records[0]["text"] == "hello"

    def test_list_of_strings(self):
        records = _extract_records({"text": ["a", "b", "c"]})
        assert len(records) == 3
        assert [r["text"] for r in records] == ["a", "b", "c"]

    def test_doc_name_from_documents_list(self):
        records = _extract_records({
            "text": ["t1", "t2"],
            "documents": [{"name": "img1.jpg"}, {"name": "img2.jpg"}],
        })
        assert records[0]["doc_name"] == "img1.jpg"
        assert records[1]["doc_name"] == "img2.jpg"

    def test_fallback_doc_name_when_missing(self):
        records = _extract_records({"text": ["t"]})
        assert records[0]["doc_name"] == "item-1"

    def test_dict_becomes_json(self):
        records = _extract_records({"text": {"key": "value"}})
        assert len(records) == 1
        assert '"key"' in records[0]["text"]


class TestWriteFileIntegration:
    @pytest.mark.asyncio
    async def test_per_file_mode_writes_one_per_record(self):
        from fichero_server.llm import LLMConfig

        with tempfile.TemporaryDirectory() as tmp:
            inputs = {
                "text": ["transcript one", "transcript two"],
                "documents": [{"name": "a.jpg"}, {"name": "b.jpg"}],
                "_config": {
                    "output_dir": tmp,
                    "filename_template": "{doc_name}.{ext}",
                    "format": "txt",
                    "mode": "per_file",
                },
            }
            llm = LLMConfig(provider="test", model="test-model")
            result = await write_file(inputs, state={}, llm_config=llm)
            assert result["count"] == 2
            files = sorted(Path(tmp).iterdir())
            assert len(files) == 2
            assert {f.read_text() for f in files} == {
                "transcript one",
                "transcript two",
            }

    @pytest.mark.asyncio
    async def test_aggregate_mode_writes_single_file(self):
        from fichero_server.llm import LLMConfig

        with tempfile.TemporaryDirectory() as tmp:
            inputs = {
                "text": ["chunk A", "chunk B"],
                "_config": {
                    "output_dir": tmp,
                    "filename_template": "combined.{ext}",
                    "format": "md",
                    "mode": "aggregate",
                    "aggregate_separator": "\n---\n",
                },
            }
            llm = LLMConfig(provider="", model="")
            result = await write_file(inputs, state={}, llm_config=llm)
            assert result["count"] == 1
            files = list(Path(tmp).iterdir())
            assert len(files) == 1
            assert files[0].name == "combined.md"
            assert files[0].read_text() == "chunk A\n---\nchunk B"

    @pytest.mark.asyncio
    async def test_missing_output_dir_returns_error(self):
        from fichero_server.llm import LLMConfig

        inputs = {"text": "x", "_config": {"output_dir": ""}}
        llm = LLMConfig(provider="", model="")
        result = await write_file(inputs, state={}, llm_config=llm)
        assert result["count"] == 0
        assert result.get("error")

    @pytest.mark.asyncio
    async def test_collision_auto_suffixes(self):
        from fichero_server.llm import LLMConfig

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "item-0.txt").write_text("existing")
            inputs = {
                "text": ["new"],
                "_config": {
                    "output_dir": tmp,
                    "filename_template": "item-{index}.{ext}",
                    "format": "txt",
                    "mode": "per_file",
                },
            }
            llm = LLMConfig(provider="", model="")
            result = await write_file(inputs, state={}, llm_config=llm)
            assert result["count"] == 1
            # Existing file untouched, new file suffixed
            assert (Path(tmp) / "item-0.txt").read_text() == "existing"
            assert any(p.name == "item-0-2.txt" for p in Path(tmp).iterdir())
