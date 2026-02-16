#!/usr/bin/env python3
"""
Scan Swift source files for API calls and validate against Python endpoints.

This script finds existing bugs where Swift calls the wrong endpoint.

Usage:
    python scripts/validate_swift_api_calls.py

Output:
    - List of all API calls found in Swift code
    - Mismatches between Swift calls and Python endpoints
    - Potential issues (wrong method, wrong path, etc.)
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class SwiftAPICall:
    """Represents an API call found in Swift code."""
    file: str
    line: int
    method: str  # get, post, put, delete
    path: str    # The endpoint path (may contain interpolation)
    raw_line: str


@dataclass
class PythonEndpoint:
    """Represents an endpoint from Python API."""
    method: str
    path: str
    path_pattern: str  # Regex pattern for matching


def scan_swift_files(swift_dir: Path) -> list[SwiftAPICall]:
    """Scan Swift files for API calls."""
    calls = []

    # Pattern to match apiClient.get/post/put/delete calls
    # Matches: apiClient.get("/path"), apiClient.post("/path", body: ...)
    pattern = re.compile(
        r'apiClient\.(get|post|put|delete)\s*\(\s*"([^"]+)"',
        re.IGNORECASE
    )

    for swift_file in swift_dir.rglob("*.swift"):
        if "Tests" in str(swift_file):
            continue  # Skip test files

        try:
            content = swift_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                for match in pattern.finditer(line):
                    method = match.group(1).upper()
                    path = match.group(2)

                    # Clean up path - remove /api prefix if present
                    if path.startswith("/api"):
                        path = path[4:]

                    # Handle string interpolation like \(id)
                    # Convert to {param} format for comparison
                    path_normalized = re.sub(r'\\\([^)]+\)', '{param}', path)

                    calls.append(SwiftAPICall(
                        file=str(swift_file.relative_to(swift_dir)),
                        line=i,
                        method=method,
                        path=path_normalized,
                        raw_line=line.strip()
                    ))
        except Exception as e:
            print(f"Error reading {swift_file}: {e}")

    return calls


def load_python_endpoints(contracts_dir: Path) -> list[PythonEndpoint]:
    """Load endpoints from Python's exported endpoints.json."""
    endpoints_file = contracts_dir / "endpoints.json"

    if not endpoints_file.exists():
        print(f"Error: {endpoints_file} not found. Run: python scripts/export_openapi_schema.py")
        return []

    with open(endpoints_file) as f:
        data = json.load(f)

    endpoints = []
    for resource, eps in data.get("endpoints", {}).items():
        for ep in eps:
            path = ep["path"]
            method = ep["method"]

            # Create regex pattern for path (replace {param} with wildcard)
            pattern = re.sub(r'\{[^}]+\}', r'\\{param\\}', path)
            pattern = f"^{pattern}$"

            endpoints.append(PythonEndpoint(
                method=method,
                path=path,
                path_pattern=pattern
            ))

    return endpoints


def normalize_path(path: str) -> str:
    """Normalize path for comparison."""
    # Remove query strings
    path = path.split("?")[0]
    # Remove trailing slashes
    path = path.rstrip("/")
    # Normalize parameter placeholders
    path = re.sub(r'\{[^}]+\}', '{param}', path)
    path = re.sub(r'\\\([^)]+\)', '{param}', path)
    return path


def find_matching_endpoint(call: SwiftAPICall, endpoints: list[PythonEndpoint]) -> Optional[PythonEndpoint]:
    """Find the Python endpoint that matches this Swift call."""
    call_path = normalize_path(call.path)

    for ep in endpoints:
        ep_path = normalize_path(ep.path)

        # Try exact match first
        if call_path == ep_path:
            return ep

        # Try pattern match
        pattern = ep_path.replace("{param}", "[^/]+")
        if re.match(f"^{pattern}$", call_path):
            return ep

    return None


def validate_calls(calls: list[SwiftAPICall], endpoints: list[PythonEndpoint]) -> dict:
    """Validate Swift API calls against Python endpoints."""
    results = {
        "valid": [],
        "method_mismatch": [],
        "path_not_found": [],
        "suspicious": [],
    }

    for call in calls:
        matching = find_matching_endpoint(call, endpoints)

        if matching is None:
            results["path_not_found"].append({
                "call": call,
                "issue": f"No Python endpoint found for {call.path}"
            })
        elif matching.method != call.method:
            results["method_mismatch"].append({
                "call": call,
                "expected_method": matching.method,
                "issue": f"Swift uses {call.method} but Python expects {matching.method}"
            })
        else:
            results["valid"].append(call)

    return results


def main():
    # Paths
    repo_root = Path(__file__).parent.parent
    swift_dir = repo_root / "Fichero" / "Fichero"
    contracts_dir = repo_root / "tests" / "contracts"

    print("=" * 60)
    print("Swift API Call Validator")
    print("=" * 60)

    # Scan Swift files
    print("\n📂 Scanning Swift files...")
    calls = scan_swift_files(swift_dir)
    print(f"   Found {len(calls)} API calls in Swift code")

    # Load Python endpoints
    print("\n📂 Loading Python endpoints...")
    endpoints = load_python_endpoints(contracts_dir)
    print(f"   Found {len(endpoints)} endpoints in Python API")

    # Validate
    print("\n🔍 Validating...")
    results = validate_calls(calls, endpoints)

    # Report
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(f"\n✅ Valid calls: {len(results['valid'])}")

    if results["method_mismatch"]:
        print(f"\n❌ METHOD MISMATCHES: {len(results['method_mismatch'])}")
        for item in results["method_mismatch"]:
            call = item["call"]
            print(f"   {call.file}:{call.line}")
            print(f"      Swift: {call.method} {call.path}")
            print(f"      Python expects: {item['expected_method']}")
            print(f"      Line: {call.raw_line[:80]}...")

    if results["path_not_found"]:
        print(f"\n⚠️  PATHS NOT FOUND IN PYTHON: {len(results['path_not_found'])}")
        for item in results["path_not_found"][:10]:  # Limit output
            call = item["call"]
            print(f"   {call.file}:{call.line}")
            print(f"      {call.method} {call.path}")

        if len(results["path_not_found"]) > 10:
            print(f"   ... and {len(results['path_not_found']) - 10} more")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_issues = len(results["method_mismatch"]) + len(results["path_not_found"])
    if total_issues == 0:
        print("✅ All Swift API calls match Python endpoints!")
    else:
        print(f"⚠️  Found {total_issues} potential issues to review")

    # Return exit code
    return 1 if results["method_mismatch"] else 0


if __name__ == "__main__":
    exit(main())
