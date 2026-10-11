"""Every persisted id field is classified for a transfer between projects (#5657).

WHY: a move between projects re-points every id inside the moved set and cuts every id that
crosses its edge (`source/moving-between-projects.md`, "The id map"). The adversarial review found
four tables the first draft forgot (hand attributions, letterform descriptions, declared signs'
pictures, canvas link items). A forgotten id field is a dangling id after a move. So every id field
the engine persists must appear, in ONE bucket with a reason, in
`fichero_server/transfer/id_map_classification.py`; a new one fails here until its author decides.

Three enumerations, none hand-kept:
- every model in `Database._all_schema_models` and every pydantic model nested in its fields;
- every column of every table created by hand-written SQL (`CREATE TABLE IF NOT EXISTS` /
  `ALTER TABLE ... ADD COLUMN`) in the engine's source;
- every key the correction-episode ledger writes (recorded for real into a temporary package).
"""

from __future__ import annotations

import json
import re
import typing
from pathlib import Path

from pydantic import BaseModel

from fichero_server.db import Database
from fichero_server.observability import episodes
from fichero_server.transfer import id_map_classification as cls

ENGINE_SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"

HOW_TO_FIX = (
    "Classify it in fichero_server/transfer/id_map_classification.py: MAPPED (travels, re-pointed), "
    "CUT (stays in the source, cut and listed when it names a moved item), RECOMPUTED (derived), "
    "PROJECT_VOCAB (matched by key in the target) or NOT_DOCUMENT_SCOPED (never re-pointed), with a "
    "one-line reason; then say what a transfer does with it in "
    "docs/contributor_manual/specs/source/moving-between-projects.md."
)


def _is_id_name(name: str) -> bool:
    return name.endswith("_id") or name.endswith("_ids")


def _nested_models(annotation, out: list[type[BaseModel]]) -> None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        out.append(annotation)
        return
    for arg in typing.get_args(annotation):
        _nested_models(arg, out)


def _walked_models() -> dict[type[BaseModel], set[str]]:
    """Every schema model and every model nested in one, with the tables that hold it."""
    seen: dict[type[BaseModel], set[str]] = {}

    def walk(model: type[BaseModel], holder: str) -> None:
        if model in seen:
            seen[model].add(holder)
            return
        seen[model] = {holder}
        for field in model.model_fields.values():
            nested: list[type[BaseModel]] = []
            _nested_models(field.annotation, nested)
            for sub in nested:
                walk(sub, holder)

    for model in Database._all_schema_models(None):
        walk(model, model.__name__)
    return seen


def _model_id_fields() -> dict[str, str]:
    out = {}
    for model, holders in _walked_models().items():
        for name in model.model_fields:
            if _is_id_name(name):
                out[f"{model.__name__}.{name}"] = ", ".join(sorted(holders))
    return out


_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+\"?(\w+)\"?\s*\(")
_ALTER = re.compile(r"ALTER TABLE\s+\"?(\w+)\"?\s+ADD COLUMN\s+(?:IF NOT EXISTS\s+)?\"?(\w+)\"?")


def _paren_body(text: str, open_at: int) -> str:
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : i]
    return ""


def _raw_sql_columns() -> dict[str, set[str]]:
    """table -> every column named in a hand-written CREATE TABLE / ADD COLUMN."""
    tables: dict[str, set[str]] = {}
    for path in sorted(ENGINE_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _CREATE.finditer(text):
            body = re.sub(r"\([^()]*\)", "", _paren_body(text, match.end() - 1))
            cols = {part.split()[0].strip('"') for part in body.split(",") if part.split()}
            tables.setdefault(match.group(1), set()).update(cols)
        for match in _ALTER.finditer(text):
            tables.setdefault(match.group(1), set()).add(match.group(2))
    return tables


def _raw_sql_id_fields() -> set[str]:
    return {
        f"table:{table}.{col}"
        for table, cols in _raw_sql_columns().items()
        for col in cols
        if _is_id_name(col)
    }


def _id_paths(value, prefix: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for key, sub in value.items():
            path = f"{prefix}{key}"
            if _is_id_name(key):
                out.add(path)
            out |= _id_paths(sub, path + ".")
    elif isinstance(value, list):
        for item in value:
            out |= _id_paths(item, prefix)
    return out


# --- the guard ------------------------------------------------------------------------------


def test_the_model_walk_finds_the_tables_the_review_found_forgotten():
    """The enumeration is not vacuous: the four the review caught are in it."""
    found = _model_id_fields()
    for key in (
        "HandAttribution.segment_id",
        "LetterformDescription.segment_id",
        "LetterformDescription.allograph_id",
        "DeclaredSign.picture_segment_id",
        "CanvasItem.source_item_id",
        "SpatialNode.source_id",
        "SourceAnchor.segment_id",  # nested: inside segments, readings, claims, marks
    ):
        assert key in found, key
    assert "table:sync_files.document_id" in _raw_sql_id_fields()


def test_every_model_id_field_is_classified():
    missing = {key: holders for key, holders in _model_id_fields().items() if key not in cls.CLASSIFICATION}
    assert not missing, (
        "Persisted id fields with no transfer classification "
        + "; ".join(f"{k} (in {v})" for k, v in sorted(missing.items()))
        + ". "
        + HOW_TO_FIX
    )


def test_every_raw_sql_id_column_is_classified():
    missing = sorted(key for key in _raw_sql_id_fields() if key not in cls.CLASSIFICATION)
    assert not missing, f"Hand-written SQL id columns with no transfer classification: {missing}. {HOW_TO_FIX}"


def test_every_episode_ledger_id_key_is_classified(tmp_path):
    """Record one of each episode kind for real and read the ledger back."""
    token = episodes.set_library(str(tmp_path))
    run_token = episodes.set_run_context({"thread_id": "t1", "workflow_id": "w1", "node": "n", "attempt": 1})
    try:
        first = episodes.record(subject={"document_id": "d1", "file": "f", "page_index": 0})
        episodes.record_correction(corrects_episode_id=first, artifact_id="a1", corrected_text="x")
        episodes.record_invalidation(stale_artifact_ids=["a2"], caused_by_episode_id=first)
    finally:
        episodes._episode_run_context.reset(run_token)
        episodes._episode_library_path.reset(token)
    written: set[str] = set()
    for path in (tmp_path / "episodes").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            written |= {f"episodes:{p}" for p in _id_paths(json.loads(line))}
    assert "episodes:subject.document_id" in written  # the read is not vacuous
    missing = sorted(key for key in written if key not in cls.CLASSIFICATION)
    assert not missing, f"Episode ledger id keys with no transfer classification: {missing}. {HOW_TO_FIX}"


def test_every_classification_names_a_field_that_exists():
    """No stale entries: a renamed or removed field is removed here too."""
    fields = {model.__name__: set(model.model_fields) for model in _walked_models()}
    tables = _raw_sql_columns()
    stale = []
    for key in cls.CLASSIFICATION:
        if key.startswith("episodes:"):
            continue  # written by callers across the engine; pinned by the ledger test above
        if key.startswith("table:"):
            table, col = key[len("table:") :].split(".", 1)
            if col not in tables.get(table, set()):
                stale.append(key)
            continue
        model, field = key.split(".", 1)
        if field not in fields.get(model, set()):
            stale.append(key)
    assert not stale, f"Classified fields that no longer exist: {stale}"


def test_every_entry_is_in_one_known_bucket_with_a_reason():
    for key, (bucket, reason) in cls.CLASSIFICATION.items():
        assert bucket in cls.BUCKETS, f"{key}: unknown bucket {bucket!r}"
        assert reason.strip(), f"{key}: no reason"


def test_walked_model_names_are_unique():
    """Keys are by class name; two classes of one name would share a classification silently."""
    names = [model.__name__ for model in _walked_models()]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"Two persisted models share a name: {dupes}"
