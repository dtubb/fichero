"""The bake-off, slice 1: the readers (#4951, `source.try.bakeoff-is-the-same-tool`), tested to the spec.

`source/models-chains-and-projects.md` sections 8 and 8a; `compute/distillation.md` "Evaluation against
out-of-the-box models". The bake-off is the evaluation job run on the project's corrected sample pages:
the top three readers by rule rank (and Tesseract for print, never handwriting) read the same pages, each
scored by the one CER; the table is ranked by the fixed order and kept; Use This writes an override on the
recipe for a scope, audited.

Everything goes through the routes (`/api/recipes/project/bakeoffs...`), the job as the scheduler runs it
(`jobs.KINDS["evaluate-models"].run`), and the recipe as `GET /api/recipes/project` reads it back. Kraken is
faked at its seam (`kraken_runtime.read_given_lines`): no model, no network, nothing downloaded.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.models import ActionAudit, DocType, Document
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import SegmentPass
from fichero_server.recipes import bakeoff
from fichero_server.recipes.assemble import Answers
from fichero_server.recipes.cards import all_seed_cards
from fichero_server.training import evaluation
from fichero_server.workflows import transcription_accuracy
from tests.unit.training.test_kraken_training_set import _page

#: The three readers the rules rank for Latin-script Spanish handwriting, in rule order: PP-OCRv6 has a
#: published CER; the two CATMuS readers tie on everything else and fall to their card ids.
PPOCR = "kraken:zenodo/10.5281/zenodo.21788410@unpinned"
MEDIEVAL = "kraken:zenodo/10.5281/zenodo.12743230@unpinned"
MCCATMUS = "kraken:zenodo/10.5281/zenodo.13788177@unpinned"
TESSERACT = "tesseract:tessdata/spa@unpinned"
READER_IDS = {PPOCR: "kraken-zenodo-21788410", MEDIEVAL: "kraken-catmus-medieval", MCCATMUS: "kraken-mccatmus"}
LINES_PER_PAGE = 44  # the corpus fixture's PAGE file


@pytest.fixture(autouse=True)
def homes(tmp_path, monkeypatch):
    """Kraken's readers and the MLX store in the test's own folders, never this Mac's."""
    from fichero_server.llm import mlx_model_store

    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    store = mlx_model_store.MLXModelStore(tmp_path / "mlx")
    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: store)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs the job itself


class Readers:
    """Kraken's reader, faked at the seam: PP-OCRv6 reads every line right, CATMuS Medieval drops each
    line's last character, McCATMuS its last three. Records which photograph each reader was given."""

    def __init__(self, paths: dict[str, str]):
        self.drop = {paths[PPOCR]: 0, paths[MEDIEVAL]: 1, paths[MCCATMUS]: 3}
        self.read: dict[str, list[str]] = {}

    def __call__(self, image_path, model_path, lines, **kw):
        self.read.setdefault(str(model_path), []).append(str(image_path))
        n = self.drop[str(model_path)]
        return [ln["text"][:-n] if n else ln["text"] for ln in lines]


@pytest.fixture
def readers(tmp_path, monkeypatch):
    """The three readers installed on this (test) Mac, read through the fake."""
    paths = {}
    for card, reader in READER_IDS.items():
        weights = tmp_path / f"{reader}.mlmodel"
        weights.write_bytes(b"weights")
        marker = kraken_runtime._marker_path(reader)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"model_path": str(weights)}), encoding="utf-8")
        paths[card] = str(weights)
    fake = Readers(paths)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    fake.paths = paths
    return fake


def _corrected(db, tmp_path, name: str, folder: Document) -> Document:
    """A page whose lines a person corrected: its pass is a person's."""
    doc = _page(db, tmp_path, name, folder)
    (made,) = db.query(SegmentPass, document_id=doc.id)
    made.provenance_kind = ProvenanceKind.human
    db.save(made)
    return doc


@pytest.fixture
def folder(db):
    made = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(made)
    return made


def _set_up(client, *, materials=("handwriting",)):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": list(materials),
               "pages": 1000}
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    saved = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe.json()})
    assert saved.status_code == 200, saved.text
    return saved.json()["recipe"]


def _run(client, db, **body):
    r = client.post("/api/recipes/project/bakeoffs", json=body)
    assert r.status_code == 200, r.text
    started = r.json()
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [started["job_id"]])
    assert kind == evaluation.KIND
    evaluation.register_job_kinds()
    jobs.KINDS[kind].run(db, subject)
    done = client.get(f"/api/recipes/project/bakeoffs/{started['id']}")
    assert done.status_code == 200, done.text
    return started, done.json()


def _evaluation_jobs(db) -> int:
    return db.execute_fetchone("SELECT COUNT(*) FROM jobs WHERE kind = ?", [evaluation.KIND])[0]


def test_below_the_threshold_it_says_how_many_more_and_runs_nothing(client, db, tmp_path, folder, readers):
    """source.onboard.bakeoff-minimum: "at least 100 corrected lines on at least two pages ... below that it
    says how many more are needed".
    WHY: a bake-off on a handful of lines ranks readers by noise; the person needs to know what to correct
    next, in words, and nothing may be queued that would write a meaningless score on the cards."""
    _set_up(client)
    first = _corrected(db, tmp_path, "SM_NPQ_C01_001", folder)
    one_page = client.post("/api/recipes/project/bakeoffs", json={})
    assert one_page.status_code == 422
    said = one_page.json()["detail"]
    assert f"there are {LINES_PER_PAGE} on 1 page" in said
    assert f"Correct {100 - LINES_PER_PAGE} more corrected lines and corrected lines on 1 more page" in said

    _corrected(db, tmp_path, "SM_NPQ_C01_002", folder)
    two_pages = client.post("/api/recipes/project/bakeoffs", json={})
    assert two_pages.status_code == 422
    assert f"Correct {100 - 2 * LINES_PER_PAGE} more corrected lines," in two_pages.json()["detail"]
    assert _evaluation_jobs(db) == 0 and readers.read == {}
    assert client.get("/api/recipes/project/bakeoffs").json()["items"] == []
    # A page with only a model's reading is not ground truth.
    _page(db, tmp_path, "SM_NPQ_C01_003", folder)
    assert client.post("/api/recipes/project/bakeoffs", json={}).status_code == 422
    assert first.id in bakeoff.person_made_pages(db)


def test_tesseract_joins_for_print_and_never_for_handwriting():
    """source.onboard.bakeoff-tesseract-baseline: "for print or typescript, when Tesseract has data for the
    language, a Tesseract combination is in every bake-off; for handwriting it is never proposed".
    WHY: Tesseract is the fast local baseline a costlier reader must beat on print; on handwriting it only
    loses, and offering it there would teach the person to distrust the table. Not bundled yet, it is named
    with why and never scored in its place."""
    cards = list(all_seed_cards())

    def named(**answers):
        a = Answers(purposes=("transcribe",), scripts=frozenset({"Latn"}), mac_memory_gb=16, **answers)
        return {c["card"]: c for c in bakeoff.candidates(a, cards, volume=100)}

    on_print = named(languages=frozenset({"es"}), materials=("print",))
    assert on_print[TESSERACT]["role"] == "baseline for print" and on_print[TESSERACT]["rule_rank"] is None
    assert "not in this build" in on_print[TESSERACT]["not_scored"]
    assert TESSERACT in named(languages=frozenset({"es"}), materials=("handwriting", "typescript"))
    assert TESSERACT not in named(languages=frozenset({"es"}), materials=("handwriting",))
    assert TESSERACT not in named(languages=frozenset({"fr"}), materials=("print",))  # no French data
    readers_by_rank = [c for c in named(languages=frozenset({"es"}), materials=("handwriting",)).values()]
    assert [c["card"] for c in readers_by_rank] == [PPOCR, MEDIEVAL, MCCATMUS]
    assert [c["rule_rank"] for c in readers_by_rank] == [1, 2, 3]


def test_every_candidate_is_scored_by_the_one_cer_on_the_same_pages(client, db, tmp_path, folder, readers,
                                                                     monkeypatch):
    """source.try.bakeoff-is-the-same-tool: "there is one comparison code path"; section 8a: "All run on the
    same pages".
    WHY: a ranking is only fair when every reader reads exactly the same corrected pages and is scored by
    the one CER Fichero defines; a second scorer would drift, and a reader given other pages would win or
    lose on the pages, not on its reading."""
    _set_up(client)
    pages = [_corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder) for i in (1, 2, 3)]
    _page(db, tmp_path, "SM_NPQ_C01_009", folder)  # a model's reading only: never scored against
    calls = []
    real = transcription_accuracy.character_error_rate

    def one_cer(reference, hypothesis, *, policy=None):
        calls.append(policy)
        return real(reference, hypothesis, policy=policy)

    monkeypatch.setattr(transcription_accuracy, "character_error_rate", one_cer)

    started, done = _run(client, db)

    assert started["lines"] == 3 * LINES_PER_PAGE
    assert started["rows"] and all(r["why"] == "waiting for the evaluation job to score it" for r in started["rows"])
    assert [p["document_id"] for p in done["pages"]] == [p.id for p in pages]
    photos = sorted(p.path for p in pages)
    for card in READER_IDS:
        assert sorted(readers.read[readers.paths[card]]) == photos
    assert len(calls) == 3 * 3 * len(transcription_accuracy.POLICIES)  # 3 readers x 3 pages
    rows = {r["card"]: r for r in done["rows"]}
    assert set(rows) == set(READER_IDS)
    for card, row in rows.items():
        assert {p["document_id"] for p in row["per_page"]} == {p.id for p in pages}
        assert set(row["scores"]) == set(transcription_accuracy.POLICIES)
        assert row["policy"] == transcription_accuracy.DEFAULT_POLICY_NAME
        assert row["pages_per_hour"] is not None and row["cost_usd"]["value"] == 0.0 and row["local"]
    # The scores also landed on each model's card, keyed by this job (`distill.eval.stored-on-the-model-node`).
    kept = evaluation.model_evaluations(READER_IDS[PPOCR], "kraken")
    assert [e["job_id"] for e in kept] == [started["job_id"]] and kept[0]["trust"] == {"person": 3}


def test_the_table_is_ranked_by_the_fixed_order(client, db, tmp_path, folder, readers):
    """Section 8: "accuracy first, in bands (candidates within one point of character error rate of the
    best are tied on accuracy); within a band, local before remote, then cheaper, then faster ...".
    WHY: the ranking must be deterministic and explainable: a remote reader a hair more accurate must not
    beat a free local one, and a measured reader must always outrank one that could not be scored."""
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    _, done = _run(client, db)
    assert [r["card"] for r in done["rows"]] == [PPOCR, MEDIEVAL, MCCATMUS]
    assert [r["rank"] for r in done["rows"]] == [1, 2, 3] and done["winner"] == PPOCR
    cers = [r["cer"] for r in done["rows"]]
    assert cers[0] == 0.0 < cers[1] < cers[2]

    def row(card, cer, *, runs_on="this-mac", cost=0.0, pph=None, size=0.1):
        return {"card": card, "pin": {}, "material": ["handwriting"], "runs_on": runs_on, "cer": cer,
                "cost_usd": {"value": cost}, "pages_per_hour": pph, "carbon_g_per_page": None,
                "trainable": True, "size_gb": size}

    ranked = bakeoff._rank([
        row("a:remote-best", 0.050, runs_on="cloud:openai", cost=10.0),
        row("b:local-tied", 0.058),
        row("c:local-tied-faster", 0.059, pph=500.0),
        row("d:local-two-points-worse", 0.071),
        row("e:not-scored", None),
    ], "handwriting", 100)
    assert [r["card"] for r in ranked] == ["c:local-tied-faster", "b:local-tied", "a:remote-best",
                                           "d:local-two-points-worse", "e:not-scored"]


def test_use_this_writes_an_audited_override_for_the_chosen_scope(client, db, tmp_path, folder, readers):
    """source.try.use-this-scope: "Use This makes the winner the step's ... choice for the project or for one
    folder, stored as an override on the recipe".
    WHY: the person's choice must reach the recipe Start runs, for exactly the scope they picked, be kept
    as an override (so an update of the followed recipe does not silently undo it), and be audited and
    undoable like every change."""
    recipe = _set_up(client)
    (step,) = [s for s in recipe["steps"] if s["job"] == "read-a-line"]
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    started, done = _run(client, db)
    url = f"/api/recipes/project/bakeoffs/{started['id']}/use"

    for_folder = client.post(url, json={"card": MCCATMUS, "scope": "folder", "folder_id": folder.id})
    assert for_folder.status_code == 200, for_folder.text
    saved = for_folder.json()["recipe"]
    (o,) = saved["overrides"]
    assert (o["step"], o["scope"], o["folder_id"], o["card"]) == (step["id"], "folder", folder.id, MCCATMUS)
    assert o["model"] == {"zenodo": "10.5281/zenodo.13788177"} and o["from_bakeoff"] == started["id"]
    assert next(s for s in saved["steps"] if s["id"] == step["id"])["model"] == step["model"]  # project unchanged

    for_project = client.post(url, json={"card": PPOCR, "scope": "project"})
    assert for_project.status_code == 200, for_project.text
    saved = client.get("/api/recipes/project").json()["recipe"]
    read = next(s for s in saved["steps"] if s["id"] == step["id"])
    assert read["model"] == {"zenodo": "10.5281/zenodo.21788410"} and read["card"]["id"] == PPOCR
    assert read["card"]["cer_measured_here"] == 0.0 and "bake-off" in read["reasons"][0]
    assert [(o["scope"], o["card"]) for o in saved["overrides"]] == [("folder", MCCATMUS), ("project", PPOCR)]

    audits = [a for a in db.query(ActionAudit) if a.action_name == "project.save_setup"]
    assert len(audits) == 3  # setup's save, then the two choices
    newest = max(audits, key=lambda a: a.created_at)
    assert client.post(f"/api/actions/audit/{newest.id}/undo").status_code == 200
    undone = client.get("/api/recipes/project").json()["recipe"]
    assert [o["scope"] for o in undone["overrides"]] == ["folder"]

    not_a_candidate = client.post(url, json={"card": "mlx:hf/mlx-community/Qwen2.5-VL-3B-Instruct-4bit@unpinned"})
    assert not_a_candidate.status_code == 422 and "not one of this bake-off's candidates" in not_a_candidate.json()["detail"]
    not_a_folder = client.post(url, json={"card": PPOCR, "scope": "folder", "folder_id": done["pages"][0]["document_id"]})
    assert not_a_folder.status_code == 422


def test_the_comparison_is_kept_and_readable_later(client, db, tmp_path, folder, readers, test_package):
    """source.try.kept-and-rerunnable: "a comparison is kept with its selection and options and can be run
    again later".
    WHY: finished jobs are cleared from Activity; a bake-off whose table lived only in the job row would be
    lost with it, and the person could not see why the recipe reads with the reader it does."""
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    started, done = _run(client, db)
    assert (Path(test_package) / "recipe" / "bakeoffs" / f"{started['id']}.yaml").is_file()

    db.execute("DELETE FROM jobs WHERE id = ?", [started["job_id"]])  # Activity cleared its finished jobs
    later = client.get(f"/api/recipes/project/bakeoffs/{started['id']}").json()
    assert later["state"] == "cleared"
    assert [(r["card"], r["cer"]) for r in later["rows"]] == [(r["card"], r["cer"]) for r in done["rows"]]
    (listed,) = client.get("/api/recipes/project/bakeoffs").json()["items"]
    assert listed["id"] == started["id"] and listed["winner"] == PPOCR
    assert client.get("/api/recipes/project/bakeoffs/not-a-bakeoff").status_code == 404

    _, again = _run(client, db)  # run again later, on the same pages
    assert len(client.get("/api/recipes/project/bakeoffs").json()["items"]) == 2
    assert again["winner"] == PPOCR


# --- the gaps the app found (2026-10-05): names, Use This kept, readiness up front, no ids in refusals -------


def test_a_row_names_its_reader_by_the_cards_own_name(client, db, tmp_path, folder, readers):
    """Section 7b: "never a raw model id"; the table names each reader as a recipe step names its model.
    WHY: a person choosing a reader must read the reader's name from its card (the words the reading step
    shows), not an id, and not a name the app makes up from the reader's kind and rule place."""
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    started, done = _run(client, db)
    cards = {c.id: c for c in all_seed_cards()}
    for table in (started, done, client.get("/api/recipes/project/bakeoffs").json()["items"][0]):
        for row in table["rows"]:
            assert row["name"] and row["name"] == bakeoff.reader_name(cards[row["card"]])
            assert row["card"] not in row["name"]
    names = {r["card"]: r["name"] for r in done["rows"]}
    assert names[MCCATMUS].startswith("McCATMuS") and names[MEDIEVAL].startswith("CATMuS Medieval")
    # One source: the field the recipe's reading step shows for its model (the card's note).
    recipe = client.get("/api/recipes/project").json()["recipe"]
    (step,) = [s for s in recipe["steps"] if s["job"] == "read-a-line"]
    assert names[step["card"]["id"]] == step["card"]["note"].rstrip(".")


def test_assembling_again_keeps_a_use_this_reader(client, db, tmp_path, folder, readers):
    """source.try.use-this-scope: Use This "makes the winner the step's choice ... stored as an override on
    the recipe, like any other".
    WHY: setup's How it will be done screen proposes the recipe again each time it is shown; if that ignored
    the override, the reader the person chose would quietly revert to the rules' choice and Start would read
    with a reader they turned down. A folder's choice stays an override and leaves the project's reader."""
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "pages": 1000}
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    started, _ = _run(client, db)
    url = f"/api/recipes/project/bakeoffs/{started['id']}/use"
    assert client.post(url, json={"card": MEDIEVAL, "scope": "project"}).status_code == 200  # not the rules' first
    assert client.post(url, json={"card": MCCATMUS, "scope": "folder", "folder_id": folder.id}).status_code == 200

    again = client.post("/api/recipes/assemble", json=answers)
    assert again.status_code == 200, again.text
    proposed = again.json()
    (step,) = [s for s in proposed["steps"] if s["job"] == "read-a-line"]
    assert step["card"]["id"] == MEDIEVAL and step["model"] == {"zenodo": "10.5281/zenodo.12743230"}
    assert "bake-off" in step["reasons"][0] and step["card"]["cer_measured_here"] is not None
    assert [(o["scope"], o["card"]) for o in proposed["overrides"]] == [("project", MEDIEVAL), ("folder", MCCATMUS)]
    # Saved again as proposed, the choice and both overrides survive.
    saved = client.put("/api/recipes/project", json={"answers": answers, "recipe": proposed})
    assert saved.status_code == 200, saved.text
    kept = saved.json()["recipe"]
    assert next(s for s in kept["steps"] if s["job"] == "read-a-line")["card"]["id"] == MEDIEVAL
    assert [(o["scope"], o["card"]) for o in kept["overrides"]] == [("project", MEDIEVAL), ("folder", MCCATMUS)]


def test_readiness_is_counted_as_a_start_is_and_said_before_pressing(client, db, tmp_path, folder):
    """source.onboard.bakeoff-minimum: "below that it says how many more are needed and is offered again when
    there are enough".
    WHY: setup must say what to correct before the person presses anything, and hide the button until it
    would run; the list's readiness and the start's refusal must be one count, or the screen would offer a
    comparison the engine then refuses (or hide one it would run)."""
    _set_up(client)
    empty = client.get("/api/recipes/project/bakeoffs").json()["readiness"]
    assert (empty["ready"], empty["lines"], empty["pages"], empty["more_lines"], empty["more_pages"]) == (
        False, 0, 0, 100, 2)

    _corrected(db, tmp_path, "SM_NPQ_C01_001", folder)
    short = client.get("/api/recipes/project/bakeoffs").json()["readiness"]
    refused = client.post("/api/recipes/project/bakeoffs", json={})
    assert refused.status_code == 422
    assert short["sentence"] == refused.json()["detail"]
    assert (short["lines"], short["pages"], short["more_lines"], short["more_pages"]) == (
        LINES_PER_PAGE, 1, 100 - LINES_PER_PAGE, 1)
    assert (short["min_lines"], short["min_pages"]) == (bakeoff.MIN_LINES, bakeoff.MIN_PAGES)

    for i in (2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    enough = client.get("/api/recipes/project/bakeoffs").json()["readiness"]
    assert enough["ready"] and enough["sentence"] is None
    assert (enough["lines"], enough["pages"], enough["more_lines"], enough["more_pages"]) == (
        3 * LINES_PER_PAGE, 3, 0, 0)


def test_no_card_id_in_a_refusal(client, db, tmp_path, folder):
    """Section 7b: "a step's problem is shown once, in words a historian reads ... never a raw model id".
    WHY: when no reader can be scored on this Mac (none downloaded), the refusal is all the person reads;
    an id like kraken:zenodo/10.5281/... tells them nothing, the reader's name does."""
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    refused = client.post("/api/recipes/project/bakeoffs", json={})  # no reader downloaded on this (test) Mac
    assert refused.status_code == 422
    said = refused.json()["detail"]
    cards = {c.id: c for c in all_seed_cards()}
    assert not [cid for cid in cards if cid in said] and "zenodo" not in said
    for card in (PPOCR, MEDIEVAL, MCCATMUS):
        assert bakeoff.reader_name(cards[card]) in said
    assert "not on this Mac" in said and _evaluation_jobs(db) == 0
