"""Every source-model record has a DECLARED table: an existing library gains it on open.

After the lead's review of the Reader's line map (a table created on first save bypasses the schema
and migration path every walker assumes), a sweep of the engine's `db.save`/`query`/`get` calls against
`Database._all_schema_models` found this programme's own records doing the same: hands, hand
attributions, rights records and declared signs. Declared now; this pins them.
"""

from __future__ import annotations

import duckdb
import pytest

from fichero_server.db import Database
from fichero_server.models.campaigns import Campaign, CampaignMembership, ReadingCampaigns
from fichero_server.models.editorial import EditorialFact
from fichero_server.models.georeference import ControlPointPlace, GeoreferencingSettings
from fichero_server.models.hands import Hand, HandAttribution
from fichero_server.models.letterforms import Allograph, LetterformDescription
from fichero_server.models.rights import RightsRecord
from fichero_server.models.signs import DeclaredSign

MODELS = [ControlPointPlace, GeoreferencingSettings, Hand, HandAttribution, RightsRecord, DeclaredSign, EditorialFact, Allograph, LetterformDescription,
          Campaign, CampaignMembership, ReadingCampaigns]


def _tables(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT table_name FROM duckdb_tables()").fetchall()}


@pytest.mark.parametrize("model", MODELS, ids=[m.__name__ for m in MODELS])
def test_declared_and_there_on_a_fresh_open(tmp_path, model):
    db = Database(tmp_path / "fresh.duckdb")
    try:
        assert model in db._all_schema_models()
        assert db._table_name(model) in _tables(db.conn)
    finally:
        db.close()


@pytest.mark.parametrize("model", MODELS, ids=[m.__name__ for m in MODELS])
def test_a_library_from_before_gains_it_on_open_not_on_first_save(tmp_path, model):
    path = tmp_path / "old.duckdb"
    first = Database(path)
    table = first._table_name(model)
    first.close()
    conn = duckdb.connect(str(path))
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.close()
    reopened = Database(path)
    try:
        assert table in _tables(reopened.conn)
        assert reopened.conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0
    finally:
        reopened.close()
