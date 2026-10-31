"""catalogue.export.dates-parser-checks-the-model (#6282): agree / parser only / model only / disagree, and a person's date wins."""
from __future__ import annotations

import pytest

from fichero_server.models import Artifact, DocType, Document
from fichero_server.recipes import catalogue_step as step
from fichero_server.workflows import attribute_sources as sources

KEY = "catalogue_date_normalised"


def _text(dates: str, edtf: str | None) -> str:
    return f"Title: Cartas.\nDates: {dates}\n" + (f"Dates EDTF: {edtf}\n" if edtf else "") + "Scope and content: Cartas."


def _described(db, text, run="r1"):
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    return folder.id, _put(db, folder.id, text, run)


def _put(db, folder_id, text, run="r1"):
    art = Artifact(document_id=folder_id, artifact_type=step.ARTIFACT_TYPE, content=text, provider="p", model="m")
    db.save(art)
    step.put_in_attributes(db, folder_id, text, art.id, run_id=run, provider="p", model="m")
    return db.get(Document, folder_id)


@pytest.mark.parametrize("parser,model,value,verdict", [
    ("1909-05-08", ("1909-05-08", "w"), "1909-05-08", "agree"),
    ("1909-05-08?", ("1909-05-08", "w"), "1909-05-08", "agree"),  # the ? mark is not a disagreement
    (None, ("1909-05-08", "w"), "1909-05-08", "model-only"),
    ("1909-05-08", None, "1909-05-08", "parser-only"),
    ("1909-05-08", ("1909-05-18", "w"), None, "disagree"),
    (None, None, None, None),
])
def test_check_date(parser, model, value, verdict):
    assert step.check_date(parser, model) == (value, verdict)


def test_agreement_writes_the_value_checked_by_the_parser(db):
    _, doc = _described(db, _text("8 de mayo de 1909", "1909-05-08"))
    assert doc.attributes[KEY] == "1909-05-08"
    assert sources.sources(doc)[KEY]["date_check"]["verdict"] == "agree"
    assert step.date_problems(doc) == []


def test_the_model_alone_stands_and_problemas_says_it_was_not_checked(db):
    _, doc = _described(db, _text("en tiempo de las lluvias", "1909-05"))
    assert doc.attributes[KEY] == "1909-05"
    assert step.date_problems(doc) == ["fecha: leída por el modelo, sin comprobar"]


def test_the_parser_alone_stands(db):
    _, doc = _described(db, _text("8 de mayo de 1909", None))
    assert doc.attributes[KEY] == "1909-05-08" and step.date_problems(doc) == []


def test_a_disagreement_leaves_the_cell_empty_keeps_the_proposal_and_names_both(db):
    folder, doc = _described(db, _text("8 de mayo de 1909", "1909-05-18"))
    assert KEY not in doc.attributes
    proposal = sources.pending(doc, KEY)
    assert proposal["value"] == "1909-05-18" and proposal["parser"] == "1909-05-08"
    assert step.date_problems(doc) == ["fecha: el analizador leyó 1909-05-08, el modelo 1909-05-18"]
    again = _put(db, folder, _text("8 de mayo de 1909", "1909-05-18"), run="r2")  # the same disagreement: nothing moves
    assert sources.pending(again, KEY)["proposed_at"] == proposal["proposed_at"]


def test_no_date_at_all_and_unreadable_text_go_to_problemas(db):
    _, doc = _described(db, _text("en tiempo de las lluvias", None))
    assert KEY not in doc.attributes
    assert step.date_problems(doc) == ["fecha sin normalizar: «en tiempo de las lluvias»"]


def test_an_uncertain_date_is_said(db):
    _, doc = _described(db, _text("ca. 1850", None))
    assert step.date_problems(doc) == ["fecha incierta"]


def test_a_persons_date_wins_over_a_later_run_and_no_proposal_is_made_over_it(db):
    folder, doc = _described(db, _text("8 de mayo de 1909", "1909-05-08"))
    doc.attributes = {**doc.attributes, KEY: "1909-05-09"}
    doc.metadata = sources.with_sources(doc.metadata, {KEY: {"by": "person"}})
    db.save(doc)
    after = _put(db, folder, _text("8 de mayo de 1909", "1909-05-18"), run="r2")
    assert after.attributes[KEY] == "1909-05-09" and sources.sources(after)[KEY] == {"by": "person"}
    assert sources.pending(after, KEY) is None


def test_promote_reads_a_described_folders_date_in_words_with_no_model_and_undoes(db):
    import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.actions.undo import undo_set

    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    text = _text("a los ocho días del mes de mayo de mil novecientos nueve", None)
    db.save(Artifact(document_id=folder.id, artifact_type=step.ARTIFACT_TYPE, content=text, provider="p", model="m"))
    assert KEY not in (db.get(Document, folder.id).attributes or {})
    ctx = ActionContext(actor="ui", library_path="")
    audit = registry.invoke(db, "folder.promote_catalogue", {"folder_id": folder.id}, ctx).audit_id
    assert db.get(Document, folder.id).attributes[KEY] == "1909-05-08"
    undo_set(db, [audit], ctx)
    assert KEY not in (db.get(Document, folder.id).attributes or {})
