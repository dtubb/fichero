"""`models.manage.add-by-id-or-url` (#6588, #5460): a model added by its Hugging Face id or URL, or a Kraken repository DOI, becomes
one bookmarked card filled in from its source; an address it cannot read, or a model its source does not know, is refused in words."""
from __future__ import annotations

import pytest
from fichero_server.recipes import discovery


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))


@pytest.mark.parametrize("text, expected", [
    ("acme/old-hands-reader", ("hugging-face", "acme/old-hands-reader")),
    ("https://huggingface.co/acme/old-hands-reader", ("hugging-face", "acme/old-hands-reader")),
    ("https://huggingface.co/acme/old-hands-reader/tree/main?x=1", ("hugging-face", "acme/old-hands-reader")),
    ("https://zenodo.org/records/1234", ("zenodo", "10.5281/zenodo.1234")),
    ("https://doi.org/10.5281/zenodo.1234", ("zenodo", "10.5281/zenodo.1234")),
    ("10.5281/zenodo.1234", ("zenodo", "10.5281/zenodo.1234")),
    ("anthropic:claude-sonnet-4", ("provider", "anthropic:claude-sonnet-4")),
])
def test_an_address_is_read_as_hub_zenodo_or_a_provider_id(text, expected):
    assert discovery.parse_model_address(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "just words", "https://example.com/a/b", "a/b/c",
                                  "https://huggingface.co/../x", "https://huggingface.co/acme/..", "https://huggingface.co/acme/%2e%2e",
                                  "https://huggingface.co/acme/name%3Fx", "https://hf.co/acme/na%2Fme", "acme/..", "./name"])
def test_an_address_that_names_no_model_is_refused(text):
    with pytest.raises(ValueError):
        discovery.parse_model_address(text)


def test_a_hub_model_is_added_as_a_bookmarked_card_filled_in_from_its_listing_and_card(store):
    listing = {"modelId": "acme/old-hands-reader", "tags": ["license:apache-2.0", "es", "mlx", "handwritten"],
               "pipeline_tag": "image-to-text"}
    card_text = "---\nlicense: apache-2.0\nlanguage: [es]\nmodel-index:\n- results:\n  - metrics:\n    - {type: cer, value: 0.07}\n---\n"
    key = discovery.add_by_address("https://huggingface.co/acme/old-hands-reader",
                                   fetch_model=lambda repo: listing, fetch_card=lambda repo: card_text)
    assert key == "acme/old-hands-reader"
    row = discovery.cached_hub()[key]
    assert row["bookmarked"] is True and row["licence"] == "apache-2.0" and "added by you" in row["offered_because"]
    assert "CER 7.0%" in row["offered_because"]
    cards = discovery.hub_cards(None, runnable_only=False)
    assert [c.pin.get("hf") for c in cards] == ["acme/old-hands-reader"]


def test_adding_the_same_model_twice_keeps_one_card(store):
    listing = {"modelId": "acme/x", "tags": []}
    for _ in range(2):
        discovery.add_by_address("acme/x", fetch_model=lambda repo: listing, fetch_card=lambda repo: None)
    assert list(discovery.cached_hub()) == ["acme/x"]


def test_a_model_the_hub_does_not_know_is_refused_and_nothing_is_kept(store):
    with pytest.raises(LookupError, match="acme/nothing"):
        discovery.add_by_address("acme/nothing", fetch_model=lambda repo: None, fetch_card=lambda repo: None)
    assert discovery.cached_hub() == {}


def test_a_provider_model_id_is_refused_with_where_to_add_it(store):
    with pytest.raises(ValueError, match="provider"):
        discovery.add_by_address("anthropic:claude-x", fetch_model=lambda repo: None, fetch_card=lambda repo: None)


def test_the_route_adds_a_hub_model_and_refuses_a_bad_address_with_422(client, store, monkeypatch):
    async def model(repo):
        return {"modelId": repo, "tags": ["license:mit"]}

    async def card(repo):
        return None

    from fichero_server.api.routes.system import recipes
    monkeypatch.setattr(recipes, "_fetch_hub_model", model, raising=False)
    monkeypatch.setattr(recipes, "_fetch_hub_card", card, raising=False)
    monkeypatch.setattr(discovery, "egress_allowed", lambda: True)
    done = client.post("/api/recipes/candidates/add", json={"address": "acme/x"})
    assert done.status_code == 200, done.text
    assert done.json() == {"key": "acme/x"}
    assert discovery.cached_hub()["acme/x"]["bookmarked"] is True
    assert client.post("/api/recipes/candidates/add", json={"address": "nonsense"}).status_code == 422
