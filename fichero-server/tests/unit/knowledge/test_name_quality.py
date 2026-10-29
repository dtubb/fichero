"""Names that are not entities, dates as subjects, and the line-join statements read from (synthetic Spanish)."""

import unicodedata

import pytest

from fichero_server.knowledge.svo_quality import (
    claim_rejection,
    is_date_only,
    join_lines,
    join_page,
    usable_entity_name,
)


@pytest.mark.parametrize("name,kind", [
    ("Enero", "location"), ("Noviembre", "location"),
    ("Mayo", "organization"), ("De Diciembre", "organization"), ("Agencia", "organization"),
    ("Agente", "organization"), ("Perito Avaluador Lucas Pardo", "organization"), ("1918-06-06", "event"),
])
def test_names_that_are_not_entities_are_refused(name, kind):
    assert usable_entity_name(name, kind) is None


@pytest.mark.parametrize("name,kind", [
    ("Lucas Pardo", "person"), ("Agencia de Impuestos", "organization"), ("Calle 7 de Agosto", "location"),
    ("Juzgado de Valdoro", "organization"),
    ("Primero de Mayo", "location"), ("Cinco", "location"), ("Calle Agosto 7", "location"),
    ("Puerto Mayo 1910", "location"), ("Colonia Agosto 1910", "location"), ("Villa Mayo", "location"),
])
def test_real_names_are_kept_as_written(name, kind):
    assert usable_entity_name(name, kind) == name


@pytest.mark.parametrize("name", [
    "Julio Cesar", "Juan Julio Pardo", "Juan Mayo", "Ana Mayo Ruiz", "Pedro Abril", "Septiembre Rivas",
    "Mayo", "Abril", "Agosto", "Villa Mayo",
])
def test_a_person_is_never_lost_for_a_month_in_the_name(name):
    assert usable_entity_name(name, "person") == name


def test_a_person_that_is_wholly_a_date_is_refused():
    assert usable_entity_name("7 de Agosto de 1910", "person") is None
    assert usable_entity_name("De Diciembre", "person") is None


@pytest.mark.parametrize("name", [
    "Colegio 20 de Julio", "Escuela 7 de Agosto", "Parque 20 de Julio", "Batallón Primero de Mayo",
    "Sociedad 20 de Julio", "Calle 7 de Agosto", "Plaza Mayor de Valdoro 7 de Agosto",
    "Juzgado de Valdoro julio 25",
])
def test_a_name_is_never_trimmed(name):
    for kind in ("location", "organization"):
        assert usable_entity_name(name, kind) == name


@pytest.mark.parametrize("name", [
    "Fiscal del Tribunal Superior", "Administrador de Hacienda Nacional", "Notario Primero del Circuito",
    "Juez 1.º del Circuito",
])
def test_an_organisation_with_a_role_word_but_no_person_survives(name):
    assert usable_entity_name(name, "organization") == name


def test_a_role_word_and_a_person_is_not_an_organisation():
    assert usable_entity_name("Juez Pedro Gómez", "organization") is None


@pytest.mark.parametrize("broken,whole", [
    ("Mi-\nguel Soto", "Miguel Soto"), ("Se-\nrrano", "Serrano"), ("Lo-\nrenzo", "Lorenzo"),
    ("el se-\nñor", "el señor"), ("el no-\ntario", "el notario"),
])
def test_a_short_syllable_before_the_hyphen_rejoins(broken, whole):
    assert join_lines(broken) == whole


def test_a_function_word_after_the_break_stays_a_separate_word():
    assert join_lines("el señor-\nque") == "el señor que"
    assert join_lines("Ma-\nnuel que") == "Manuel que"


def test_nfd_text_joins_like_nfc_and_offsets_point_into_the_original():
    page = unicodedata.normalize("NFD", "Pedro Gó-\nmez firmó\nel auto")
    joined = join_page(page)
    assert joined.text == "Pedro Gómez firmó el auto"
    firmo = unicodedata.normalize("NFD", "firmó")
    start = page.index(firmo)
    a, b = joined.spans_in_joined([(start, start + len(firmo))])[0]
    assert joined.text[a:b] == "firmó"
    start = page.index("auto")
    a, b = joined.spans_in_joined([(start, start + 4)])[0]
    assert joined.text[a:b] == "auto"
    start = page.index(unicodedata.normalize("NFD", "Gó"))
    a, b = joined.spans_in_joined([(start, start + 3)])[0]  # "Gó" is 3 chars in NFD
    assert joined.text[a:b] == "Gó"


@pytest.mark.parametrize("subject", ["Mayo", "Abril", "Primero de Mayo", "Cinco"])
def test_a_lone_month_or_number_word_is_not_a_date_subject(subject):
    assert not is_date_only(subject)
    assert claim_rejection(subject, "firmó", "el auto", None) is None


def test_a_month_next_to_a_day_or_year_is_a_date():
    assert is_date_only("7 de agosto") and is_date_only("Mayo 1910")


@pytest.mark.parametrize("text", ["1918-06-06", "De Diciembre", "el 1.º de enero", "veinticinco de julio de 1918"])
def test_date_only_text(text):
    assert is_date_only(text)


def test_a_date_is_not_a_claim_subject():
    assert claim_rejection("1918-06-06", "fue dictado", "el auto", None) is not None
    assert claim_rejection("Lucas Pardo", "fue dictado", "el auto", None) is None


def test_lines_join_with_a_hyphen_break_rejoined():
    assert join_lines("hubiera muerto el 1.º de Ene-\nro de 1910 y\nsu esposa") == "hubiera muerto el 1.º de Enero de 1910 y su esposa"


def test_a_line_end_hyphen_is_rejoined_only_mid_word():
    assert join_lines("el señor-\nque vino") == "el señor que vino"
    assert join_lines("de la Ene-\nro pasado") == "de la Enero pasado"
    assert join_lines("Pérez-\nGómez firmó") == "Pérez-Gómez firmó"


def test_a_blank_line_stays_a_paragraph_break():
    assert join_lines("primera frase.\n\nsegunda frase.") == "primera frase.\n\nsegunda frase."


def test_the_joined_text_maps_every_line_back_to_the_page_text():
    page = "hubiera muerto el 1.º de Ene-\nro de   1910\ty\n\nsu esposa"
    joined = join_page(page)
    lines = ["hubiera muerto el 1.º de Ene-", "ro de   1910\ty", "su esposa"]
    spans = [(page.index(line), page.index(line) + len(line)) for line in lines]
    moved = [joined.text[a:b] for a, b in joined.spans_in_joined(spans)]
    # The dropped hyphen is not in the first line's stretch; double spaces and tabs are kept as written.
    assert moved == ["hubiera muerto el 1.º de Ene", "ro de   1910\ty", "su esposa"]
    assert joined.original == page
