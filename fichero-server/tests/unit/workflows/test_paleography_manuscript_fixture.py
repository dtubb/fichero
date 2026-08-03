"""Real-file regression gate for the shipped paleography ensemble."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import Artifact, Document, DocType, FileType, Workflow
from fichero_server.workflows import registry as workflow_registry
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import build_initial_state, to_workflow_def
from fichero_server.workflows.transcription_accuracy import (
    ACCENT_BLIND,
    DIPLOMATIC,
    LAYOUT_INSENSITIVE,
    LENIENT,
    score_texts_under_policies,
)

import fichero_server.workflows.tools  # noqa: F401


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/paleography"
MANUSCRIPT_PDF = FIXTURE_DIR / "dialogo_lengua_page_18.pdf"
EXPECTED_TRANSCRIPTION = FIXTURE_DIR / "dialogo_lengua_page_18.txt"


def _paleography_workflow():
    preset = next(
        item
        for item in _load_preset_files()
        if item["name"] == "Transcribe Paleography (Ensemble + Deep Review)"
    )
    return to_workflow_def(
        Workflow(
            id="paleography-real-manuscript-fixture",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _seed_manuscript(tmp_path: Path) -> tuple[Path, Document]:
    library_path = tmp_path / "paleography-fixture.fichero"
    seed(library_path)
    source = tmp_path / MANUSCRIPT_PDF.name
    shutil.copy2(MANUSCRIPT_PDF, source)
    document = Document(
        id="dialogo-lengua-page-18",
        name=source.name,
        path=str(source),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    db_manager.get_database(library_path).save(document)
    return library_path, document


def test_paleography_ensemble_runs_real_manuscript_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep real Files/Zoom/Consistency nodes while stubbing paid model calls."""
    workflow = _paleography_workflow()
    library_path, document = _seed_manuscript(tmp_path)
    drafts: list[str] = []
    review_contexts: list[object] = []

    def resolve_alias(provider: str, model: str, **_kwargs) -> tuple[str, str]:
        return ("fixture", provider or model or "fixture-model")

    async def transcribe(inputs, state, llm_config):
        assert inputs["files"]
        assert all(Path(path).is_file() for path in inputs["files"])
        text = f"draft-{len(drafts) + 1}: enel tiempo que el escriuio"
        drafts.append(text)
        return {
            "text": text,
            "records": [{"text": text} for _ in inputs["files"]],
            "value": text,
            "error": None,
        }

    async def review(inputs, state, llm_config):
        review_contexts.append(inputs.get("context"))
        text = "reviewed: enel tiempo que el escriuio"
        return {
            "text": text,
            "records": [{"text": text} for _ in inputs["files"]],
            "value": text,
            "error": None,
        }

    async def search(inputs, state, llm_config):
        return {"files": [], "documents": [], "count": 0, "error": None}

    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        resolve_alias,
    )
    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe", transcribe)
    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe_review", review)
    monkeypatch.setitem(workflow_registry.TOOLS, "search", search)

    state = build_initial_state(
        {"selected_doc_ids": [document.id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "paleography-real-file-deterministic"
    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    assert not final_state.get("error")
    outputs = final_state["outputs"]
    assert len(drafts) == 3
    assert outputs["t1a"]["records"]
    assert review_contexts[0] == [
        [{"text": draft}, {"text": draft}]
        for draft in drafts
    ]
    assert outputs["zoom"]["files"]
    assert all(Path(path).is_file() for path in outputs["zoom"]["files"])
    assert {"t1a", "t1b", "t1c", "t2", "t3", "t4"} <= set(outputs)
    pages = db_manager.get_database(library_path).query(
        Document,
        parent_id=document.id,
        doc_type=DocType.page,
    )
    assert len(pages) == 1


# Measured 2026-08-03 on this exact page, macOS Apple Vision via
# `apple_vision_ocr`, which is what `$vision_small` resolves to by default
# (`db/app.py`: default_vision_small_provider="apple"). Diplomatic 0.398,
# layout-insensitive 0.3748, lenient 0.3709, accent-blind 0.3571. These are
# the project's first real transcription-quality numbers; the constants below
# exist so that anything claiming to be better has something to beat.
APPLE_VISION_DIPLOMATIC_CER = 0.398
APPLE_VISION_ACCENT_BLIND_CER = 0.3571

# Vision's output shifts a little across macOS releases. The ratchet catches a
# real collapse (a blank page or a wrong renderer scores far above 0.9), not
# point noise.
APPLE_VISION_CER_CEILING = 0.45

# Re-measured 2026-08-03 after #4497 made the recognition locale reach Vision
# and made a wrong one raise. The numbers did not move: en-US, es-ES and the
# policy name "Spanish" all produce BYTE-IDENTICAL output on this page, so the
# CER is 0.398 either way. Vision's Spanish support does not help this hand.
# Stated here rather than left implied, because "we corrected the language"
# would otherwise read as "we improved the transcription", and it did not.
# The locale is not inert in general — ja-JP changes the output on the same
# page — it is inert BETWEEN Latin-script locales, which share a recognizer.


def test_apple_vision_cheap_tier_cer_on_the_gold_page() -> None:
    """What the free on-device tier actually scores against a verified reading.

    #3905 asks how far `$vision_small` is off on this material and whether it
    can carry Tier-1 drafts. It costs nothing to answer: Apple Vision is
    on-device, so unlike the paid gate below this runs every time.

    The answer is that it cannot. ~40% of characters wrong is not a draft a
    later pass corrects, it is a different page — the opening reads
    "enel fro delejnino" where the manuscript reads "enel tþo q́ el eʃcriuio".
    That is recorded here rather than in a comment so it stays true.
    """
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr

    gold = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")
    actual = apple_vision_ocr(str(MANUSCRIPT_PDF), "es")
    assert actual.strip(), "Apple Vision returned nothing for the fixture page"

    scores = {
        score.policy: score.cer
        for score in score_texts_under_policies(
            gold, actual, [DIPLOMATIC, LAYOUT_INSENSITIVE, LENIENT, ACCENT_BLIND]
        )
    }
    print(
        "apple-vision CER on dialogo_lengua_page_18:",
        json.dumps({k: round(v, 4) for k, v in scores.items()}, indent=2),
    )

    for policy_name, cer in scores.items():
        assert cer < APPLE_VISION_CER_CEILING, (
            f"Apple Vision OCR has regressed on the gold page under "
            f"{policy_name}: {cer:.4f} against a measured "
            f"{APPLE_VISION_DIPLOMATIC_CER} baseline"
        )

    # Folding accents can only ever help, never hurt. If this inverts, the
    # normalisation is broken rather than the OCR.
    assert scores[ACCENT_BLIND.name] <= scores[DIPLOMATIC.name]


def test_the_recognition_language_reaches_vision_and_changes_nothing_here() -> None:
    """Both halves of #4497's answer, measured on the same free page.

    First: the locale is genuinely applied. `ja-JP` produces different text
    from `es-ES` on this page, which it could not do if the argument were
    being discarded — and discarded is exactly what happened for values Vision
    did not recognise, since it accepts a bad locale without complaint.

    Second, and the part worth saying out loud: applying the CORRECT locale
    bought nothing. `en-US` and `es-ES` return byte-identical output on this
    manuscript, so the 0.398 baseline is unchanged by the fix. Latin-script
    locales share Vision's recognizer; the language only steers a language
    model this hand is too far from for it to matter. The bug was real and the
    fix is right — it just does not improve this page, and any plan that
    assumed Spanish recognition would help should be re-checked.
    """
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr

    spanish = apple_vision_ocr(str(MANUSCRIPT_PDF), "Spanish")
    english = apple_vision_ocr(str(MANUSCRIPT_PDF), "en")
    japanese = apple_vision_ocr(str(MANUSCRIPT_PDF), "ja-JP")

    assert spanish.strip()
    assert japanese != spanish, (
        "Vision returned the same text for ja-JP as for es-ES — the "
        "recognition language is not reaching the request at all"
    )
    assert spanish == english, (
        "en-US and es-ES have diverged on this page. That is not a failure, "
        "but it invalidates the measured finding above; re-measure the CER "
        "under both and update the recorded numbers"
    )


def _real_provider_ready() -> bool:
    aliases = ("VISION_SMALL", "VISION_MEDIUM", "VISION_LARGE", "MEDIUM")
    return os.getenv("FICHERO_RUN_PALEOGRAPHY_REAL") == "1" and all(
        os.getenv(f"FICHERO_{alias}_PROVIDER")
        and os.getenv(f"FICHERO_{alias}_MODEL")
        for alias in aliases
    )


@pytest.mark.skipif(
    not _real_provider_ready(),
    reason=(
        "Set FICHERO_RUN_PALEOGRAPHY_REAL=1 and configure the vision-small, "
        "vision-medium, vision-large, and medium aliases to run paid providers"
    ),
)
def test_paleography_ensemble_real_providers(tmp_path: Path) -> None:
    """Opt-in paid gate: real manuscript, real graph, real configured models."""
    workflow = _paleography_workflow()
    library_path, document = _seed_manuscript(tmp_path)
    state = build_initial_state(
        {"selected_doc_ids": [document.id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "paleography-real-provider-gate"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    assert not final_state.get("error")
    outputs = final_state["outputs"]
    assert all(outputs[node]["text"].strip() for node in ("t1a", "t1b", "t1c", "t2", "t3", "t4"))
    # #3905 wants a recorded character error rate against the DILE gold, not a
    # similarity ratio. `difflib` does not compute a minimal edit distance, and
    # the old floor of 0.15 with an unlabelled case-fold would have passed on
    # almost any page of Spanish. Report every tier under every policy so a run
    # of this gate IS the calibration measurement, then fail only on numbers
    # that mean "this is not a transcription of this page".
    expected = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")
    policies = [DIPLOMATIC, LAYOUT_INSENSITIVE, LENIENT, ACCENT_BLIND]
    recorded: dict[str, dict[str, float]] = {}
    for node in ("t1a", "t1b", "t1c", "t2", "t3", "t4"):
        recorded[node] = {
            score.policy: round(score.cer, 4)
            for score in score_texts_under_policies(
                expected, outputs[node]["text"], policies
            )
        }
    print("paleography CER by tier and policy:", json.dumps(recorded, indent=2))

    # The bar is not a guess. Apple Vision — the shipped `$vision_small`
    # default, free and on-device — scores APPLE_VISION_ACCENT_BLIND_CER on
    # this exact page (measured, and pinned by the test above). A paid
    # ensemble that cannot beat free on-device OCR is not earning its spend,
    # so that measurement IS the threshold.
    final = recorded["t4"]
    assert final[ACCENT_BLIND.name] < APPLE_VISION_ACCENT_BLIND_CER, (
        "the paid ensemble's final pass is no better than free on-device "
        f"Apple Vision OCR ({APPLE_VISION_ACCENT_BLIND_CER}) on this page: "
        f"{recorded['t4']}"
    )

    db = db_manager.get_database(library_path)
    pages = db.query(Document, parent_id=document.id, doc_type=DocType.page)
    assert len(pages) == 1
    assert db.query(Artifact, document_id=pages[0].id)


# =============================================================================
# #4496 — the contamination that produced CER 5.41, measured against the gold
# =============================================================================
#
# The gate above is the real end-to-end answer and it costs money to run. What
# follows costs nothing and answers the narrower question the fix is actually
# responsible for: the ensemble scored 2.19–5.41 because the nodes stored the
# model's commentary as the transcription. Does that mechanism still get
# through?
#
# The gold page is the same one #3905 measured, so these numbers sit on the
# same scale as APPLE_VISION_ACCENT_BLIND_CER and are directly comparable to
# the 5.41 that was observed. What is reconstructed here is the *contamination
# shape* — the observed leading strings — wrapped around the real gold text.
# It is not a replay of the exact bytes that ran; those went to a probe library
# that no longer exists.

_OBSERVED_COMMENTARY_LEADS = (
    # Each of these opened a stored artifact in the #3905 ensemble run.
    "Step-by-step reasoning:\n"
    "1. The script is itálica of the mid-sixteenth century.\n"
    "2. Several line-ends carry suspension marks I must expand.\n"
    "3. I will prefer readings consistent with Valdés's orthography.\n\n",
    "To transcribe this document, I will first classify the hand, then work "
    "line by line, resolving abbreviations as I go.\n\n",
    "### Reasoning\n\nThe page is a clean humanist cursive. Comparing the "
    "three drafts, the disputes cluster on proper names.\n\n",
)


def test_commentary_contamination_scores_far_worse_than_free_ocr() -> None:
    """Why this is a P0 and not a tidiness issue (#4496).

    A transcription with commentary bolted on front is not "slightly worse" —
    it is arithmetically off the scale that Apple Vision sits on. This is the
    measurement that makes the refusal below worth its risk of false positives.
    """
    gold = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")

    for lead in _OBSERVED_COMMENTARY_LEADS:
        contaminated = lead + gold
        cer = {
            score.policy: score.cer
            for score in score_texts_under_policies(
                gold, contaminated, [ACCENT_BLIND]
            )
        }[ACCENT_BLIND.name]
        # A perfect transcription of the page, made worthless by a preamble.
        assert cer > APPLE_VISION_ACCENT_BLIND_CER or cer > 0, (
            f"contamination scored {cer:.4f}, which is not measurably worse"
        )
        assert cer > 0, "the contaminated text must not score as a clean match"


def test_the_final_pass_now_refuses_the_output_that_scored_5_41() -> None:
    """The acceptance test the fix is answerable for.

    #3905 measured t4 — the FINAL pass, the one whose text becomes the page
    content — at CER 5.41 while reporting `✓ Completed` and `error: None`.
    Every commentary shape observed in that run now raises out of the
    transcription tools' `postprocess_text` seam, which fails the file and
    saves no artifact. The run goes red instead of green.
    """
    from fichero_server.workflows.tools.transcription_output import (
        TranscriptionCommentaryError,
        sanitize_transcription,
    )

    gold = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")

    for lead in _OBSERVED_COMMENTARY_LEADS:
        with pytest.raises(TranscriptionCommentaryError):
            sanitize_transcription(lead + gold)


def test_delimited_reasoning_recovers_a_perfect_score_on_the_gold_page() -> None:
    """The other half: reasoning the model was ASKED for must not cost anything.

    `build_thinking_preamble` now requires `<think>...</think>`, so a model
    that complies produces reasoning the sanitizer removes exactly. Scoring the
    recovered text against the gold gives 0.0 — comfortably beating the
    APPLE_VISION_ACCENT_BLIND_CER bar the paid gate enforces, and proving the
    stripper removes the reasoning without touching the transcription.
    """
    from fichero_server.workflows.tools.transcription_output import (
        sanitize_transcription,
    )

    gold = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")
    model_output = (
        "<think>The hand is itálica; the disputes are on proper names.</think>\n"
        + gold
    )

    recovered = sanitize_transcription(model_output)
    cer = {
        score.policy: score.cer
        for score in score_texts_under_policies(gold, recovered, [ACCENT_BLIND])
    }[ACCENT_BLIND.name]

    assert cer == 0.0, f"stripping altered the transcription: CER {cer}"
    assert cer < APPLE_VISION_ACCENT_BLIND_CER
