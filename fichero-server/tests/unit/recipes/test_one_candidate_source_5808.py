"""One candidate source for the stage page, Compare and Find a Reader (#5808;
docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.find.one-candidate-source`,
`source.onboard.stages.page-lists-found-models`, `compare-names-its-models`).

WHY: the staged build listed only Kraken and PP-OCR models under Compare, showed one model twice, truncated names,
and ranked an 11th-century reader beside 16th-century ones for 20th-century pages. The list is one function now."""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, Card, rank_key

READ = frozenset({"read-a-line"})
PAGE = frozenset({"read-a-page"})


def card(cid, *, pin, jobs=READ, source="shipped", runs_on="this-mac", period=None, languages=None, scripts=None,
         offered_only=False, note="A reader", cer=None, runs_here=True):
    return Card(id=cid, pin=pin, jobs=jobs, scripts=frozenset(scripts) if scripts else frozenset({"Latn"}),
                languages=frozenset(languages) if languages else None, material=frozenset({"handwriting"}),
                runs_on=runs_on, note=note, source=source, period=period, offered_only=offered_only,
                cer_published=cer, runs_here=runs_here)


def answers(period="", languages=("es",)):
    return Answers(purposes=("transcribe",), languages=frozenset(languages), scripts=frozenset({"Latn"}),
                   materials=("handwriting",), period=period)


# --- one list, every kind of reader -------------------------------------------------------------------------------

def test_the_candidates_for_read_include_one_of_each_reader_kind_available():
    from fichero_server.recipes.discovery import step_candidates

    found = [
        card("kraken:catmus@1", pin={"zenodo": "10.5281/zenodo.1"}, source="kraken-repository"),
        card("ppocr:latin@1", pin={"ppocr": "latin"}),
        card("mlx:qwen2.5-vl@1", pin={"hf": "mlx-community/Qwen2.5-VL"}, jobs=PAGE, source="installed"),
        card("apple:vision@os", pin={"apple": "vision"}, jobs=PAGE),
        card("anthropic:claude@x", pin={"cloud": "anthropic", "model": "claude"}, jobs=PAGE, runs_on="cloud:anthropic",
             source="remote", offered_only=True),
        card("remote:studio@1", pin={"cloud": "ollama", "model": "qwen"}, jobs=PAGE, runs_on="own-machine:studio",
             source="remote-endpoints", offered_only=True),
    ]
    ids = {c.id for c in step_candidates(found, "read-a-line")}
    assert ids == {c.id for c in found}, "a page reader reads the line step's lines too: nothing is dropped"
    # a job a card does not name is never a candidate for it
    assert {c.id for c in step_candidates(found, "find-lines")} == set()


def test_compare_reads_the_same_list_so_a_wanted_page_reader_is_not_dropped(monkeypatch):
    from fichero_server.recipes import discovery, samples

    vlm = card("mlx:qwen2.5-vl@1", pin={"hf": "mlx-community/Qwen2.5-VL"}, jobs=PAGE, source="installed")
    monkeypatch.setattr(discovery, "discover", lambda a, **k: ([vlm], []))
    monkeypatch.setattr(discovery, "known_cards", lambda a, include_not_built=False: [])
    step = {"id": "read", "job": "read-a-line", "model": {"hf": "x"}}
    setup = {"answers": {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"],
                         "materials": ["handwriting"]}, "recipe": {"steps": [step]}}
    assert [c.id for c in samples._cards_for(setup, step, [vlm.id])] == [vlm.id]


# --- no model id twice, full names, a link ------------------------------------------------------------------------

def test_one_model_found_by_two_sources_is_one_candidate_the_first_source_keeps():
    from fichero_server.recipes.discovery import dedupe_cards

    shipped = card("kraken:cat@1", pin={"zenodo": "10.5281/zenodo.123"}, source="shipped")
    found = card("kraken:cat-repo@1", pin={"zenodo": "10.5281/zenodo.123"}, source="kraken-repository")
    other = card("kraken:other@1", pin={"zenodo": "10.5281/zenodo.999"}, source="kraken-repository")
    hf_a = card("hf:a@1", pin={"hf": "Org/Model", "revision": "r1"}, source="hugging-face")
    hf_b = card("hf:b@2", pin={"hf": "org/model", "revision": "r2"}, source="installed")
    kept = dedupe_cards([shipped, found, other, hf_a, hf_b])
    assert [c.id for c in kept] == ["kraken:cat@1", "kraken:other@1", "hf:a@1"]
    assert dedupe_cards([]) == []


def test_a_candidate_links_to_its_own_page():
    from fichero_server.recipes.discovery import model_link

    assert model_link(card("a", pin={"hf": "Org/Model"})) == "https://huggingface.co/Org/Model"
    assert model_link(card("b", pin={"zenodo": "10.5281/zenodo.13788177"})) == "https://doi.org/10.5281/zenodo.13788177"
    assert model_link(card("c", pin={"cloud": "anthropic", "model": "claude"})) is None, "nothing invented"


def test_the_candidate_response_carries_the_link_the_period_fit_and_the_whole_name():
    from fichero_server.api.routes.system.recipes import ModelCandidate

    fields = ModelCandidate.model_fields
    assert {"link", "other_period"} <= set(fields)
    assert fields["other_period"].default is False and fields["link"].default is None


# --- ranked and filtered by period, language, script ---------------------------------------------------------------

def test_a_reader_made_for_another_period_is_flagged_and_ranks_after_the_period_matched_ones():
    from fichero_server.recipes.assemble import other_period

    a = answers(period="20th century")
    eleventh = card("k:11th", pin={"zenodo": "1"}, period=(1000, 1100), cer=0.02)
    twentieth = card("k:20th", pin={"zenodo": "2"}, period=(1900, 1999), cer=0.05)
    unstated = card("k:any", pin={"zenodo": "3"}, period=None, cer=0.05)
    assert other_period(eleventh, a) is True
    assert other_period(twentieth, a) is False and other_period(unstated, a) is False
    ranked = sorted([eleventh, unstated, twentieth], key=lambda c: rank_key("read-a-line", c, "handwriting", a))
    assert [c.id for c in ranked][-1] == "k:11th", "an 11th-century reader is last for 20th-century pages"
    assert ranked[0].id == "k:20th"


def test_without_a_period_nothing_is_another_period():
    from fichero_server.recipes.assemble import other_period

    assert other_period(card("k", pin={"zenodo": "1"}, period=(1000, 1100)), answers(period="")) is False


def test_language_matched_readers_rank_before_others():
    es = card("k:es", pin={"zenodo": "1"}, languages={"es"}, cer=0.05)
    la = card("k:la", pin={"zenodo": "2"}, languages={"la"}, cer=0.05)
    a = answers(languages=("es",))
    ranked = sorted([la, es], key=lambda c: rank_key("read-a-line", c, "handwriting", a))
    assert [c.id for c in ranked] == ["k:es", "k:la"]


# --- Compare names its models before it runs -----------------------------------------------------------------------

def test_a_candidate_column_names_its_model_and_links_it_before_the_run():
    from fichero_server.recipes.samples import _column

    plan = {"workflows": [], "runs": [], "estimate": {"total_cost_usd": 0}, "refusals": []}
    column = _column(card("hf:a@1", pin={"hf": "Org/Model"}, source="hugging-face"), plan)
    assert column["name"] and column["link"] == "https://huggingface.co/Org/Model"
