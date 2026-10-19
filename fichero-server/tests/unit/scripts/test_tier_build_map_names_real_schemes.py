"""Every scheme and configuration tier_build_map.sh hands the release scripts exists in the project.

#5730 retired the per-tier "Local iOS" schemes and the map kept naming them, so the iOS
TestFlight archive failed at release time (2026-10-18) with nothing red before.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PROJECT = ROOT / "fichero" / "fichero.xcodeproj"


def _map(tier: str) -> dict[str, str]:
    out = subprocess.run(
        ["bash", "-c", 'source scripts/tier_build_map.sh 2>/dev/null; env'],
        cwd=ROOT, env={"FICHERO_RELEASE_TIER": tier, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


@pytest.mark.parametrize("tier", ["release", "beta", "alpha", "dev", "unknown"])
def test_each_tier_names_a_scheme_and_configuration_that_exist(tier):
    names = set(re.findall(r'^\s*name = "?([^";]+)"?;', (PROJECT / "project.pbxproj").read_text(), re.M))
    got = _map(tier)
    for scheme_key, config_key in (("MAC_SCHEME", "MAC_CONFIG"), ("IOS_SCHEME", "IOS_CONFIG"),
                                   ("MAC_APP_STORE_SCHEME", "MAC_APP_STORE_CONFIG")):
        assert (PROJECT / "xcshareddata" / "xcschemes" / f"{got[scheme_key]}.xcscheme").is_file(), (tier, got[scheme_key])
        assert got[config_key] in names, (tier, got[config_key])
