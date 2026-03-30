#!/usr/bin/env python3
"""Validate backend runtime deps are complete and synchronized.

Checks:
1) Required runtime provider/tool deps are present in BOTH:
   - tool.briefcase.app.fichero-backend.requires
   - project.dependencies
2) Those required deps are not left in project.optional-dependencies.dev
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python <3.11
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        print(
            "ERROR: Need Python 3.11+ (tomllib) or 'tomli' installed. "
            "Run with project .venv: .venv/bin/python fichero-api/scripts/check_runtime_deps.py"
        )
        raise SystemExit(2)


REQUIRED_RUNTIME_DEPS = {
    "langchain-openai",
    "langchain-anthropic",
    "langchain-google-genai",
    "langchain-aws",
    "langchain-cohere",
    "langchain-mistralai",
    "langchain-community",
    "langchain-mcp-adapters",
    "mcp",
}


def main() -> int:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    briefcase_requires = set(
        data["tool"]["briefcase"]["app"]["fichero-backend"]["requires"]
    )
    project_deps = set(data["project"]["dependencies"])
    dev_deps = set(data["project"]["optional-dependencies"]["dev"])

    errors: list[str] = []

    missing_in_briefcase = sorted(REQUIRED_RUNTIME_DEPS - briefcase_requires)
    missing_in_project = sorted(REQUIRED_RUNTIME_DEPS - project_deps)
    misplaced_in_dev = sorted(REQUIRED_RUNTIME_DEPS & dev_deps)

    if missing_in_briefcase:
        errors.append(
            f"Missing from [tool.briefcase.app.fichero-backend].requires: {missing_in_briefcase}"
        )
    if missing_in_project:
        errors.append(f"Missing from [project].dependencies: {missing_in_project}")
    if misplaced_in_dev:
        errors.append(
            f"Runtime deps should not be dev-only, but still found in [project.optional-dependencies].dev: {misplaced_in_dev}"
        )

    if errors:
        print("Runtime dependency validation FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Runtime dependency validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
