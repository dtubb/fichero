"""A training request's `name` becomes a file name (`<reader folder>/<name>.mlmodel`, `ketos -o <out>/<name>`), so a
name that is not one path component is refused at the request model, before any job is made."""
import pytest
from pydantic import ValidationError

from fichero_server.models.compute_requests import TrainKrakenHereRequest, TrainKrakenRequest, TrainVisionLoraRequest

CARDS = (TrainKrakenRequest, TrainKrakenHereRequest, TrainVisionLoraRequest)


@pytest.mark.parametrize("card", CARDS)
@pytest.mark.parametrize("name", ["../../escaped", "a/b", "a\\b", "..", ".", "", "/abs", "nul\0byte"])
def test_a_name_that_leaves_its_folder_is_refused(card, name):
    with pytest.raises(ValidationError):
        card(scope_ids=["p"], teacher="t", name=name)


@pytest.mark.parametrize("card", CARDS)
@pytest.mark.parametrize("name", ["reader", "my reader 2", "notarial-1650.v2"])
def test_a_plain_name_is_kept(card, name):
    assert card(scope_ids=["p"], teacher="t", name=name).name == name


def test_the_default_names_pass():
    assert [card(scope_ids=["p"], teacher="t").name for card in CARDS] == ["reader", "reader", "student"]
