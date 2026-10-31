"""A date row that states something is not a claim about the date: its statement goes to the one actor named in it."""

from types import SimpleNamespace

from fichero_server.workflows.tools.extract_svo_only import _attach_date_subjects


def _entities(*names):
    return {n.lower(): ("people", SimpleNamespace(name=n)) for n in names}


def test_the_one_named_actor_takes_the_dated_statement():
    row = {"date_normalized": "1918-06-06", "verb": "fue dictado", "object": "el auto",
           "source_text": "el auto fue dictado por Lucas Pardo"}
    kept, claims = _attach_date_subjects([row], _entities("Lucas Pardo", "Rosa Vega"))
    assert kept == []
    assert [(c["subject"], c["date"], c["verb"]) for c in claims] == [("Lucas Pardo", "1918-06-06", "fue dictado")]


def test_no_actor_or_two_leaves_the_dated_row_for_the_timeline():
    said = {"date_normalized": "1918-06-06", "verb": "fue dictado", "object": "el auto",
            "source_text": "fue dictado por Lucas Pardo y Rosa Vega"}
    bare = {"date_normalized": "1918-06-06", "verb": "", "object": "", "source_text": "6 de junio"}
    kept, claims = _attach_date_subjects([said, bare], _entities("Lucas Pardo", "Rosa Vega"))
    assert kept == [said, bare] and claims == []


def test_a_name_inside_a_longer_one_is_not_the_actor():
    row = {"date_normalized": "1918-06-06", "verb": "fue dictado", "object": "el auto",
           "source_text": "el auto fue dictado por Mariana Vega"}
    kept, claims = _attach_date_subjects([row], _entities("Ana", "Mariana Vega"))
    assert [c["subject"] for c in claims] == ["Mariana Vega"]
