"""Setup, the maintainer's test notes of 2026-10-09: the engine half (section 7b of
`source/models-chains-and-projects.md`; #5625, #5626, #5627).

Why it matters: the difference between "The full knowledge graph", "Statements" and "Entities" was unclear, so
the goals are ordered and grouped (`source.onboard.purposes-grouped`); a person who names English was then asked
for its script, which Fichero can know (`source.onboard.script-from-language`); and the plan on Ready could not be
edited (`source.onboard.plan-editable`). Through the real routes, so the app, MCP and the command line all see
exactly what is pinned here.
"""
from __future__ import annotations

TRANSCRIBE = ["find-lines", "read-a-line", "correct"]


def _assemble(client, **answers):
    body = {"languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16, **answers}
    return client.post("/api/recipes/assemble", json=body)


def _jobs(recipe: dict) -> list[str]:
    return [s["job"] for s in recipe["steps"]]


# --- The goals, ordered and grouped (#5625, source.onboard.purposes-grouped) ------------------------------


def test_the_goals_come_in_the_ruled_order_with_their_options_under_them(client):
    """WHY: ruled 2026-10-09: Transcribe; Search under it; Translate after it; the Knowledge graph with Entities
    and Statements as its options below it. If the order or the grouping drifted, setup would again list three
    look-alike graph goals side by side."""
    items = client.get("/api/recipes/purposes").json()["items"]
    ids = [p["id"] for p in items]
    assert ids[:6] == ["transcribe", "search", "translate-normalise", "knowledge-graph", "entities", "statements"]
    parents = {p["id"]: p.get("parent") for p in items}
    assert parents["search"] == "transcribe"
    assert parents["entities"] == parents["statements"] == "knowledge-graph"
    assert parents["transcribe"] is None and parents["knowledge-graph"] is None and parents["map-places"] is None
    titles = {p["id"]: p["title"] for p in items}
    assert (titles["transcribe"], titles["knowledge-graph"], titles["entities"]) == (
        "Transcribe", "Knowledge graph", "Entities")


def test_the_knowledge_graph_holds_every_job_of_its_options(client):
    """WHY: the options are listed under the graph because ticking it includes them; the app shows them as
    included only when the graph's jobs really hold theirs."""
    items = {p["id"]: {j["id"] for j in p["jobs"]} for p in client.get("/api/recipes/purposes").json()["items"]}
    assert items["entities"] <= items["knowledge-graph"] and items["statements"] <= items["knowledge-graph"]


def test_an_option_is_still_a_purpose_of_its_own(client):
    """WHY: Entities alone (names found, no graph) must stay possible: grouping changes where it is listed, not
    what it does."""
    r = _assemble(client, purposes=["entities"])
    assert r.status_code == 200, r.text
    assert _jobs(r.json()) == [*TRANSCRIBE, "find-names-tag-words"]


# --- A language proposes its usual script (#5626, source.onboard.script-from-language) ------------------


def test_a_language_match_carries_its_usual_script(client):
    """WHY: English is written in Latin and Russian in Cyrillic; asking would be asking what Fichero knows. Old
    languages too: Classical Syriac is written in Syriac and Ancient Greek in Greek, never a Latin default."""
    def first(q):
        return client.get("/api/recipes/languages", params={"q": q}).json()["items"][0]

    english = first("English")
    assert (english["code"], english["script"], english["script_name"]) == ("en", "Latn", "Latin")
    assert first("Russian")["script"] == "Cyrl"
    assert first("syc")["script"] == "Syrc"
    assert first("grc")["script"] == "Grek"


def test_a_language_with_no_usual_script_on_record_proposes_none():
    """WHY: a guess is worse than asking: a language CLDR does not know proposes nothing, and a tag that names
    its own script keeps it (Serbian in Latin)."""
    from fichero_server.recipes.names import usual_script

    assert usual_script("zz") is None and usual_script(None) is None
    assert usual_script("und-x-abcd1234") is None
    assert usual_script("sr") == "Cyrl" and usual_script("sr-Latn") == "Latn"
    assert usual_script("eng") == "Latn"  # an ISO 639-3 code reads as its tag


def test_every_usual_script_is_a_known_script():
    """WHY: a proposed script the rules cannot read would refuse every reader."""
    from fichero_server.recipes.derived import unknown_scripts
    from fichero_server.recipes.names import _usual_scripts

    assert not unknown_scripts(sorted(set(_usual_scripts().values())))


# --- Ready: the plan can be edited (#5627, source.onboard.plan-editable) -----------------------------------


def test_a_step_taken_out_leaves_the_plan_and_is_offered_back(client):
    """WHY: a person who does not want search vectors takes that step out on Ready; proposing the plan again
    (any change of answer re-assembles it) must not bring it back, and Ready must be able to put it back."""
    r = _assemble(client, purposes=["transcribe", "search"], removed_jobs=["make-a-vector"])
    assert r.status_code == 200, r.text
    assert _jobs(r.json()) == TRANSCRIBE
    assert r.json()["removed"] == [{"job": "make-a-vector", "title": r.json()["removed"][0]["title"]}]
    assert r.json()["removed"][0]["title"]
    assert not r.json()["problems"]


def test_a_step_another_needs_stays_and_says_which(client):
    """WHY: taking out Find lines would leave Read each line with nothing to read; the plan would fail its own
    check at Start. Such a step stays, carrying the steps that need it, and is never listed as taken out."""
    r = _assemble(client, purposes=["transcribe"], removed_jobs=["find-lines"]).json()
    assert _jobs(r) == TRANSCRIBE and r["removed"] == []
    lines = next(s for s in r["steps"] if s["job"] == "find-lines")
    assert "read-a-line" in lines["needed_by"]
    last = next(s for s in r["steps"] if s["job"] == "correct")
    assert not last.get("needed_by")  # the last step can always go


def test_taking_out_a_step_and_the_one_that_needed_it_frees_both(client):
    """WHY: removing Find names and Find statements together (statements need names) must take out both, not
    keep names because statements were still there when names were looked at."""
    r = _assemble(client, purposes=["statements"], removed_jobs=["find-names-tag-words", "find-statements"]).json()
    assert _jobs(r) == TRANSCRIBE
    assert [t["job"] for t in r["removed"]] == ["find-names-tag-words", "find-statements"]


def test_the_removed_steps_are_saved_with_the_project_and_start_runs_the_edited_plan(client):
    """WHY: the edit is kept with the project's setup, so Set Up… reopens with it and Start runs what Ready
    showed, not the plan from before the edit."""
    answers = {"purposes": ["transcribe", "search"], "languages": ["es"], "scripts": ["Latn"],
               "removed_jobs": ["make-a-vector"]}
    recipe = _assemble(client, **{k: v for k, v in answers.items()}).json()
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
    assert r.status_code == 200, r.text
    saved = client.get("/api/recipes/project").json()
    assert saved["answers"]["removed_jobs"] == ["make-a-vector"]
    assert "make-a-vector" not in [s["job"] for s in saved["recipe"]["steps"]]
    plan = client.get("/api/recipes/project/start").json()
    planned = {j for w in plan["workflows"] for j in w["steps"]} | {s["step"] for s in plan["skipped"]}
    assert "make-a-vector" not in planned


def test_an_unknown_removed_job_is_refused_in_words(client):
    r = client.put("/api/recipes/project", json={"answers": {
        "purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "removed_jobs": ["astrology"]},
        "recipe": None})
    assert r.status_code == 422 and "astrology" in r.text
