"""Prepare Images, check side: the pages to look at after the run (`prep.check.worklist-of-proposals-and-a-sample`, #5382).

Every page with an open proposal (`metadata.prep_proposals`: a page box, a turn, a blank the run was unsure of), proposals
first, each saying in words what is unsure; then one confident page in twenty as a sample, so a run that is wrong with
confidence is still seen. A person's answer removes a page's proposal (`image.square`, `image.rotate`,
`image.mark_blank`, `image.accept_proposal`); the page then leaves the list.
"""
from __future__ import annotations

import json
from typing import Any

SAMPLE_EVERY = 20
KINDS = ("page_box", "turn", "blank")
_DEFAULT_WORDS = {
    "page_box": "the page edge was not found with confidence: the box is a proposal",
    "turn": "the lines do not agree which way the page runs",
    "blank": "very little ink beyond its ruling: kept, not hidden",
}


def _words(kind: str, proposal: Any) -> list[str]:
    if isinstance(proposal, dict):
        if proposal.get("words"):
            return [str(w) for w in proposal["words"]]
        if proposal.get("reason"):
            return [str(proposal["reason"])]
    return [_DEFAULT_WORDS[kind]]


def worklist(db: Any) -> list[dict[str, Any]]:
    """`[{id, name, kinds, words, sample}]`: pages with a proposal first (in the project's page order), then every
    twentieth confident page that the step found a page in. A page hidden as blank is never listed."""
    rows = {r[0]: r for r in db.execute_fetchall(
        "SELECT d.id, d.name, json_extract_string(d.metadata, '$.prep_proposals'), "
        "json_extract_string(d.metadata, '$.page_region.method') "
        f"FROM documents d WHERE {db._UNIT_OF_WORK_WHERE}", committed=True)}
    proposed: list[dict[str, Any]] = []
    sampled: list[dict[str, Any]] = []
    confident = 0
    for page_id in db.unit_of_work_ids():
        row = rows.get(page_id)
        if row is None:
            continue
        proposals = json.loads(row[2]) if row[2] else {}
        kinds = [k for k in KINDS if proposals.get(k)]
        if kinds:
            proposed.append({"id": page_id, "name": row[1], "kinds": kinds, "sample": False,
                             "words": [w for k in kinds for w in _words(k, proposals[k])]})
        elif row[3]:  # the step found a page here and is sure of it
            if confident % SAMPLE_EVERY == 0:
                sampled.append({"id": page_id, "name": row[1], "kinds": [], "sample": True,
                                "words": [f"checked as a sample: one confident page in {SAMPLE_EVERY}"]})
            confident += 1
    return proposed + sampled


def to_check(db: Any) -> int:
    return len(worklist(db))
