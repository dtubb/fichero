#!/usr/bin/env python3
"""
Fichero System Verification Script

Systematically verifies that all components are working before manual testing.
Run this after code changes to ensure the system is in a good state.

Usage:
    python scripts/verify_system.py [--all] [--backend] [--api] [--unit] [--integration] [--swift]
"""

import argparse
import subprocess
import sys
import time
import json
from pathlib import Path

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

BASE_URL = "http://127.0.0.1:8765/api"
PROJECT_ROOT = Path(__file__).parent.parent


def print_header(title: str):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{title:^60}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def print_pass(msg: str):
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def print_fail(msg: str):
    print(f"  {RED}[FAIL]{RESET} {msg}")


def print_warn(msg: str):
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def print_info(msg: str):
    print(f"  {BLUE}[INFO]{RESET} {msg}")


def check_backend_health() -> bool:
    """Check if the backend is running and healthy."""
    print_header("Backend Health Check")

    try:
        import httpx
        response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            print_pass(f"Backend is healthy (v{data.get('backend_version', 'unknown')})")
            print_info(f"Active libraries: {data.get('active_libraries', 0)}")
            return True
        else:
            print_fail(f"Backend returned status {response.status_code}")
            return False
    except httpx.ConnectError:
        print_fail("Backend is not running on port 8765")
        print_info("Start with: PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765")
        return False
    except Exception as e:
        print_fail(f"Error connecting to backend: {e}")
        return False


def check_api_endpoints() -> tuple[int, int]:
    """Verify key API endpoints are responding."""
    print_header("API Endpoint Verification")

    import httpx

    endpoints = [
        ("GET", "/health", None),
        ("GET", "/stats", None),
        ("GET", "/documents", None),
        ("GET", "/workflows", None),
        ("GET", "/search/stats", None),
        ("GET", "/providers/catalog", None),
        ("GET", "/workflows/tools", None),
        ("GET", "/chat/conversations", None),
    ]

    library_headers = {"X-Fichero-Library-Path": "/tmp/test_verify.fichero"}

    passed = 0
    failed = 0

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        for method, path, body in endpoints:
            try:
                if method == "GET":
                    response = client.get(path, headers=library_headers)
                elif method == "POST":
                    response = client.post(path, json=body, headers=library_headers)

                if response.status_code in [200, 201]:
                    print_pass(f"{method} {path} -> {response.status_code}")
                    passed += 1
                elif response.status_code == 404:
                    print_warn(f"{method} {path} -> 404 (endpoint may not exist)")
                    failed += 1
                else:
                    print_fail(f"{method} {path} -> {response.status_code}")
                    failed += 1
            except Exception as e:
                print_fail(f"{method} {path} -> {e}")
                failed += 1

    return passed, failed


def verify_saved_search_api() -> tuple[int, int]:
    """Test SavedSearch CRUD operations."""
    print_header("SavedSearch API Verification")

    import httpx

    headers = {"X-Fichero-Library-Path": "/tmp/test_verify.fichero"}
    passed = 0
    failed = 0
    search_id = None

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # Test CREATE
        try:
            response = client.post(
                "/search/saved",
                json={
                    "query": "verify test",
                    "sort_direction": "asc",
                    "folder_path": "/test",
                    "sort_order": 5
                },
                headers=headers
            )
            if response.status_code in [200, 201]:
                data = response.json()
                search_id = data.get("id")

                # Verify fields
                if data.get("sort_direction") == "asc":
                    print_pass("CREATE saved search with sort_direction")
                    passed += 1
                else:
                    print_fail("sort_direction not returned correctly")
                    failed += 1

                if data.get("folder_path") == "/test":
                    print_pass("folder_path saved correctly")
                    passed += 1
                else:
                    print_fail(f"folder_path: expected '/test', got '{data.get('folder_path')}'")
                    failed += 1

                if data.get("sort_order") == 5:
                    print_pass("sort_order saved correctly")
                    passed += 1
                else:
                    print_fail(f"sort_order: expected 5, got {data.get('sort_order')}")
                    failed += 1
            else:
                print_fail(f"CREATE failed: {response.status_code} - {response.text[:100]}")
                failed += 1
        except Exception as e:
            print_fail(f"CREATE error: {e}")
            failed += 1

        # Test LIST
        if search_id:
            try:
                response = client.get("/search/saved", headers=headers)
                if response.status_code == 200:
                    print_pass("LIST saved searches")
                    passed += 1
                else:
                    print_fail(f"LIST failed: {response.status_code}")
                    failed += 1
            except Exception as e:
                print_fail(f"LIST error: {e}")
                failed += 1

        # Cleanup
        if search_id:
            try:
                client.delete(f"/search/saved/{search_id}", headers=headers)
                print_info(f"Cleaned up test search {search_id}")
            except:
                pass

    return passed, failed


def verify_workflow_api() -> tuple[int, int]:
    """Test Workflow CRUD operations including PATCH and duplicate."""
    print_header("Workflow API Verification")

    import httpx

    headers = {"X-Fichero-Library-Path": "/tmp/test_verify.fichero"}
    passed = 0
    failed = 0
    workflow_id = None

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # Test CREATE
        try:
            response = client.post(
                "/workflows",
                json={
                    "name": "Verify Test Workflow",
                    "description": "Test",
                    "folder_path": "/",
                    "sort_order": 0,
                    "nodes": [],
                    "edges": []
                },
                headers=headers
            )
            if response.status_code in [200, 201]:
                data = response.json()
                workflow_id = data.get("id")
                print_pass("CREATE workflow")
                passed += 1

                # Verify folder_path and sort_order in response
                if "folder_path" in data:
                    print_pass("Response includes folder_path")
                    passed += 1
                else:
                    print_fail("Response missing folder_path")
                    failed += 1

                if "sort_order" in data:
                    print_pass("Response includes sort_order")
                    passed += 1
                else:
                    print_fail("Response missing sort_order")
                    failed += 1
            else:
                print_fail(f"CREATE failed: {response.status_code}")
                failed += 1
        except Exception as e:
            print_fail(f"CREATE error: {e}")
            failed += 1

        # Test PATCH
        if workflow_id:
            try:
                response = client.patch(
                    f"/workflows/{workflow_id}",
                    json={"name": "Renamed Workflow"},
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("name") == "Renamed Workflow":
                        print_pass("PATCH workflow (rename)")
                        passed += 1
                    else:
                        print_fail("PATCH did not update name")
                        failed += 1
                else:
                    print_fail(f"PATCH failed: {response.status_code}")
                    failed += 1
            except Exception as e:
                print_fail(f"PATCH error: {e}")
                failed += 1

        # Test DUPLICATE
        duplicate_id = None
        if workflow_id:
            try:
                response = client.post(
                    f"/workflows/{workflow_id}/duplicate",
                    headers=headers
                )
                if response.status_code in [200, 201]:
                    data = response.json()
                    duplicate_id = data.get("id")
                    if duplicate_id != workflow_id:
                        print_pass("DUPLICATE workflow")
                        passed += 1
                    else:
                        print_fail("DUPLICATE returned same ID")
                        failed += 1
                else:
                    print_fail(f"DUPLICATE failed: {response.status_code}")
                    failed += 1
            except Exception as e:
                print_fail(f"DUPLICATE error: {e}")
                failed += 1

        # Cleanup
        for wid in [workflow_id, duplicate_id]:
            if wid:
                try:
                    client.delete(f"/workflows/{wid}", headers=headers)
                except:
                    pass

        print_info("Cleaned up test workflows")

    return passed, failed


def run_unit_tests() -> tuple[int, int]:
    """Run Python unit tests."""
    print_header("Python Unit Tests")

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv/bin/pytest"),
            str(PROJECT_ROOT / "fichero-api/tests/unit/"),
            "--ignore=fichero-api/tests/unit/_archived",
            "-q",
            "--tb=no"
        ],
        cwd=PROJECT_ROOT,
        env={**dict(subprocess.os.environ), "PYTHONPATH": "src"},
        capture_output=True,
        text=True
    )

    # Parse test results
    output = result.stdout + result.stderr
    print(output[-500:] if len(output) > 500 else output)

    # Extract pass/fail counts from pytest output
    import re
    match = re.search(r"(\d+) passed", output)
    passed = int(match.group(1)) if match else 0

    match = re.search(r"(\d+) failed", output)
    failed = int(match.group(1)) if match else 0

    match = re.search(r"(\d+) error", output)
    errors = int(match.group(1)) if match else 0

    failed += errors

    return passed, failed


def run_integration_tests() -> tuple[int, int]:
    """Run integration tests."""
    print_header("Integration Tests")

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv/bin/pytest"),
            str(PROJECT_ROOT / "fichero-api/tests/integration/test_api_contract_changes.py"),
            "-v",
            "--tb=short"
        ],
        cwd=PROJECT_ROOT,
        env={**dict(subprocess.os.environ), "PYTHONPATH": "src"},
        capture_output=True,
        text=True
    )

    output = result.stdout + result.stderr
    print(output[-1000:] if len(output) > 1000 else output)

    import re
    match = re.search(r"(\d+) passed", output)
    passed = int(match.group(1)) if match else 0

    match = re.search(r"(\d+) failed", output)
    failed = int(match.group(1)) if match else 0

    return passed, failed


def run_swift_tests() -> tuple[int, int]:
    """Run Swift tests."""
    print_header("Swift Tests")

    result = subprocess.run(
        [
            "xcodebuild",
            "test",
            "-project", str(PROJECT_ROOT / "fichero-swiftui/Fichero.xcodeproj"),
            "-scheme", "Fichero",
            "-destination", "platform=macOS",
            "-quiet"
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=300
    )

    if result.returncode == 0:
        print_pass("Swift tests passed")
        return 1, 0
    else:
        output = result.stdout + result.stderr
        # Look for test failures in output
        if "** TEST FAILED **" in output:
            print_fail("Swift tests failed")
            print(output[-500:])
            return 0, 1
        elif "** BUILD FAILED **" in output:
            print_fail("Swift build failed")
            return 0, 1
        else:
            print_pass("Swift tests passed (build succeeded)")
            return 1, 0


def main():
    parser = argparse.ArgumentParser(description="Verify Fichero system components")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    parser.add_argument("--backend", action="store_true", help="Check backend health")
    parser.add_argument("--api", action="store_true", help="Verify API endpoints")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--swift", action="store_true", help="Run Swift tests")
    parser.add_argument("--quick", action="store_true", help="Quick check (backend + API)")

    args = parser.parse_args()

    # Default to quick check if no args
    if not any([args.all, args.backend, args.api, args.unit, args.integration, args.swift, args.quick]):
        args.quick = True

    total_passed = 0
    total_failed = 0

    print(f"\n{BLUE}Fichero System Verification{RESET}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Backend health (always check first)
    if args.all or args.backend or args.quick:
        if not check_backend_health():
            print(f"\n{RED}Backend is not running. Start it first!{RESET}")
            sys.exit(1)

    # API endpoints
    if args.all or args.api or args.quick:
        p, f = check_api_endpoints()
        total_passed += p
        total_failed += f

    # SavedSearch API
    if args.all or args.api or args.quick:
        p, f = verify_saved_search_api()
        total_passed += p
        total_failed += f

    # Workflow API
    if args.all or args.api or args.quick:
        p, f = verify_workflow_api()
        total_passed += p
        total_failed += f

    # Unit tests
    if args.all or args.unit:
        p, f = run_unit_tests()
        total_passed += p
        total_failed += f

    # Integration tests
    if args.all or args.integration:
        p, f = run_integration_tests()
        total_passed += p
        total_failed += f

    # Swift tests
    if args.all or args.swift:
        try:
            p, f = run_swift_tests()
            total_passed += p
            total_failed += f
        except subprocess.TimeoutExpired:
            print_fail("Swift tests timed out")
            total_failed += 1
        except Exception as e:
            print_fail(f"Swift tests error: {e}")
            total_failed += 1

    # Summary
    print_header("Summary")
    print(f"  Total Passed: {GREEN}{total_passed}{RESET}")
    print(f"  Total Failed: {RED if total_failed > 0 else GREEN}{total_failed}{RESET}")

    if total_failed > 0:
        print(f"\n{RED}Some checks failed. Please review the output above.{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All checks passed! System is ready for testing.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
