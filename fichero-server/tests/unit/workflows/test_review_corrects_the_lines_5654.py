"""The paleographer's review corrects the page's lines (`source.job.correct-onto-lines`, #5654 item 3).

Spec (source/models-chains-and-projects.md, job `correct`: "a reading + the picture it was read from ->
a new reading that names the first"; source-model.md: "reading, correcting and checking add readings to
its segments").

WHY: on the demo (2026-10-10) the recipe's Paleographer Review step stored its corrections only as a
whole-page `transcription_review` artifact. The page's text is derived from its lines, so the corrected
text never became the page's text, and the names, statements and search steps read Kraken's raw lines.

Driven through the real Transcribe tool (Kraken finds and reads the lines) and the real Transcribe Review
tool, the real reading writes and the real derived text. Only Kraken's segmenter and reader and the vision
model's answer are faked.
"""
from __future__ import annotations

import pytest

from fichero_server.db.manager import db_manager

WIDTH, HEIGHT = 400, 300
REVIEWER = ("mlx", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
KRAKEN_READS = ["el dicho escrivano", "vezino de la cibdad", "y lo firmo"]


def _poly(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


FOUND = {
    "width": WIDTH, "height": HEIGHT, "regions": [],
    "lines": [
        {"baseline": [[20, 50], [380, 50]], "polygon": _poly(20, 20, 380, 60), "region": None},
        {"baseline": [[20, 110], [380, 110]], "polygon": _poly(20, 80, 380, 120), "region": None},
        {"baseline": [[20, 250], [380, 250]], "polygon": _poly(20, 220, 380, 260), "region": None},
    ],
}


@pytest.fixture
async def page(test_package, tmp_path, monkeypatch):
    """A page whose lines Kraken found and read."""
    from PIL import Image

    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    library = str(test_package)
    db = db_manager.get_database(library)
    path = tmp_path / "testamento_p1.png"
    Image.new("RGB", (WIDTH, HEIGHT), "white").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kw: FOUND)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda image_path, model_path, lines, **kw: KRAKEN_READS)
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=LLMConfig(provider="", model=""))
    for extra in ({}, {"kraken_model": "kraken-mccatmus"}):  # find the lines, then read them
        done = await transcribe(
            inputs={"files": src["files"], "documents": src["documents"], "vision_mode": "kraken",
                    "regions_first": False, **extra},
            state={"library_path": library, "task_id": None}, llm_config=LLMConfig(provider="", model=""))
        assert not done.get("error"), done.get("error")
    return {"library": library, "db": db, "doc": doc, "src": src}


def _lines(page):
    from fichero_server.llm.working_lines import working_lines

    return working_lines(page["db"], page["doc"].id).lines


def _counting(page):
    from fichero_server.api.routes.document.segment_readings import counting_texts

    rows = _lines(page)
    texts = counting_texts(page["db"], rows)
    return [texts.get(row.id, "") for row in rows]


def _readings(page, row):
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    return readings_of_segment(page["db"], row.id)


async def _review(page, monkeypatch, answer: str, **extra):
    import fichero_server.llm as llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    seen = {}

    async def reviewer(images, prompt, config, **kw):
        seen["prompt"] = prompt
        return answer

    monkeypatch.setattr(llm, "vision", reviewer)
    result = await transcribe_review(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"],
                "skip_if_artifact_exists": False, **extra},
        state={"library_path": page["library"], "task_id": "run-review-1"},
        llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
    assert not result.get("error"), result.get("error")
    result["prompt"] = seen["prompt"]
    return result


def _page_text(page):
    from fichero_server.api.routes.document.segment_readings import document_text
    from fichero_server.models import Document

    return document_text(page["db"], page["doc"].id).text, page["db"].get(Document, page["doc"].id).page_content


@pytest.mark.asyncio
async def test_a_reviewed_line_gets_the_reviewers_reading_and_the_page_text_follows(page, monkeypatch):
    """#5654 item 3: the review that changes line 2 leaves line 2 with a new counting reading made by the
    review's model, derived from Kraken's reading of it; lines 1 and 3, unchanged, get nothing; the page's
    text (derived and cached) carries the correction, so the steps after it read it.
    WHY: the corrections stayed on a page-level artifact nothing downstream reads."""
    from fichero_server.models import Artifact, ContentRepresentation

    assert _counting(page) == KRAKEN_READS
    before = {row.id: [r.id for r in _readings(page, row)] for row in _lines(page)}
    kraken_reading_of_2 = _readings(page, _lines(page)[1])[0]

    result = await _review(page, monkeypatch, "el dicho escrivano\nvezino de la ciudad\ny lo firmo")

    assert _counting(page) == ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"]
    first, second, third = _lines(page)
    assert [r.id for r in _readings(page, first)] == before[first.id]
    assert [r.id for r in _readings(page, third)] == before[third.id]
    (new,) = [r for r in _readings(page, second) if r.id not in before[second.id]]
    (review,) = page["db"].query(Artifact, document_id=page["doc"].id, artifact_type="transcription_review")
    assert (review.provider, review.model) == REVIEWER
    assert new.derived_from_artifact_id == review.id
    assert new.derived_from_representation_id == kraken_reading_of_2.id
    assert (new.kind, new.level) == ("transcription", "as_written")
    assert page["db"].get(ContentRepresentation, new.id).producer_run_id == "run-review-1"
    assert getattr(new.provenance_kind, "value", new.provenance_kind) == "workflow"
    derived, cached = _page_text(page)
    assert "vezino de la ciudad" in derived and "cibdad" not in derived
    assert cached == derived
    assert result["results"][0]["lines"] == "1 of 3 line(s) corrected"


@pytest.mark.asyncio
async def test_a_review_that_names_the_lines_by_id_is_matched_by_id(page, monkeypatch):
    """The review is shown the lines as `id | box | maker | text`; a model that answers in that shape (even
    leaving a line out) is put back on the lines by id, not by position.
    WHY: matching by position would put line 3's correction on line 2 when the model drops a line."""
    first, second, third = _lines(page)
    await _review(page, monkeypatch, f"{third.id} | 0 0 1 1 | machine | y lo firmó\n")
    assert _counting(page) == ["el dicho escrivano", "vezino de la cibdad", "y lo firmó"]


@pytest.mark.asyncio
async def test_a_line_a_person_read_keeps_the_persons_reading(page, monkeypatch):
    """A run never writes over a person: a line whose counting reading is a person's gets no review
    reading, while the review's other corrections still land.
    WHY: a person's transcription is the page's ground truth; a model's second look must not displace it."""
    import fichero_server.api.routes.document.content_representations  # noqa: F401
    from fichero_server.actions.registry import ActionContext, registry

    first, second, third = _lines(page)
    registry.invoke(page["db"], "representation.create", {
        "document_id": page["doc"].id, "segment_id": first.id, "kind": "transcription",
        "content": "el dicho escriuano"}, ActionContext(actor="daniel", library_path=page["library"]))
    before = [r.id for r in _readings(page, first)]

    result = await _review(page, monkeypatch, "el dicho escrivano\nvezino de la ciudad\ny lo firmo")

    assert [r.id for r in _readings(page, first)] == before
    assert _counting(page) == ["el dicho escriuano", "vezino de la ciudad", "y lo firmo"]
    assert result["results"][0]["lines"] == "1 of 3 line(s) corrected; 1 line(s) a person read kept"


@pytest.mark.asyncio
async def test_a_review_that_cannot_be_matched_stays_an_artifact_and_says_so(page, monkeypatch):
    """A review whose text does not line up with the page's lines (here two lines for three) writes no
    reading: it stays the page's `transcription_review` artifact, and the step's per-page result says it
    was not tied to lines.
    WHY: guessing which line a correction belongs to would put words on the wrong line, silently."""
    from fichero_server.models import Artifact

    before = {row.id: [r.id for r in _readings(page, row)] for row in _lines(page)}
    result = await _review(page, monkeypatch, "el dicho escrivano vezino de la ciudad\ny lo firmo")

    assert {row.id: [r.id for r in _readings(page, row)] for row in _lines(page)} == before
    assert _counting(page) == KRAKEN_READS
    (review,) = page["db"].query(Artifact, document_id=page["doc"].id, artifact_type="transcription_review")
    assert "y lo firmo" in review.content
    said = result["results"][0]["lines"]
    assert "gave no reading" in said and "readings are unchanged" in said  # #5720: asked again, then the step fails
    assert any(note.endswith(said) for note in result["notes"])


@pytest.mark.asyncio
async def test_the_review_prompt_asks_for_one_answer_line_per_segment_id(page, monkeypatch):
    """`source.job.review-asks-one-answer-line-per-segment-id` (#5719): a model that answers by segment id only
    when the prompt it is sent asks for that gets its corrections tied to the lines; one that is not asked
    answers a paragraph and nothing is tied.
    WHY: Qwen2.5-VL answered 16 lines for 44 on 39_Hoja_549_Recto.JPG because the prompt never asked for one
    line per segment id; the Paleographer Review preset (r1, r2, r3) carries its own prompts, so the ask is made
    by the tool whatever prompt it is given."""
    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    first, second, third = _lines(page)

    async def model(images, prompt, config, **kw):
        asked = "one line per" in prompt.lower() and "segment id" in prompt.lower()
        if not asked:
            return "el dicho escrivano vezino de la ciudad y lo firmo"
        return f"{first.id} | el dicho escrivano\n{second.id} | vezino de la ciudad\n{third.id} | y lo firmo"

    monkeypatch.setattr(llm, "vision", model)
    result = await transcribe_review(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"],
                "skip_if_artifact_exists": False,
                # the preset's own wording (Paleographer Review r1): the recipe never sends the default prompt
                "prompt": "You are a paleographer reviewing an EXISTING transcription. Output the COMPLETE "
                          "corrected transcription (same line breaks), nothing else."},
        state={"library_path": page["library"], "task_id": "run-review-2"},
        llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
    assert not result.get("error"), result.get("error")

    assert _counting(page) == ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"]
    assert result["results"][0]["lines"] == "1 of 3 line(s) corrected"


def test_the_review_knows_a_page_listed_by_segment_id_from_a_paragraph():
    """`source.job.review-asks-one-answer-line-per-segment-id`: the ask is made for the lines as shown and for an
    earlier pass's answer by id (what Paleographer Review's r2 and r3 are given), never for a plain paragraph.
    WHY: r2 and r3 take r1's output as context; if only the first pass asked, the later passes would untie it."""
    from fichero_server.workflows.tools.transcribe_review import shows_segment_lines

    sid = "595a7e84a5595d528eff5bf33244635e"
    assert shows_segment_lines(f"{sid} | 0.1 0.2 0.5 0.03 | machine | el dicho")
    assert shows_segment_lines([f"{sid} | el dicho escrivano"])
    assert not shows_segment_lines("el dicho escrivano vezino de la ciudad")
    assert not shows_segment_lines(None)


def _shipped_review_prompts():
    """Every `transcribe_review` node of every shipped workflow, with the prompt it carries (what a recipe sends)."""
    import json
    from pathlib import Path

    import fichero_server
    from fichero_server.workflows.tools.transcribe_review import build_transcribe_review_prompt

    root = Path(fichero_server.__file__).parent / "resources" / "default_workflows"
    found = []
    for path in sorted(root.glob("*.json")):
        for node in json.loads(path.read_text()).get("nodes", []):
            data = node.get("data") or {}
            config = node.get("config") or data.get("config") or {}
            if (node.get("tool") or node.get("type") or data.get("tool")) == "transcribe_review" and (
                    config.get("prompt") or config.get("lens")):
                found.append(pytest.param(build_transcribe_review_prompt(config), id=f"{path.stem}:{node.get('id')}"))
    return found


def test_the_shipped_review_prompts_are_found():
    """A floor under the parametrised test below, so it cannot pass by finding nothing (the preset has r1, r2, r3)."""
    assert len(_shipped_review_prompts()) >= 3


@pytest.mark.asyncio
async def test_every_shipped_review_node_ties_its_answer_to_the_lines(page, monkeypatch):
    """`source.job.review-asks-one-answer-line-per-segment-id` through the REAL prompts a recipe sends, not a stand-in:
    a model that answers by id only when asked is tied to the lines under each shipped node's own prompt (one review
    after another on the same page, each changing the last line so its tie is visible).
    WHY: the first fix changed the default prompt, which no preset uses; the page stayed untied."""
    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    first, second, third = _lines(page)
    turn = {"n": 0}

    async def model(images, prompt, config, **kw):
        if not ("one line per" in prompt.lower() and "segment id" in prompt.lower()):
            return "el dicho escrivano vezino de la ciudad y lo firmo"
        return (f"{first.id} | el dicho escrivano\n{second.id} | vezino de la cibdad\n"
                f"{third.id} | y lo firmo {turn['n']}")

    monkeypatch.setattr(llm, "vision", model)
    prompts = [param.values[0] for param in _shipped_review_prompts()]
    for number, shipped_prompt in enumerate(prompts, start=1):
        turn["n"] = number
        result = await transcribe_review(
            inputs={"files": page["src"]["files"], "documents": page["src"]["documents"],
                    "skip_if_artifact_exists": False, "prompt": shipped_prompt},
            state={"library_path": page["library"], "task_id": f"run-review-{number}"},
            llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
        assert not result.get("error"), result.get("error")
        assert _counting(page)[2] == f"y lo firmo {number}", f"prompt {number} of {len(prompts)} was not tied"


@pytest.mark.asyncio
async def test_a_line_the_review_flags_unreadable_is_left_as_read_and_says_so_5724(page, monkeypatch):
    """`source.job.review-is-segment-native` (#5724): a flag per line; a line the model marks unreadable keeps
    its reading (never invented text), the others are corrected by id.
    WHY: a model forced to give text for a line it cannot read invents it."""
    first, second, third = _lines(page)
    result = await _review(page, monkeypatch, "\n".join([
        f"{first.id} | certain | el dicho escriuano",
        f"{second.id} | unreadable | xxxx",
        f"{third.id} | certain | y lo firmó"]))
    assert _counting(page) == ["el dicho escriuano", "vezino de la cibdad", "y lo firmó"]
    assert "1 line(s) flagged unreadable" in result["results"][0]["lines"]


def _set_confidence(page, row, value):
    from fichero_server.models import ContentRepresentation

    reading = _readings(page, row)[0]
    stored = page["db"].get(ContentRepresentation, reading.id)
    stored.machine_confidence = value
    page["db"].save(stored)


@pytest.mark.asyncio
async def test_the_review_is_shown_each_lines_confidence_5724(page, monkeypatch):
    """`source.job.review-is-segment-native`: the review is given the lines as `id | box | maker | confidence |
    text`, so it knows which line the machine was unsure of.
    WHY: without the machine's confidence the review cannot spend its attention where the reading is weak."""
    first, second, third = _lines(page)
    _set_confidence(page, second, 0.41)
    result = await _review(page, monkeypatch, "\n".join(
        f"{r.id} | certain | {t}" for r, t in zip((first, second, third), KRAKEN_READS)))
    shown = {line.split(" | ")[0]: line.split(" | ") for line in result["prompt"].splitlines()
             if line[:32] in {first.id, second.id, third.id} and " | " in line and "|" in line[32:40]}
    assert shown[second.id][3] == "0.41" and shown[second.id][4] == KRAKEN_READS[1]
    assert shown[first.id][3] == "-"  # none stated: said so, not guessed


@pytest.mark.asyncio
async def test_an_uncertain_line_keeps_the_machines_confidence_5724(page, monkeypatch):
    """A line the review flags uncertain, and changes, is not made more sure than the machine was: its new reading
    carries the confidence of the reading it corrects; a line flagged certain is not given one.
    WHY: a correction the model is unsure of must not read as a checked line (#5694)."""
    first, second, third = _lines(page)
    _set_confidence(page, second, 0.41)
    await _review(page, monkeypatch, "\n".join([
        f"{first.id} | certain | el dicho escriuano",
        f"{second.id} | uncertain | vezino de la ciudad",
        f"{third.id} | certain | y lo firmó"]))
    by_text = {r.content: r for row in _lines(page) for r in _readings(page, row)}
    assert by_text["vezino de la ciudad"].machine_confidence == 0.41
    assert by_text["el dicho escriuano"].machine_confidence is None


@pytest.mark.asyncio
async def test_a_corrected_line_records_the_lens_that_changed_it_5724(page, monkeypatch):
    """The step is run through a lens (a name the recipe gives it); the reading it writes names the review
    artifact it came from, and that artifact records the lens.
    WHY: an apparatus must say which look at the page made a change, so a lens is judged by what it changed."""
    from fichero_server.models import Artifact, ContentRepresentation

    second = _lines(page)[1]
    await _review(page, monkeypatch, f"{second.id} | certain | vezino de la ciudad", lens="orthography")
    (new,) = [r for r in _readings(page, second) if r.content == "vezino de la ciudad"]
    artifact = page["db"].get(Artifact, page["db"].get(ContentRepresentation, new.id).derived_from_artifact_id)
    assert artifact.data["lens"] == "orthography"


@pytest.mark.asyncio
async def test_a_lines_short_note_is_kept_with_the_review_and_never_read_as_its_text_5724(page, monkeypatch):
    """The review may add a short note after a line (`<id> | <flag> | <text> | <note>`): the line's reading is the
    text, and the note is kept on the review artifact under the line's id.
    WHY: a person checking a correction needs the reviewer's reason, and a note read as the text would replace the line."""
    from fichero_server.models import Artifact, ContentRepresentation

    second = _lines(page)[1]
    await _review(page, monkeypatch, f"{second.id} | uncertain | vezino de la ciudad | note: c and z unclear in this hand")
    (new,) = [r for r in _readings(page, second) if r.content == "vezino de la ciudad"]
    artifact = page["db"].get(Artifact, page["db"].get(ContentRepresentation, new.id).derived_from_artifact_id)
    assert artifact.data["line_notes"] == {second.id: "c and z unclear in this hand"}
    assert not [r for r in _readings(page, second) if "unclear" in r.content]


def _shipped_review_node_configs():
    import json
    from pathlib import Path

    import fichero_server

    path = Path(fichero_server.__file__).parent / "resources" / "default_workflows" / "transcribe_paleography_review.json"
    return [node["config"] for node in json.loads(path.read_text())["nodes"] if node.get("tool") == "transcribe_review"]


@pytest.mark.asyncio
async def test_the_shipped_review_is_built_from_the_projects_answers_5723(page, monkeypatch):
    """`source.job.review-is-built-from-the-project-and-a-profile`, through the REAL preset (Paleographer Review's own
    three nodes) and the project's saved setup: an English project is never sent "carta de poder" or "ç/c/z", a
    Spanish colonial one is.
    WHY: the preset's prompts were Spanish colonial whatever the project said."""
    from pathlib import Path

    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.recipes.project import write_project_setup
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    seen = []

    async def model(images, prompt, config, **kw):
        seen.append(prompt)
        return "el dicho escrivano\nvezino de la cibdad\ny lo firmo"

    monkeypatch.setattr(llm, "vision", model)
    configs = _shipped_review_node_configs()
    assert len(configs) == 3
    for tags, years, sent in ((["en"], "1600", False), (["es"], "1650", True)):
        write_project_setup(Path(page["db"].path).parent, {
            "purposes": ["transcribe"], "languages": tags, "scripts": ["Latn"], "materials": ["handwriting"],
            "period": years}, None)
        seen.clear()
        for config in configs:
            result = await transcribe_review(
                inputs={**config, "files": page["src"]["files"], "documents": page["src"]["documents"],
                        "skip_if_artifact_exists": False},
                state={"library_path": page["library"], "task_id": "run-profile"},
                llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
            assert not result.get("error"), result.get("error")
            assert any("profile" in n or "review is used" in n for n in result["notes"])
        assert len(seen) >= 3
        for prompt in seen:
            assert ("carta de poder" in prompt or "ç/c/z" in prompt) is sent, (tags, prompt)


@pytest.mark.asyncio
async def test_a_bar_inside_a_lines_text_stays_in_its_text_5724(page, monkeypatch):
    """Diplomatic text may hold `|` or `||` (a line or verse divider on the page): only the leading id and flag are
    split off, so the whole rest is the line's text.
    WHY: splitting on every bar kept only the last piece and dropped the line's beginning."""
    second = _lines(page)[1]
    await _review(page, monkeypatch, f"{second.id} | certain | vezino || de la ciudad | note: divider kept")
    assert [r.content for r in _readings(page, second) if "vezino" in r.content and "ciudad" in r.content] == [
        "vezino || de la ciudad"]


@pytest.mark.asyncio
async def test_a_note_without_a_flag_is_never_the_lines_text_5724(page, monkeypatch):
    """A model that drops the flag but adds a note (`<id> | <text> | note: ...`): the text is still the line's
    reading and the note is still kept as its note.
    WHY: with the flag gone, the last column was taken as the text, so the note replaced the line."""
    from fichero_server.models import Artifact, ContentRepresentation

    second = _lines(page)[1]
    await _review(page, monkeypatch, f"{second.id} | vezino de la ciudad | note: z for c")
    (new,) = [r for r in _readings(page, second) if r.content == "vezino de la ciudad"]
    artifact = page["db"].get(Artifact, page["db"].get(ContentRepresentation, new.id).derived_from_artifact_id)
    assert artifact.data["line_notes"] == {second.id: "z for c"}


@pytest.mark.asyncio
async def test_a_page_over_the_models_budget_is_sent_the_lines_that_fit_and_told_what_was_left_out_5648(page, monkeypatch):
    """A model whose card states a prefill budget is sent the page's lines in reading order up to it; the prompt
    says how many lines were left out, and the lines it was sent still land.
    WHY: 656 rows (43k tokens) to a local 3B model never reached its first token before the engine's wait ran out."""
    from fichero_server.recipes import cards

    first, second, third = _lines(page)
    monkeypatch.setattr(cards, "prefill_tokens_for", lambda model: 1)  # room for the first line only
    result = await _review(page, monkeypatch, f"{first.id} | certain | el dicho escriuano")
    assert first.id in result["prompt"] and third.id not in result["prompt"]
    assert "2 of the page's 3 lines were left out" in result["prompt"]
    assert _counting(page)[0] == "el dicho escriuano"
    assert any("left out" in note for note in result.get("notes") or [])


def test_the_3b_mlx_reader_states_its_prefill_budget_5648():
    from fichero_server.recipes.cards import prefill_tokens_for

    assert prefill_tokens_for("mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
    assert prefill_tokens_for("gemini-2.5-pro") is None
