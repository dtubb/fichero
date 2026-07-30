"""Preset-version bump guardrail (#4298).

Shipped default-workflow presets only reach EXISTING libraries when their
``config.preset_version`` is bumped — ``seed_default_workflows`` force-replaces
a stored copy only when the shipped version is greater than the stored one.
The paleography-ensemble widening bug (#4298) happened exactly because the
preset's graph was fixed repeatedly (#4146/#4153/#4154/#4156) while
``preset_version`` stayed at 1: every already-seeded library kept the broken
stored graph forever.

This module makes that mistake un-shippable: a checked-in manifest records
(sha256, preset_version) per preset, and a unit test verifies every shipped
preset against it. Editing a preset without bumping its version (or without
refreshing the manifest) fails the suite with instructions.

Regenerate the manifest after a legitimate preset change:

    python -m fichero_server.workflows.preset_manifest --regen
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PRESET_DIR = Path(__file__).resolve().parent.parent / "resources" / "default_workflows"
MANIFEST_PATH = PRESET_DIR / "preset_version_manifest.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _preset_version(raw: bytes) -> int:
    config = json.loads(raw).get("config") or {}
    return int(config.get("preset_version", 1))


def load_shipped_presets(preset_dir: Path = PRESET_DIR) -> dict[str, tuple[bytes, int]]:
    """Map preset filename -> (raw bytes, preset_version) for every shipped preset."""
    presets: dict[str, tuple[bytes, int]] = {}
    for path in sorted(preset_dir.glob("*.json")):
        if path.name == MANIFEST_PATH.name:
            continue
        raw = path.read_bytes()
        presets[path.name] = (raw, _preset_version(raw))
    return presets


def check_preset_manifest(
    presets: dict[str, tuple[bytes, int]],
    manifest: dict[str, dict[str, object]],
) -> list[str]:
    """Return human-readable violations of the version-bump discipline.

    Rules per preset:
    - missing manifest entry -> violation (new presets must be recorded);
    - content hash matches   -> version must equal the recorded one;
    - content hash differs   -> version must be STRICTLY greater than the
      recorded one (the bump is what delivers the fix to seeded libraries),
      and the manifest must be regenerated.
    """
    violations: list[str] = []
    regen_hint = (
        "then regenerate the manifest: "
        "python -m fichero_server.workflows.preset_manifest --regen"
    )
    for name, (raw, version) in presets.items():
        entry = manifest.get(name)
        digest = _sha256(raw)
        if entry is None:
            violations.append(
                f"{name}: not in preset_version_manifest.json — record it; {regen_hint}"
            )
            continue
        recorded_sha = entry.get("sha256")
        recorded_version = int(entry.get("preset_version", 0))
        if digest == recorded_sha:
            if version != recorded_version:
                violations.append(
                    f"{name}: preset_version {version} disagrees with manifest "
                    f"{recorded_version} for unchanged content — {regen_hint}"
                )
        elif version <= recorded_version:
            violations.append(
                f"{name}: content changed but preset_version is still {version} "
                f"(manifest records {recorded_version}). Stored library copies "
                f"only upgrade on a bump (#4298) — set preset_version to "
                f">= {recorded_version + 1}; {regen_hint}"
            )
        else:
            # Version was bumped correctly — the manifest just needs refreshing.
            violations.append(
                f"{name}: content + version changed — refresh the manifest; {regen_hint}"
            )
    for name in manifest:
        if name not in presets:
            violations.append(
                f"{name}: in the manifest but not shipped — remove its entry; {regen_hint}"
            )
    return violations


def build_manifest(presets: dict[str, tuple[bytes, int]]) -> dict[str, dict[str, object]]:
    return {
        name: {"preset_version": version, "sha256": _sha256(raw)}
        for name, (raw, version) in sorted(presets.items())
    }


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict[str, object]]:
    return json.loads(path.read_text())


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regen", action="store_true", help="rewrite the manifest")
    args = parser.parse_args()
    presets = load_shipped_presets()
    if args.regen:
        MANIFEST_PATH.write_text(json.dumps(build_manifest(presets), indent=1) + "\n")
        print(f"Wrote {MANIFEST_PATH} ({len(presets)} presets)")
    else:
        manifest = load_manifest() if MANIFEST_PATH.exists() else {}
        for violation in check_preset_manifest(presets, manifest):
            print(violation)


if __name__ == "__main__":
    _main()
