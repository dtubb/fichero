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

import re
from dataclasses import dataclass, field
from typing import Any

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

