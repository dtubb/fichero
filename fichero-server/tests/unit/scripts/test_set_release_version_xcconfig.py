"""Single-sourced app version via Version.xcconfig (#3234).

MARKETING_VERSION / CURRENT_PROJECT_VERSION live ONLY in
fichero/Configs/Version.xcconfig; scripts/set-release-version.sh stamps that
file (never project.pbxproj), and every release-pipeline reader resolves the
value from the xcconfig. These tests pin:

- the stamp round-trips through the xcconfig (unquoted, exact lines);
- the stamp refuses to run if pbxproj version literals reappear (a target
  literal would silently override the xcconfig);
- the real pbxproj carries no version literals and wires the xcconfig via a
  project-level baseConfigurationReference;
- the release scripts read the version from the xcconfig, not raw pbxproj
  greps (which now come back empty);
- the script's --self-check contract keeps passing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "set-release-version.sh"
XCCONFIG = REPO_ROOT / "fichero" / "Configs" / "Version.xcconfig"
PBXPROJ = REPO_ROOT / "fichero" / "fichero.xcodeproj" / "project.pbxproj"


def _make_fixture(tmp_path: Path, pbx_contents: str = "// no version literals\n") -> Path:
    """A minimal repo layout the stamp script can run against."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "set-release-version.sh").write_bytes(SCRIPT.read_bytes())
    (root / "fichero" / "Configs").mkdir(parents=True)
    (root / "fichero" / "Configs" / "Version.xcconfig").write_text(
        "MARKETING_VERSION = 2026.07.01\nCURRENT_PROJECT_VERSION = 2026070101\n",
        encoding="utf-8",
    )
    (root / "fichero" / "fichero.xcodeproj").mkdir(parents=True)
    (root / "fichero" / "fichero.xcodeproj" / "project.pbxproj").write_text(
        pbx_contents, encoding="utf-8"
    )
    (root / "fichero-server").mkdir()
    (root / "fichero-server" / "pyproject.toml").write_text(
        '[project]\nname = "fichero-server"\nversion = "2026.7.1"\n',
        encoding="utf-8",
    )
    (root / "RELEASE_NOTES.md").write_text(
        "## 2026.07.01\n\n- previous entry\n", encoding="utf-8"
    )
    return root


def _run_stamp(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts" / "set-release-version.sh"), *args],
        capture_output=True,
        text=True,
        # Skip git tag counting so the fixture needs no git history.
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "FICHERO_RELEASE_SEQ": "1"},
        check=False,
    )


def test_stamp_round_trips_through_xcconfig(tmp_path: Path) -> None:
    root = _make_fixture(tmp_path)
    result = _run_stamp(root, "2026.07.31", "--beta")
    assert result.returncode == 0, result.stdout + result.stderr

    xcconfig = (root / "fichero" / "Configs" / "Version.xcconfig").read_text(encoding="utf-8")
    lines = xcconfig.splitlines()
    # Exact, UNQUOTED lines — quotes would leak into CFBundleShortVersionString.
    assert "MARKETING_VERSION = 2026.07.31-beta" in lines
    assert "CURRENT_PROJECT_VERSION = 2026073101" in lines
    assert '"' not in xcconfig

    # The pbxproj is untouched by the stamp.
    pbx = (root / "fichero" / "fichero.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
    assert pbx == "// no version literals\n"

    # Engine version moves in lockstep, in PEP 440 form.
    pyproject = (root / "fichero-server" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "2026.7.31b1"' in pyproject

    # Release-notes heading tracks the stamp.
    notes = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert notes.startswith("## 2026.07.31-beta\n")


def test_stamp_refuses_pbxproj_version_literals(tmp_path: Path) -> None:
    root = _make_fixture(
        tmp_path, pbx_contents="\t\t\t\tMARKETING_VERSION = 2026.07.01;\n"
    )
    result = _run_stamp(root, "2026.07.31")
    assert result.returncode != 0
    assert "single source" in result.stderr

    # Refusal means NOTHING was stamped — no half-applied version.
    xcconfig = (root / "fichero" / "Configs" / "Version.xcconfig").read_text(encoding="utf-8")
    assert "MARKETING_VERSION = 2026.07.01" in xcconfig


def test_real_pbxproj_has_no_version_literals_and_wires_the_xcconfig() -> None:
    pbx = PBXPROJ.read_text(encoding="utf-8")
    for setting in ("MARKETING_VERSION = ", "CURRENT_PROJECT_VERSION = "):
        assert setting not in pbx, (
            f"project.pbxproj carries a {setting.strip(' =')} literal; "
            "fichero/Configs/Version.xcconfig is the single source (#3234)"
        )
    # The xcconfig must actually be wired in, or the app would build versionless.
    assert "Version.xcconfig" in pbx
    assert pbx.count("baseConfigurationReference") >= 8  # all project-level configs


def test_version_xcconfig_is_unquoted_and_complete() -> None:
    xcconfig = XCCONFIG.read_text(encoding="utf-8")
    settings = dict(
        line.split(" = ", 1)
        for line in xcconfig.splitlines()
        if " = " in line and not line.lstrip().startswith("//")
    )
    assert set(settings) == {"MARKETING_VERSION", "CURRENT_PROJECT_VERSION"}
    for value in settings.values():
        assert value == value.strip()
        assert '"' not in value
    assert settings["CURRENT_PROJECT_VERSION"].isdigit()


def test_release_scripts_read_the_version_from_the_xcconfig() -> None:
    """Every pipeline reader resolves the version via Version.xcconfig — a raw
    pbxproj grep now returns empty and would silently ship a versionless
    artifact."""
    readers = [
        "release-all.sh",
        "build-release-dmg.sh",
        "create-github-release.sh",
        "check_version_date.sh",
    ]
    for name in readers:
        text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "Configs/Version.xcconfig" in text, f"{name} does not read Version.xcconfig"
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            assert not ("MARKETING_VERSION" in line and "pbxproj" in line), (
                f"{name} still greps MARKETING_VERSION out of project.pbxproj: {line!r}"
            )


def test_self_check_contract_still_passes() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--self-check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "self-check: PASS" in result.stdout
