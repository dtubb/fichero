"""Names that are not entities, dates as subjects, and the line-join statements read from (synthetic Spanish)."""

import pytest

from fichero_server.knowledge.svo_quality import (
    claim_rejection,
    is_date_only,
    join_lines,
    usable_entity_name,
)


@pytest.mark.parametrize("name,kind", [
    ("Agosto", "person"), ("Villa Mayo", "person"), ("Enero", "location"), ("Noviembre", "location"),
    ("Mayo", "organization"), ("De Diciembre", "organization"), ("Agencia", "organization"),
    ("Agente", "organization"), ("Perito Avaluador Lucas Pardo", "organization"), ("1918-06-06", "event"),
])
def test_names_that_are_not_entities_are_refused(name, kind):
    assert usable_entity_name(name, kind) is None


@pytest.mark.parametrize("name,kind", [
    ("Lucas Pardo", "person"), ("Agencia de Impuestos", "organization"), ("Calle 7 de Agosto", "location"),
    ("Juzgado de Valdoro", "organization"),
])
def test_real_names_are_kept_as_written(name, kind):
    assert usable_entity_name(name, kind) == name


def test_a_date_fused_onto_a_name_is_trimmed_off():
    assert usable_entity_name("Juzgado de Valdoro julio veinticinco", "organization") == "Juzgado de Valdoro"
    assert usable_entity_name("Juzgado de Valdoro julio 25", "organization") == "Juzgado de Valdoro"


@pytest.mark.parametrize("text", ["1918-06-06", "De Diciembre", "el 1.º de enero", "veinticinco de julio de 1918"])
def test_date_only_text(text):
    assert is_date_only(text)


def test_a_date_is_not_a_claim_subject():
    assert claim_rejection("1918-06-06", "fue dictado", "el auto", None) is not None
    assert claim_rejection("Lucas Pardo", "fue dictado", "el auto", None) is None


def test_lines_join_with_a_hyphen_break_rejoined():
    assert join_lines("hubiera muerto el 1.º de Ene-\nro de 1910 y\nsu esposa") == "hubiera muerto el 1.º de Enero de 1910 y su esposa"
