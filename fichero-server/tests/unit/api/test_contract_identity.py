"""#5047 — `contract.runtime-compatibility`, engine half.

Spec: `docs/contributor_manual/specs/harness/version-and-contract-integrity.md`.

The engine must be able to say WHICH contract its wire speaks, so a remote app
can refuse a connection when the two builds disagree and name both versions
(ruling 1). `backend_version` cannot answer that: two builds can share a
contract, and one build can change it.

These assert the BEHAVIOUR — that the reported identity is the identity of the
document the client is generated from, that it is stated once rather than
recomputed, and that a missing identity is reported as absent rather than
invented.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero_server.api import main as api_main  # noqa: E402
from fichero_server.models import ContractIdentity, HealthResponse  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
COMMITTED_CONTRACT = REPO_ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"
# Every copy of the contract. The Swift client bakes its identity from ITS copy,
# so if these ever differ byte-for-byte the two ends hash different documents and
# every remote connection refuses on a false premise.
CONTRACT_COPIES = (
    COMMITTED_CONTRACT,
    REPO_ROOT / "fichero" / "fichero-api-client" / "Sources" / "FicheroAPIClient" / "openapi.json",
    REPO_ROOT / "docs" / "contributor_manual" / "api-reference" / "openapi.json",
)


def _committed_contract_bytes() -> bytes:
    # Rule 0: a guard that cannot read its input FAILS. An unreadable contract
    # must never let these tests pass by comparing nothing to nothing.
    assert COMMITTED_CONTRACT.is_file(), f"committed contract missing: {COMMITTED_CONTRACT}"
    raw = COMMITTED_CONTRACT.read_bytes()
    assert raw, f"committed contract is empty: {COMMITTED_CONTRACT}"
    return raw


def test_engine_states_the_contract_it_speaks():
    """The identity the engine reports IS the committed contract's identity."""
    raw = _committed_contract_bytes()
    identity = api_main._resolve_contract_identity()
    assert identity is not None, (
        "this engine cannot state its contract; run sync_openapi_schema.sh"
    )
    assert identity.sha256 == hashlib.sha256(raw).hexdigest()
    assert identity.version == json.loads(raw)["info"]["version"]


def test_health_surfaces_the_identity_for_the_connect_time_check(client):
    """`GET /api/health` carries it, because that is where connect-time looks."""
    payload = client.get("/api/health").json()
    contract = payload.get("contract")
    assert contract is not None, "health must report the contract, not only backend_version"

    raw = _committed_contract_bytes()
    assert contract["version"] == json.loads(raw)["info"]["version"]
    assert contract["sha256"] == hashlib.sha256(raw).hexdigest()

    # The thing this replaces: backend_version is the APP version and is NOT the
    # contract identity. Asserting they are reported separately keeps a future
    # change from quietly collapsing one into the other.
    assert "backend_version" in payload
    assert payload["backend_version"] != contract["sha256"]


def test_identity_is_stated_once_not_recomputed_per_request(client, monkeypatch):
    """Computed at import. The contract is ~2 MB; per-request hashing is absurd.

    Proven by swapping the module-level constant for a sentinel: if the handler
    reported it, the handler is reading the constant. A handler that recomputed
    per request would keep reporting the real identity and ignore the swap.
    """
    sentinel = ContractIdentity(version="0.0.0-sentinel", sha256="0" * 64)
    monkeypatch.setattr(api_main, "_CONTRACT_IDENTITY", sentinel)
    reported = client.get("/api/health").json()["contract"]
    assert reported == {"version": "0.0.0-sentinel", "sha256": "0" * 64}
    # Stable across calls, so nothing is being rebuilt behind the constant.
    assert client.get("/api/health").json()["contract"] == reported


def test_a_missing_identity_is_absent_not_invented(monkeypatch, caplog):
    """An engine that cannot state its contract says so — no placeholder.

    The client refuses an unverifiable remote connection (ruling 1), so absence
    must be distinguishable from agreement. A fabricated "dev" or "" here would
    read as a real identity and could even MATCH another broken build.
    """
    import builtins

    real_import = builtins.__import__

    def _refuse_identity_module(name, *args, **kwargs):
        if name == "fichero_server.api.contract_identity_generated":
            raise ImportError("simulated: contract identity was never generated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _refuse_identity_module)
    with caplog.at_level("ERROR"):
        assert api_main._resolve_contract_identity() is None
    # Loud, and it names the fix — rule 0.
    assert any("contract_identity_generated" in r.message for r in caplog.records)
    assert any("sync_openapi_schema.sh" in r.message for r in caplog.records)

    # And an engine with no identity still serializes honestly rather than 500ing.
    assert HealthResponse(status="healthy", contract=None).contract is None


def test_identity_is_a_typed_field_not_a_dict():
    """AGENTS.md: a structured payload is a typed field, never `dict[str, Any]`.

    A dict here would generate a Swift `[String: String]`, and the comparison
    that decides whether to refuse a connection would be string-keyed lookups
    that no generator could check.
    """
    field = HealthResponse.model_fields["contract"]
    assert field.annotation is not None
    assert ContractIdentity in getattr(field.annotation, "__args__", (field.annotation,))
    assert set(ContractIdentity.model_fields) == {"version", "sha256"}
    assert all(f.annotation is str for f in ContractIdentity.model_fields.values())


@pytest.mark.parametrize("copy_path", CONTRACT_COPIES, ids=lambda p: p.parent.name)
def test_every_contract_copy_hashes_the_same(copy_path):
    """Both ends can only agree if they hash the same bytes.

    `sync_openapi_schema.sh` `cp`s one document to all three homes. A drifted
    copy is invisible today — the Swift package's copy is what the app bakes
    its identity from, so drift there refuses every connection while every
    other check stays green (#5046's failure shape).
    """
    assert copy_path.is_file(), f"contract copy missing: {copy_path}"
    expected = hashlib.sha256(_committed_contract_bytes()).hexdigest()
    assert hashlib.sha256(copy_path.read_bytes()).hexdigest() == expected


def test_baked_version_tracks_pyproject():
    """Ruling 2: `info.version` ALWAYS equals `pyproject.toml`.

    Checked here too, at the identity, because this is the value that decides a
    refusal — a stale one would name the wrong version to the user.
    """
    pyproject = REPO_ROOT / "fichero-server" / "pyproject.toml"
    assert pyproject.is_file(), f"pyproject missing: {pyproject}"
    declared = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in pyproject.read_text().splitlines()
        if line.startswith("version =")
    )
    identity = api_main._resolve_contract_identity()
    assert identity is not None
    assert identity.version == declared


def test_exporter_bakes_the_identity_of_the_bytes_it_wrote(tmp_path):
    """The generator hashes the FILE it produced, not the dict in memory.

    Every other copy of the contract is `cp`ed from that file, and the Swift
    client bakes its identity from one of those copies — so the file's bytes are
    the only thing both ends can agree on. Hashing a re-serialised dict would
    drift on any formatting change.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fichero_openapi_exporter_probe",
        REPO_ROOT / "fichero-server" / "scripts" / "export_openapi_schema.py",
    )
    assert spec is not None and spec.loader is not None
    # Importing the exporter constructs the FastAPI app, which is slow but is
    # also the only honest way to test the real writer rather than a copy of it.
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    contract = tmp_path / "openapi.json"
    contract.write_text(json.dumps({"info": {"version": "2026.1.1"}}, indent=2))
    out = tmp_path / "contract_identity_generated.py"

    digest = module.write_contract_identity(contract.read_bytes(), path=out)
    assert digest == hashlib.sha256(contract.read_bytes()).hexdigest()

    namespace: dict[str, object] = {}
    exec(compile(out.read_text(), str(out), "exec"), namespace)
    assert namespace["CONTRACT_VERSION"] == "2026.1.1"
    assert namespace["CONTRACT_SHA256"] == digest

    # Idempotent: a no-op sync must not churn the file.
    before = out.stat().st_mtime_ns
    module.write_contract_identity(contract.read_bytes(), path=out)
    assert out.stat().st_mtime_ns == before
