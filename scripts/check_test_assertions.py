#!/usr/bin/env python3
"""Heuristic vacuous-test guardrail for Python and Swift tests.

This is a ratcheting guard:
- scans current test files
- reports test functions that contain zero assertions
- tracks the current set in KNOWN_VACUOUS so the repo is green today

Usage:
    scripts/check_test_assertions.py
    scripts/check_test_assertions.py --list
    scripts/check_test_assertions.py --help

Exit codes:
    0  no new vacuous tests (and no stale KNOWN_VACUOUS entries)
    1  one or more vacuous tests are not in KNOWN_VACUOUS
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_TEST_ROOT = ROOT / "fichero-server" / "tests"
CLI_ROOT = ROOT / "fichero" / "fichero-cli"
SWIFT_ROOT = ROOT / "fichero" / "fichero"

# Seeded with current-tree vacuous tests.
KNOWN_VACUOUS = {
    # Allowlist-hygiene meta-tests: they assert via a shared helper
    # (_assert_allowlist_has_reasons / stale-check) which the AST detector
    # cannot trace into; the assertions are real (#2153).
    "fichero-server/tests/unit/test_security_guardrails.py::test_security_guardrail_allowlist_entries_have_reasons",
    "fichero-server/tests/unit/test_security_guardrails.py::test_security_guardrail_allowlists_are_not_stale",
    "fichero-server/tests/conftest.py::test_package",
    "fichero-server/tests/integration/test_action_library_integration.py::test_action_data",
    "fichero-server/tests/integration/test_api_contracts.py::TestAPIConventions::test_snake_case_query_params",
    "fichero-server/tests/integration/test_api_contracts.py::TestExportedSchemaMatchesLive::test_exported_endpoints_match_live",
    "fichero-server/tests/integration/test_api_contracts.py::TestOpenAPISchemaValidity::test_endpoints_have_operation_ids",
    "fichero-server/tests/integration/test_api_contracts.py::TestSwiftCompatibility::test_date_formats_documented",
    "fichero-server/tests/integration/test_api_contracts.py::TestSwiftCompatibility::test_response_models_are_serializable",
    "fichero-server/tests/integration/test_contract_endpoint_walk.py::test_no_envelope_get_endpoint_returns_500",
    "fichero-server/tests/integration/test_contract_endpoint_walk.py::test_no_new_bare_array_get_endpoint",
    "fichero-server/tests/unit/core/test_bookmarks.py::TestStopAccessing::test_no_error_for_nonexistent_file",
    "fichero-server/tests/unit/core/test_bookmarks.py::TestStopAccessing::test_no_error_for_regular_file",
    "fichero-server/tests/unit/test_change_stream.py::TestEmitChange::test_emit_change_never_raises",
    "fichero-server/tests/unit/test_db_access_guardrail.py::test_no_new_raw_db_access_outside_persistence_layer",
    "fichero-server/tests/unit/test_fuzzy_clean_rgba.py::test_fuzzy_clean_la_and_palette_modes",
    "fichero-server/tests/unit/mcp/test_integration_security.py::TestEnvironmentSecurity::test_api_key_required_in_production",
    "fichero-server/tests/unit/mcp/test_integration_security.py::TestLibraryPathSecurity::test_library_path_validates_allowed_locations",
    "fichero-server/tests/unit/mcp/test_integration_security.py::TestSecurityHeaders::test_security_headers_present",
    "fichero-server/tests/unit/test_knowledge_graph_security.py::TestEntityAccessControl::test_claim_linking_prevents_cross_library",
    "fichero-server/tests/unit/test_knowledge_graph_security.py::TestEntityAccessControl::test_entity_access_requires_ownership_check",
    "fichero-server/tests/unit/test_library_registry.py::TestLibraryAutoRegistration::test_create_library_auto_registers",
    "fichero-server/tests/unit/mcp/test_mcp_manager.py::TestMCPManager::test_remove_nonexistent_server",
    "fichero-server/tests/unit/test_model_profiles.py::test_enforce_allows_private_local_profile",
    "fichero-server/tests/unit/test_model_profiles.py::test_enforce_allows_standard_cloud_profile",
    "fichero-server/tests/unit/test_new_data_layer.py::test_db",
    "fichero-server/tests/unit/media/test_ocr_geometry_helpers.py::test_bbox_edge_epsilon_tolerance",
    "fichero-server/tests/unit/media/test_ocr_geometry_helpers.py::test_policy_allows_cloud_when_not_local_only",
    "fichero-server/tests/unit/media/test_ocr_geometry_helpers.py::test_policy_allows_local_providers",
    "fichero-server/tests/unit/test_path_security_roots.py::test_validate_clean_relative_path_is_trusted",
    "fichero-server/tests/unit/test_path_security_roots.py::test_validate_none_and_empty_are_noops",
    "fichero-server/tests/unit/test_path_security_roots.py::test_validate_relative_with_parent_ref_that_stays_inside",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateAPIBase::test_empty_url",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateAPIBase::test_valid_http_localhost",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateAPIBase::test_valid_https_url",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateAPIKeyFormat::test_anthropic_key_valid",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateAPIKeyFormat::test_openai_key_valid",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateProviderConfig::test_azure_with_valid_config",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateProviderConfig::test_local_provider_no_key_required",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateProviderConfig::test_omlx_accepts_arbitrary_local_key",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateProviderConfig::test_valid_anthropic_config",
    "fichero-server/tests/unit/test_provider_validation_errors.py::test_clean_key_still_passes",
    "fichero-server/tests/unit/test_provider_validation.py::TestValidateProviderConfig::test_valid_openai_config",
    "fichero-server/tests/unit/test_research_ssrf_security.py::TestSSRFResourceLimits::test_web_search_timeout_enforced",
    "fichero-server/tests/unit/test_storage.py::TestShutdown::test_shutdown_idempotent",
    "fichero-server/tests/unit/test_transcription_save.py::TestParseJsonFieldsNullMetadata::test_null_metadata_does_not_raise_validation_error",
    "fichero-server/tests/unit/test_vision_warning_activity.py::TestLogVisionWarning::test_no_tracker_does_not_raise",
    "fichero-server/tests/unit/test_vision_warning_activity.py::TestLogVisionWarning::test_tracker_import_failure_falls_back_gracefully",
    "fichero-server/tests/unit/test_vision_warning_activity.py::TestLogVisionWarning::test_tracker_log_exception_does_not_propagate",
    "fichero-server/tests/unit/test_workflow_executor.py::test_tool",
    "fichero-server/tests/unit/workflows/test_default_workflow_e2e_harness.py::test_catalogue_default_workflow_lands_artifacts_and_kg_rows",
    "fichero-server/tests/unit/workflows/test_default_workflow_e2e_harness.py::test_catalogue_twostage_workflow_lands_kg_rows",
    "fichero-server/tests/unit/workflows/test_ner_config_schema.py::test_extract_all_exposes_ner_provider_and_model",
    "fichero-server/tests/unit/workflows/test_ner_config_schema.py::test_section_extractors_expose_ner_provider_and_model",
    "fichero-server/tests/unit/test_backend_integration.py::TestIngestWithTextExtraction::test_ingest_file_skips_non_extractable",
    "fichero-server/tests/unit/importers/test_ingest_module.py::TestCopyToLibrary::test_falls_back_to_shutil",
    "fichero-server/tests/unit/importers/test_ingest_module.py::TestCopyToLibrary::test_uses_apfs_clone_when_available",
}

SWIFT_FUNC_RE = re.compile(r"^\s*(?:\w+\s+)*func\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\(")
SWIFT_TEST_ATTR_RE = re.compile(r"^\s*@\s*Test\b")
SWIFT_ASSERT_RE = re.compile(r"\b(?:XCTAssert\w*|XCTFail|assertSnapshot)\b|#(?:expect|require)\b")


@dataclass(frozen=True)
class TestEntry:
    key: str
    has_assertion: bool


def _swift_test_files(*, root: Path | None = None, swift_root: Path | None = None) -> list[Path]:
    base_root = root or ROOT
    tests_root = swift_root or base_root / "fichero" / "fichero"
    if not tests_root.exists():
        return []
    return sorted(tests_root.glob("**/*Tests/**/*.swift"))


def _python_test_files(
    *,
    root: Path | None = None,
    py_test_root: Path | None = None,
    cli_root: Path | None = None,
) -> list[Path]:
    base_root = root or ROOT
    tests_root = py_test_root or base_root / "fichero-server" / "tests"
    cli_tests_root = cli_root or base_root / "fichero" / "fichero-cli"
    tests = sorted(tests_root.rglob("*.py"))
    if not cli_tests_root.exists():
        return tests
    cli_tests = []
    for path in cli_tests_root.rglob("*"):
        if not path.is_dir():
            continue
        if path.name == "tests":
            cli_tests.extend(sorted(path.rglob("*.py")))
    for path in cli_tests:
        if path not in tests:
            tests.append(path)
    return sorted(tests)


def _py_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _python_asserts(function: ast.AST) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Assert):
            return True

        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name):
                if callee.id == "raises":
                    return True
            elif isinstance(callee, ast.Attribute):
                if isinstance(callee.value, ast.Name) and callee.value.id == "pytest" and callee.attr == "raises":
                    return True
                if isinstance(callee.value, ast.Name) and callee.value.id == "self" and callee.attr.startswith("assert"):
                    return True
                if callee.attr == "assert_called":
                    return True

        if isinstance(node, ast.With):
            for item in node.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call):
                    callee = expr.func
                    if isinstance(callee, ast.Name) and callee.id == "raises":
                        return True
                    if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name) and callee.value.id == "pytest" and callee.attr == "raises":
                        return True
    return False


def _relative_key(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _scan_python(*, root: Path | None = None, paths: list[Path] | None = None) -> list[TestEntry]:
    base_root = root or ROOT
    entries: list[TestEntry] = []
    for path in paths if paths is not None else _python_test_files(root=base_root):
        try:
            tree = ast.parse(_py_text(path))
        except (SyntaxError, OSError):
            continue

        rel = _relative_key(path, base_root)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                entries.append(TestEntry(f"{rel}::{node.name}", _python_asserts(node)))
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, ast.FunctionDef) and child.name.startswith("test_"):
                        entries.append(
                            TestEntry(f"{rel}::{node.name}::{child.name}", _python_asserts(child))
                        )
    return entries


def _strip_swift_comments(text: str) -> str:
    block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(re.sub(r"(?<!:)//.*", "", line) for line in block.splitlines())


def _scan_swift(*, root: Path | None = None, paths: list[Path] | None = None) -> list[TestEntry]:
    base_root = root or ROOT
    entries: list[TestEntry] = []
    for path in paths if paths is not None else _swift_test_files(root=base_root):
        rel = _relative_key(path, base_root)
        try:
            lines = _strip_swift_comments(path.read_text(encoding="utf-8", errors="ignore")).splitlines()
        except OSError:
            continue

        pending_test_attr = False
        in_test = False
        func_name = ""
        test_key = ""
        has_assertion = False
        depth = 0
        target_depth = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if SWIFT_TEST_ATTR_RE.match(stripped):
                pending_test_attr = True
                continue

            opens = stripped.count("{")
            closes = stripped.count("}")
            match = SWIFT_FUNC_RE.match(stripped)
            starts_with_test = False
            if match:
                starts_with_test = match.group("name").startswith("test")

            is_test = bool((match and (starts_with_test or pending_test_attr)) or (pending_test_attr and "func " in stripped and not starts_with_test))

            if is_test and match:
                if in_test and func_name:
                    entries.append(TestEntry(test_key, has_assertion))
                in_test = True
                func_name = match.group("name")
                test_key = f"{rel}::{func_name}"
                target_depth = depth + opens - closes
                has_assertion = bool(SWIFT_ASSERT_RE.search(stripped))
                pending_test_attr = False

                if opens == closes and "{" not in stripped:
                    entries.append(TestEntry(test_key, has_assertion))
                    in_test = False
                    func_name = ""
                    test_key = ""
                    has_assertion = False
                    target_depth = 0

            elif pending_test_attr and not stripped.startswith("@"):
                pending_test_attr = False

            if in_test and SWIFT_ASSERT_RE.search(stripped):
                has_assertion = True

            depth += opens - closes
            if in_test and depth < target_depth:
                entries.append(TestEntry(test_key, has_assertion))
                in_test = False
                func_name = ""
                test_key = ""
                has_assertion = False
                target_depth = 0

        if in_test and test_key:
            entries.append(TestEntry(test_key, has_assertion))

    return entries


def scan(
    *,
    root: Path | None = None,
    python_paths: list[Path] | None = None,
    swift_paths: list[Path] | None = None,
) -> list[TestEntry]:
    base_root = root or ROOT
    return _scan_python(root=base_root, paths=python_paths) + _scan_swift(
        root=base_root,
        paths=swift_paths,
    )


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    tests = scan()
    vacuous = [t for t in tests if not t.has_assertion]
    asserting = [t for t in tests if t.has_assertion]

    found = {t.key for t in vacuous}
    known = set(KNOWN_VACUOUS)

    if "--list" in sys.argv[1:]:
        print(f"test-assertions ({len(tests)} test function(s)): {len(vacuous)} vacuous, {len(asserting)} asserting\n")
        for test in sorted(vacuous, key=lambda t: t.key):
            tag = "known" if test.key in known else "NEW"
            print(f"  [{tag}] {test.key}")
        return 0

    new = sorted(found - known)
    stale = sorted(known - found)

    print(f"test-assertions: {len(known)} known vacuous, {len(asserting)} asserting tests")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VACUOUS entries are now clean; remove them:")
        for entry in stale:
            print(f"      {entry}")

    if new:
        print(f"\n  {len(new)} new vacuous tests:")
        for entry in new:
            print(f"      {entry}")
        print(
            "\nA vacuous test has no assertions and does not increase confidence in "
            "behavior. If intentional, add it to KNOWN_VACUOUS in "
            "scripts/check_test_assertions.py"
        )
        return 1

    if stale:
        print("\n(KNOWN_VACUOUS has stale entries; clean them up when convenient.)")

    print("\n✓ No vacuous-test regressions beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
