"""The Fichero 1.0 archive converter.

The fixtures build a miniature 1.0 document folder on disk — the same shape the
Compañía Minera archives have — so the tests exercise real path walking and real
manifest parsing rather than a mocked filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.errors import ValidationError
from fichero_server.importers import legacy_10_archive as legacy


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_folder(
    root: Path,
    name: str = "1936-Frank-E-Smith-contra-Compania-Minera",
    *,
    pages: int = 2,
    sizes: list[int] | None = None,
    catalogue: bool = True,
    truncated_step: bool = False,
) -> Path:
    """Build a minimal but faithful 1.0 document folder."""
    folder = root / name
    sizes = sizes or [7275431 + index for index in range(pages)]
    stems = [f"{name}-{index + 1}" for index in range(pages)]

    manifest_lines = [json.dumps({"path": name, "type": "directory"})]
    for stem, size in zip(stems, sizes):
        rel = f"{name}/{stem}.JPG"
        _write(folder / "documents" / rel, "jpg-bytes")
        manifest_lines.append(
            json.dumps(
                {
                    "path": rel,
                    "type": "file",
                    "mtime": 1751044512.7,
                    "size": size,
                    "format": "jpg",
                }
            )
        )
    _write(folder / legacy.MARKER, "\n".join(manifest_lines) + "\n")

    for stage, manifest_name in (
        ("crops", "crop_manifest.jsonl"),
        ("rotated", "rotate_manifest.jsonl"),
        ("enhanced", "enhance_manifest.jsonl"),
        ("background_removed", "background_removed_manifest.jsonl"),
    ):
        suffix = "png" if stage == "background_removed" else "jpg"
        lines = []
        for stem in stems:
            out_rel = f"{name}/{stem}.{suffix}"
            _write(folder / "assets" / stage / "documents" / out_rel, "img")
            details: dict = {}
            if stage == "crops":
                # The real crop record: a detected box in the EXIF-rotated
                # original frame, with both pixel sizes.
                details = {
                    "box": {"x1": 0, "y1": 62, "x2": 3107, "y2": 4796},
                    "confidence": 0.806,
                    "method": "yolo",
                    "original_size": [3107, 4839],
                    "cropped_size": [3107, 4734],
                }
            lines.append(
                json.dumps(
                    {
                        "source": f"{name}/{stem}.JPG",
                        "outputs": [out_rel],
                        "details": details,
                    }
                )
            )
        _write(folder / "assets" / stage / manifest_name, "\n".join(lines) + "\n")

    lines = []
    for index, stem in enumerate(stems):
        out_rel = f"{name}/{stem}.txt"
        _write(folder / "assets" / "transcriptions" / "documents" / out_rel,
               f"transcribed page {index + 1}")
        lines.append(
            json.dumps({"source": f"{name}/{stem}.png", "outputs": [out_rel],
                        "success": True})
        )
    _write(folder / "assets" / "transcriptions" / "transcription_manifest.jsonl",
           "\n".join(lines) + "\n")

    _write(
        folder / "assets" / "segmented" / "segment_manifest.jsonl",
        "\n".join(
            json.dumps(
                {
                    "source": f"{name}/{stem}.png",
                    "details": {
                        "num_segments": 3,
                        "segments": [{"index": 0, "bounding_box": [0, 1521]}],
                    },
                }
            )
            for stem in stems
        )
        + "\n",
    )
    _write(
        folder / "assets" / "segmented_transcriptions"
        / "segmented_transcription_manifest.jsonl",
        json.dumps(
            {
                "source": f"{name}/{stems[0]}_segments/segment_001.jpg",
                "outputs": ["x.txt"],
                "details": {"model": "qwen-vl-max", "has_content": True},
            }
        )
        + "\n",
    )

    _write(folder / "assets" / "word" / "documents" / f"{name}.docx", "docx")
    _write(folder / "logs" / "workflow_00)_default_20250629_214012.log",
           "[21:40:12] Workflow: 00) default\n[21:40:12] Task ID: abc\n")

    if catalogue:
        _write(
            folder / "assets" / "llm_catalogue" / "llm_process_manifest.jsonl",
            json.dumps({"source": "documents", "outputs": ["s.json"],
                        "files_processed": pages, "model": "gpt-4.1-mini"}) + "\n",
        )
        steps = folder / "assets" / "llm_catalogue" / "steps" / "documents"
        people = {
            "personas": [
                {
                    "nombre": "FRANK E. SMITH",
                    "ortografias_alternativas": ["Frank Smith"],
                    "contexto": "Demandante.",
                }
            ],
            "organizaciones": [
                {"nombre": "COMPAÑÍA MINERA CHOCÓ PACÍFICO", "contexto": "Demandada."}
            ],
            "ubicaciones": [{"nombre": "ANDAGOYA", "contexto": "Corregimiento."}],
        }
        payload = json.dumps(people, ensure_ascii=False)
        if truncated_step:
            # Exactly the 1.0 failure: the generation hit a length cap and the
            # JSON is cut off mid-object.
            payload = payload[: payload.index('"ubicaciones"') + 30]
        _write(
            steps / "extraer_entidades_personas_organizaciones_ubicaciones.json",
            json.dumps({"source": "/old/path", "step": "e", "result": payload},
                       ensure_ascii=False),
        )
        _write(
            steps / "linea_temporal.json",
            json.dumps(
                {
                    "source": "/old/path",
                    "step": "linea_temporal",
                    "result": {
                        "linea_temporal": [
                            {"fecha": "1919-12-10", "evento": "Smith comenzó a trabajar."}
                        ]
                    },
                },
                ensure_ascii=False,
            ),
        )
        _write(
            steps / "resumen.json",
            json.dumps({"source": "/old/path", "step": "resumen",
                        "result": {"resumen": "Un juicio laboral."}},
                       ensure_ascii=False),
        )
        _write(
            steps / "personas_clave_y_etiquetas.json",
            json.dumps(
                {
                    "source": "/old/path",
                    "step": "personas_clave_y_etiquetas",
                    "result": {
                        "personas_clave": [{"nombre": "FRANK E. SMITH"}],
                        "etiquetas": "juicio ejecutivo; cesantía",
                    },
                },
                ensure_ascii=False,
            ),
        )
    return folder


def _document_folder_node(scan) -> dict:
    """The DOCUMENT folder node, not the corpus root that groups them."""
    return next(
        n
        for n in legacy.to_canonical_nodes(scan)
        if n["node_type"] == "folder" and n.get("parent_external_id")
    )

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_finds_document_folder_at_any_depth(tmp_path: Path) -> None:
    """Depth VARIES between the two archives — detection is by marker."""
    shallow = tmp_path / "archive-a" / "04 Checked"
    deep = tmp_path / "archive-b" / "05 Posted" / "1930-1949_processed"
    build_folder(shallow, name="doc-shallow")
    build_folder(deep, name="doc-deep")

    found = {p.name for p in legacy.find_legacy_document_folders(tmp_path)}
    assert found == {"doc-shallow", "doc-deep"}


def test_does_not_descend_into_a_matched_folder(tmp_path: Path) -> None:
    """The assets/ tree of a matched folder is never walked — it is 21 GB."""
    folder = build_folder(tmp_path, name="doc")
    assert list(legacy.find_legacy_document_folders(folder)) == [folder]


def test_plain_folder_is_not_a_legacy_archive(tmp_path: Path) -> None:
    (tmp_path / "photos").mkdir()
    (tmp_path / "photos" / "a.jpg").write_text("x", encoding="utf-8")
    assert legacy.looks_like_legacy_archive(tmp_path) is False


def test_looks_like_legacy_archive_finds_a_nested_one(tmp_path: Path) -> None:
    build_folder(tmp_path / "05 Posted", name="doc")
    assert legacy.looks_like_legacy_archive(tmp_path) is True


# ---------------------------------------------------------------------------
# Reading one folder
# ---------------------------------------------------------------------------


def test_reads_pages_renditions_text_and_catalogue(tmp_path: Path) -> None:
    folder = build_folder(tmp_path, pages=3)
    entry = legacy.read_document_folder(folder, archive="Smaller", stage="04 Checked")

    assert len(entry.pages) == 3
    page = entry.pages[0]
    assert {image["role"] for image in page.images} == {
        "original", "crop", "rotated", "enhanced", "background_removed",
    }
    assert all(Path(image["source_path"]).is_file() for image in page.images)
    assert page.text_path is not None and Path(page.text_path).is_file()

    assert entry.year == "1936"
    assert entry.stage == "04 Checked"
    assert entry.summary == "Un juicio laboral."
    assert entry.tags == ["juicio ejecutivo", "cesantía"]
    assert entry.catalogue_model == "gpt-4.1-mini"
    assert entry.transcription_model == "qwen-vl-max"
    assert entry.workflow == "00) default"
    assert entry.segment_count == 3  # 3 pages × 1 recorded band
    assert entry.docx_count == 1

    names = {e["canonical_name"] for e in entry.entities}
    assert "FRANK E. SMITH" in names
    assert "ANDAGOYA" in names
    kinds = {e["canonical_name"]: e["entity_type"] for e in entry.entities}
    assert kinds["ANDAGOYA"] == "location"
    assert kinds["COMPAÑÍA MINERA CHOCÓ PACÍFICO"] == "organization"
    assert entry.timeline == [
        {"fecha": "1919-12-10", "evento": "Smith comenzó a trabajar."}
    ]


def test_pages_sort_numerically_not_lexically(tmp_path: Path) -> None:
    """``-99`` must precede ``-100``; string sorting gets this backwards."""
    folder = build_folder(tmp_path, name="doc", pages=120)
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    sequences = [page.sequence for page in entry.pages]
    assert sequences == sorted(sequences)
    assert sequences[:3] == [1, 2, 3]
    assert sequences[-1] == 120


def test_a_folder_without_a_catalogue_still_reads(tmp_path: Path) -> None:
    folder = build_folder(tmp_path, catalogue=False)
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    assert entry.pages
    assert entry.entities == []
    assert entry.catalogue_model is None


def test_unreadable_stage_manifest_warns_rather_than_raising(tmp_path: Path) -> None:
    folder = build_folder(tmp_path)
    (folder / "assets" / "crops" / "crop_manifest.jsonl").write_text(
        "{not json\n", encoding="utf-8"
    )
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    assert any("unparseable" in w for w in entry.warnings)
    roles = {image["role"] for image in entry.pages[0].images}
    assert "crop" not in roles
    assert "original" in roles


# ---------------------------------------------------------------------------
# The truncated-JSON salvage — real damage in the real archive
# ---------------------------------------------------------------------------


def test_salvage_recovers_complete_entries_from_truncated_json() -> None:
    text = '{"personas": [{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C'
    value, salvaged = legacy.salvage_json(text)
    assert salvaged is True
    assert [p["nombre"] for p in value["personas"]] == ["A", "B"]


def test_salvage_leaves_valid_json_alone() -> None:
    value, salvaged = legacy.salvage_json('{"a": [1, 2]}')
    assert salvaged is False
    assert value == {"a": [1, 2]}


def test_salvage_gives_up_rather_than_inventing() -> None:
    assert legacy.salvage_json("not json at all") == (None, False)
    assert legacy.salvage_json('{"a": "unterminated') == (None, False)


def test_truncated_catalogue_step_is_salvaged_and_reported(tmp_path: Path) -> None:
    folder = build_folder(tmp_path, truncated_step=True)
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    names = {e["canonical_name"] for e in entry.entities}
    # The entries before the cut survive; the cut-off one is gone for good.
    assert "FRANK E. SMITH" in names
    assert "ANDAGOYA" not in names
    assert entry.salvaged_steps
    assert any("truncated" in w for w in entry.warnings)


# ---------------------------------------------------------------------------
# Scanning and dedupe (Daniel's ruling 1)
# ---------------------------------------------------------------------------


def test_identical_folders_in_two_archives_import_once(tmp_path: Path) -> None:
    big, small = tmp_path / "Big", tmp_path / "Smaller"
    build_folder(big / "05 Posted", name="1936-doc", sizes=[111, 222])
    build_folder(small / "04 Checked", name="1936-doc", sizes=[111, 222])

    scan = legacy.scan_archives([big, small], corpus_name="Compañía Minera")
    assert len(scan.folders) == 1
    assert len(scan.duplicates) == 1
    assert scan.duplicates[0].duplicate_of == scan.folders[0].path


def test_dedupe_is_by_content_not_by_name(tmp_path: Path) -> None:
    """Same name, different pages — two different documents."""
    big, small = tmp_path / "Big", tmp_path / "Smaller"
    build_folder(big, name="1936-doc", sizes=[111, 222])
    build_folder(small, name="1936-doc", sizes=[333, 444])

    scan = legacy.scan_archives([big, small], corpus_name="c")
    assert len(scan.folders) == 2
    assert scan.duplicates == []


def test_differently_named_identical_folders_still_dedupe(tmp_path: Path) -> None:
    """Content identity, not path — a ``-1`` suffixed copy is the same doc."""
    big, small = tmp_path / "Big", tmp_path / "Smaller"
    build_folder(big, name="doc", sizes=[111, 222])
    build_folder(small, name="doc-1", sizes=[111, 222])
    scan = legacy.scan_archives([big, small], corpus_name="c")
    assert len(scan.folders) == 1


def test_unprocessed_folders_are_reported_not_silently_dropped(tmp_path: Path) -> None:
    root = tmp_path / "Archive"
    build_folder(root / "04 Checked", name="doc")
    raw = root / "05 posted" / "1946 loose scans"
    raw.mkdir(parents=True)
    (raw / "page_001.JPG").write_text("x", encoding="utf-8")

    scan = legacy.scan_archives([root], corpus_name="c")
    assert any("loose scans" in path for path in scan.unprocessed)


def test_scan_requires_a_real_directory(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        legacy.scan_archives([tmp_path / "nope"], corpus_name="c")
    with pytest.raises(ValidationError):
        legacy.scan_archives([], corpus_name="c")


# ---------------------------------------------------------------------------
# Canonical node emission
# ---------------------------------------------------------------------------


def test_nodes_are_canonical_and_parent_before_child(tmp_path: Path) -> None:
    build_folder(tmp_path / "Archive" / "04 Checked", name="1936-doc", pages=2)
    scan = legacy.scan_archives([tmp_path / "Archive"], corpus_name="Compañía Minera")
    nodes = list(legacy.to_canonical_nodes(scan))

    # The importer's own validator is the contract — run it.
    from fichero_server.importers.manifest_import import validate_nodes

    validate_nodes(nodes)

    kinds = [node["node_type"] for node in nodes]
    assert kinds == ["folder", "folder", "page", "page"]
    assert all(n["canonical_version"] == legacy.CANONICAL_VERSION for n in nodes)


def test_curation_stage_is_metadata_not_a_folder(tmp_path: Path) -> None:
    """Ruling 2: tiers flatten. No node is named for the stage."""
    build_folder(tmp_path / "Archive" / "04 Checked", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "Archive"], corpus_name="c")
    nodes = list(legacy.to_canonical_nodes(scan))

    assert not any(node["name"] == "04 Checked" for node in nodes)
    folder_node = nodes[1]
    assert folder_node["metadata"]["legacy_stage"] == "04 Checked"


def test_page_nodes_carry_every_rendition_as_a_linked_role(tmp_path: Path) -> None:
    build_folder(tmp_path / "A", name="1936-doc", pages=1)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    page = [n for n in legacy.to_canonical_nodes(scan) if n["node_type"] == "page"][0]

    roles = {image["role"] for image in page["images"]}
    assert roles == {"original", "crop", "rotated", "enhanced", "background_removed"}
    # Link mode: every path points at the file where it already lives.
    for image in page["images"]:
        assert Path(image["source_path"]).is_file()

    from fichero_server.importers.manifest_import import preferred_image

    assert preferred_image(page)["role"] == "enhanced"


def test_page_text_and_dates_ride_on_the_node(tmp_path: Path) -> None:
    build_folder(tmp_path / "A", name="1936-doc", pages=1)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    page = [n for n in legacy.to_canonical_nodes(scan) if n["node_type"] == "page"][0]
    assert page["text"] == "transcribed page 1"
    assert page["date"] == "1936"
    assert page["sequence"] == 1


def test_provenance_names_the_1_0_pipeline_and_both_models(tmp_path: Path) -> None:
    """Delta 1: two different models in one import, so it is per node."""
    build_folder(tmp_path / "A", name="1936-doc", pages=1)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    nodes = list(legacy.to_canonical_nodes(scan))
    folder_node = nodes[1]
    page_node = nodes[2]

    assert folder_node["provider"] == "fichero-1.0"
    assert folder_node["model"] == "gpt-4.1-mini"
    assert folder_node["step_name"] == "catalogue_folder"
    assert page_node["provider"] == "fichero-1.0"
    assert page_node["model"] == "qwen-vl-max"


def test_timeline_becomes_claims_with_stable_ids(tmp_path: Path) -> None:
    build_folder(tmp_path / "A", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    folder_node = list(legacy.to_canonical_nodes(scan))[1]

    claim = folder_node["claims"][0]
    assert claim["text"] == "Smith comenzó a trabajar."
    assert claim["metadata"]["fecha"] == "1919-12-10"
    assert claim["external_id"].endswith("#timeline:0")


def test_deferred_work_is_recorded_for_the_bbox_program(tmp_path: Path) -> None:
    """Ruling 3: deferred, but named — not silently dropped."""
    build_folder(tmp_path / "A", name="1936-doc", pages=2)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    folder_node = list(legacy.to_canonical_nodes(scan))[1]

    deferred = folder_node["metadata"]["legacy_deferred"]
    assert deferred["segment_strips"] == 2
    assert "background_removed" in deferred["segment_geometry"]
    assert deferred["docx"] == 1


def test_external_ids_are_stable_across_scans(tmp_path: Path) -> None:
    """Idempotency depends on this: the same archive yields the same ids."""
    build_folder(tmp_path / "A", name="1936-doc", pages=2)
    first = [n["external_id"] for n in
             legacy.to_canonical_nodes(legacy.scan_archives([tmp_path / "A"],
                                                            corpus_name="c"))]
    second = [n["external_id"] for n in
              legacy.to_canonical_nodes(legacy.scan_archives([tmp_path / "A"],
                                                             corpus_name="c"))]
    assert first == second


# ---------------------------------------------------------------------------
# Writing the manifest — never into the archive
# ---------------------------------------------------------------------------


def test_write_manifest_refuses_to_write_inside_the_archive(tmp_path: Path) -> None:
    archive = tmp_path / "Archive"
    build_folder(archive, name="1936-doc")
    scan = legacy.scan_archives([archive], corpus_name="c")

    with pytest.raises(ValidationError, match="Refusing to write"):
        legacy.write_manifest(scan, archive / "manifest.jsonl")


def test_write_manifest_round_trips(tmp_path: Path) -> None:
    archive = tmp_path / "Archive"
    build_folder(archive, name="1936-doc", pages=2)
    scan = legacy.scan_archives([archive], corpus_name="c")
    out = tmp_path / "scratch" / "manifest.jsonl"

    count = legacy.write_manifest(scan, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert count == len(lines) == 4
    assert all(json.loads(line)["canonical_version"] == legacy.CANONICAL_VERSION
               for line in lines)


def test_dry_run_report_names_what_is_not_imported(tmp_path: Path) -> None:
    archive = tmp_path / "Archive"
    build_folder(archive / "04 Checked", name="1936-doc", pages=2)
    scan = legacy.scan_archives([archive], corpus_name="Compañía Minera")

    report = legacy.dry_run_report(scan)
    assert "NOT IMPORTED" in report
    assert "segment strips" in report
    assert "qwen-vl-max" in report
    assert "gpt-4.1-mini" in report
    assert "flattened to metadata" in report


# ---------------------------------------------------------------------------
# Renditions: real rows, chained frames, real geometry
# ---------------------------------------------------------------------------


def test_crop_transform_is_normalised_against_the_original_frame() -> None:
    transform = legacy.crop_transform(
        {
            "box": {"x1": 0, "y1": 62, "x2": 3107, "y2": 4796},
            "method": "yolo",
            "original_size": [3107, 4839],
            "cropped_size": [3107, 4734],
        }
    )
    assert transform is not None
    x, y, width, height = transform["rect"]
    assert x == 0.0
    assert y == pytest.approx(62 / 4839)
    assert width == pytest.approx(1.0)
    assert height == pytest.approx((4796 - 62) / 4839)
    assert transform["space"] == "normalized"
    assert transform["confidence"] == "measured"
    assert transform["method"] == "fichero-1.0-yolo"


def test_crop_transform_refuses_nonsense_rather_than_guessing() -> None:
    assert legacy.crop_transform({}) is None
    assert legacy.crop_transform({"box": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}}) is None
    assert legacy.crop_transform(
        {"box": {"x1": 5, "y1": 0, "x2": 5, "y2": 10}, "original_size": [10, 10]}
    ) is None


def test_rendition_chain_is_recorded_stage_by_stage(tmp_path: Path) -> None:
    """Frames CHAIN — each stage derives from the previous one that ran."""
    build_folder(tmp_path / "A", name="1936-doc", pages=1)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    page = [n for n in legacy.to_canonical_nodes(scan) if n["node_type"] == "page"][0]
    by_role = {image["role"]: image for image in page["images"]}

    assert "derived_from_role" not in by_role["original"]
    assert by_role["crop"]["derived_from_role"] == "original"
    assert by_role["rotated"]["derived_from_role"] == "crop"
    assert by_role["enhanced"]["derived_from_role"] == "rotated"
    assert by_role["background_removed"]["derived_from_role"] == "enhanced"
    assert by_role["crop"]["transform"]["space"] == "normalized"
    assert by_role["crop"]["pixel_width"] == 3107
    assert by_role["original"]["pixel_width"] == 3107


def test_plan_renditions_builds_linked_rows_with_geometry(tmp_path: Path) -> None:
    from fichero_server.importers.manifest_renditions import plan_renditions
    from fichero_server.models import Document, DocType

    build_folder(tmp_path / "A", name="1936-doc", pages=1)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    page = [n for n in legacy.to_canonical_nodes(scan) if n["node_type"] == "page"][0]
    document = Document(
        name=page["name"], doc_type=DocType.page, metadata={"images": page["images"]}
    )

    plan = plan_renditions(document)
    assert plan.refused == []
    by_role = {rendition.role: rendition for rendition in plan.renditions}
    assert set(by_role) == {
        "original", "crop", "rotated", "enhanced", "background_removed",
    }
    assert all(r.document_id == document.id for r in plan.renditions)

    # Lineage resolves to real row ids, not role strings.
    assert by_role["crop"].derived_from_rendition_id == by_role["original"].id
    assert by_role["background_removed"].derived_from_rendition_id == (
        by_role["enhanced"].id
    )
    assert by_role["original"].derived_from_rendition_id is None

    crop = by_role["crop"]
    assert crop.transform is not None
    # A region must name the frame it was measured on.
    assert crop.transform.rendition_id == by_role["original"].id
    assert crop.producer_tool == "fichero-1.0/crops"
    assert crop.pixel_width == 3107


def test_plan_renditions_keeps_the_row_when_geometry_is_bad() -> None:
    """Bad geometry costs the transform, never the pixels."""
    from fichero_server.importers.manifest_renditions import plan_renditions
    from fichero_server.models import Document, DocType

    document = Document(
        name="p",
        doc_type=DocType.page,
        metadata={
            "images": [
                {"role": "original", "source_path": "/tmp/a.jpg"},
                {
                    "role": "crop",
                    "source_path": "/tmp/b.jpg",
                    "derived_from_role": "original",
                    "transform": {"rect": [0, 0, 9, 9], "space": "normalized"},
                },
            ]
        },
    )
    plan = plan_renditions(document)
    assert {r.role for r in plan.renditions} == {"original", "crop"}
    crop = next(r for r in plan.renditions if r.role == "crop")
    assert crop.transform is None
    assert any("transform rejected" in why for why in plan.refused)


def test_plan_renditions_refuses_and_says_why() -> None:
    from fichero_server.importers.manifest_renditions import plan_renditions
    from fichero_server.models import Document, DocType

    document = Document(
        name="p",
        doc_type=DocType.page,
        metadata={
            "images": [
                {"role": "original", "source_path": "/tmp/a.jpg"},
                {"role": "original", "source_path": "/tmp/dup.jpg"},
                {"role": "enhanced"},
                {"source_path": "/tmp/c.jpg"},
                {"role": "x", "source_path": "/tmp/x.jpg", "derived_from_role": "ghost"},
            ]
        },
    )
    plan = plan_renditions(document)
    assert {r.role for r in plan.renditions} == {"original", "x"}
    joined = " ".join(plan.refused)
    assert "duplicate role" in joined
    assert "no source_path" in joined
    assert "has no role" in joined
    assert "'ghost' not present" in joined


def test_plan_renditions_is_empty_without_images() -> None:
    from fichero_server.importers.manifest_renditions import plan_renditions
    from fichero_server.models import Document, DocType

    plan = plan_renditions(Document(name="p", doc_type=DocType.page, metadata={}))
    assert plan.renditions == []


# ---------------------------------------------------------------------------
# Deferred segment bands ride verbatim (ruling 3)
# ---------------------------------------------------------------------------


def test_segment_bands_ride_verbatim_on_the_page(tmp_path: Path) -> None:
    """Deferred is not discarded: the bbox program must not re-read 300 GB."""
    build_folder(tmp_path / "A", name="1936-doc", pages=1)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    page = [n for n in legacy.to_canonical_nodes(scan) if n["node_type"] == "page"][0]

    deferred = page["metadata"]["legacy_deferred_segments"]
    assert deferred["bands"] == [[0, 1521]]
    assert deferred["space"] == "background_removed"
    assert deferred["axis"] == "y"


# ---------------------------------------------------------------------------
# Overlaps resolve to the BETTER copy (Daniel's amendment)
# ---------------------------------------------------------------------------


def _strip_stage(folder: Path, stage: str, manifest_name: str) -> None:
    """Make a copy look abandoned mid-pipeline, as the Big Files copies are."""
    import shutil

    shutil.rmtree(folder / "assets" / stage)
    _ = manifest_name


def test_the_more_complete_copy_wins(tmp_path: Path) -> None:
    """A copy that was never transcribed loses to one that was."""
    big, small = tmp_path / "Big", tmp_path / "Smaller"
    abandoned = build_folder(big, name="1936-doc", sizes=[111, 222])
    _strip_stage(abandoned, "transcriptions", "transcription_manifest.jsonl")
    _strip_stage(abandoned, "llm_catalogue", "llm_process_manifest.jsonl")
    build_folder(small, name="1936-doc", sizes=[111, 222])

    scan = legacy.scan_archives([big, small], corpus_name="c")
    assert len(scan.folders) == 1
    winner = scan.folders[0]
    assert winner.archive == "Smaller"
    assert winner.transcribed_pages == 2
    assert scan.duplicates[0].archive == "Big"


def test_fewer_truncated_catalogue_steps_wins(tmp_path: Path) -> None:
    """Same stages, same pages — the intact catalogue decides."""
    a, b = tmp_path / "A", tmp_path / "B"
    build_folder(a, name="1936-doc", sizes=[111, 222], truncated_step=True)
    build_folder(b, name="1936-doc", sizes=[111, 222])

    scan = legacy.scan_archives([a, b], corpus_name="c")
    assert len(scan.folders) == 1
    assert scan.folders[0].archive == "B"
    assert scan.folders[0].salvaged_steps == []


def test_the_winning_copy_is_recorded_in_provenance(tmp_path: Path) -> None:
    big, small = tmp_path / "Big", tmp_path / "Smaller"
    abandoned = build_folder(big, name="1936-doc", sizes=[111, 222])
    _strip_stage(abandoned, "transcriptions", "transcription_manifest.jsonl")
    build_folder(small, name="1936-doc", sizes=[111, 222])

    scan = legacy.scan_archives([big, small], corpus_name="c")
    folder_node = list(legacy.to_canonical_nodes(scan))[1]
    chosen = folder_node["metadata"]["legacy_chosen_copy"]

    assert chosen["won"] == "Smaller"
    assert chosen["over"][0]["archive"] == "Big"
    assert chosen["over"][0]["identical"] is False
    assert "stages_completed" in chosen["ranking"]


def test_identical_copies_are_reported_as_identical(tmp_path: Path) -> None:
    a, b = tmp_path / "A", tmp_path / "B"
    build_folder(a, name="1936-doc", sizes=[111, 222])
    build_folder(b, name="1936-doc", sizes=[111, 222])

    scan = legacy.scan_archives([a, b], corpus_name="c")
    assert scan.overlap_tally == {"identical": 1}
    assert "identical (later run kept)" in legacy.dry_run_report(scan)


def test_dry_run_reports_the_overlap_tally(tmp_path: Path) -> None:
    """Daniel sees the decision before the real run."""
    big, small = tmp_path / "Big", tmp_path / "Smaller"
    abandoned = build_folder(big, name="1936-doc", sizes=[111, 222])
    _strip_stage(abandoned, "transcriptions", "transcription_manifest.jsonl")
    build_folder(small, name="1936-doc", sizes=[111, 222])

    scan = legacy.scan_archives([big, small], corpus_name="c")
    report = legacy.dry_run_report(scan)
    assert "Smaller wins" in report
    assert "the BETTER copy is imported" in report


# ---------------------------------------------------------------------------
# Defects the SAMPLE IMPORT found (2026-09-04) — real data, real routes
# ---------------------------------------------------------------------------


def test_bare_dates_never_become_entities(tmp_path: Path) -> None:
    """`fechas` holds dates, not names.

    Naming an entity "1937-01-01" produces a name with no letters, which the
    entities route rightly refuses — 422 on every one, measured live.
    """
    folder = build_folder(tmp_path / "A", name="1936-doc")
    steps = (
        folder / "assets" / "llm_catalogue" / "steps" / "documents"
    )
    _write(
        steps / "extraer_entidades_fechas_legales_rios.json",
        json.dumps(
            {
                "source": "/old",
                "step": "extraer_entidades_fechas_legales_rios",
                "result": {
                    "fechas": [
                        {
                            "fecha": "20 de noviembre de 1891",
                            "fecha_normalizada": "1891-11-20",
                            "contexto": "La ley 10 de 1891 comenzó a regir.",
                        }
                    ],
                    "rios": [{"nombre": "RÍO OPOGODÓ", "contexto": "Afluente."}],
                },
            },
            ensure_ascii=False,
        ),
    )
    entry = legacy.read_document_folder(folder, archive="a", stage=None)

    names = {e["canonical_name"] for e in entry.entities}
    assert "1891-11-20" not in names
    assert "20 de noviembre de 1891" not in names
    assert all(any(ch.isalpha() for ch in name) for name in names)
    # The river IS an entity, and a location.
    assert "RÍO OPOGODÓ" in names
    # The date is not lost — it rides as folder metadata.
    assert entry.dates and entry.dates[0]["fecha_normalizada"] == "1891-11-20"

    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    folder_node = _document_folder_node(scan)
    assert folder_node["metadata"]["legacy_dates"][0]["contexto"].startswith("La ley")


def test_timeline_survives_a_tier_that_hides_claims(tmp_path: Path) -> None:
    """`/api/claims` is tier-gated; a release engine drops the claims phase.

    The timeline is Daniel's data, so it must not depend on the engine's tier.
    """
    build_folder(tmp_path / "A", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    folder_node = _document_folder_node(scan)

    assert folder_node["claims"]
    timeline = folder_node["metadata"]["legacy_timeline"]
    assert timeline == [{"fecha": "1919-12-10", "evento": "Smith comenzó a trabajar."}]


def test_a_single_dropped_folder_gets_no_wrapper(tmp_path: Path) -> None:
    """Dropping one document folder must not wrap it in a folder of one."""
    folder = build_folder(tmp_path, name="1936-doc")
    scan = legacy.scan_archives([folder], corpus_name="1936-doc")
    nodes = list(legacy.to_canonical_nodes(scan))

    assert [n["node_type"] for n in nodes].count("folder") == 1
    assert nodes[0]["parent_external_id"] is None


def test_a_multi_folder_archive_still_gets_its_corpus_root(tmp_path: Path) -> None:
    build_folder(tmp_path / "A", name="1936-doc")
    build_folder(tmp_path / "A", name="1947-otro", sizes=[5, 6])
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="Corpus")
    nodes = list(legacy.to_canonical_nodes(scan))

    assert nodes[0]["name"] == "Corpus"
    assert [n["node_type"] for n in nodes].count("folder") == 3


def test_timeline_claims_use_a_real_claim_type(tmp_path: Path) -> None:
    """ClaimType is an enum; "timeline_event" 422s and aborted a full import."""
    from fichero_server.models.knowledge import ClaimType

    build_folder(tmp_path / "A", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    claim = _document_folder_node(scan)["claims"][0]

    assert claim["claim_type"] in {member.value for member in ClaimType}
    # The finer 1.0 label survives as provenance rather than as a bad enum.
    assert claim["metadata"]["legacy_claim_kind"] == "timeline_event"


def test_claim_payload_from_a_legacy_node_validates(tmp_path: Path) -> None:
    """Build the real request body and let the route's own model judge it."""
    from fichero_server.api.routes.claim.claims import ClaimCreateRequest
    from fichero_server.importers.manifest_import import claim_payload

    build_folder(tmp_path / "A", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    node = _document_folder_node(scan)

    body = claim_payload(node["claims"][0], node, "doc-1", [])
    validated = ClaimCreateRequest.model_validate(body)
    # The enum mapping IS the regression this test exists for: attempt 1 of
    # the full import died on claim_type="timeline_event" (not a member).
    assert validated.claim_type == "fact"


# ---------------------------------------------------------------------------
# The catalogue itself — the ficha Daniel could not find (2026-09-05)
# ---------------------------------------------------------------------------


def test_the_resumen_becomes_a_catalogue_artifact(tmp_path: Path) -> None:
    """The prose ficha must reach artifact_type "catalogue" — the surface the
    app already renders — not metadata that no view reads."""
    build_folder(tmp_path / "A", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    folder_node = _document_folder_node(scan)

    artifacts = folder_node["artifacts"]
    assert len(artifacts) == 1
    catalogue = artifacts[0]
    assert catalogue["artifact_type"] == "catalogue"
    # The whole ficha, not just the resumen field.
    content = catalogue["content"]
    assert content.startswith("# 1936 doc")
    assert "## Resumen" in content and "Un juicio laboral." in content
    assert "## Palabras Clave" in content
    assert "## Línea Temporal" in content
    assert catalogue["data"]["format"] == "markdown"
    assert catalogue["data"]["resumen"] == "Un juicio laboral."
    # Provenance names the 1.0 pipeline and the model that actually wrote it.
    assert catalogue["provider"] == "fichero-1.0"
    assert catalogue["model"] == "gpt-4.1-mini"
    assert catalogue["step_name"] == "catalogue_folder"
    # Tags ride with the ficha rather than becoming new machinery.
    assert catalogue["data"]["tags"] == ["juicio ejecutivo", "cesantía"]


def test_a_folder_without_a_resumen_emits_no_catalogue(tmp_path: Path) -> None:
    """15 folders were never catalogued by 1.0 — they must not get an empty one."""
    build_folder(tmp_path / "A", name="1936-doc", catalogue=False)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    assert _document_folder_node(scan)["artifacts"] == []


def test_pages_carry_no_catalogue_artifact(tmp_path: Path) -> None:
    """The ficha is folder-scoped; it must not be stamped on every page."""
    build_folder(tmp_path / "A", name="1936-doc", pages=3)
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    for node in legacy.to_canonical_nodes(scan):
        if node["node_type"] == "page":
            assert not node.get("artifacts")


def test_manifest_importer_passes_declared_artifacts_through(tmp_path: Path) -> None:
    """The importer previously built artifacts ONLY from text and entities."""
    from fichero_server.importers.manifest_import import node_provenance

    build_folder(tmp_path / "A", name="1936-doc")
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    node = _document_folder_node(scan)

    # The shape the importer consumes, asserted explicitly so a rename breaks
    # here rather than silently dropping the ficha again.
    artifact = node["artifacts"][0]
    assert set(artifact) >= {
        "artifact_type", "content", "data", "provider", "model", "step_name",
    }
    # An artifact WITHOUT its own provider falls back to the node's.
    assert node_provenance(node, "import_manifest")["provider"] == "fichero-1.0"


def test_catalogue_artifact_lands_once_through_the_drop_path(
    client, db, test_package, tmp_path
) -> None:
    """End-to-end through the real routes: the ficha arrives, and a re-drop
    adds nothing.

    Verified live against the Compañía Minera corpus 2026-09-05 before this
    test existed; encoded here so the idempotency cannot regress silently.
    """
    from fichero_server.api.routes.ingest.core import (
        IngestFolderRequest,
        import_folder_impl,
    )
    import fichero_server.api.routes.ingest.core as core
    from fichero_server.models import Artifact, DocType, Document

    from .test_manifest_import import _TestClientAdapter

    source = tmp_path / "archive"
    build_folder(source, name="1936-doc")
    build_folder(source, name="1950-nocat", sizes=[7, 8], catalogue=False)
    core._InProcessManifestClient = lambda _lib: _TestClientAdapter(client)

    request = IngestFolderRequest(path=str(source), mode="link")
    import_folder_impl(db, request, Path(test_package))

    catalogues = [a for a in db.query(Artifact) if a.artifact_type == "catalogue"]
    # One folder has a resumen, the other never was catalogued by 1.0.
    assert len(catalogues) == 1
    artifact = catalogues[0]
    owner = db.get(Document, artifact.document_id)
    assert owner.doc_type == DocType.folder, "the ficha is folder-scoped"
    assert "## Resumen" in artifact.content
    assert "Un juicio laboral." in artifact.content
    assert artifact.provider == "fichero-1.0"
    assert artifact.model == "gpt-4.1-mini"
    assert artifact.data["tags"] == ["juicio ejecutivo", "cesantía"]

    import_folder_impl(db, request, Path(test_package))
    again = [a for a in db.query(Artifact) if a.artifact_type == "catalogue"]
    assert len(again) == 1, "a re-drop must repair, never duplicate"
    pages = [d for d in db.query(Document) if d.doc_type == DocType.page]
    assert len(pages) == 4, "a re-drop must not double the pages either"


def test_the_ficha_is_the_whole_catalogue_not_one_field(tmp_path: Path) -> None:
    """The archive's own .docx renders Resumen, Palabras Clave, the entity
    sections and the Línea Temporal. The artifact must carry all of it — the
    resumen alone was ~1 KB of an ~8.7 KB document."""
    folder = build_folder(tmp_path / "A", name="1936-doc")
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    ficha = legacy.catalogue_markdown(entry)

    for heading in ("## Resumen", "## Palabras Clave", "## Línea Temporal"):
        assert heading in ficha
    # Entities appear under their 1.0 bucket headings, with their context.
    assert "## Personas" in ficha
    assert "FRANK E. SMITH" in ficha
    assert "Demandante." in ficha
    assert "## Organizaciones" in ficha
    assert "## Ubicaciones" in ficha
    # A dated event reads as a line, not a bare date.
    assert "**1919-12-10** — Smith comenzó a trabajar." in ficha
    assert len(ficha) > len(entry.summary or "") * 3


def test_an_unlisted_bucket_is_rendered_not_dropped(tmp_path: Path) -> None:
    """The 1.0 prompts invented buckets freely; an unknown one still shows."""
    folder = build_folder(tmp_path / "A", name="1936-doc")
    steps = folder / "assets" / "llm_catalogue" / "steps" / "documents"
    _write(
        steps / "extraer_entidades_especializadas.json",
        json.dumps(
            {
                "source": "/old",
                "step": "extraer_entidades_especializadas",
                "result": {"cosas_raras": [{"nombre": "COSA", "contexto": "Rara."}]},
            },
            ensure_ascii=False,
        ),
    )
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    ficha = legacy.catalogue_markdown(entry)
    assert "## cosas_raras" in ficha
    assert "**COSA** — Rara." in ficha


def test_a_folder_with_only_entities_still_gets_a_ficha(tmp_path: Path) -> None:
    """No resumen is not the same as no catalogue."""
    folder = build_folder(tmp_path / "A", name="1936-doc")
    (folder / "assets" / "llm_catalogue" / "steps" / "documents" / "resumen.json").unlink()
    entry = legacy.read_document_folder(folder, archive="a", stage=None)
    assert entry.summary is None
    assert entry.entities
    scan = legacy.scan_archives([tmp_path / "A"], corpus_name="c")
    artifacts = _document_folder_node(scan)["artifacts"]
    assert len(artifacts) == 1
    assert "## Resumen" not in artifacts[0]["content"]
    assert "## Personas" in artifacts[0]["content"]
