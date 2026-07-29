from pathlib import Path

from fichero_server.verification_targets import plan_backend_verification


ROOT = Path(__file__).resolve().parents[4]


def test_route_change_maps_to_targeted_tests_only() -> None:
    plan = plan_backend_verification(
        ["fichero-server/src/fichero_server/api/routes/mcp_tools.py"],
        repo_root=ROOT,
    )

    assert plan.requires_full_gate is False
    assert "fichero-server/tests/unit/api/test_routes_mcp_tools.py" in plan.pytest_targets
    assert "fichero-server/tests/unit/api/test_mcp_tools.py" in plan.pytest_targets
    assert "fichero-server/tests/unit/api/test_mcp_knowledge_adapters.py" in plan.pytest_targets
    assert plan.unmatched_paths == ()


def test_god_node_change_requires_full_gate() -> None:
    plan = plan_backend_verification(
        ["fichero-server/src/fichero_server/db.py"],
        repo_root=ROOT,
    )

    assert plan.requires_full_gate is True
    assert "database god-node changed" in plan.reasons
    assert "fichero-server/tests/unit/db/test_db.py" in plan.pytest_targets


def test_contract_change_requires_full_gate_and_includes_changed_test() -> None:
    plan = plan_backend_verification(
        ["fichero-server/tests/contracts/test_extensibility_guarantee.py"],
        repo_root=ROOT,
    )

    assert plan.requires_full_gate is True
    assert "contract or integration surface changed" in plan.reasons
    assert plan.pytest_targets == (
        "fichero-server/tests/contracts/test_extensibility_guarantee.py",
    )


def test_security_sensitive_path_requires_full_gate() -> None:
    plan = plan_backend_verification(
        ["fichero-server/src/fichero_server/api/routes/auth_accounts.py"],
        repo_root=ROOT,
    )

    assert plan.requires_full_gate is True
    assert "security-sensitive backend path changed" in plan.reasons
    assert "fichero-server/tests/unit/security/test_auth_accounts.py" in plan.pytest_targets


def test_unmatched_source_is_reported() -> None:
    plan = plan_backend_verification(
        ["fichero-server/src/fichero_server/nonexistent_slice.py"],
        repo_root=ROOT,
    )

    assert plan.pytest_targets == ()
    assert plan.unmatched_paths == (
        "fichero-server/src/fichero_server/nonexistent_slice.py",
    )
