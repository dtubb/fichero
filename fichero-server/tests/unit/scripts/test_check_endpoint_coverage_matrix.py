from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_endpoint_coverage_matrix.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_endpoint_coverage_matrix", _SCRIPT)
assert _SPEC and _SPEC.loader
check_endpoint_coverage_matrix = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_endpoint_coverage_matrix
_SPEC.loader.exec_module(check_endpoint_coverage_matrix)  # type: ignore[attr-defined]


def test_generated_swift_operation_names_count_as_store_wiring():
    rows = {row.endpoint: row for row in check_endpoint_coverage_matrix.scan()}

    for endpoint in (
        "GET /api/libraries/{lib}/entity-types",
        "POST /api/libraries/{lib}/entity-types",
        "DELETE /api/libraries/{lib}/entity-types/{entity_type_key}",
        "GET /api/citation-usages",
    ):
        row = rows[endpoint]
        assert row.store is True
        assert row.cli is True
        assert row.gap is False


def test_witnesses_are_limited_to_the_repaired_store_methods():
    assert check_endpoint_coverage_matrix.SWIFT_OPERATION_WITNESSES == {
        "GET /api/citation-usages": "listCitationUsagesApiCitationUsagesGet",
        "GET /api/libraries/{lib}/entity-types": "listLibraryEntityTypesApiLibrariesLibEntityTypesGet",
        "POST /api/libraries/{lib}/entity-types": "addLibraryEntityTypeApiLibrariesLibEntityTypesPost",
        "DELETE /api/libraries/{lib}/entity-types/{entity_type_key}": (
            "removeLibraryEntityTypeApiLibrariesLibEntityTypesEntityTypeKeyDelete"
        ),
    }
