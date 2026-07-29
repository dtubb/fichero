#!/usr/bin/env python3
"""Read-only validator for feature-tier promotions."""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES_YAML = ROOT / "features.yaml"
GENERATOR = ROOT / "scripts" / "gen_feature_tiers.py"
GENERATED_SWIFT = ROOT / "fichero" / "fichero" / "Models" / "FeatureTiers.generated.swift"
GENERATED_PYTHON = ROOT / "fichero-server" / "src" / "fichero_server" / "api" / "feature_tiers_generated.py"
GENERATED_DOC = ROOT / "docs" / "user" / "features.md"
GENERATED_OUTPUTS = (GENERATED_SWIFT, GENERATED_PYTHON, GENERATED_DOC)
GENERATED_RELATIVE_OUTPUTS = tuple(path.relative_to(ROOT) for path in GENERATED_OUTPUTS)
TIER_ORDER = {"dev": 1, "alpha": 2, "beta": 3, "release": 4}


class ValidationError(Exception):
    """Expected validation failure."""


def _parse_scalar(value: str) -> str | None:
    value = value.strip()
    if value == "null":
        return None
    return value


def _parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if value == "[]":
        return []
    if not (value.startswith("[") and value.endswith("]")):
        raise ValidationError(f"Unsupported list syntax: {value}")
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip() for item in inner.split(",")]


def load_features(path: Path) -> list[dict[str, object]]:
    features: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    in_routes = False
    seen_keys: set[str] = set()

    for lineno, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("- "):
            if current is not None:
                features.append(current)
            key, _, value = line[2:].partition(":")
            if not _:
                raise ValidationError(f"{path}:{lineno}: expected key: value")
            current = {key.strip(): _parse_scalar(value), "routes": []}
            in_routes = key.strip() == "routes"
            continue
        if current is None:
            raise ValidationError(f"{path}:{lineno}: expected a top-level feature entry")
        if line.startswith("    - "):
            if not in_routes:
                raise ValidationError(f"{path}:{lineno}: route item outside routes block")
            routes = current.setdefault("routes", [])
            assert isinstance(routes, list)
            routes.append(line[6:].strip())
            continue
        if line.startswith("  "):
            field, _, value = line[2:].partition(":")
            if not _:
                raise ValidationError(f"{path}:{lineno}: expected key: value")
            field = field.strip()
            value = value.strip()
            if field == "routes":
                current["routes"] = _parse_inline_list(value) if value else []
                in_routes = not value
            else:
                current[field] = _parse_scalar(value)
                in_routes = False
            continue
        raise ValidationError(f"{path}:{lineno}: unsupported YAML shape")

    if current is not None:
        features.append(current)

    for feature in features:
        key = feature.get("key")
        tier = feature.get("tier")
        routes = feature.get("routes", [])
        if not isinstance(key, str) or not key:
            raise ValidationError("Every feature must have a non-empty key")
        if key in seen_keys:
            raise ValidationError(f"Duplicate feature key: {key}")
        seen_keys.add(key)
        if tier not in TIER_ORDER:
            raise ValidationError(f"Unknown tier {tier!r} for {key}")
        if not isinstance(routes, list):
            raise ValidationError(f"Routes for {key} must be a list")
    return features


def _copy_repo_subset(src_root: Path, dst_root: Path) -> None:
    for relative in (
        Path("features.yaml"),
        Path("scripts/gen_feature_tiers.py"),
        *GENERATED_RELATIVE_OUTPUTS,
    ):
        src = src_root / relative
        dst = dst_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _generate_in_temp(repo_root: Path) -> dict[Path, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        _copy_repo_subset(repo_root, tmp_root)
        result = subprocess.run(
            [sys.executable, str(tmp_root / "scripts" / "gen_feature_tiers.py")],
            cwd=tmp_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown generator failure"
            raise ValidationError(f"Could not regenerate feature-tier artifacts: {message}")

        generated: dict[Path, str] = {}
        for relative in GENERATED_RELATIVE_OUTPUTS:
            generated[repo_root / relative] = (tmp_root / relative).read_text()
        return generated


def validate_generation_sync(repo_root: Path) -> None:
    expected = _generate_in_temp(repo_root)
    stale = [path for path, content in expected.items() if path.read_text() != content]
    if stale:
        files = ", ".join(str(path.relative_to(repo_root)) for path in stale)
        raise ValidationError(
            f"Generated outputs are stale: {files}. Run `python scripts/gen_feature_tiers.py`."
        )


def load_generated_python(path: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    module = ast.parse(path.read_text(), filename=str(path))
    needed = {"ROUTE_PREFIX_TIERS", "CUMULATIVE_ROUTE_PREFIXES"}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in needed:
            values[target.id] = ast.literal_eval(node.value)
    missing = needed - values.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValidationError(f"Missing generated assignments in {path}: {names}")
    return values


def validate_route_membership(feature: dict[str, object], new_tier: str, repo_root: Path) -> None:
    if TIER_ORDER[new_tier] < TIER_ORDER["beta"]:
        return
    routes = feature.get("routes", [])
    if not routes:
        return
    generated = load_generated_python(repo_root / GENERATED_PYTHON.relative_to(ROOT))
    route_tiers = generated["ROUTE_PREFIX_TIERS"]
    cumulative = generated["CUMULATIVE_ROUTE_PREFIXES"]
    assert isinstance(route_tiers, dict)
    assert isinstance(cumulative, dict)
    allowed = cumulative.get(new_tier)
    if not isinstance(allowed, list):
        raise ValidationError(f"Generated cumulative route set missing tier {new_tier}")

    missing_from_map = [route for route in routes if route not in route_tiers]
    if missing_from_map:
        missing = ", ".join(missing_from_map)
        raise ValidationError(f"Routes for {feature['key']} missing from generated route map: {missing}")

    missing_from_tier = [route for route in routes if route not in allowed]
    if missing_from_tier:
        missing = ", ".join(missing_from_tier)
        raise ValidationError(
            f"Routes for {feature['key']} are not enabled in the {new_tier} cumulative route set: {missing}"
        )


def find_feature(features: list[dict[str, object]], key: str) -> dict[str, object]:
    for feature in features:
        if feature.get("key") == key:
            return feature
    raise ValidationError(f"Unknown feature key: {key}")


def validate_promotion(key: str, new_tier: str, allow_demote: bool, repo_root: Path) -> None:
    if new_tier not in TIER_ORDER:
        choices = ", ".join(TIER_ORDER)
        raise ValidationError(f"Unknown tier {new_tier!r}. Expected one of: {choices}")

    features = load_features(repo_root / FEATURES_YAML.relative_to(ROOT))
    feature = find_feature(features, key)
    current_tier = feature["tier"]
    assert isinstance(current_tier, str)

    if new_tier == current_tier:
        raise ValidationError(f"{key} is already at {new_tier}")
    if not allow_demote and TIER_ORDER[new_tier] <= TIER_ORDER[current_tier]:
        raise ValidationError(
            f"{key} is {current_tier}; {new_tier} is not a strict promotion. Use --allow-demote to override."
        )

    validate_generation_sync(repo_root)
    validate_route_membership(feature, new_tier, repo_root)


def run_self_check(repo_root: Path) -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        _copy_repo_subset(repo_root, tmp_root)
        drifted = tmp_root / GENERATED_PYTHON.relative_to(ROOT)
        drifted.write_text(drifted.read_text() + "\n# self-check drift\n")
        try:
            validate_generation_sync(tmp_root)
        except ValidationError:
            print("OK: self-check caught stale/generated drift")
            return 0
    print("FAIL: self-check did not catch stale/generated drift", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate whether a feature is eligible for promotion to a higher tier."
    )
    parser.add_argument("key", nargs="?", help="Feature key from features.yaml")
    parser.add_argument("new_tier", nargs="?", help="Target tier: dev, alpha, beta, or release")
    parser.add_argument("--allow-demote", action="store_true", help="Allow moving to a lower tier")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Prove the stale/generated drift failure path fires",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check:
        if args.key or args.new_tier:
            parser.error("--self-check does not take <key> or <new_tier>")
        return run_self_check(ROOT)

    if not args.key or not args.new_tier:
        parser.error("the following arguments are required: key, new_tier")

    try:
        validate_promotion(args.key, args.new_tier, args.allow_demote, ROOT)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.key} eligible for {args.new_tier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
