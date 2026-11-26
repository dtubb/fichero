"""`models.cards.richer-and-more` (#6588): every card in the shipped catalogue (`recipes/seed/cards.yaml`) states what it reads
(note, jobs, scripts, languages, period, material), its licence, size and memory, its published accuracy, where it runs, what it
costs and a link to its own source, or says in `unstated` why a fact is not there. Nothing is filled in by guessing."""
from __future__ import annotations

import re

import pytest
import yaml
from fichero_server.recipes import cards as cards_module

#: A fact every card has: a key in the row, or a reason in `unstated`.
FACTS = ("note", "jobs", "scripts", "languages", "period", "material", "licence", "size_gb", "memory_gb", "cer_published",
         "runs_on", "cost", "source_url")

ROWS = yaml.safe_load(cards_module.SEED.read_text(encoding="utf-8"))["cards"]


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_a_card_states_each_fact_or_says_why_not(row):
    unstated = row.get("unstated") or {}
    missing = [f for f in FACTS if row.get(f) in (None, "", []) and not str(unstated.get(f) or "").strip()]
    assert missing == [], f"{row['id']} states neither a value nor a reason for: {missing}"
    stated_and_unstated = [f for f in unstated if row.get(f) not in (None, "", [])]
    assert stated_and_unstated == [], f"{row['id']} both states and excuses: {stated_and_unstated}"
    assert set(unstated) <= set(FACTS), f"{row['id']} excuses a fact the catalogue does not have: {set(unstated) - set(FACTS)}"


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_a_cards_link_is_its_own_page(row):
    url = row["source_url"]
    assert re.match(r"^https://[a-z0-9.-]+/\S+$", url), url
    pin = row["pin"]
    if pin.get("zenodo"):
        assert url == f"https://zenodo.org/records/{pin['zenodo'].rsplit('.', 1)[-1]}", url
    if pin.get("hf"):
        assert url == f"https://huggingface.co/{pin['hf']}", url


def test_no_card_states_an_accuracy_measured_on_a_persons_pages():
    """Measured accuracy is the person's own (`Card.cer_measured_here`, from a bake-off): the shipped catalogue holds none."""
    assert [r["id"] for r in ROWS if "cer_measured_here" in r] == []
    assert all(c.cer_measured_here is None for c in cards_module.all_seed_cards())


def test_the_loaded_card_carries_its_link_and_cost():
    loaded = {c.id: c for c in cards_module.all_seed_cards()}
    assert set(loaded) == {r["id"] for r in ROWS}
    assert all(c.source_url and c.cost for c in loaded.values())


def test_apple_intelligence_and_the_cloud_card_say_their_cost_and_link_to_their_source():
    from fichero_server.recipes import discovery

    made = {c.id: c for c in discovery.other_text_cards()}
    apple, claude = made["apple:intelligence/foundation-models@os"], made.get("anthropic:claude@settings")
    assert apple.cost == "Free, on this Mac" and apple.source_url.startswith("https://developer.apple.com/")
    assert claude is not None and "leave this Mac" in claude.cost and claude.source_url.startswith("https://")


def test_a_downloaded_reader_with_no_memory_stated_is_offered_not_chosen():
    """A reader from Zenodo or the Hub whose memory nothing states could be chosen for a Mac it does not fit: the catalogue
    offers it to compare, and the rules never choose it by themselves."""
    loaded = {c.id: c for c in cards_module.all_seed_cards()}
    readers = [r for r in ROWS if "memory_gb" in (r.get("unstated") or {}) and (r["pin"].get("zenodo") or r["pin"].get("hf"))
               and {"read-a-line", "read-a-page"} & set(r["jobs"])]
    assert readers, "the catalogue has readers whose memory is unstated"
    assert [r["id"] for r in readers if not loaded[r["id"]].offered_only] == []


def test_the_rules_never_choose_an_offered_only_seed_card():
    """A Syriac handwritten project: no step is read by an offered-only seed card, and with only those to pick from a step
    has a gap rather than a reader whose memory nothing states."""
    from fichero_server.recipes.assemble import Answers, _choose

    a = Answers(purposes=("transcribe",), languages=frozenset({"syr"}), scripts=frozenset({"Syrc"}),
                materials=("handwriting",), material="handwriting")
    seed = cards_module.all_seed_cards()
    offered = {c.id for c in seed if c.offered_only}
    assert any("Syrc" in (c.scripts or ()) for c in seed if c.offered_only)
    for job in ("read-a-line", "read-a-page"):
        choice = _choose(job, seed, a)
        assert choice.card is None or choice.card.id not in offered
        assert not {c.id for c in choice.chain} & offered
    assert _choose("read-a-line", [c for c in seed if c.offered_only], a).card is None
