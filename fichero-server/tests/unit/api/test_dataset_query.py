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
    async def test_recursive_scope_reaches_grandchildren(self, dataset_db):
        # The REAL diary shape (Daniel 2026-08-14 live): entries hang under
        # IMAGE pages, which hang under the browsed folder — two levels down.
        # The store always queries recursive=True; a CTE that only reaches
        # direct children renders "No Items" over 204 pages of entries.
        dataset_db.save(
            Document(id="img1", name="page img", parent_id="folder", doc_type=DocType.file)
        )
        dataset_db.save(
            Document(
                id="entry1",
                name="1942-01-04",
                parent_id="img1",
                doc_type=DocType.file,
                prototype_key="entry",
                attributes={"date": "1942-01-04", "weather": "fair"},
            )
        )
        flat = await dataset_query(
            DatasetQuery(parent_id="folder", recursive=False, limit=500), db=dataset_db
        )
        assert all(r["id"] != "entry1" for r in flat["rows"])
        deep = await dataset_query(
            DatasetQuery(parent_id="folder", recursive=True, limit=500), db=dataset_db
        )
        ids = {r["id"] for r in deep["rows"]}
        assert "entry1" in ids, "recursive scope must reach grandchildren"
        assert "img1" in ids


    @pytest.mark.asyncio
    async def test_attributed_only_excludes_bare_images_and_excerpt_carries_text(
        self, dataset_db
    ):
        # The live confusion (Daniel 2026-08-14 night): entry rows AND their
        # source page images interleaved in the data views, and entries showed
        # "just dates, no transcript".
        dataset_db.save(
            Document(id="img1", name="page.png", parent_id="folder", doc_type=DocType.file)
        )
        dataset_db.save(
            Document(
                id="entry1",
                name="1942-01-04",
                parent_id="img1",
                doc_type=DocType.file,
                prototype_key="entry",
                attributes={"date": "1942-01-04"},
                page_content="Rained all day. Went to Istmina by canoe.",
            )
        )
        result = await dataset_query(
            DatasetQuery(parent_id="folder", recursive=True, attributed_only=True, limit=500),
            db=dataset_db,
        )
        ids = {r["id"] for r in result["rows"]}
        assert "entry1" in ids
        assert "img1" not in ids, "a bare image carries no data; it is not a dataset row"
        # A TRANSCRIBED image carries data (its text) and joins the views.
        dataset_db.save(
            Document(
                id="img2",
                name="page2.png",
                parent_id="folder",
                doc_type=DocType.file,
                page_content="Went up to dredge for clean-up.",
            )
        )
        again = await dataset_query(
            DatasetQuery(parent_id="folder", recursive=True, attributed_only=True, limit=500),
            db=dataset_db,
        )
        again_ids = {r["id"] for r in again["rows"]}
        assert "img2" in again_ids, "a transcribed page IS a dataset row"
        assert "img1" not in again_ids
        assert result["total"] == 42  # 40 + undated + entry1, image excluded
        entry = next(r for r in result["rows"] if r["id"] == "entry1")
        assert entry["excerpt"].startswith("Rained all day.")

    @pytest.mark.asyncio
    async def test_extract_dates_documents_appear_with_their_iso_date(self, dataset_db):
        # Extract Dates writes date COLUMNS, not attributes (Daniel
        # 2026-08-15: "I run extract dates … I don't see it") — a dated
        # document with no attributes/prototype must still be a data-view
        # row, carrying the converted ISO the renderers bin on.
        dataset_db.save(
            Document(
                id="dated-scan",
                name="scan_007.png",
                parent_id="folder",
                doc_type=DocType.file,
                date_original="Jan. 8th 1942",
                date_jdn=2430368,
                date_meta={"status": "dated", "converted_gregorian_iso": "1942-01-08"},
            )
        )
        result = await dataset_query(
            DatasetQuery(parent_id="folder", recursive=True, attributed_only=True, limit=500),
            db=dataset_db,
        )
        row = next((r for r in result["rows"] if r["id"] == "dated-scan"), None)
        assert row is not None, "a dated document carries data; attributed_only must keep it"
        assert row["date_iso"] == "1942-01-08"
        assert row["date_original"] == "Jan. 8th 1942"

    @pytest.mark.asyncio
    async def test_sidebar_prefixed_parent_id_is_normalized(self, dataset_db):
        # The sidebar passes "doc:UUID" ids; matched raw, every sidebar-driven
        # data view rendered zero rows while the data sat there (2026-08-15).
        result = await dataset_query(
            DatasetQuery(parent_id="doc:folder", recursive=True, limit=500),
            db=dataset_db,
        )
        assert result["total"] > 0, "a doc:-prefixed scope must match its bare id"

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

    # Search scoping (Daniel 2026-08-22): a data view under an active search
    # must show ONLY the hits — the "91 results over 4,237 items" defect.
    @pytest.mark.asyncio
    async def test_ids_scope_constrains_rows(self, dataset_db):
        result = await dataset_query(
            DatasetQuery(parent_id="folder", ids=["d1"], limit=500),
            db=dataset_db,
        )
        assert result["total"] == 1
        assert [row["id"] for row in result["rows"]] == ["d1"]

    @pytest.mark.asyncio
    async def test_empty_ids_scope_matches_nothing_never_all(self, dataset_db):
        # Zero search hits = zero rows. An empty scope that fell through to
        # "unscoped" would resurrect the whole-folder listing under a search.
        result = await dataset_query(
            DatasetQuery(parent_id="folder", ids=[], limit=500),
            db=dataset_db,
        )
        assert result["total"] == 0
        assert result["rows"] == []

    @pytest.mark.asyncio
    async def test_none_ids_is_unscoped(self, dataset_db):
        scoped = await dataset_query(
            DatasetQuery(parent_id="folder", ids=None, limit=500), db=dataset_db
        )
        assert scoped["total"] >= 2

