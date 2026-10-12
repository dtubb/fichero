"""The acknowledgements are generated from what is bundled, and a component with no licence fails the build (#5639),
tested to the spec: `about.acknowledgements.generated` (docs/contributor_manual/specs/ui/about.md).

WHY: the About window's credits were a hand-typed Swift list; a package added to the engine (ultralytics, AGPL)
would ship uncredited until someone remembered. The script reads the bundle itself, and fails on what it cannot
credit.
"""

from __future__ import annotations

import importlib.util
import json
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RESOLVED = [ROOT / "fichero/fichero.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved",
            ROOT / "fichero/fichero-api-client/Package.resolved"]


def _script():
    spec = importlib.util.spec_from_file_location("write_acknowledgements", ROOT / "scripts/write_acknowledgements.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dist(packages: Path, name: str, version: str, metadata: str, licence_text: str | None = None) -> None:
    folder = packages / f"{name}-{version}.dist-info"
    folder.mkdir(parents=True)
    (folder / "METADATA").write_text(f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata}\n")
    if licence_text is not None:
        (folder / "licenses").mkdir()
        (folder / "licenses" / "LICENSE").write_text(licence_text)


def test_every_swift_package_the_repo_pins_has_its_licence_recorded():
    """A new Swift dependency fails here until its licence is in `SWIFT_LICENCES`."""
    ack = _script()
    for resolved in RESOLVED:
        for c in ack.swift_components(resolved):
            assert c["licence"], f"{c['name']} ({resolved.name}): add its licence to SWIFT_LICENCES"
            assert c["licence_text"] and c["licence_text"].startswith("https://")


def test_every_package_in_the_engines_own_environment_is_credited():
    """The engine's environment the tests run in, as the bundle is: every package has a licence."""
    ack = _script()
    folders = [Path(p) for p in site.getsitepackages() if Path(p).is_dir()]
    components = [c for folder in folders for c in ack.python_components(folder)]
    assert components, "no packages read: the guard proves nothing"
    missing = [f"{c['name']} {c['version']}" for c in components if not c["licence"]]
    assert not missing, f"no licence found for: {missing}"


def test_a_licence_is_read_from_metadata_or_its_text_and_fichero_itself_is_not_listed(tmp_path):
    ack = _script()
    packages = tmp_path / "app_packages"
    _dist(packages, "spdx", "1.0", "License-Expression: Apache-2.0")
    _dist(packages, "longtext", "2.0", "License: MIT License\n        Copyright (c) someone")
    _dist(packages, "classified", "3.0", "Classifier: License :: OSI Approved :: BSD License")
    _dist(packages, "textonly", "4.0", "License-File: LICENSE", "Permission is hereby granted, free of charge, to any")
    _dist(packages, "fichero_server", "2026.9.8", "")
    got = {c["name"]: c for c in ack.python_components(packages)}
    assert {n: c["licence"] for n, c in got.items()} == {
        "classified": "BSD License", "longtext": "MIT License", "spdx": "Apache-2.0", "textonly": "MIT"}
    assert got["textonly"]["licence_text"] == "textonly-4.0.dist-info/licenses/LICENSE"


def test_the_json_is_written_and_an_uncredited_package_fails_by_name(tmp_path, capsys):
    ack = _script()
    packages = tmp_path / "app_packages"
    _dist(packages, "kraken", "7.1.1", "License-Expression: Apache-2.0")
    out = tmp_path / "acknowledgements.json"
    assert ack.main(["--python", str(packages), "--swift", str(RESOLVED[0]), "--out", str(out)]) == 0
    made = json.loads(out.read_text())
    assert made["format"] == "fichero-acknowledgements-v1"
    assert {(c["layer"], c["kind"]) for c in made["components"]} == {("engine", "python"), ("app", "swift")}

    _dist(packages, "mystery", "0.1", "")
    assert ack.main(["--python", str(packages), "--out", str(out)]) == 1
    assert "python mystery 0.1" in capsys.readouterr().err


def test_the_engine_bundle_build_writes_it():
    preflight = (ROOT / "scripts/preflight-embedded-engine.sh").read_text(encoding="utf-8")
    assert "write_acknowledgements.py" in preflight and "acknowledgements.json" in preflight
    assert sys.version_info >= (3, 9)  # the script runs on macOS's own python3 (3.9) in the build
