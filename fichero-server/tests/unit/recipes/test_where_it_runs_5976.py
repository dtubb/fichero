"""Every candidate says where it can run and what it needs (`source.onboard.model-search-says-where-it-runs-and-what-it-needs`,
#5976): this Mac, Hugging Face Jobs, each cluster set up here. A place it cannot use says why in words. The cluster is listed
for Kraken readers and vision-language models, but sending from the app stays refused until the app's key and sign-in step
exist (#5238), and the option says so. Pure: the Mac's memory, the Hugging Face account and the clusters are passed in."""

from __future__ import annotations

from fichero_server.recipes import discovery
from fichero_server.recipes.assemble import Card
from fichero_server.recipes.where_it_runs import places_it_can_run

READ = frozenset({"read-a-line"})


def card(**kw) -> Card:
    base = dict(id="c", pin={}, jobs=READ, scripts=None, languages=None, material=frozenset(), runs_on="this-mac")
    base.update(kw)
    return Card(**base)


def by_place(options):
    return {(o["place"], o["name"]): o for o in options}


def test_a_kraken_reader_runs_on_the_mac_on_hugging_face_and_on_each_cluster():
    kraken = card(pin={"kraken_hf": "a/b"}, size_gb=0.013)
    got = by_place(places_it_can_run(kraken, this_mac_gb=16, hf_ready=True, clusters=["acenet", "other"]))
    assert list(got) == [("this-mac", "this Mac"), ("hf-jobs", "Hugging Face Jobs"), ("cluster", "acenet"),
                         ("cluster", "other")]
    assert got[("this-mac", "this Mac")]["can"] and got[("hf-jobs", "Hugging Face Jobs")]["can"]
    acenet = got[("cluster", "acenet")]
    assert acenet["can"] and "#5238" in acenet["blocked"]  # a place it could run; the live send waits for the key
    assert "Kraken" in got[("this-mac", "this Mac")]["needs"]


def test_hugging_face_without_an_account_says_what_to_add():
    got = by_place(places_it_can_run(card(pin={"zenodo": "10.5281/zenodo.1"}), this_mac_gb=16, hf_ready=False, clusters=[]))
    hf = got[("hf-jobs", "Hugging Face Jobs")]
    assert not hf["can"] and "Settings" in hf["why"]


def test_an_mlx_build_too_big_for_this_mac_says_how_much_it_needs_and_what_this_mac_has():
    big = card(pin={"hf": "mlx-community/Qwen3-VL-8B-Instruct-4bit", "revision": "main"}, memory_gb=24.0)
    got = by_place(places_it_can_run(big, this_mac_gb=8, hf_ready=True, clusters=["acenet"]))
    mac = got[("this-mac", "this Mac")]
    assert not mac["can"] and "24 GB" in mac["why"] and "8 GB" in mac["why"]
    assert not got[("hf-jobs", "Hugging Face Jobs")]["can"]
    assert "MLX" in got[("hf-jobs", "Hugging Face Jobs")]["why"]  # an MLX build runs only on a Mac


def test_a_vision_model_with_no_mlx_build_runs_on_hugging_face_and_the_cluster_not_the_mac():
    remote = card(pin={"hf": "kranidiotis/ottoman-ocr-qwen2.5-vl-7b", "revision": "main"},
                  runs_on=discovery.REMOTE_RUNS_ON, size_gb=15.5)
    got = by_place(places_it_can_run(remote, this_mac_gb=16, hf_ready=True, clusters=["acenet"]))
    assert not got[("this-mac", "this Mac")]["can"] and "MLX" in got[("this-mac", "this Mac")]["why"]
    assert got[("hf-jobs", "Hugging Face Jobs")]["can"]
    assert got[("cluster", "acenet")]["can"] and got[("cluster", "acenet")]["blocked"]
    assert "GB" in got[("hf-jobs", "Hugging Face Jobs")]["needs"]


def test_a_reader_this_build_cannot_run_names_why_in_every_place():
    stuck = card(pin={"hf": "x/trocr"}, runs_here=False, cannot_run_because="a TrOCR model, and this build runs MLX builds only")
    got = places_it_can_run(stuck, this_mac_gb=16, hf_ready=True, clusters=["acenet"])
    assert got and not any(o["can"] for o in got)
    assert all("TrOCR" in o["why"] for o in got)


def test_a_cloud_reader_runs_at_its_provider_only():
    cloud = card(pin={"cloud": "anthropic", "model": "claude"}, runs_on="cloud:anthropic")
    got = places_it_can_run(cloud, this_mac_gb=16, hf_ready=True, clusters=["acenet"])
    assert [o["place"] for o in got] == ["provider"] and got[0]["can"]


def test_the_candidate_list_carries_the_options():
    from fichero_server.api.routes.system.recipes import ModelCandidate

    assert "places" in ModelCandidate.model_fields
