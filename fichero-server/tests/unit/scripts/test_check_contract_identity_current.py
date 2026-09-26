"""The guardrail that binds the baked contract identity to the contract (#5047).

`check_openapi_version_current.py` binds every contract's `info.version` to
`pyproject.toml`. This one binds the DIGEST to the document, which is a
different property and was unguarded until a merge exposed it.

**The incident these tests exist for.** On 2026-09-26, merging `integration`
into `spec/page-model` left the baked `CONTRACT_SHA256` hashing `integration`'s
contract while the branch's own contract was a different document. Nobody edited
anything; two correct branches combined into an incorrect state. A runtime
contract mismatch refuses a remote connection, so that branch would have shipped
an engine turning remote clients away — and the version guardrail could not see
it, because `info.version` matched on both sides.

`tests/unit/api/test_contract_identity.py` already asserts
`CONTRACT_SHA256 == digest`, but against a temp file it wrote moments earlier:
that proves the WRITER, not the committed pair. These tests are about the pair.

Shaped like `test_check_capability_reference_current.py`: drive the script's own
`--self-test` in a subprocess, then assert the properties a self-test cannot
assert about itself.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"
CHECK = SCRIPTS_DIR / "check_contract_identity_current.py"


@pytest.fixture(scope="module")
def module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import check_contract_identity_current as check

    return check


def _build(root: Path, *, contract: bytes, sha: str | None) -> None:
    """A minimal repo: a contract, and an identity file that may or may not
    hash it."""
    contract_path = root / "fichero-server/tests/contracts/openapi.json"
    identity_path = (
        root / "fichero-server/src/fichero_server/api/contract_identity_generated.py"
    )
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_bytes(contract)
    digest = hashlib.sha256(contract).hexdigest() if sha is None else sha
    identity_path.write_text(
        f'"""generated"""\n\nCONTRACT_VERSION = "1.2.3"\n'
        f'CONTRACT_SHA256 = "{digest}"\n'
    )


FAITHFUL = b'{"info": {"version": "1.2.3"}, "paths": {}}\n'


def test_self_test_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK), "--self-test"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_self_test_actually_exercises_a_mismatch() -> None:
    """A self-test that only ever proved the happy path would be decoration.

    Asserted on its OUTPUT, so a self-test quietly reduced to one case fails
    here rather than continuing to report success.
    """
    result = subprocess.run(
        [sys.executable, str(CHECK), "--self-test"],
        capture_output=True, text=True, timeout=60,
    )
    for expected in (
        "a faithful pair passes",
        "a digest of another document is caught",
        "a one-byte contract change is caught",
        "a MISSING contract goes BLIND, not pass",
        "an identity file with NO digest goes BLIND, not pass",
    ):
        assert expected in result.stdout, f"the self-test no longer covers: {expected}"


def test_the_real_repository_is_clean(module) -> None:
    """The committed pair agrees, right now, in this checkout.

    This is the assertion the whole guard exists for, and it is the one a
    self-test in a temp directory cannot make.
    """
    assert module.check(REPO_ROOT) == 0


def test_a_faithful_pair_passes(module, tmp_path) -> None:
    _build(tmp_path, contract=FAITHFUL, sha=None)
    assert module.check(tmp_path) == 0


def test_a_digest_of_another_document_is_caught(module, tmp_path) -> None:
    """THE 2026-09-26 SHAPE: a perfectly valid digest, of the wrong document.

    This is what a merge produces. The digest is well-formed, the version
    agrees, and the pair is still wrong.
    """
    other = hashlib.sha256(b'{"info": {"version": "1.2.3"}, "paths": {"/a": {}}}\n').hexdigest()
    _build(tmp_path, contract=FAITHFUL, sha=other)
    assert module.check(tmp_path) == 1


def test_a_one_byte_change_is_caught(module, tmp_path) -> None:
    _build(tmp_path, contract=FAITHFUL, sha=None)
    (tmp_path / "fichero-server/tests/contracts/openapi.json").write_bytes(
        FAITHFUL.replace(b"1.2.3", b"1.2.4")
    )
    assert module.check(tmp_path) == 1


def test_a_missing_contract_goes_blind_rather_than_passing(module, tmp_path) -> None:
    _build(tmp_path, contract=FAITHFUL, sha=None)
    (tmp_path / "fichero-server/tests/contracts/openapi.json").unlink()
    with pytest.raises(module.Blind):
        module.check(tmp_path)


def test_a_missing_identity_file_goes_blind(module, tmp_path) -> None:
    _build(tmp_path, contract=FAITHFUL, sha=None)
    (
        tmp_path / "fichero-server/src/fichero_server/api/contract_identity_generated.py"
    ).unlink()
    with pytest.raises(module.Blind):
        module.check(tmp_path)


def test_a_hand_edited_digest_that_is_not_hex_goes_blind(module, tmp_path) -> None:
    """A digest replaced by something that is not a digest must not read as
    "no digest to check" — the regex requires 64 hex characters, so a
    hand-edit to `"TODO"` is blindness, which is the honest answer."""
    _build(tmp_path, contract=FAITHFUL, sha=None)
    identity = (
        tmp_path / "fichero-server/src/fichero_server/api/contract_identity_generated.py"
    )
    identity.write_text(
        '"""generated"""\n\nCONTRACT_VERSION = "1.2.3"\nCONTRACT_SHA256 = "TODO"\n'
    )
    with pytest.raises(module.Blind):
        module.check(tmp_path)


def test_the_check_is_offline_and_imports_nothing_from_the_package(module) -> None:
    """`verify_all.sh` auto-runs every `scripts/check_*.py` with no arguments,
    and a guardrail that needs the network or builds the app breaks that sweep
    (a guardrail was deleted this morning for exactly that). Asserted on the
    source rather than trusted: no network client, no engine import."""
    source = CHECK.read_text(encoding="utf-8")
    for forbidden in (
        "import requests", "import httpx", "urllib.request", "socket",
        "from fichero_server", "import fichero_server", "TestClient",
    ):
        assert forbidden not in source, f"the guard must stay offline: found {forbidden}"


def test_it_runs_with_no_arguments_from_the_repo_root() -> None:
    """The exact invocation `verify_all.sh` uses."""
    result = subprocess.run(
        [sys.executable, str(CHECK)],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
