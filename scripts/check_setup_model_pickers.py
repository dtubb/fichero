#!/usr/bin/env python3
"""Every Set Up step is a chooser or says "Fichero does this one" (`wide.picker.guard`, #6052; wide-onboarding.md section J).

For every stage in `STAGES` and every job it offers (`runs_or_by_hand`):
  1. a job with `needs_a_model=True` has at least one card in `recipes/seed/cards.yaml` naming it, or is one of the text-model
     jobs the finder serves with local and cloud text models (`discovery.TEXT_MODEL_JOBS`, imported so the list cannot drift),
     or is in `NO_PICKER_YET`;
  2. a job with `needs_a_model=False` is one Fichero does itself (`assemble.FICHERO_DOES_IT`, the `PREPARE` step, Find
     documents, the plan's own readers) with a topic that says how (`start.how_it_works`), or one a tool does by hand
     (`start.BY_HAND_FIX`), or is in `NO_PICKER_YET`;
  3. the contract (`tests/contracts/openapi.json`) carries `needs_a_model` on `JobInfo`, which is what the app's row shape reads;
  4. an allowlist entry that no longer applies (the job gained a card, or says how) fails as stale, so the list only shrinks.

`NO_PICKER_YET` is one line per job: an issue and why. It may only name a job that truly runs no model.

Run: PYTHONPATH=fichero-server/src python scripts/check_setup_model_pickers.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"

#: job id -> "issue: why". Starts empty (the four text-model jobs and Find where readers disagree are covered above).
NO_PICKER_YET: dict[str, str] = {}


def problems(*, stage_jobs: list[str], needs_a_model: dict[str, bool], card_jobs: set[str], text_jobs: set[str],
             does_it: set[str], by_hand: set[str], how: dict[str, str | None], contract_has_needs_a_model: bool,
             allowlist: dict[str, str]) -> list[str]:
    """The guard's rules over plain data, so a test can feed it a scratch registry."""
    out: list[str] = []
    if not contract_has_needs_a_model:
        out.append("the contract (openapi.json) has no `needs_a_model` on JobInfo: the app cannot tell a chooser from "
                   "'Fichero does this one'; regenerate it with fichero-server/scripts/sync_openapi_schema.sh")
    for job in sorted(set(stage_jobs)):
        if job not in needs_a_model:
            out.append(f"{job}: a stage offers it but the job registry does not know it")
            continue
        covered = job in card_jobs or job in text_jobs
        if needs_a_model[job]:
            if not covered and job not in allowlist:
                out.append(f"{job}: runs a model but no card names it, it is not a text-model job and it is not in "
                           "NO_PICKER_YET: its picker would be empty on a Mac without a key")
        else:
            says_how = bool(how.get(job))
            fine = job in by_hand or (job in does_it and says_how)
            if not fine and job not in allowlist:
                out.append(f"{job}: runs no model but is not one Fichero does itself with a 'How it works:' topic, nor a "
                           "by-hand step: its row would read like a model's")
    for job, why in sorted(allowlist.items()):
        if job not in needs_a_model:
            out.append(f"NO_PICKER_YET names {job}, which is not a job: stale")
        elif needs_a_model[job] and (job in card_jobs or job in text_jobs):
            out.append(f"NO_PICKER_YET names {job}, which now has a card: stale, remove it")
        elif not needs_a_model[job] and (job in by_hand or (job in does_it and how.get(job))):
            out.append(f"NO_PICKER_YET names {job}, which now says how Fichero does it: stale, remove it")
        elif not why.strip():
            out.append(f"NO_PICKER_YET names {job} with no issue and reason")
    return out


def _facts() -> dict[str, Any]:
    from fichero_server.recipes.assemble import FICHERO_DOES_IT, FIND_DOCUMENTS, PREPARE
    from fichero_server.recipes.cards import seed_cards
    from fichero_server.recipes.discovery import TEXT_MODEL_JOBS
    from fichero_server.recipes.jobs import all_jobs
    from fichero_server.recipes.stages import STAGES, offered, runs_or_by_hand
    from fichero_server.recipes.start import BY_HAND_FIX, how_it_works

    jobs = {j.id: bool(j.needs_a_model) for j in all_jobs()}
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))["components"]["schemas"]["JobInfo"]["properties"]
    return {
        "stage_jobs": [j for s in STAGES if offered(s) for j in s.jobs if runs_or_by_hand(j)],
        "needs_a_model": jobs,
        "card_jobs": {j for c in seed_cards() for j in c.jobs},
        "text_jobs": set(TEXT_MODEL_JOBS),
        "does_it": {*FICHERO_DOES_IT, PREPARE, FIND_DOCUMENTS},
        "by_hand": set(BY_HAND_FIX) | {"find-where-readers-disagree"},  # the last names the plan's own readers on its row
        "how": {job: how_it_works(job) for job in jobs},
        "contract_has_needs_a_model": "needs_a_model" in schema,
        "allowlist": NO_PICKER_YET,
    }


def main() -> int:
    found = problems(**_facts())
    if found:
        print("Set Up model pickers guardrail: FAIL (wide.picker.guard, docs/contributor_manual/specs/source/wide-onboarding.md section J)")
        for line in found:
            print(f"  - {line}")
        return 1
    print("Set Up model pickers guardrail: every stage job is a chooser or says Fichero does it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
