"""`source.recipe.candidates-fallback-chain` (#5758): when the reader leaves a page empty or mostly blank, the summary
names the next candidate of the step's chain: a local one free, a cloud one offered and needing permission."""
from __future__ import annotations

from fichero_server.recipes.run_view import next_reader

LOCAL = {"id": "mlx-qwen", "model": {"provider": "mlx", "name": "qwen"}, "runs_on": "this-mac"}
CLOUD = {"id": "claude-vision", "model": {"provider": "anthropic", "name": "claude"}, "runs_on": "cloud:anthropic"}
KRAKEN = {"provider": "kraken", "name": "es-hand"}


def recipe(*chain):
    return {"steps": [{"id": "r", "job": "read-a-line", "model": KRAKEN, "chain": list(chain)}]}


def ask(chain, *, found=66, blank=0, nothing=0, cloud_allowed=False):
    return next_reader(recipe(*chain), lines_found=found, lines_blank=blank, pages_read_nothing=nothing,
                       cloud_allowed=cloud_allowed)


def test_a_page_the_reader_returned_nothing_for_names_the_next_local_reader():
    got = ask([CLOUD, LOCAL], nothing=1)
    assert got["id"] == "mlx-qwen" and got["needs_permission"] is False


def test_a_mostly_blank_hand_names_the_next_reader():
    assert ask([LOCAL], found=66, blank=36)["id"] == "mlx-qwen"


def test_a_mostly_read_hand_names_none():
    assert ask([LOCAL], found=66, blank=10) is None


def test_with_only_a_cloud_reader_next_it_is_offered_needing_permission():
    got = ask([CLOUD], nothing=1)
    assert got["id"] == "claude-vision" and got["needs_permission"] is True
    assert ask([CLOUD], nothing=1, cloud_allowed=True)["needs_permission"] is False


def test_no_chain_no_next_reader():
    assert ask([], nothing=1) is None
