"""catalogue.export.problems-column (catalogue-export.md step 1.5): the computed clauses, read and never stored."""
from fichero_server import catalogue_sheet as sheet
from fichero_server.models import Artifact
from fichero_server.models.checking import CheckVerdict
from fichero_server.models.knowledge import EntityCurationState, EntityType, KnowledgeClaim, KnowledgeEntity
from tests.unit.export.helpers import folder, page


def _problems(db, f):
    return sheet.problems_for(db, f, sheet.pages_of(db, f))


def test_numbering_gaps_are_named_as_image_ranges():
    assert sheet.missing_numbers(["IMG_001", "IMG_002", "IMG_005", "IMG_007"]) == ["IMG_003", "IMG_004", "IMG_006"]
    assert sheet.missing_numbers(["a", "b"]) == []


def test_a_gap_and_unread_pages_and_blank_pages_each_get_a_clause(db):
    f = folder(db, "Doc")
    page(db, "IMG_001.jpg", f.id, seq=1)
    page(db, "IMG_002.jpg", f.id, seq=2, attrs={"material": "blank"})
    page(db, "IMG_005.jpg", f.id, seq=3)
    out = _problems(db, f)
    assert "en blanco: IMG_002" in out
    assert "sin líneas: IMG_001, IMG_005" in out  # the blank page is not "without lines"
    assert "faltan IMG_003\u2013IMG_004" in out


def test_lint_flags_print_as_written(db):
    f = folder(db, "Doc")
    db.save(Artifact(document_id=f.id, artifact_type="catalogue.narrative", content="x", data={"lint_flags": ["fecha dudosa"]}))
    assert "fecha dudosa" in _problems(db, f)


def test_access_points_the_graph_does_not_know_and_names_nobody_confirmed(db):
    db.save(KnowledgeEntity(canonical_name="Ana Ruiz", entity_type=EntityType.person))
    db.save(KnowledgeEntity(canonical_name="Sevilla", entity_type=EntityType.location,
                            curation_state=EntityCurationState.verified))
    f = folder(db, "Doc", attrs={"catalogue_access_points": ["Juzgado del Circuito", "Ana Ruiz", "Sevilla"],
                                 "catalogue_people": ["Ana Ruiz"], "catalogue_places": ["Sevilla"]})
    out = _problems(db, f)
    assert "sin clasificar: Juzgado del Circuito" in out
    assert "nombre sin confirmar: Ana Ruiz" in out
    assert not any("Sevilla" in clause for clause in out)


def test_a_statement_a_check_rejected_is_named(db):
    f = folder(db, "Doc")
    p = page(db, "IMG_001.jpg", f.id, seq=1)
    claim = KnowledgeClaim(text="El juez murió en 1900", source_document_id=p.id)
    db.save(claim)
    db.save(CheckVerdict(layer="claims", target_id=claim.id, verdict="reject", reasons="no", checker="m", trust="model"))
    assert "declaración rechazada: El juez murió en 1900" in _problems(db, f)


def test_nothing_computed_is_stored(db):
    f = folder(db, "Doc", attrs={"catalogue_problems": ["a mano"]})
    page(db, "IMG_001.jpg", f.id, seq=1)
    out = _problems(db, f)
    assert out[0] == "a mano" and f.attributes == {"catalogue_problems": ["a mano"]}
