"""Unit tests for scripts/check_ios_remote_client_target.py (#2099)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_ios_remote_client_target.py"
_SPEC = importlib.util.spec_from_file_location("check_ios_remote_client_target", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)


def _write_minimal_repo(root: Path) -> None:
    (root / "fichero/fichero.xcodeproj").mkdir(parents=True)
    (root / "fichero/fichero-api-client").mkdir(parents=True)
    (root / "fichero/fichero/Services").mkdir(parents=True)

    (root / "fichero/fichero.xcodeproj/project.pbxproj").write_text(
        # Post-#3754 the app target compiles via a synchronized root group
        # (folder = source of truth), so the checker verifies the sync-group
        # invariant instead of a `FicheroApp_iOS.swift in Sources` build-file line.
        'isa = PBXFileSystemSynchronizedRootGroup;\n'
        'path = fichero;\n'
        'SUPPORTED_PLATFORMS = "iphoneos iphonesimulator macosx";\n'
        'TARGETED_DEVICE_FAMILY = "1,2,7";\n',
        encoding="utf-8",
    )
    (root / "fichero/fichero-api-client/Package.swift").write_text(".iOS(.v17)\n", encoding="utf-8")
    (root / "fichero/fichero/FicheroApp_iOS.swift").write_text(
        "#if os(iOS)\n",
        encoding="utf-8",
    )
    (root / "fichero/fichero/Services/EngineConfig.swift").write_text(
        "allowsImplicitEmbeddedLocalDefault: false\n"
        "iOS/iPadOS never runs a local engine\n"
        # The provisioning strategy is the real enforcement (#3109): iOS with
        # no configured host resolves to the paired companion, never localhost.
        "return inputs.hasExplicitConfiguredHost ? .configuredRemote : .iosCompanion\n",
        encoding="utf-8",
    )
    (root / "fichero/fichero/Services/EmbeddedBackendService.swift").write_text(
        "#if os(macOS)\n"
        'errorMessage = "No remote engine host configured. Set a custom host in Settings."\n',
        encoding="utf-8",
    )


def test_collect_violations_passes_for_wired_ios_remote_target(tmp_path):
    _write_minimal_repo(tmp_path)

    assert _mod.collect_violations(tmp_path) == []


def test_collect_violations_flags_missing_ios_api_client_platform(tmp_path):
    _write_minimal_repo(tmp_path)
    (tmp_path / "fichero/fichero-api-client/Package.swift").write_text(".macOS(.v14)\n", encoding="utf-8")

    assert _mod.collect_violations(tmp_path) == ["shared OpenAPI client package supports iOS"]


def test_real_repo_ios_remote_client_target_guardrail_passes():
    assert _mod.collect_violations() == []
