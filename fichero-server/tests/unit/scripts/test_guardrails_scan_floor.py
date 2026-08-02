"""#4487: a floored guardrail FAILS (rc=2) when its scan resolves nothing.

Companion to test_guardrails_fail_on_missing_input.py, one level up: that
module proves checks fail when their roots are MISSING; this proves the
floored checks fail when the roots are PRESENT BUT EMPTY — the state that is
otherwise indistinguishable from a clean tree. A floor never observed to
fire is the same defect one level up, so every check converted under #4487
gets a row here.

METHOD: copy the check + _check_floor.py into a repo-shaped tmp tree whose
scan roots exist but hold nothing (plus a minimal near-empty OpenAPI where
the check reads one), run it, assert exit code 2 — BLIND, never 1 (violation)
and never 0 (clean).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"

_EMPTY_OPENAPI = json.dumps(
    {"openapi": "3.1.0", "info": {"title": "t", "version": "0"}, "paths": {}}
)

# Every check converted under #4487, with the empty-but-present scaffolding
# its scan expects. Growing Phase 1/2 = adding rows here.
FLOORED_CHECKS: dict[str, dict] = {
    "check_emit_change_coverage.py": {
        "dirs": [
            "fichero-server/src/fichero_server/api/routes",
            "fichero/fichero/Models",
        ],
        "files": {},
        "extra_scripts": [],
    },
    "check_undo_coverage.py": {
        "dirs": ["fichero/fichero"],
        # An OpenAPI spec with zero paths: rows == 0, far below the floor.
        "files": {
            "fichero-server/tests/contracts/openapi.json": json.dumps(
                {"openapi": "3.1.0", "info": {"title": "t", "version": "0"}, "paths": {}}
            ),
            "docs/contributor/api-reference/openapi.json": json.dumps(
                {"openapi": "3.1.0", "info": {"title": "t", "version": "0"}, "paths": {}}
            ),
        },
        "extra_scripts": ["check_undo_coverage_known_gaps.json", "matrix_guardrail_common.py"],
    },
    "check_ui_wiring.py": {
        "dirs": ["fichero/fichero", "fichero-cli/src"],
        "files": {
            "fichero-server/tests/contracts/openapi.json": json.dumps(
                {"openapi": "3.1.0", "info": {"title": "t", "version": "0"}, "paths": {}}
            ),
            "docs/contributor/api-reference/openapi.json": json.dumps(
                {"openapi": "3.1.0", "info": {"title": "t", "version": "0"}, "paths": {}}
            ),
        },
        "extra_scripts": [],
    },
    "check_endpoint_coverage_matrix.py": {
        "dirs": [
            "fichero/fichero/Services",
            "fichero/fichero/Models",
            "fichero-cli/src/fichero_cli",
        ],
        "files": {
            "fichero-server/tests/contracts/openapi.json": _EMPTY_OPENAPI,
            "docs/contributor/api-reference/openapi.json": _EMPTY_OPENAPI,
        },
        "extra_scripts": [
            "matrix_guardrail_common.py",
            "check_endpoint_coverage_matrix_known_gaps.json",
        ],
    },
    "check_action_surface_matrix.py": {
        "dirs": ["fichero/fichero/Views", "fichero/fichero/App/Menus"],
        "files": {
            "fichero/fichero/FicheroApp.swift": "",
            "fichero/fichero/App/Menus/FocusedCommandButtons.swift": "",
        },
        "extra_scripts": [
            "matrix_guardrail_common.py",
            "check_action_surface_matrix_known_gaps.json",
        ],
    },
    "check_appkit_imports.py": {
        "dirs": ["fichero/fichero"],
        "files": {},
        "extra_scripts": [],
    },
    "check_dead_files.py": {
        "dirs": ["fichero/fichero"],
        "files": {},
        "extra_scripts": [],
    },
    "check_view_endpoint_access.py": {
        "dirs": ["fichero/fichero/Views"],
        "files": {},
        "extra_scripts": [],
    },
    "check_test_assertions.py": {
        "dirs": [
            "fichero/fichero",
            "fichero-server/tests",
            "fichero/fichero-cli",
        ],
        "files": {},
        "extra_scripts": [],
    },
    "check_artifact_type_contract.py": {
        "dirs": [
            "fichero-server/src/fichero_server",
            "fichero/fichero",
        ],
        "files": {},
        "extra_scripts": [],
    },
    "check_change_event_contract.py": {
        "dirs": ["fichero-server/src/fichero_server/api", "fichero/fichero/Services"],
        "files": {
            "fichero-server/src/fichero_server/api/change_stream.py": "",
            "fichero/fichero/Services/LibraryChangeStream.swift": "",
        },
        "extra_scripts": [],
    },
    "check_naive_datetimes.py": {
        "dirs": [
            "fichero-server/src/fichero_server",
            "fichero-cli/src",
            "fichero-mcp/src",
        ],
        "files": {},
        "extra_scripts": [],
    },
    "check_silent_write_swallow.py": {
        "dirs": ["fichero-server/src/fichero_server"],
        "files": {},
        "extra_scripts": [],
    },
    "check_swift_transport.py": {
        "dirs": ["fichero/fichero"],
        "files": {},
        "extra_scripts": [],
    },
    "check_tcp_transport_wrapper.py": {
        "dirs": [
            "fichero-server/src/fichero_server",
            "fichero-server/scripts",
            "scripts",
            "fichero/fichero",
        ],
        "files": {},
        "extra_scripts": [],
    },
    "check_no_raw_urlsession.py": {
        "dirs": ["fichero/fichero-api-client/Sources"],
        "files": {},
        "extra_scripts": [],
    },
    "check_no_raw_urlsession_app.py": {
        "dirs": ["fichero/fichero"],
        "files": {},
        "extra_scripts": [],
    },
    "check_no_hardcoded_engine_base.py": {
        "dirs": ["fichero/fichero"],
        "files": {},
        "extra_scripts": [],
    },
    "check_observer_pattern.py": {
        "dirs": ["fichero/fichero/Views"],
        "files": {},
        "extra_scripts": [],
    },
    "check_openapi_typed_fields.py": {
        "dirs": ["fichero/fichero/Services"],
        "files": {
            "fichero-server/tests/contracts/openapi.json": _EMPTY_OPENAPI,
            "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json": _EMPTY_OPENAPI,
        },
        "extra_scripts": [],
    },
    "check_openapi_shadow_types.py": {
        "dirs": ["fichero/fichero"],
        "files": {"fichero-server/tests/contracts/openapi.json": _EMPTY_OPENAPI},
        "extra_scripts": [],
    },
    "check_generated_wrapper_drift.py": {
        "dirs": ["fichero/fichero/Services"],
        "files": {
            "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json": _EMPTY_OPENAPI,
        },
        "extra_scripts": [],
    },
    "check_service_consistency.py": {
        "dirs": ["fichero/fichero/Services"],
        "files": {},
        "extra_scripts": [],
    },
    "check_canonical_renderers.py": {
        "dirs": ["fichero/fichero/Views"],
        "files": {},
        "extra_scripts": [],
    },
    "check_xcode_registration.py": {
        "dirs": ["fichero/fichero"],
        "files": {"fichero/fichero.xcodeproj/project.pbxproj": ""},
        "extra_scripts": [],
    },
    "check_mainactor_view_statics.py": {
        "dirs": ["fichero/fichero", "fichero/fichero-tests"],
        "files": {},
        "extra_scripts": [],
    },
    "check_feature_flags.py": {
        "dirs": ["fichero/fichero/Models"],
        "files": {},
        "extra_scripts": [],
    },
    "check_localization.py": {
        "dirs": ["fichero/fichero"], "files": {}, "extra_scripts": [],
    },
    "check_model_download_location.py": {
        "dirs": ["fichero-server/src/fichero_server"], "files": {}, "extra_scripts": [],
    },
    "check_no_emoji_sf_symbols.py": {
        "dirs": ["fichero/fichero"], "files": {}, "extra_scripts": [],
    },
    "check_python_comment_hygiene.py": {
        "dirs": ["fichero-server/src/fichero_server"], "files": {}, "extra_scripts": [],
    },
    "check_swift_hand_rolled_urls.py": {
        "dirs": ["fichero/fichero"], "files": {}, "extra_scripts": [],
    },
    "check_test_userdefaults_isolation.py": {
        "dirs": ["fichero/fichero-tests", "fichero/fichero-ui-tests"],
        "files": {}, "extra_scripts": [],
    },
    "check_tooltips.py": {
        "dirs": ["fichero/fichero/Views"], "files": {}, "extra_scripts": [],
    },
    "check_shell_chrome.py": {
        "dirs": ["fichero/fichero/Views"], "files": {}, "extra_scripts": [],
    },
    "check_appsource_paths.py": {
        "dirs": ["fichero/fichero-tests", "fichero/fichero-ui-tests", "fichero/fichero"],
        "files": {}, "extra_scripts": [],
    },
    "check_folder_organization.py": {
        "dirs": ["fichero/fichero"], "files": {}, "extra_scripts": [],
    },
    "check_app_intent_action_coverage.py": {
        "dirs": ["fichero-server/src/fichero_server", "fichero/fichero"],
        "files": {}, "extra_scripts": [],
    },
    "check_docs_paths.py": {
        "dirs": ["docs"], "files": {}, "extra_scripts": [],
    },
    "check_applescript_coverage.py": {
        "dirs": ["fichero/fichero"],
        "files": {
            "fichero/fichero/Fichero.sdef": "<dictionary></dictionary>",
        },
        "extra_scripts": [],
    },
    "check_import_render_completeness.py": {
        "dirs": ["fichero-server/src/fichero_server/models", "fichero/fichero/Services"],
        "files": {
            "fichero-server/src/fichero_server/models/__init__.py": "",
            "fichero/fichero/Services/DocumentService.swift": "",
        },
        "extra_scripts": [],
    },
    "check_docs_publication.py": {
        "dirs": ["docs"],
        "files": {"mkdocs.yml": "site_name: t\nnav: []\n"},
        "extra_scripts": ["check_docs_publication_allowlist.json"],
    },
    "check_sidebar_items.py": {
        "dirs": ["fichero/fichero/Views/Shell/ContentView"],
        "files": {
            "fichero/fichero/Views/Shell/ContentView/ContentView+Navigation.swift": "",
        },
        "extra_scripts": [],
    },
    "check_endpoint_usage.py": {
        "dirs": [
            "fichero/fichero/Services",
            "fichero/fichero/Models",
            "fichero-cli/src/fichero_cli",
        ],
        "files": {
            "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json": _EMPTY_OPENAPI,
        },
        "extra_scripts": [],
    },
}


def _materialize(tmp_path: Path, name: str, spec: dict) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(SCRIPTS_DIR / name, scripts / name)
    shutil.copy2(SCRIPTS_DIR / "_check_floor.py", scripts / "_check_floor.py")
    for extra in spec["extra_scripts"]:
        src = SCRIPTS_DIR / extra
        if src.exists():
            shutil.copy2(src, scripts / extra)
    for d in spec["dirs"]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    for rel, content in spec["files"].items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return scripts / name


def test_the_floored_inventory_is_not_empty():
    """Guard the guard: this sweep is the proof the floors can fire."""
    assert len(FLOORED_CHECKS) >= 44


@pytest.mark.parametrize("name", sorted(FLOORED_CHECKS))
def test_floored_check_exits_blind_on_an_empty_tree(name, tmp_path):
    script = _materialize(tmp_path, name, FLOORED_CHECKS[name])
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
    )
    assert proc.returncode == 2, (
        f"{name} scanned an EMPTY tree and exited {proc.returncode} — "
        f"'found nothing' and 'looked at nothing' produced the same verdict.\n"
        f"stdout: {proc.stdout[-400:]}\nstderr: {proc.stderr[-400:]}"
    )
    assert "BLIND" in proc.stderr, "the refusal must say it is blindness, not a violation"
