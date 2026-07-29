from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "check_pydantic_persistence_writes.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "check_pydantic_persistence_writes",
    _SCRIPT,
)
assert _SPEC and _SPEC.loader
check_pydantic_persistence_writes = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_pydantic_persistence_writes
_SPEC.loader.exec_module(check_pydantic_persistence_writes)  # type: ignore[attr-defined]


def test_scan_source_flags_direct_undeclared_field_write_and_allows_declared_field():
    offenders = check_pydantic_persistence_writes.scan_source(
        """
from pydantic import BaseModel, ConfigDict


class Thing(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str
    sort_order: int = 0


def update_thing() -> None:
    thing = Thing(title="x")
    thing.sort_order = 2
    thing.shadow = "oops"
""",
        "fichero-server/src/fichero_server/api/routes/things.py",
    )

    assert {(offender.rule, offender.line) for offender in offenders} == {
        ("direct_undeclared_model_attribute_write", 14),
    }


def test_scan_source_flags_dynamic_setattr_from_extra_allow_request_model():
    offenders = check_pydantic_persistence_writes.scan_source(
        """
from pydantic import BaseModel, ConfigDict


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str | None = None


class Thing(BaseModel):
    title: str = ""
    sort_order: int = 0


def patch_thing(request: PatchRequest) -> None:
    thing = Thing(title="x")
    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(thing, field, value)
""",
        "fichero-server/src/fichero_server/api/routes/things.py",
    )

    assert {(offender.rule, offender.line) for offender in offenders} == {
        ("dynamic_setattr_from_extra_allow_model_dump", 19),
    }


def test_scan_source_allows_explicit_allow_comment_suppression():
    offenders = check_pydantic_persistence_writes.scan_source(
        """
from pydantic import BaseModel, ConfigDict


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str | None = None


class Thing(BaseModel):
    title: str = ""


def patch_thing(request: PatchRequest) -> None:
    thing = Thing(title="x")
    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        # pydantic-persistence-guardrail: allow intentional metadata passthrough
        setattr(thing, field, value)
""",
        "fichero-server/src/fichero_server/api/routes/things.py",
    )

    assert offenders == []


def test_main_returns_nonzero_and_prints_offender_location(
    monkeypatch, capsys, tmp_path
):
    root = tmp_path
    routes_dir = root / "fichero-server" / "src" / "fichero" / "api" / "routes"
    routes_dir.mkdir(parents=True)
    route = routes_dir / "things.py"
    route.write_text(
        """
from pydantic import BaseModel, ConfigDict


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str | None = None


class Thing(BaseModel):
    title: str = ""


def patch_thing(request: PatchRequest) -> None:
    thing = Thing(title="x")
    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(thing, field, value)
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_pydantic_persistence_writes, "ROOT", root)
    monkeypatch.setattr(check_pydantic_persistence_writes, "ROUTES_DIR", routes_dir)
    monkeypatch.setattr(check_pydantic_persistence_writes, "ALLOWLIST", {})
    monkeypatch.setattr(
        check_pydantic_persistence_writes.sys,
        "argv",
        ["check_pydantic_persistence_writes.py"],
    )

    assert check_pydantic_persistence_writes.main() == 1
    output = capsys.readouterr().out
    assert "Pydantic persistence guardrail" in output
    assert "fichero-server/src/fichero_server/api/routes/things.py:18" in output
    assert "dynamic_setattr_from_extra_allow_model_dump" in output
