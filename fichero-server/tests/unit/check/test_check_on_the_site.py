"""`source.check.on-the-site` (docs/contributor_manual/specs/source/checking.md), tested to the spec.

A model's check run and a person's verdict through the check routes, then the site through the site export's
route; the checker is the check tests' stub at `llm.chat`.
"""
from __future__ import annotations

from tests.unit.check.test_check_to_spec import (  # noqa: F401  (fixtures)
    CHECKER,
    _run,
    checker,
    page,
    statements,
)


def test_source_check_on_the_site(client, db, page, statements, checker, tmp_path):  # noqa: F811
    """source.check.on-the-site: "where a check has run, the published site shows it beside the statement or
    entity it checked, on the page the statement was found on, in the claim index and on the entity's page:
    the verdict, the reasons, the checker and its trust level (a person, or a model, named as a model), and for
    a correction the values offered; a statement or entity no check has seen is shown without one, never as
    confirmed.\""""
    folder, claims, juan = statements
    checker.script = [{"verdict": "reject", "why": "the passage says he bought it"},
                      {"verdict": "correct", "why": "eleven, not ten",
                       "correction": {"text": "Juan de Mosquera owed eleven pesos.", "subject": "Juan de Mosquera",
                                      "relation": "owed", "object": "eleven pesos"}}]
    _run(client, db, layer="claims", scope_ids=[folder.id])  # the third is confirmed (the stub's default)
    from fichero_server.models.knowledge import KnowledgeClaim

    db.save(KnowledgeClaim(text="the scribe signed the deed.", svo_subject="the scribe", svo_verb="signed",
                           svo_object="the deed", source_document_id=page[1].id, entity_ids=[]))  # never checked
    r = client.post("/api/check/verdicts", json={"layer": "entities", "target_id": juan.id, "verdict": "confirm",
                                                 "reasons": "his signature is on f. 3"})
    assert r.status_code == 200, r.text

    site = tmp_path / "site"
    r = client.post("/api/export/eleventy-site", json={"output_path": str(site), "overwrite": True})
    assert r.status_code == 200, r.text
    claim_index = (site / "src" / "claims" / "index.md").read_text(encoding="utf-8")
    page_md = next(p for p in (site / "src").glob("*/*.md") if page[1].name.split(".")[0] in p.name).read_text()
    entity_md = next((site / "src" / "entities").glob("*.md")).read_text(encoding="utf-8")

    for text in (claim_index, page_md):
        rejected = next(line for line in text.splitlines() if "sold a house" in line or "rejected" in line
                        and "bought it" in line)
        assert "rejected" in text and "the passage says he bought it" in text and CHECKER in text
        assert "a model" in text and "Offered instead: Juan de Mosquera owed eleven pesos." in text, "the correction offered"
        assert rejected
        assert "confirmed" in text and "witnessed the sale" in text
        unchecked = next(line for line in text.splitlines() if "the scribe signed the deed." in line)
        assert "check" not in unchecked.lower() and "confirm" not in unchecked.lower()
    assert "confirmed" in entity_md and "his signature is on f. 3" in entity_md and "a person" in entity_md
