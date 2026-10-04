"""Line pictures and their teacher's readings, as training pairs for a vision model (#5398).

The vision-model card of the train job (`compute.tune.lora`) learns from the SAME training set as the
Kraken card: the teacher's line passes written as PAGE XML beside each photograph
(`training.kraken_set`). Each TextLine becomes one pair:

* the picture: cut from the photograph by `llm.line_reader.crop_line`, the very cut the teacher
  read (`compute.tune.input-is-a-training-set`: no second way to cut line pictures);
* the instruction: the line reader's own prompt for one picture (`line_reader.prompt_for(1, …)`);
* the answer: what the teacher's reply to that prompt is, a JSON array of one string.

So the student learns the teacher's task as the line reader asks it, and can be put in the teacher's
place in the same workflow. Pairs are written to `pairs.jsonl` beside a `lines/` folder, inside the
set, so the same send carries both.
"""
from __future__ import annotations

import json
from fichero_server.security.xml_security import parse_xml_string
from pathlib import Path

from PIL import Image

from fichero_server.formats.pagexml import PAGE_NS_2019
from fichero_server.llm.line_reader import crop_line, prompt_for
from fichero_server.training.kraken_set import MANIFEST

PAIRS = "pairs.jsonl"
LINES_DIR = "lines"
_NS = f"{{{PAGE_NS_2019}}}"


def _points(coords: str) -> list[tuple[float, float]]:
    return [tuple(float(v) for v in pair.split(",")) for pair in coords.split()]


def lines_with_ids(page_xml: str) -> list[tuple[str, list[tuple[float, float]], str]]:
    """(PAGE id, polygon in pixels, text) for each TextLine with an outline and some text, in file order.
    Fichero's writer gives a line the id of its segment (`formats.harness.xml_id`), so the same line
    is found again in the episode ledger."""
    root = parse_xml_string(page_xml)
    found = []
    for line in root.iter(f"{_NS}TextLine"):
        coords = line.find(f"{_NS}Coords")
        text = "".join(u.text or "" for u in line.iter(f"{_NS}Unicode")).strip()
        if coords is not None and coords.get("points") and text:
            found.append((line.get("id") or "", _points(coords.get("points")), text))
    return found


def lines_of(page_xml: str) -> list[tuple[list[tuple[float, float]], str]]:
    """(polygon in pixels, text) for each TextLine with an outline and some text, in file order."""
    return [(polygon, text) for _id, polygon, text in lines_with_ids(page_xml)]


#: The arms of the reasons A/B (`distill.reasoning.two-arms`): the same lines, the same checked answer.
AB_ARMS = ("answer", "why", "thinking")
ARMS = (*AB_ARMS, "review")
MAX_TRACE_CER = 0.10


def _within(checked: str, teacher: str | None, limit: float) -> bool:
    """The teacher's own reading is within `limit` CER of the checked one: its reasons are for the right
    reading (`distill.reasoning.answer-is-checked`)."""
    from fichero_server.workflows.transcription_accuracy import RunComparisonError, character_error_rate

    if not teacher:
        return False
    try:
        return character_error_rate(checked, teacher).cer <= limit
    except RunComparisonError:
        return False


def arms_for(line_id: str, text: str, language: str | None, traces: dict[str, dict], reviews: dict[str, dict],
             max_trace_cer: float, dropped: dict[str, int]) -> dict[str, dict[str, str]]:
    """The (prompt, answer) of each arm this line has. The answer is ALWAYS the checked text; the
    teacher's reasons ride with it only where the teacher read the line within `max_trace_cer`."""
    from fichero_server.training import reasons

    arms = {"answer": {"prompt": prompt_for(1, language), "answer": json.dumps([text], ensure_ascii=False)}}
    trace = traces.get(line_id)
    if trace is not None:
        if _within(text, trace.get("text"), max_trace_cer):
            why = {k: trace.get(k) for k in ("letterforms", "abbreviations", "uncertain")}
            arms["why"] = {"prompt": reasons.prompt_for(reasons.READ, 1, language),
                           "answer": json.dumps([{**why, "text": text}], ensure_ascii=False)}
            if trace.get("thinking"):
                arms["thinking"] = {"prompt": prompt_for(1, language),
                                    "answer": f"<think>\n{trace['thinking']}\n</think>\n\n" + arms["answer"]["answer"]}
        else:
            dropped["why"] += 1
            dropped["thinking"] += bool(trace.get("thinking"))
    review = reviews.get(line_id)
    if review is not None and review.get("draft") is not None:
        # The check job's readings card (`source.check.readings-card`): the student is asked exactly as the
        # palaeographer reviewer was, so it can take its place in a check run; its answer is the checked text.
        if _within(text, review.get("text"), max_trace_cer):
            from fichero_server.checking.cards import Proposal
            from fichero_server.checking.cards import prompt_for as check_prompt

            shown = Proposal("readings", line_id, None, {"reading": json.dumps(review["draft"], ensure_ascii=False)})
            agrees = review["draft"] == text
            arms["review"] = {"prompt": check_prompt(shown, language=language),
                              "answer": json.dumps({"verdict": "confirm" if agrees else "correct",
                                                    "why": review.get("why"),
                                                    "correction": None if agrees else {"text": text}},
                                                   ensure_ascii=False)}
        else:
            dropped["review"] += 1
    return arms


def write_line_pairs(set_dir: str | Path, *, language: str | None = None, traces: dict[str, dict] | None = None,
                     reviews: dict[str, dict] | None = None, max_trace_cer: float = MAX_TRACE_CER) -> int:
    """Add `lines/` and `pairs.jsonl` to a training set; returns the number of pairs.

    With a palaeographer's `traces` and `reviews` (`training.reasons.traces_by_line`), each pair also
    carries the arms its line has, and `in_every_arm` marks the lines every reasoning arm of the set
    covers, so an answer-only and a reasoning student can be trained on the same lines."""
    root = Path(set_dir)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    (root / LINES_DIR).mkdir(exist_ok=True)
    reasoned = traces is not None or reviews is not None
    dropped = dict.fromkeys(ARMS, 0)
    rows = []
    for page in manifest["pages"]:
        image = Image.open(root / page["image"])
        image.load()
        stem = Path(page["xml"]).stem
        for index, (line_id, polygon, text) in enumerate(
                lines_with_ids((root / page["xml"]).read_text(encoding="utf-8")), 1):
            name = f"{LINES_DIR}/{stem}_{index:03d}.jpg"
            crop_line(image, polygon).save(root / name, format="JPEG", quality=90)
            row = {"image": name, "prompt": prompt_for(1, language), "answer": json.dumps([text], ensure_ascii=False),
                   "document_id": page["document_id"], "line": index, "line_id": line_id}
            if reasoned:
                row["arms"] = arms_for(line_id, text, language, traces or {}, reviews or {}, max_trace_cer, dropped)
            rows.append(row)
    if reasoned:
        present = [arm for arm in AB_ARMS if any(arm in r["arms"] for r in rows)]
        for row in rows:
            row["in_every_arm"] = all(arm in row["arms"] for arm in present)
        manifest["arms"] = {arm: sum(arm in r["arms"] for r in rows) for arm in ARMS}
        manifest["arms_dropped_outside_cer"] = dropped
        manifest["max_trace_cer"] = max_trace_cer
        manifest["lines_in_every_arm"] = sum(r["in_every_arm"] for r in rows)
    with (root / PAIRS).open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest["line_pairs"] = len(rows)
    (root / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return len(rows)
