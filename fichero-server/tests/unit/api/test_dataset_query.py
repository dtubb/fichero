"""Dataset query surface (datasets Stage 2) — REAL DuckDB, no mocks.

The endpoint is SQL over json_extract; a mocked db would test nothing but
string concatenation. Every renderer shape runs against a real temp
library: paging with typed sort, typed filters, date bins, facet counts,
and the defaults sidecar (including the unresolved-prototype honesty).
"""

import pytest

from fichero_server.api.routes.document.dataset import (
    DatasetBins,
    DatasetFilter,
    DatasetQuery,
    DatasetSort,
    dataset_query,
)
from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)

WEATHER = ["fair", "rain", "fog", "snow"]


@pytest.fixture
def dataset_db(tmp_path):
    db = Database(path=tmp_path / "t.duckdb")
    db.save(Document(id="folder", name="Diary", doc_type=DocType.folder))
    db.save(
        ClassificationValue(
            dimension=ClassificationDimension.document_prototype,
            key="entry",
            label="Entry",
            attributes={"source": "unknown", "date": {"type": "date", "role": "date"}},
        )
    )
    for i in range(40):
        db.save(
            Document(
                id=f"d{i}",
                name=f"Entry {i:02d}",
                parent_id="folder",
                doc_type=DocType.file,
                prototype_key="entry",
                attributes={
                    "date": f"1890-{1 + (i % 4):02d}-{1 + (i % 28):02d}",
                    "weather": WEATHER[i % 4],
                    "temperature": float(i),
                },
            )
        )
    # One row with NO date — must sort last and stay out of the bins.
    db.save(
        Document(
            id="undated",
            name="Undated",
            parent_id="folder",
            doc_type=DocType.file,
            prototype_key="entry",
            attributes={"weather": "fair"},
        )
    )
    return db


class TestDatasetQuery:
    @pytest.mark.asyncio
    async def test_paged_sort_by_date_nulls_last(self, dataset_db):
        result = await dataset_query(
            DatasetQuery(
                parent_id="folder",
                sort=DatasetSort(attr="date", direction="asc", type="date"),
                limit=10,
            ),
            db=dataset_db,
        )
        assert result["total"] == 41
        assert len(result["rows"]) == 10
        dates = [r["attributes"].get("date") for r in result["rows"]]
        assert dates == sorted(dates), "server-side date sort"
        # The undated row lands on the LAST page, never the first.
        assert all(r["id"] != "undated" for r in result["rows"])
        last = await dataset_query(
            DatasetQuery(
                parent_id="folder",
                sort=DatasetSort(attr="date", direction="asc", type="date"),
                limit=10,
                offset=40,
            ),
            db=dataset_db,
        )
        assert [r["id"] for r in last["rows"]] == ["undated"]

    @pytest.mark.asyncio
    async def test_typed_filters(self, dataset_db):
        result = await dataset_query(
            DatasetQuery(
                parent_id="folder",
                filters=[
                    DatasetFilter(attr="weather", op="eq", value="rain"),
                    DatasetFilter(
                        attr="temperature", op="gte", value=10, type="number"
                    ),
                ],
            ),
            db=dataset_db,
        )
        # rain = i % 4 == 1 → i in {1,5,…,37}; of those, temperature=i ≥ 10
        # leaves {13,17,21,25,29,33,37}.
        assert result["total"] == 7
        for row in result["rows"]:
            assert row["attributes"]["weather"] == "rain"
            assert row["attributes"]["temperature"] >= 10

    @pytest.mark.asyncio
    async def test_month_bins_exclude_unset(self, dataset_db):
        result = await dataset_query(
            DatasetQuery(
                parent_id="folder",
                limit=1,
                bins=DatasetBins(attr="date", granularity="month"),
            ),
            db=dataset_db,
        )
        bins = {b["bin"]: b["count"] for b in result["bins"]}
        assert bins == {"1890-01": 10, "1890-02": 10, "1890-03": 10, "1890-04": 10}

    @pytest.mark.asyncio
    async def test_facet_counts(self, dataset_db):
        result = await dataset_query(
            DatasetQuery(parent_id="folder", limit=1, facets=["weather"]),
            db=dataset_db,
        )
        counts = {f["value"]: f["count"] for f in result["facets"]["weather"]}
        assert counts == {"fair": 11, "rain": 10, "fog": 10, "snow": 10}

    @pytest.mark.asyncio
    async def test_defaults_sidecar_and_unresolved_honesty(self, dataset_db):
        result = await dataset_query(
            DatasetQuery(parent_id="folder", limit=5), db=dataset_db
        )
        assert result["defaults_by_prototype"]["entry"]["source"] == "unknown"

        # A row whose prototype no longer resolves reports the error, never
        # silently drops the key.
        dataset_db.save(
            Document(
                id="orphan",
                name="Orphan",
                parent_id="folder",
                doc_type=DocType.file,
                prototype_key="missing_proto",
            )
        )
        result = await dataset_query(
            DatasetQuery(parent_id="folder", limit=500), db=dataset_db
        )
        assert "_unresolved" in result["defaults_by_prototype"]["missing_proto"]

    @pytest.mark.asyncio
    async def test_attribute_names_cannot_inject(self, dataset_db):
        # A hostile attribute name is data, not SQL: bound as a json path,
        # it matches nothing and the query still runs.
        result = await dataset_query(
            DatasetQuery(
                parent_id="folder",
                filters=[
                    DatasetFilter(
                        attr="x) OR 1=1 --", op="eq", value="anything"
                    )
                ],
            ),
            db=dataset_db,
        )
        assert result["total"] == 0
