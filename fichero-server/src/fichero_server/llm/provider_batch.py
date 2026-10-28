"""A recipe step on a provider's batch API (`compute.recipe.cloud-batch-*`, spec compute/recipe-steps-at-scale.md, #5940).

The providers' batch APIs take many requests at once and answer within a day at half the price. One client per API
shape, each the same four calls over the provider's own SDK (the ones LangChain's plain calls already bring in):
`submit` (the ids to keep on the run's row), `poll` (`open` / `ended` / `gone`), `lines` (one `BatchLine` per request,
matched by its key, never by position) and `cancel`. A request's key is the plain call's result-cache key
(`llm._vision_cache_key`), so a line lands as the pass a plain call would have written, and a page whose key is
already answered is never sent (#6127). The SDK client is passed in: the engine makes it with the provider's key from
the Keychain; tests pass a fake of the same surface.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

#: Pages of one step on one cloud model in one run from which the step goes as a batch (ruling 4, 2026-10-28):
#: below it, plain calls finish sooner and the saving is cents. ponytail: re-set from step 2's real runs.
BATCH_THRESHOLD = 100
#: Anthropic's own limits on a batch (platform.claude.com, checked 2026-10-28).
ANTHROPIC_CAP_BYTES = 256 * 1024 * 1024
ANTHROPIC_MAX_REQUESTS = 100_000
_CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@dataclass(frozen=True)
class BatchRequest:
    """One page of one step: its key (the result-cache key), the prompt, and the page's images as data URIs."""

    key: str
    prompt: str
    images: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchLine:
    """One request's answer: its text and billed usage, or why it failed in the provider's words."""

    key: str
    ok: bool
    text: str | None = None
    why: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


def goes_as_batch(pages: int, *, waiting: bool, threshold: int = BATCH_THRESHOLD) -> bool:
    """`compute.recipe.cloud-batch-above-threshold`: a step's pages go as a batch from the threshold, never when a person
    is waiting on the answer (a Read Now press, a bake-off sample)."""
    return not waiting and pages >= threshold


def request_bytes(request: BatchRequest) -> int:
    return len(request.prompt.encode()) + sum(len(image) for image in request.images) + len(request.key)


def cut_to_cap(requests: list[BatchRequest], *, cap_bytes: int, max_requests: int | None = None) -> list[list[BatchRequest]]:
    """The requests in order, cut into as many batches as the provider's byte cap (and request count) allow."""
    out: list[list[BatchRequest]] = []
    size = 0
    for request in requests:
        n = request_bytes(request)
        if not out or size + n > cap_bytes or (max_requests and len(out[-1]) >= max_requests):
            out.append([])
            size = 0
        out[-1].append(request)
        size += n
    return out


def _is_gone(exc: Exception) -> bool:
    """The SDKs' answer for an id the provider no longer keeps (past retention): an error carrying HTTP 404."""
    return 404 in (getattr(exc, "status_code", None), getattr(exc, "code", None))


def _split_data_uri(uri: str) -> tuple[str, str]:
    head, data = uri.split(",", 1)
    return head.removeprefix("data:").split(";", 1)[0], data


class AnthropicBatches:
    """Anthropic Message Batches: submitted INLINE, one `messages.batches.create` of `{custom_id, params}`; polled by
    `processing_status` (`in_progress` -> `ended`); answered as typed results (`succeeded`, `errored`, `canceled`,
    `expired`), only `succeeded` billed."""

    name = "Anthropic"
    cap_bytes = ANTHROPIC_CAP_BYTES

    def __init__(self, client: Any):
        self.client = client

    def submit(self, model: str, requests: list[BatchRequest], *, max_tokens: int) -> dict[str, str]:
        bad = [r.key for r in requests if not _CUSTOM_ID.match(r.key)]
        if bad:
            raise ValueError(f"Anthropic refuses a custom_id that is not 1-64 letters, digits, _ or -: {bad[0]!r}")
        made = self.client.messages.batches.create(requests=[
            {"custom_id": r.key, "params": {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": [
                *({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
                  for media, data in map(_split_data_uri, r.images)),
                {"type": "text", "text": r.prompt}]}]}}
            for r in requests])
        return {"batch_id": made.id}

    def poll(self, ids: dict[str, str]) -> dict[str, Any]:
        try:
            batch = self.client.messages.batches.retrieve(ids["batch_id"])
        except Exception as exc:
            if _is_gone(exc):
                return {"state": "gone"}
            raise
        if batch.processing_status != "ended":
            return {"state": "open"}
        c = batch.request_counts
        return {"state": "ended", "counts": {"succeeded": c.succeeded, "failed": c.errored + c.canceled + c.expired,
                                             "open": c.processing}}

    def lines(self, ids: dict[str, str]) -> list[BatchLine]:
        out = []
        for row in self.client.messages.batches.results(ids["batch_id"]):
            result = row.result
            if result.type == "succeeded":
                text = "".join(b.text for b in result.message.content if b.type == "text")
                usage = result.message.usage
                out.append(BatchLine(row.custom_id, True, text=text,
                                     usage={"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}))
            elif result.type == "errored":
                error = result.error.error
                out.append(BatchLine(row.custom_id, False, why=f"Anthropic: {error.type}: {error.message}"))
            else:  # canceled, expired
                out.append(BatchLine(row.custom_id, False, why=f"Anthropic: {result.type} before it was answered"))
        return out

    def cancel(self, ids: dict[str, str]) -> None:
        self.client.messages.batches.cancel(ids["batch_id"])



#: OpenAI's limits on one batch file (developers.openai.com, checked 2026-10-28).
OPENAI_CAP_BYTES = 200 * 1024 * 1024
OPENAI_MAX_REQUESTS = 50_000
_OPENAI_OPEN = frozenset({"validating", "in_progress", "finalizing", "cancelling"})


class OpenAIBatches:
    """OpenAI Batch: submitted as a FILE (`files.create(purpose="batch")`, one chat request a line, one model a file),
    then `batches.create` over it with the 24-hour window; answers in `output_file_id`, failures in `error_file_id`,
    matched by `custom_id` (their order differs). An `expired` or `cancelled` batch ends with what it answered."""

    name = "OpenAI"
    cap_bytes = OPENAI_CAP_BYTES
    endpoint = "/v1/chat/completions"

    def __init__(self, client: Any):
        self.client = client

    def submit(self, model: str, requests: list[BatchRequest], *, max_tokens: int) -> dict[str, str]:

        lines = [json.dumps({"custom_id": r.key, "method": "POST", "url": self.endpoint, "body": {
            "model": model, "max_completion_tokens": max_tokens, "messages": [{"role": "user", "content": [
                {"type": "text", "text": r.prompt}, *({"type": "image_url", "image_url": {"url": i}} for i in r.images)]}]}})
            for r in requests]
        uploaded = self.client.files.create(file=("fichero-batch.jsonl", "\n".join(lines).encode()), purpose="batch")
        made = self.client.batches.create(input_file_id=uploaded.id, endpoint=self.endpoint, completion_window="24h")
        return {"batch_id": made.id, "input_file_id": uploaded.id}

    def _batch(self, ids: dict[str, str]) -> Any | None:
        try:
            return self.client.batches.retrieve(ids["batch_id"])
        except Exception as exc:
            if _is_gone(exc):
                return None
            raise

    def poll(self, ids: dict[str, str]) -> dict[str, Any]:
        batch = self._batch(ids)
        if batch is None:
            return {"state": "gone"}
        if batch.status in _OPENAI_OPEN:
            return {"state": "open"}
        c = batch.request_counts
        out: dict[str, Any] = {"state": "ended", "counts": {"succeeded": c.completed, "failed": c.failed,
                                                            "open": c.total - c.completed - c.failed}}
        if batch.status == "failed":  # the file itself was refused: no line is answered
            out["why"] = "OpenAI refused the batch: " + "; ".join(
                e.message for e in (getattr(batch.errors, "data", None) or [])) if batch.errors else "OpenAI refused the batch"
        return out

    def lines(self, ids: dict[str, str]) -> list[BatchLine]:

        batch = self._batch(ids)
        out = []
        for file_id in (batch.output_file_id, batch.error_file_id) if batch else ():
            if not file_id:
                continue
            for raw in self.client.files.content(file_id).text.splitlines():
                if not raw.strip():
                    continue
                row = json.loads(raw)
                response, error = row.get("response") or {}, row.get("error")
                body = response.get("body") or {}
                if not error and response.get("status_code") == 200:
                    usage = body.get("usage") or {}
                    out.append(BatchLine(row["custom_id"], True, text=body["choices"][0]["message"]["content"] or "",
                                         usage={"input_tokens": usage.get("prompt_tokens", 0),
                                                "output_tokens": usage.get("completion_tokens", 0)}))
                elif error:
                    out.append(BatchLine(row["custom_id"], False, why=f"OpenAI: {error.get('code')}: {error.get('message')}"))
                else:
                    message = (body.get("error") or {}).get("message")
                    out.append(BatchLine(row["custom_id"], False, why=f"OpenAI: {response.get('status_code')}: {message}"))
        return out

    def cancel(self, ids: dict[str, str]) -> None:
        self.client.batches.cancel(ids["batch_id"])


#: Gemini's file batches (ai.google.dev, checked 2026-10-28): a `.jsonl` through the Files API, up to 2 GB.
GEMINI_CAP_BYTES = 2 * 1024 * 1024 * 1024
_GEMINI_ENDED = frozenset({"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"})


class GeminiBatches:
    """Gemini Batch Mode, always by FILE: a `.jsonl` of `{key, request}` uploaded through the Files API, the job made over
    it; the answers come back as a file of `{key, response | error}`. ponytail: its inline mode (under about 20 MB, answers
    by position) is not used; one path keeps every answer under its key."""

    name = "Gemini"
    cap_bytes = GEMINI_CAP_BYTES

    def __init__(self, client: Any):
        self.client = client

    def submit(self, model: str, requests: list[BatchRequest], *, max_tokens: int) -> dict[str, str]:
        import io

        lines = [json.dumps({"key": r.key, "request": {
            "contents": [{"role": "user", "parts": [{"text": r.prompt}, *(
                {"inline_data": {"mime_type": media, "data": data}} for media, data in map(_split_data_uri, r.images))]}],
            "generation_config": {"max_output_tokens": max_tokens}}}) for r in requests]
        uploaded = self.client.files.upload(file=io.BytesIO("\n".join(lines).encode()),
                                            config={"mime_type": "jsonl", "display_name": "fichero-batch"})
        made = self.client.batches.create(model=model, src=uploaded.name)
        return {"batch_id": made.name, "input_file_id": uploaded.name}

    def _job(self, ids: dict[str, str]) -> Any | None:
        try:
            return self.client.batches.get(name=ids["batch_id"])
        except Exception as exc:
            if _is_gone(exc):
                return None
            raise

    def poll(self, ids: dict[str, str]) -> dict[str, Any]:
        job = self._job(ids)
        if job is None:
            return {"state": "gone"}
        state = job.state.name
        if state not in _GEMINI_ENDED:
            return {"state": "open"}
        return {"state": "ended", **({} if state == "JOB_STATE_SUCCEEDED" else {"why": f"Gemini: {state}"})}

    def lines(self, ids: dict[str, str]) -> list[BatchLine]:
        job = self._job(ids)
        name = getattr(getattr(job, "dest", None), "file_name", None)
        if not name:
            return []
        out = []
        for raw in self.client.files.download(file=name).decode().splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("response"):
                response = row["response"]
                parts = ((response.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                usage = response.get("usageMetadata") or {}
                out.append(BatchLine(row["key"], True, text="".join(p.get("text", "") for p in parts),
                                     usage={"input_tokens": usage.get("promptTokenCount", 0),
                                            "output_tokens": usage.get("candidatesTokenCount", 0)}))
            else:
                error = row.get("error") or row.get("status") or {}
                out.append(BatchLine(row["key"], False, why=f"Gemini: {error.get('code')}: {error.get('message')}"))
        return out

    def cancel(self, ids: dict[str, str]) -> None:
        self.client.batches.cancel(name=ids["batch_id"])


# --- the seam in `llm.vision` -----------------------------------------------------------------------------------
#: Set by the batch step around a run of the step's own workflow: ("capture", calls, answer) records each vision
#: call as a request and answers it with `answer(prompt, images)` without calling anyone; ("answers", book) answers a call
#: from the batch's lines by its key. Unset, `llm.vision` is untouched.
_SEAM: contextvars.ContextVar[tuple | None] = contextvars.ContextVar("provider_batch_seam", default=None)


@contextlib.contextmanager
def capturing(answer: Callable[[str, list[str]], str]) -> Iterator[list[BatchRequest]]:
    """The vision calls made inside, as batch requests under their cache keys; none of them is sent. `answer(prompt,
    images)` stands in for the model so the step goes on to its next call as if answered (no re-ask is captured)."""
    calls: list[BatchRequest] = []
    token = _SEAM.set(("capture", calls, answer))
    try:
        yield calls
    finally:
        _SEAM.reset(token)


@contextlib.contextmanager
def answering(book: dict[str, str]) -> Iterator[None]:
    """Vision calls inside are answered from the batch's lines by key; a key with no line goes as a plain call."""
    token = _SEAM.set(("answers", book))
    try:
        yield
    finally:
        _SEAM.reset(token)


def through_the_seam(key: str, prompt: str, images: list[str]) -> str | None:
    """`llm.vision`'s hook, at its cache lookup: the seam's answer for this call, or None to go on as a plain call."""
    seam = _SEAM.get()
    if seam is None:
        return None
    if seam[0] == "capture":
        seam[1].append(BatchRequest(key=key, prompt=prompt, images=tuple(images)))
        return seam[2](prompt, list(images))
    return seam[1].get(key)


class AnswerBook:
    """The run's answered lines, on disk (one JSON line each), so what a provider answered is never asked again: a
    resume, a restart or a rerun reads it back, leaves its keys out of the next batch and answers the step from it
    (#6127). Only answers are kept; a failed line is asked again."""

    def __init__(self, path: Any):
        from pathlib import Path

        self.path = Path(path)

    def answers(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        out = {}
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row = json.loads(raw)
                out[row["key"]] = row["text"]
        return out

    def keep(self, lines: list[BatchLine]) -> None:
        known = self.answers()
        new = [line for line in lines if line.ok and line.key not in known]
        if not new:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for line in new:
                handle.write(json.dumps({"key": line.key, "text": line.text, "usage": line.usage}) + "\n")
            handle.flush()

    def still_to_send(self, requests: list[BatchRequest]) -> list[BatchRequest]:
        known = self.answers()
        return [r for r in requests if r.key not in known]


def in_a_batch() -> bool:
    """A step sent as a provider batch is under way (its capture or its replay): its calls go through the batch."""
    return _SEAM.get() is not None


def is_capturing() -> bool:
    """A capture run is under way: the step's tools save nothing (its answers are stand-ins)."""
    seam = _SEAM.get()
    return seam is not None and seam[0] == "capture"
