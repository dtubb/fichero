"""A recipe step sent as a provider batch: ONE `cloud-batch` row under the step (#5940, spec compute/recipe-steps-at-scale.md).

`compute.recipe.cloud-batch-*`. The step's own vision calls are captured (`provider_batch.capturing`, nothing is called
or kept), the ones not answered before (the run's `answers.jsonl`, #6127) are cut to the provider's cap and submitted;
each batch's ids are on the row the moment the provider acknowledges them, so a restart adopts them and never submits
again. The row polls gently (a minute, backing off to five), keeps every answered line as it lands, and ends when every
batch has; the recipe then runs the step once more under `provider_batch.answering`, so each page lands through the
step's own path, and a line that failed goes as a plain call there. Stop cancels at the provider, polls each batch to
its end and keeps what was answered (it was billed) before the row reads Stopped (`ai.where.batch-stop-reaches-the-provider`).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fichero_server.execution import jobs
from fichero_server.llm import provider_batch as pb
from fichero_server.remote_read.job import PagesMayNotLeave, _project_must_agree

logger = logging.getLogger(__name__)

KIND = "cloud-batch"
#: A batch still out past this long says so once (`compute.recipe.cloud-batch-slow-path-record`, #6251).
SLOW_HOURS = 12
POLL_FIRST, POLL_MOST = 60.0, 300.0
#: The providers whose own batch API Fichero speaks, by the provider id a step's card names; the rest go as plain calls.
CLIENTS = {"anthropic": ("Anthropic", pb.AnthropicBatches), "openai": ("OpenAI", pb.OpenAIBatches),
           "google": ("Gemini", pb.GeminiBatches)}
#: Room for one step's answer: the plain call's own ceiling for a page of lines.
MAX_TOKENS = 4096


def client_for(provider: str) -> Any:
    """The batch client over the provider's own SDK, made with its key from the Keychain (never stored, never logged)."""
    from fichero_server import llm

    if provider not in CLIENTS:
        raise ValueError(f"{provider} has no batch API Fichero speaks: its pages go as plain calls")
    name, shape = CLIENTS[provider]
    key = llm.get_api_key(provider)
    if not key:
        raise ValueError(f"no {name} key in Settings › AI, so no batch can be sent to {name}")
    if provider == "anthropic":
        import anthropic

        return shape(anthropic.Anthropic(api_key=key))
    if provider == "openai":
        import openai

        return shape(openai.OpenAI(api_key=key))
    from google import genai

    return shape(genai.Client(api_key=key))


def start(db: Any, *, card: dict[str, Any], documents: list[str], parent_job_id: str, started_by: str,
          pages_may_leave: bool) -> str:
    """Queue one batch row under the recipe's step. A batch is a package that is SENT: the request's yes, the app's
    cloud place and the project's own yes, each refusing in words with nothing queued
    (`compute.recipe.cloud-batch-consent-and-cost`, `ai.where.one-egress-gate`)."""
    import uuid

    from fichero_server.recipes import places

    provider = card["provider_override"]
    if provider not in CLIENTS:
        raise ValueError(f"{provider} has no batch API Fichero speaks: its pages go as plain calls")
    name = CLIENTS[provider][0]
    if not pages_may_leave:
        raise PagesMayNotLeave(f"A batch sends these pages to {name}. Say yes for this project first (pages_may_leave).")
    if (no := places.refusal("cloud")):
        raise PagesMayNotLeave(no)
    _project_must_agree(db, f"Sending this step to {name} as a batch")
    detail = {"provider": provider, "model": card["model_override"], "max_tokens": MAX_TOKENS, "card": card,
              "documents": list(documents)}
    job_id = jobs.enqueue_remote(db, KIND, f"batch:{uuid.uuid4()}", target=provider, detail=json.dumps(detail),
                                 reason=f"Waiting to send to {name} as a batch", started_by=started_by)
    jobs.set_parent(db, job_id, parent_job_id)
    return job_id


def out_under(db: Any, parent_job_id: str) -> str | None:
    """The batch still out under a recipe's step, by its id, so a resumed recipe waits on it and never sends again."""
    row = db.execute_fetchone("SELECT id FROM jobs WHERE parent_id = ? AND kind = ? AND state IN ('waiting', 'running', "
                              "'paused') ORDER BY created_at DESC, rowid DESC LIMIT 1", [parent_job_id, KIND])
    return row[0] if row else None


def _work_dir(job_id: str) -> Path:
    from fichero_server.db.paths import server_state_dir

    return server_state_dir() / "cloud-batch" / job_id


def _detail(db: Any, job_id: str) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None:
        raise LookupError(f"no batch run {job_id}")
    return json.loads(row["detail"] or "{}")


def _save(db: Any, job_id: str, detail: dict[str, Any], reason: str | None = None) -> None:
    if _detail(db, job_id).get("cancel"):  # a Stop asked meanwhile is kept, never saved over
        detail["cancel"] = True
    jobs.save_detail(db, job_id, json.dumps(detail), reason=reason)


def book_for(job_id: str) -> pb.AnswerBook:
    return pb.AnswerBook(_work_dir(job_id) / "answers.jsonl")


def run(db: Any, subject: str, *, client: Any, capture: Callable[[Any, dict[str, Any]], list[pb.BatchRequest]],
        sleep: Callable[[float], None] = time.sleep, now: Callable[[], datetime] | None = None) -> dict[str, int]:
    """Submit what is still to answer (or adopt what is out), poll to the end, keep the answers. {answered, failed}."""
    from fichero_server.core.timeutil import utc_now

    from fichero_server.llm import spend

    now = now or utc_now
    job_id = jobs.job_id_for(db, KIND, subject)
    detail = _detail(db, job_id)
    book = book_for(job_id)
    who = client.name
    library = str(Path(db.path).parent)
    provider, model = detail["provider"], detail["model"]
    if not detail.get("batches"):
        to_send = book.still_to_send(capture(db, detail))
        detail["batches"] = []
        for chunk in pb.cut_to_cap(to_send, cap_bytes=client.cap_bytes):
            # The cap holds the batch's worst case from now until it ends; refused in words before it is sent.
            held = spend.reserve_batch(library, provider, model, requests=len(chunk), max_tokens=detail["max_tokens"])
            try:
                ids = client.submit(model, chunk, max_tokens=detail["max_tokens"])
            except BaseException:
                spend.settle_batch(library, held, 0.0)  # not sent: nothing owed
                raise
            detail["batches"].append({"ids": ids, "state": "open", "requests": len(chunk), "sent_at": now().isoformat(),
                                      "held_usd": held})
            _save(db, job_id, detail, reason=f"Sent as a batch to {who}: {sum(b['requests'] for b in detail['batches'])} "
                                              "requests, answered within a day")  # on the row before anything else
    else:  # adopted after a restart: the holds of the batches still out are held again in this process
        for batch in detail["batches"]:
            if batch["state"] == "open" and batch.get("held_usd"):
                spend.hold_again(library, batch["held_usd"])
    counts = {"answered": 0, "failed": 0}
    wait, stopping = POLL_FIRST, False
    while any(b["state"] == "open" for b in detail["batches"]):
        if not stopping and _detail(db, job_id).get("cancel"):
            stopping = True
            for batch in detail["batches"]:
                if batch["state"] == "open":
                    client.cancel(batch["ids"])
        for batch in detail["batches"]:
            if batch["state"] != "open":
                continue
            seen = client.poll(batch["ids"])
            at = now()
            if seen["state"] == "open":
                sent = datetime.fromisoformat(batch["sent_at"]) if batch.get("sent_at") else None
                if sent and (at - sent).total_seconds() > SLOW_HOURS * 3600 and not batch.get("slow_said"):
                    batch["slow_said"] = True
                    logger.warning("slow path: a batch to %s has waited past twelve hours (%d requests, sent %s)",
                                   who, batch["requests"], batch["sent_at"])
                continue
            if seen["state"] == "gone":  # past the provider's retention: its unanswered pages are asked again
                batch["state"] = "gone"
                spend.settle_batch(library, batch.get("held_usd", 0.0), batch.get("held_usd", 0.0))  # never free
                continue
            lines = client.lines(batch["ids"])
            book.keep(lines)
            batch.update(state="ended", answered=sum(line.ok for line in lines),
                         failed=sum(not line.ok for line in lines), why=seen.get("why"), ended_at=at.isoformat(),
                         tokens={k: sum(line.usage.get(k, 0) for line in lines) for k in ("input_tokens", "output_tokens")})
            costs = [spend.batch_cost_usd(provider, model, line.usage.get("input_tokens", 0),
                                          line.usage.get("output_tokens", 0)) for line in lines if line.ok]
            # What it was billed; a line that cannot be priced is booked at the hold (never free).
            batch["cost_usd"] = (round(sum(costs), 6) if all(c is not None for c in costs)
                                 else batch.get("held_usd", 0.0))
            spend.settle_batch(library, batch.get("held_usd", 0.0), batch["cost_usd"])
            if batch.get("sent_at"):
                batch["waited_hours"] = round((at - datetime.fromisoformat(batch["sent_at"])).total_seconds() / 3600, 2)
        counts = {"answered": sum(b.get("answered", 0) for b in detail["batches"]),
                  "failed": sum(b.get("failed", 0) for b in detail["batches"])}
        open_ = sum(b["state"] == "open" for b in detail["batches"])
        _save(db, job_id, detail, reason=(f"{'Stopping' if stopping else 'Sent as a batch'} to {who}: "
                                          f"{counts['answered']} answered, {counts['failed']} failed, {open_} batches out"))
        if open_:
            sleep(wait)
            wait = min(wait * 2, POLL_MOST)
    words = f"{who} answered {counts['answered']}, {counts['failed']} failed (asked again as plain calls)"
    if stopping:
        _save(db, job_id, detail, reason=f"Stopped: {words}; nothing answered is lost")
        raise jobs.JobCancelled(f"Stopped: {words}; nothing answered is lost")
    _save(db, job_id, detail, reason=f"Done: {words}")
    return counts


def request_cancel(db: Any, job_id: str) -> str:
    row = jobs.read_job(db, job_id)
    if row["state"] == "waiting":
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    detail = json.loads(row["detail"] or "{}")
    detail["cancel"] = True
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Stopping: cancelling the batch at the provider")
    return row["state"]


def _run_row(db: Any, subject: str) -> dict[str, int]:
    """The row's real run: the provider's own client, and the step's calls captured below the run machinery."""
    import asyncio

    from fichero_server.remote_read.capture import capture_step

    detail = _detail(db, jobs.job_id_for(db, KIND, subject))
    return run(db, subject, client=client_for(detail["provider"]),
               capture=lambda db, d: asyncio.run(capture_step(db, d["card"], d["documents"])))


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, _run_row, model=None, lane="remote", name="Cloud batch", cancel=request_cancel)


def run_step(db: Any, card: dict[str, Any], documents: list[str], parent: str, started_by: str, *,
             wait: Callable[[Any, str, str], tuple[str | None, str, str | None]],
             replay: Callable[[], tuple[str | None, str, str | None]]) -> tuple[str | None, str, str | None]:
    """A recipe step sent as a batch: one row under the step (adopted on a resume), waited on as any child, then the
    step run once more with its calls answered from the batch's lines, so each page lands through the step's own path.
    The project's yes is read now, where the pages would leave; a refusal fails the step in words, nothing queued."""
    from fichero_server.recipes import places
    from fichero_server.recipes.project import read_project_setup

    register_job_kinds()
    child = out_under(db, parent)
    if child is None:
        may_leave = places.may_leave_to(read_project_setup(Path(db.path).parent)["answers"], "cloud")
        try:
            child = start(db, card=card, documents=documents, parent_job_id=parent, started_by=started_by,
                          pages_may_leave=may_leave)
        except (PagesMayNotLeave, ValueError) as no:
            return None, "failed", str(no)
    _, state, why = wait(db, child, parent)
    if state != "done":
        return child, state, why
    with pb.answering(book_for(child).answers()):
        return replay()
