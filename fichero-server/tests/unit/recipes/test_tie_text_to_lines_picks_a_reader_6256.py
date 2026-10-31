"""Tie text to lines runs a Kraken reader, so setup offers a picker for it (#6256).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.job.tie-text-to-lines`. WHY: with
`needs_a_model=False` the step row had no model finder though Start runs it with the step's Kraken reader.
"""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)


def test_tie_text_to_lines_needs_a_model_and_the_finder_lists_the_kraken_readers(client, mac):  # noqa: F811
    jobs = {j["id"]: j["needs_a_model"] for j in client.get("/api/recipes/jobs").json()["items"]}
    assert jobs["tie-text-to-lines"] is True

    r = client.get("/api/recipes/candidates", params={"job": "tie-text-to-lines", "scripts": "Latn", "languages": "en"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and all("kraken" in str(i["pin"]) or "zenodo" in str(i["pin"]) for i in items), items


def test_wide_the_assembled_tie_step_defaults_to_the_projects_line_reader():
    """`wide.picker.tie-text-picker-visible` (#6256): the tie's anchor is a Kraken reader's rough read, so its default is the
    project's own line reader where that is a Kraken reader; a line step read by a vision model keeps the rules' own choice."""
    from fichero_server.recipes.assemble import tie_follows_the_line_reader

    catmus = {"zenodo": "10.5281/zenodo.12743230"}
    mccatmus = {"zenodo": "10.5281/zenodo.13788177"}
    steps = [{"job": "read-a-line", "model": catmus, "runs_on": "this-mac"},
             {"job": "tie-text-to-lines", "model": mccatmus, "runs_on": "this-mac", "reasons": ["its card names this job"]}]
    tie_follows_the_line_reader(steps)
    assert steps[1]["model"] == catmus and "line reader" in steps[1]["reasons"][0]

    vision = {"hf": "wjbmattingly/comma-qwen-3.5-0.8b-full-33k", "revision": "x"}
    kept = [{"job": "read-a-line", "model": vision}, {"job": "tie-text-to-lines", "model": mccatmus, "reasons": []}]
    tie_follows_the_line_reader(kept)
    assert kept[1]["model"] == mccatmus, "a vision model is not a Kraken reader: the rules' choice stays"


def test_wide_a_step_with_no_model_carries_how_fichero_does_it_and_a_model_step_does_not(client):
    """`wide.nomodel.fichero-does-this-one`: the job's `how_it_works` (the topic's words) is served for a job with no model."""
    jobs = {j["id"]: j for j in client.get("/api/recipes/jobs").json()["items"]}
    for job in ("leave-out", "find-documents-in-a-folder", "prepare-the-image", "work-out-dates", "split-pages"):
        assert jobs[job]["needs_a_model"] is False and jobs[job]["how_it_works"], job
    assert jobs["tie-text-to-lines"]["how_it_works"] is None and jobs["read-a-line"]["how_it_works"] is None
