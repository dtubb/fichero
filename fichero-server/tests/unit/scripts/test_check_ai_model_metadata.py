from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_ai_model_metadata.py"
_SPEC = importlib.util.spec_from_file_location("check_ai_model_metadata", _SCRIPT)
assert _SPEC and _SPEC.loader
check_ai_model_metadata = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_ai_model_metadata
_SPEC.loader.exec_module(check_ai_model_metadata)  # type: ignore[attr-defined]


def test_scan_source_flags_buggy_fastembed_custom_model_pattern():
    offenders = check_ai_model_metadata.scan_source(
        """
from fastembed import TextEmbedding

def register():
    supported = TextEmbedding.list_supported_models()
    source = next(model for model in supported if model["model"] == "x")
    TextEmbedding.add_custom_model(
        model="alias",
        sources=source["sources"],
        dim=source["dim"],
        model_file=source["model_file"],
        size_in_gb=source["size_in_GB"],
    )
""",
        "fichero-server/src/fichero_server/db_embeddings.py",
    )

    rules = {(offender.rule, offender.line) for offender in offenders}
    assert ("list_supported_models_in_custom_registration", 5) in rules
    assert ("raw_model_metadata_dict_subscript", 6) not in rules  # model key is not guarded
    assert ("raw_model_metadata_dict_subscript", 9) in rules
    assert ("raw_model_metadata_dict_subscript", 10) in rules
    assert ("raw_model_metadata_dict_subscript", 11) in rules
    assert ("raw_model_metadata_dict_subscript", 12) in rules


def test_scan_source_allows_typed_fastembed_model_description_usage():
    offenders = check_ai_model_metadata.scan_source(
        """
from fastembed import TextEmbedding

def register():
    supported = TextEmbedding._list_supported_models()
    source = next(model for model in supported if model.model == "x")
    TextEmbedding.add_custom_model(
        model="alias",
        sources=source.sources,
        dim=source.dim,
        model_file=source.model_file,
        size_in_gb=source.size_in_GB,
    )
""",
        "fichero-server/src/fichero_server/db_embeddings.py",
    )

    assert offenders == []


def test_main_returns_nonzero_and_prints_offender_location(monkeypatch, capsys, tmp_path):
    rel_path = "fichero-server/src/fichero_server/db_embeddings.py"
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from fastembed import TextEmbedding

def register():
    supported = TextEmbedding.list_supported_models()
    source = next(iter(supported))
    TextEmbedding.add_custom_model(model="alias", sources=source["sources"])
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_ai_model_metadata, "ROOT", tmp_path)
    monkeypatch.setattr(check_ai_model_metadata, "TARGET_FILES", (rel_path,))
    monkeypatch.setattr(check_ai_model_metadata, "ALLOWLIST", {})
    monkeypatch.setattr(
        check_ai_model_metadata.sys,
        "argv",
        ["check_ai_model_metadata.py"],
    )

    assert check_ai_model_metadata.main() == 1
    output = capsys.readouterr().out
    assert "AI model metadata guardrail" in output
    assert "fichero-server/src/fichero_server/db_embeddings.py:5" in output


def test_main_returns_zero_when_current_code_is_clean(monkeypatch):
    monkeypatch.setattr(check_ai_model_metadata, "scan", lambda: [])
    monkeypatch.setattr(check_ai_model_metadata, "ALLOWLIST", {})
    monkeypatch.setattr(
        check_ai_model_metadata.sys,
        "argv",
        ["check_ai_model_metadata.py"],
    )

    assert check_ai_model_metadata.main() == 0
