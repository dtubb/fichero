#!/usr/bin/env python3
"""Datasets Stage 2 scale measurement: 100k attribute-bearing nodes in DuckDB.

The spec's (§4) central backend question before the grid locks in: at
100,000 rows, is per-query ``json_extract`` over ``Document.attributes``
fast enough for grid paging / timeline binning / calendar binning / facet
counts, or do hot attributes need promotion (materialized typed columns)?

Three storage strategies over the SAME synthetic data:
  json      — attributes stay a JSON column; every query extracts inline.
  promoted  — hot attributes are real typed columns (what a promotion
              migration would produce), plus ART indexes.
  hybrid    — JSON storage with typed GENERATED columns extracted from it
              (promotion without a second write path).

Query shapes, straight from the renderer table (spec §3.1):
  page      — grid page: ORDER BY date LIMIT 50 OFFSET 50_000 (deep page).
  filter    — typed filter: date range + select equality, COUNT + first page.
  timeline  — month binning: COUNT GROUP BY month(date).
  facet     — facet counts: COUNT GROUP BY weather.
  aggregate — AVG(temperature) per month (summarize-row shape).

Usage: python fichero-server/scripts/bench_attribute_scale.py [rows]
Writes a markdown table to stdout. Pure measurement — no library touched.
"""

from __future__ import annotations

import json
import statistics
import sys
import time

import duckdb

ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
REPEATS = 5
WEATHER = ["fair", "rain", "fog", "snow"]


def _attributes(i: int) -> str:
    return json.dumps(
        {
            "date": f"{1870 + (i % 40)}-{1 + (i % 12):02d}-{1 + (i % 28):02d}",
            "weather": WEATHER[i % 4],
            "temperature": (i % 400) / 10.0,
            "title": f"Entry {i}",
        }
    )


def _seed(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE TABLE docs (id VARCHAR, prototype_key VARCHAR, attributes JSON)")
    rows = [(f"d{i}", "diary_entry", _attributes(i)) for i in range(ROWS)]
    con.executemany("INSERT INTO docs VALUES (?, ?, ?)", rows)


def _promote(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE docs_promoted AS
        SELECT id, prototype_key,
               CAST(json_extract_string(attributes, '$.date') AS DATE) AS attr_date,
               json_extract_string(attributes, '$.weather')            AS attr_weather,
               CAST(json_extract_string(attributes, '$.temperature') AS DOUBLE) AS attr_temp
        FROM docs
        """
    )
    con.execute("CREATE INDEX idx_p_date ON docs_promoted(attr_date)")
    con.execute("CREATE INDEX idx_p_weather ON docs_promoted(attr_weather)")


def _hybrid(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE docs_hybrid (
            id VARCHAR, prototype_key VARCHAR, attributes JSON,
            attr_date DATE GENERATED ALWAYS AS
                (CAST(json_extract_string(attributes, '$.date') AS DATE)) VIRTUAL,
            attr_weather VARCHAR GENERATED ALWAYS AS
                (json_extract_string(attributes, '$.weather')) VIRTUAL
        )
        """
    )
    con.execute("INSERT INTO docs_hybrid (id, prototype_key, attributes) SELECT * FROM docs")


QUERIES: dict[str, dict[str, str]] = {
    "json": {
        "page": """
            SELECT id FROM docs
            ORDER BY json_extract_string(attributes, '$.date')
            LIMIT 50 OFFSET 50000""",
        "filter": """
            SELECT COUNT(*) FROM docs
            WHERE json_extract_string(attributes, '$.date') BETWEEN '1880-01-01' AND '1890-12-31'
              AND json_extract_string(attributes, '$.weather') = 'rain'""",
        "timeline": """
            SELECT substr(json_extract_string(attributes, '$.date'), 1, 7) AS m, COUNT(*)
            FROM docs GROUP BY m ORDER BY m""",
        "facet": """
            SELECT json_extract_string(attributes, '$.weather') AS w, COUNT(*)
            FROM docs GROUP BY w""",
        "aggregate": """
            SELECT substr(json_extract_string(attributes, '$.date'), 1, 7) AS m,
                   AVG(CAST(json_extract_string(attributes, '$.temperature') AS DOUBLE))
            FROM docs GROUP BY m""",
    },
    "promoted": {
        "page": "SELECT id FROM docs_promoted ORDER BY attr_date LIMIT 50 OFFSET 50000",
        "filter": """
            SELECT COUNT(*) FROM docs_promoted
            WHERE attr_date BETWEEN DATE '1880-01-01' AND DATE '1890-12-31'
              AND attr_weather = 'rain'""",
        "timeline": """
            SELECT date_trunc('month', attr_date) AS m, COUNT(*)
            FROM docs_promoted GROUP BY m ORDER BY m""",
        "facet": "SELECT attr_weather, COUNT(*) FROM docs_promoted GROUP BY attr_weather",
        "aggregate": """
            SELECT date_trunc('month', attr_date) AS m, AVG(attr_temp)
            FROM docs_promoted GROUP BY m""",
    },
    "hybrid": {
        "page": "SELECT id FROM docs_hybrid ORDER BY attr_date LIMIT 50 OFFSET 50000",
        "filter": """
            SELECT COUNT(*) FROM docs_hybrid
            WHERE attr_date BETWEEN DATE '1880-01-01' AND DATE '1890-12-31'
              AND attr_weather = 'rain'""",
        "timeline": """
            SELECT date_trunc('month', attr_date) AS m, COUNT(*)
            FROM docs_hybrid GROUP BY m ORDER BY m""",
        "facet": "SELECT attr_weather, COUNT(*) FROM docs_hybrid GROUP BY attr_weather",
        "aggregate": """
            SELECT date_trunc('month', attr_date) AS m,
                   AVG(CAST(json_extract_string(attributes, '$.temperature') AS DOUBLE))
            FROM docs_hybrid GROUP BY m""",
    },
}


def _median_ms(con: duckdb.DuckDBPyConnection, sql: str) -> float:
    times = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        con.execute(sql).fetchall()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def main() -> None:
    con = duckdb.connect()  # in-memory; measures compute, not disk
    seed_start = time.perf_counter()
    _seed(con)
    seed_ms = (time.perf_counter() - seed_start) * 1000
    _promote(con)
    _hybrid(con)

    print(f"# Attribute scale measurement — {ROWS:,} rows, median of {REPEATS}")
    print(f"duckdb {duckdb.__version__}; seed {seed_ms:.0f}ms\n")
    shapes = list(QUERIES["json"])
    print("| query | json (ms) | promoted (ms) | hybrid (ms) |")
    print("|---|---|---|---|")
    for shape in shapes:
        cells = [f"{_median_ms(con, QUERIES[s][shape]):.1f}" for s in QUERIES]
        print(f"| {shape} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
