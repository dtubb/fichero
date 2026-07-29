"""Unit tests for scripts/check_import_render_completeness.py (#2270)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_import_render_completeness.py"
)
_SPEC = importlib.util.spec_from_file_location("check_import_render_completeness", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

violations = _mod.violations
_py = _mod._python_enum_cases
_handled = _mod._swift_handled_cases

_PY = """
class FileType(str, Enum):
    image = "image"
    pdf = "pdf"
    docx = "docx"
    weird = "weird"
"""

# Decoder folds docx -> word (covered) but does NOT handle `weird`.
_DECODER = """
class DocumentServiceGenerated {
    private func convertFromGeneratedFileType(_ fileType: Components.Schemas.FileType?) -> FileType? {
        guard let fileType = fileType else { return nil }
        switch fileType {
        case .image: return .image
        case .pdf: return .pdf
        case .docx: return .word  // folded onto word, still renders
        }
    }
}
"""


def test_parses_python_cases():
    assert _py(_PY, "FileType") == {"image", "pdf", "docx", "weird"}


def test_parses_handled_decoder_cases():
    assert _handled(_DECODER, "convertFromGeneratedFileType") == {"image", "pdf", "docx"}


def test_folded_type_is_not_a_violation(tmp_path):
    py = tmp_path / "models.py"
    py.write_text(_PY)
    dec = tmp_path / "DocumentServiceGenerated.swift"
    dec.write_text(_DECODER)
    bad = violations(py_models=py, decoder=dec)
    # docx folds onto word -> covered; weird is genuinely unhandled.
    assert "FileType.docx" not in bad
    assert "FileType.weird" in bad


def test_real_tree_clean():
    # The shipped decoder handles every importable type (docx folds to word).
    assert not violations(), "every importable type must be handled by the decoder"
