"""Guard: security floors in pyproject stay put, and stay in sync (#4337).

Almost every dependency in ``fichero-server/pyproject.toml`` is unpinned on
purpose — the set floats upward. The consequence is that the only thing
standing between a fresh install and a known-vulnerable (or outright broken)
version is a handful of ``>=`` floors and one ``<`` ceiling. Those were added
with reason comments, and comments do not fail a build.

Two failure modes this makes executable:

1. A floor gets dropped or loosened during an unrelated edit — the fresh
   resolve silently takes a version with a published advisory again.
2. A floor gets added to ONE of the two dependency lists. pyproject carries the
   same dependency set twice (``[tool.briefcase.app.fichero_server].requires``
   for the bundled app, ``[project].dependencies`` for pip) and says in a
   comment "both sections must be maintained" — which, until now, nothing
   checked. A floor present in only one list protects only one of the two ways
   Fichero gets installed, and the bundle is the one users run.

Fixtures below prove each rule actually fires, so the tests cannot rot into
tautologies that pass against any input.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

# package -> minimum version, with the advisory/reason the floor exists for.
# Keep in step with the reason comments in pyproject.toml and the table in
# agent-work/status/deps-refresh-2026-07-30.md.
_REQUIRED_FLOORS = {
    "aiohttp": ("3.14.1", "PYSEC-2026-237, 2104-2113"),
    "cryptography": ("48.0.1", "GHSA-537c-gmf6-5ccf"),
    "starlette": ("1.3.1", "PYSEC-2026-248/249"),
    "python-multipart": ("0.0.31", "PYSEC-2026-3036/3037/3040 multipart DoS"),
    "pydantic": ("2.13", "openrouter 0.11.x caps <2.13 and downgrades what ships"),
    "pydantic-settings": ("2.14.2", "GHSA-4xgf-cpjx-pc3j"),
    "langchain": ("1.3.9", "PYSEC-2026-2192"),
    "langchain-anthropic": ("1.4.6", "PYSEC-2026-2556"),
    "mcp": ("1.28.1", "PYSEC-2026-3483"),
    "pillow": ("12.3.0", "22 image-decoder advisories"),
}

_SHIPPED_LISTS = ("briefcase.requires", "project.dependencies")


def _pyproject() -> dict:
    root = Path(__file__).resolve().parents[2]  # fichero-server/
    with open(root / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _base_name(requirement: str) -> str:
    """Strip version/extras: 'uvicorn[standard]>=1' -> 'uvicorn'."""
    name = requirement.strip()
    for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
        name = name.split(sep, 1)[0]
    return name.strip().lower()


def _specifier(requirement: str) -> str:
    """The version part: 'Pillow>=12.3.0' -> '>=12.3.0'; bare name -> ''."""
    name = _base_name(requirement)
    rest = requirement.strip().lower()
    idx = rest.find(name)
    tail = rest[idx + len(name) :]
    # Drop an extras group so 'uvicorn[standard]>=1' yields '>=1'.
    if tail.startswith("["):
        tail = tail.split("]", 1)[-1]
    return tail.strip()


def _shipped_lists() -> dict[str, list[str]]:
    data = _pyproject()
    briefcase = data["tool"]["briefcase"]["app"]["fichero_server"]
    return {
        "briefcase.requires": briefcase.get("requires", []),
        "project.dependencies": data["project"]["dependencies"],
    }


def _requirement_map(requirements: list[str]) -> dict[str, str]:
    return {_base_name(r): _specifier(r) for r in requirements}


def _version_tuple(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _floor_of(specifier: str) -> str | None:
    """Extract the '>=' bound from a specifier, ignoring any upper bound."""
    for clause in specifier.split(","):
        clause = clause.strip()
        if clause.startswith(">="):
            return clause[2:].strip()
    return None


def _meets(actual: str | None, minimum: str) -> bool:
    if actual is None:
        return False
    a, m = _version_tuple(actual), _version_tuple(minimum)
    width = max(len(a), len(m))
    a += (0,) * (width - len(a))
    m += (0,) * (width - len(m))
    return a >= m


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize("list_name", _SHIPPED_LISTS)
@pytest.mark.parametrize("package", sorted(_REQUIRED_FLOORS))
def test_security_floor_is_declared(list_name, package):
    minimum, reason = _REQUIRED_FLOORS[package]
    declared = _requirement_map(_shipped_lists()[list_name])

    assert package in declared, (
        f"{package} is missing from {list_name}; it needs a >={minimum} floor "
        f"({reason})."
    )
    floor = _floor_of(declared[package])
    assert _meets(floor, minimum), (
        f"{list_name} declares {package}{declared[package] or ' (unpinned)'} — "
        f"needs >={minimum} because of {reason}. Floors may only move UP."
    )


def test_mcp_is_capped_below_2_in_both_lists():
    """mcp 2.0 deleted ``mcp.server.fastmcp``, which fichero-mcp imports.

    Without the ceiling a fresh unbounded install resolves 2.x and the MCP
    product stops importing entirely. Lifting the cap is a port to
    ``mcp.server.mcpserver``, not a version bump.
    """
    for list_name, requirements in _shipped_lists().items():
        specifier = _requirement_map(requirements).get("mcp")
        assert specifier is not None, f"mcp missing from {list_name}"
        assert "<2" in specifier.replace(" ", ""), (
            f"{list_name} declares mcp{specifier} with no <2 ceiling — mcp 2.x "
            "removed mcp.server.fastmcp and fichero-mcp fails to import."
        )


def test_installed_mcp_still_exposes_fastmcp():
    """The thing the ceiling protects is actually there at the resolved version.

    Asserted rather than skipped: if this environment's ``mcp`` cannot provide
    ``FastMCP``, every fichero-mcp tool module is already broken and the run
    should say so instead of quietly passing.
    """
    from mcp.server.fastmcp import FastMCP

    assert callable(FastMCP), (
        "mcp.server.fastmcp.FastMCP is not usable — the resolved mcp version "
        "has moved on (2.x renames it to mcp.server.mcpserver.MCPServer) and "
        "fichero_mcp.{server,full,simple} cannot import."
    )
    # The client half fichero_server.mcp.manager depends on is separate and
    # survived the 2.0 reshuffle; assert it too so a future cap change cannot
    # break one side unnoticed.
    from mcp.client.session import ClientSession

    assert hasattr(ClientSession, "call_tool")


def test_floored_packages_agree_across_both_lists():
    """A floor in one list only protects one of the two install paths."""
    briefcase = _requirement_map(_shipped_lists()["briefcase.requires"])
    project = _requirement_map(_shipped_lists()["project.dependencies"])

    mismatched = {
        package: (briefcase.get(package), project.get(package))
        for package in _REQUIRED_FLOORS
        if _floor_of(briefcase.get(package) or "")
        != _floor_of(project.get(package) or "")
    }
    assert not mismatched, (
        "floors differ between briefcase.requires and project.dependencies "
        f"(briefcase, project): {mismatched}. pyproject keeps the dependency "
        "set twice and both must carry the same floor."
    )


def test_no_new_exact_pins_in_shipped_deps():
    """Floors, never ``==``. An exact pin freezes us on a stale version."""
    for list_name, requirements in _shipped_lists().items():
        pinned = [r for r in requirements if "==" in _specifier(r)]
        assert not pinned, (
            f"{list_name} exact-pins {pinned} — use a >= floor so the "
            "dependency can still float upward (#4337)."
        )


# --------------------------------------------------------------------------
# Fixtures proving the rules fire (guardrails must be able to fail)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "requirement,expected_name,expected_spec",
    [
        ("Pillow>=12.3.0", "pillow", ">=12.3.0"),
        ("uvicorn[standard]", "uvicorn", ""),
        ("uvicorn[standard]>=0.48", "uvicorn", ">=0.48"),
        ("mcp>=1.28.1,<2", "mcp", ">=1.28.1,<2"),
        ("duckdb", "duckdb", ""),
    ],
)
def test_parser_splits_name_and_specifier(requirement, expected_name, expected_spec):
    assert _base_name(requirement) == expected_name
    assert _specifier(requirement) == expected_spec


@pytest.mark.parametrize(
    "specifier,expected",
    [(">=1.28.1,<2", "1.28.1"), ("<2", None), ("", None), (">=12.3.0", "12.3.0")],
)
def test_floor_extraction_ignores_upper_bounds(specifier, expected):
    assert _floor_of(specifier) == expected


@pytest.mark.parametrize(
    "actual,minimum,ok",
    [
        ("3.14.3", "3.14.1", True),
        ("3.14.0", "3.14.1", False),
        ("2.13.4", "2.13", True),
        ("2.12.5", "2.13", False),  # the openrouter-induced silent downgrade
        ("12.3.0", "12.3.0", True),
        (None, "1.0", False),
        ("13.1", "9.0", True),  # not string-compared
    ],
)
def test_version_comparison_is_numeric(actual, minimum, ok):
    assert _meets(actual, minimum) is ok


def test_missing_floor_would_be_caught():
    """A bare, unfloored requirement must not satisfy a floor check."""
    declared = _requirement_map(["aiohttp", "cryptography>=1.0"])
    assert not _meets(_floor_of(declared["aiohttp"]), "3.14.1")
    assert not _meets(_floor_of(declared["cryptography"]), "48.0.1")


def test_exact_pin_detection_would_catch_a_pin():
    assert "==" in _specifier("duckdb==1.5.5")
    assert "==" not in _specifier("duckdb>=1.5.5")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
