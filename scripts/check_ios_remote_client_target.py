#!/usr/bin/env python3
"""iOS remote-client target guardrail (#2099)."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "fichero" / "fichero.xcodeproj" / "project.pbxproj"
API_PACKAGE = ROOT / "fichero" / "fichero-api-client" / "Package.swift"
IOS_APP = ROOT / "fichero" / "fichero" / "FicheroApp_iOS.swift"
ENGINE_CONFIG = ROOT / "fichero" / "fichero" / "Services" / "EngineConfig.swift"
EMBEDDED_BACKEND = ROOT / "fichero" / "fichero" / "Services" / "EmbeddedBackendService.swift"


def collect_violations(root: Path = ROOT) -> list[str]:
    project = (root / PROJECT_FILE.relative_to(ROOT)).read_text(encoding="utf-8")
    package = (root / API_PACKAGE.relative_to(ROOT)).read_text(encoding="utf-8")
    ios_app = (root / IOS_APP.relative_to(ROOT)).read_text(encoding="utf-8")
    engine_config = (root / ENGINE_CONFIG.relative_to(ROOT)).read_text(encoding="utf-8")
    embedded_backend = (root / EMBEDDED_BACKEND.relative_to(ROOT)).read_text(encoding="utf-8")

    checks = {
        "FicheroApp_iOS.swift is registered in the app target": "FicheroApp_iOS.swift in Sources" in project,
        "app target supports iPhone/iPad simulator/device builds": (
            "iphoneos iphonesimulator" in project and 'TARGETED_DEVICE_FAMILY = "1,2' in project
        ),
        "shared OpenAPI client package supports iOS": ".iOS(" in package,
        "iOS app entry is platform-gated": "#if os(iOS)" in ios_app,
        # iOS without a configured host must route to the paired companion,
        # NEVER a local engine. #3109 centralized this in EngineConfig's
        # provisioning strategy (was a `guard EngineConfig.hasConfiguredHost`
        # in FicheroApp_iOS.swift, removed in the refactor); verify the strategy
        # itself so the guardrail tracks the real enforcement, not a moved detail.
        "iOS without a configured host routes to the companion, never localhost": (
            "hasExplicitConfiguredHost ? .configuredRemote : .iosCompanion" in engine_config
        ),
        "non-macOS backend start does not launch embedded Python": (
            "#if os(macOS)" in embedded_backend
            and 'errorMessage = "No remote engine host configured. Set a custom host in Settings."' in embedded_backend
        ),
        "EngineConfig can disable implicit localhost for iOS": (
            "allowsImplicitEmbeddedLocalDefault: false" in engine_config
            and "iOS/iPadOS never runs a local engine" in engine_config
        ),
    }
    return [message for message, ok in checks.items() if not ok]


def main() -> int:
    violations = collect_violations()
    if violations:
        print("iOS remote-client target guardrail offenders:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("iOS remote-client target guardrail: app target, API client, and remote-only startup are wired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
