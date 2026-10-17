"""Nothing assumes spaces, direction or an alphabet (`source.recipe.nothing-assumes-spaces-direction-or-an-alphabet`, #5728).

Spec: the matrix of four chosen to differ (Spanish colonial: spaced, left to right, alphabet; German Kurrent: spaced,
left to right, long s; Aramaic in Syriac and Hebrew letters: right to left; Chinese: vertical columns, no spaces,
characters), each with a stub reviewer, never sent another's wording; a right-to-left and a vertical page both returned
in their segments' reading order; the table's WER only where the script separates words, Chinese scored by character.
WHY: a Chinese page scored by whitespace words is one "word" per line, so one wrong character read as WER 100%.
No language is named in the engine's code: the matrix below is test data.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.review_profiles import lens_ids, review_prompt
from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401
    REVIEWER,
    _lines,
    page,
)

SETUP = {"purposes": ["transcribe"], "materials": ["handwriting"]}
MATRIX = {  # id -> (answers, script, direction, the three lines a reviewer returns)
    "es-colonial": ({**SETUP, "languages": ["es"], "scripts": ["Latn"], "period": "1650"}, "Latn", "ltr",
                    ["el dicho escrivano", "vezino de la cibdad", "y lo firmo"]),
    "de-kurrent": ({**SETUP, "languages": ["de"], "scripts": ["Latn"], "period": "1850"}, "Latn", "ltr",
                   ["Nachdem ich Euch geſchrieben", "habe ich die Antwort", "erhalten und gelesen"]),
    "aramaic": ({**SETUP, "languages": ["arc"], "scripts": ["Syrc"], "directions": {"Syrc": "rtl"}}, "Syrc", "rtl",
                ["ܒܫܡܐ ܕܡܪܝܐ ܐܠܗܐ", "ܘܒܫܡܐ ܕܒܪܐ", "ܘܕܪܘܚܐ ܕܩܘܕܫܐ"]),
    "zh": ({**SETUP, "languages": ["zh"], "scripts": ["Hant"], "directions": {"Hant": "ttb"}}, "Hant", "ttb",
           ["天地玄黃宇宙洪荒", "日月盈昃辰宿列張", "寒來暑往秋收冬藏"]),
}


def _all_lenses(answers) -> str:
    return "\n".join(review_prompt(lens, answers)[0] for lens in lens_ids())


@pytest.mark.parametrize("name", MATRIX)
def test_each_script_is_never_sent_another_scripts_wording_5728(name):
    from fichero_server.recipes.review_profiles import choose, profiles

    prompt = _all_lenses(MATRIX[name][0])
    assert choose(MATRIX[name][0])[0].id == name
    for other in MATRIX.keys() - {name}:
        theirs = profiles()[other]
        assert theirs.context not in prompt, (name, other)
        assert all(theirs.lenses[lens]["text"].strip() not in prompt for lens in lens_ids()
                   if theirs.lenses[lens]["text"] != profiles()[name].lenses[lens]["text"]), (name, other)


def test_what_every_profile_shares_assumes_no_alphabet_no_spaces_and_no_direction_5728():
    """An absence scan of the words every review is built from (the shared frame and the generic profile)."""
    from fichero_server.recipes.review_profiles import frame, profiles

    shared = " ".join([frame()["intro"], frame()["closing"], profiles()["generic"].context,
                       *(profiles()["generic"].lenses[lens]["text"] for lens in lens_ids())]).lower()
    for assumed in ("alphabet", "left to right", "left-to-right", "right to left", "upper case", "lower case",
                    "between words", "letter-shape", "word division", "letters of this script"):
        assert assumed not in shared, assumed


# --- the scores ----------------------------------------------------------------------------------------------------


def _row(reference: list[str], reads: list[str]) -> dict:
    """The table row for one page read as `reads`, built by the evaluation's own functions."""
    from fichero_server.recipes.bakeoff import _scored_row
    from fichero_server.training.evaluation import judge_page, score_page, word_errors

    page_ = judge_page({"document_id": "p1", "name": "p1", "trust": "checked", "lines": len(reference),
                        "scores": score_page(reference, reads), "words": word_errors(reference, reads)})
    return _scored_row({"per_page": [page_], "pages": ["p1"]})


@pytest.mark.parametrize("name", ["es-colonial", "de-kurrent", "aramaic"])
def test_where_the_script_separates_words_a_wrong_word_is_counted_5728(name):
    reference = MATRIX[name][3]
    reads = [reference[0].replace(reference[0].split()[-1], "xyz"), *reference[1:]]
    words = sum(len(line.split()) for line in reference)
    row = _row(reference, reads)
    assert row["wer"] == pytest.approx(1 / words) and row["cer"] > 0


def test_where_the_script_does_not_separate_words_the_page_is_scored_by_character_5728():
    reference = MATRIX["zh"][3]
    reads = [reference[0].replace("玄", "女"), *reference[1:]]
    row = _row(reference, reads)
    assert row["wer"] is None
    assert row["cer"] == pytest.approx(1 / len("\n".join(reference)))  # one character of the page's characters


def test_a_hebrew_page_with_spaces_is_scored_by_word_and_by_character_5728():
    row = _row(["בראשית ברא אלהים", "את השמים ואת הארץ"], ["בראשית ברא אלהים", "את השמים ואת הארך"])
    assert row["wer"] == pytest.approx(1 / 7) and row["cer"] == pytest.approx(1 / 34)


def test_a_page_in_neither_is_not_given_a_word_rate_it_cannot_have_5728():
    """Digits only: no script to say the words are unseparated, so the whitespace words stand as they did."""
    assert _row(["1650 12 3"], ["1650 12 4"])["wer"] == pytest.approx(1 / 3)


# --- the lines --------------------------------------------------------------------------------------------------------


async def _set_up_page(page, answers, script, direction):  # noqa: F811
    """The page's lines as segments of that script and direction; vertical columns when the direction is ttb
    (right to left across the page, as the segments' own order has them)."""
    from pathlib import Path

    from fichero_server.recipes.project import write_project_setup

    db = page["db"]
    write_project_setup(Path(db.path).parent, answers, None)
    for i, row in enumerate(_lines(page)):
        row.script, row.direction = script, direction
        if direction == "ttb":  # box order would put the leftmost column first; the segments' order has it last
            row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h = 0.8 - 0.3 * i, 0.05, 0.1, 0.9
        db.save(row)


@pytest.mark.asyncio
async def test_each_scripts_review_lands_on_its_segments_in_their_reading_order_5728(page, monkeypatch):  # noqa: F811
    """One loop over the matrix, not a parametrize: pytest-asyncio and parametrize break this fixture."""
    from fichero_server import llm
    from fichero_server.api.routes.document.segment_readings import counting_texts
    from fichero_server.llm import LLMConfig
    from fichero_server.recipes.review_profiles import profiles
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    for name, (answers, script, direction, texts) in MATRIX.items():
        await _set_up_page(page, answers, script, direction)
        rows = _lines(page)
        sent = []

        async def reviewer(images, prompt, config, rows=rows, texts=texts, sent=sent, **kw):
            sent.append(prompt)
            return "\n".join(f"{row.id} | certain | {text}" for row, text in zip(rows, texts))

        monkeypatch.setattr(llm, "vision", reviewer)
        result = await transcribe_review(
            inputs={"lens": "orthography", "files": page["src"]["files"], "documents": page["src"]["documents"],
                    "skip_if_artifact_exists": False},
            state={"library_path": page["library"], "task_id": f"run-matrix-{name}"},
            llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
        assert not result.get("error"), (name, result.get("error"))
        assert profiles()[name].context in sent[0], name

        after = _lines(page)
        assert [r.id for r in after] == [r.id for r in rows], name  # the segments' own order, whatever the boxes say
        read = counting_texts(page["db"], after)
        assert [read[r.id] for r in after] == texts, name
        assert all((r.script, r.direction) == (script, direction) for r in after), name  # a reading, not a setting
