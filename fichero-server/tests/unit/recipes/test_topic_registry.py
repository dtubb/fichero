"""The topic registry: each topic's and each job's explanation is written once (#5471).

Spec: `source/models-chains-and-projects.md`, `source.onboard.topics-written-once` and
`source.onboard.teaches-the-method`. Why it matters: setup, the Inspector and Activity each need to
explain a step or a topic. If the engine does not serve the text, each surface writes its own copy,
and the copies drift (a step described one way in setup and another way in the Inspector). These
tests go through the real routes the app reads.
"""
from __future__ import annotations

import re
from pathlib import Path

import fichero_server
from _scan_files import scan_rglob
from fichero_server.recipes import topics as registry

#: The topics of section 7a ("What onboarding teaches"). Setup must be able to explain every one.
SECTION_7A = {
    "languages", "scripts", "fonts", "glyphs-and-unicode", "faithful-writing", "finding-sources",
    "models-and-memory", "kraken", "layout", "forms-and-tables", "workflows-and-recipes", "entities",
    "statements", "maps", "time-and-calendars", "normalisation", "output-formats", "fine-tuning",
    "remote-compute",
}
#: Shorter sentences ("Facts only.") are too common to prove a copy.
MIN_SENTENCE = 25
ENGINE = Path(fichero_server.__file__).parent
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".txt", ".jinja", ".j2"}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;?!])\s+", text) if len(s) >= MIN_SENTENCE]


def _flatten(source: str) -> str:
    """One line of text: Python's implicit string joins ("... the "\\n "image") and YAML's folded
    lines both become plain running text, so a sentence split across lines is still found."""
    joined = re.sub(r"[\"']\s*\n\s*[\"']", "", source)
    return " ".join(joined.split())


def test_every_job_any_purpose_can_propose_has_a_topic(client):
    """Every step setup can put in a recipe, for every purpose (and the training step a large volume
    adds), has its explanation in the registry. WHY: a step setup cannot explain is a step the
    person is asked to accept blind (`source.onboard.teaches-the-method`)."""
    purposes = [p["id"] for p in client.get("/api/recipes/purposes").json()["items"]]
    assert purposes
    proposed: set[str] = set()
    for purpose in purposes:
        r = client.post("/api/recipes/assemble", json={
            "purpose": purpose, "languages": ["es"], "scripts": ["Latn"], "pages": 10_000,
            "mac_memory_gb": 16})
        assert r.status_code == 200, (purpose, r.text)
        proposed |= {s["job"] for s in r.json()["steps"]}
        proposed |= set(r.json().get("cloud_options") or [])
    assert "train-a-model" in proposed  # the large volume really did reach the training step
    for job in proposed:
        r = client.get(f"/api/topics/{job}")
        assert r.status_code == 200, (job, r.text)
        assert r.json()["kind"] == "job" and r.json()["short"] and r.json()["long"]


def test_every_registered_job_reads_its_words_from_its_topic(client):
    """The jobs route names each job's topic, and its name and description ARE that topic's words.
    WHY: setup already shows `description` from `GET /api/recipes/jobs`; if it were a second copy,
    setup and the Inspector could disagree (`source.onboard.topics-written-once`)."""
    jobs = client.get("/api/recipes/jobs").json()["items"]
    topics = {t["id"]: t for t in client.get("/api/topics").json()["items"]}
    assert jobs
    for job in jobs:
        topic = topics[job["topic"]]
        assert topic["kind"] == "job"
        assert job["name"] == topic["title"]
        assert job["description"] == f"{topic['short']} {topic['long']}"
    # Every job topic belongs to a registered job: no orphan text for a job that does not exist.
    assert {t["id"] for t in topics.values() if t["kind"] == "job"} == {j["topic"] for j in jobs}


def test_the_list_and_item_routes_serve_every_topic_setup_teaches(client):
    """WHY: setup walks the topics of section 7a; each must be servable by id, with a one-sentence
    short, a paragraph and an example from the person's own pages."""
    body = client.get("/api/topics").json()
    assert body["count"] == len(body["items"])
    listed = {t["id"]: t for t in body["items"]}
    assert SECTION_7A <= {i for i, t in listed.items() if t["kind"] == "topic"}
    for topic_id in SECTION_7A:
        r = client.get(f"/api/topics/{topic_id}")
        assert r.status_code == 200, r.text
        topic = r.json()
        assert topic == listed[topic_id]
        assert topic["title"] and topic["example"]
        # short is one sentence: no full stop before its last character
        assert not re.search(r"[.?!]\s", topic["short"]), topic["short"]
        assert topic["short"] not in topic["long"]  # the paragraph follows it, never repeats it


def test_an_unknown_topic_is_a_404_not_an_empty_explanation(client):
    """WHY: an empty 200 would let a surface show a blank explanation as if it were the text."""
    r = client.get("/api/topics/no-such-topic")
    assert r.status_code == 404
    assert "no-such-topic" in r.json()["detail"]


def test_a_manual_link_names_a_page_that_exists():
    """WHY: a manual link to a page that is not there sends the person nowhere."""
    root = ENGINE.parents[2]
    for topic in registry.all_topics():
        if topic.manual:
            assert (root / topic.manual).is_file(), (topic.id, topic.manual)


def test_the_flattening_finds_a_sentence_split_across_python_lines():
    """The duplicate check below must see through Python's implicit string joins, the way the job
    descriptions were written before #5471 moved them; otherwise it would pass while blind."""
    source = ('_job("x", "Crops, straightens, rotates or brightens a page and keeps the result as a new "\n'
              '     "version of the image; the original is never changed.")')
    topic = registry.get_topic("prepare-the-image")
    assert topic is not None
    assert _sentences(topic.short)[0] in _flatten(source)


def test_each_sentence_of_a_topic_is_written_in_exactly_one_engine_file():
    """`source.onboard.topics-written-once`: a topic's words live in `recipes/seed/topics.yaml` and
    nowhere else in the engine's code or resources. WHY: a second copy (in a route, a workflow's
    JSON, a prompt) drifts from the first the next time either is edited."""
    sentences = {s: t.id for t in registry.all_topics() for s in _sentences(t.short) + _sentences(t.long)}
    assert sentences
    seen_in: dict[str, list[str]] = {s: [] for s in sentences}
    for path in scan_rglob(ENGINE, "*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = _flatten(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        for sentence in sentences:
            if sentence in text:
                seen_in[sentence].append(str(path.relative_to(ENGINE)))
    wrong = {s: files for s, files in seen_in.items() if files != [str(registry.SEED.relative_to(ENGINE))]}
    assert not wrong, wrong
