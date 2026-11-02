"""`sharing.trust-rule-is-one-function` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.2).

Which hosts are trusted by the system (Tailscale's certificate, no pin) and which need the link's pin is written once, in
`test-fixtures/files/trust_rule_table.json`. This test reads it over the CLI's rule; `RemoteCertificatePinningTests.swift`
reads the same file over the app's, so the two cannot drift.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_cli import pairing

TABLE = json.loads((Path(__file__).resolve().parents[2] / "test-fixtures" / "files" / "trust_rule_table.json").read_text())


@pytest.mark.parametrize("row", TABLE, ids=[r["host"] for r in TABLE])
def test_the_cli_follows_the_trust_table(row):
    assert pairing._is_public_ca(row["host"]) is row["public_ca"]


@pytest.mark.parametrize("row", TABLE, ids=[r["host"] for r in TABLE])
def test_a_link_carries_a_pin_only_where_the_table_says_to(row):
    link = pairing.invite_link(api_url=f"https://{row['host']}:8765", code="ABCD-1234", spki="c3BraS1waW4=", expires_at=None, library_path=None)
    assert ("spki" in json.loads(pairing._payload_of(link))) is (not row["public_ca"])
