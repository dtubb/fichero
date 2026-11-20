"""`runner.soak.google-reading-efficiency` (#6732): the cloud line reader with a fake Gemini client (recorded replies, no network, no
spend) batches lines per request, keeps every provider's requests within its slot cap, retries 429 and 5xx with a back-off that honours
Retry-After, and never sends a line it has already read twice."""
from __future__ import annotations

import asyncio

from PIL import Image, ImageDraw

from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader, retry
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult
from fichero_server.workflows import circuit_breaker as cb

GOOGLE = LLMConfig(provider="google", model="gemini-test")


class _Status(Exception):
    def __init__(self, status_code, retry_after=None):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


def _page(tmp_path, n_lines):
    path = tmp_path / "page.png"
    image = Image.new("RGB", (400, 12 * n_lines + 20), "white")
    draw = ImageDraw.Draw(image)
    boxes = []
    for i in range(n_lines):
        y = 5 + 12 * i
        draw.rectangle([10, y, 390, y + 8], fill=((i * 5) % 256, (i * 11) % 256, (i * 17) % 256))  # a picture of its own for every line
        poly = [[10, y], [390, y], [390, y + 8], [10, y + 8]]
        boxes.append(OCRGeometryBox(text="", bbox=[0.05, 0.1, 0.9, 0.01], level=OCRGeometryLevel.LINE, provider="kraken", model="m",
                                    source="working-pass", metadata={"segment_id": f"s{i}", "polygon_px": poly,
                                                                      "baseline_px": [[10, y + 7], [390, y + 7]],
                                                                      "pixel_frame": {"width": 400, "height": 12 * n_lines + 20}}))
    image.save(path)
    return str(path), OCRGeometryResult(text="", provider="kraken", model="m", boxes=boxes, source="working-pass", metadata={})


def _read(monkeypatch, tmp_path, n_lines):
    path, geometry = _page(tmp_path, n_lines)
    page = Image.open(path)
    by_picture = {line_reader._crop_data_uri(page, b.metadata["polygon_px"]): f"line {i}" for i, b in enumerate(geometry.boxes)}
    sent: list[list[str]] = []
    in_flight = {"now": 0, "peak": 0}

    async def gemini(images, prompt, config, **_):
        sent.append(list(images))
        in_flight["now"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["now"])
        await asyncio.sleep(0.01)
        in_flight["now"] -= 1
        return "[" + ", ".join(f'"{by_picture[i]}"' for i in images) + "]"

    monkeypatch.setattr(llm, "vision", gemini)
    out = asyncio.run(line_reader.read_lines(path, geometry, GOOGLE))
    return out, sent, in_flight


def test_a_page_of_40_lines_goes_in_three_requests_and_each_line_is_sent_once(monkeypatch, tmp_path):
    out, sent, in_flight = _read(monkeypatch, tmp_path, 40)
    assert [len(s) for s in sent] == [line_reader.LINES_PER_CALL, line_reader.LINES_PER_CALL, 8]
    assert len({i for s in sent for i in s}) == 40 and sum(map(len, sent)) == 40, "no line picture sent twice"
    assert [b.text for b in out.boxes] == [f"line {i}" for i in range(40)]
    assert in_flight["peak"] <= line_reader.CONCURRENT_CALLS


def test_requests_in_flight_never_pass_the_providers_slot_cap():
    peak = {"now": 0, "max": 0}

    async def call():
        peak["now"] += 1
        peak["max"] = max(peak["max"], peak["now"])
        await asyncio.sleep(0.02)
        peak["now"] -= 1
        return "ok"

    async def go():
        return await asyncio.gather(*(retry.resilient(call, GOOGLE) for _ in range(5 * cb._cap_for("google").cap)))

    asyncio.run(go())
    assert 0 < peak["max"] <= cb._cap_for("google").cap


def _slept(monkeypatch):
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(cb.asyncio, "sleep", sleep)
    monkeypatch.setattr(retry, "_DEAD", {})
    return waits


def test_a_429_is_retried_after_at_least_the_providers_retry_after(monkeypatch):
    waits = _slept(monkeypatch)
    answers = [_Status(429, retry_after=7), "read"]

    async def call():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert asyncio.run(retry.resilient(call, GOOGLE)) == "read"
    assert answers == [] and max(waits) >= 7


def test_a_503_is_retried_with_a_growing_back_off(monkeypatch):
    waits = _slept(monkeypatch)
    answers = [_Status(503), _Status(503), "read"]

    async def call():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert asyncio.run(retry.resilient(call, GOOGLE)) == "read"
    backoffs = [w for w in waits if w >= 0.1]
    assert len(backoffs) == 2 and backoffs[1] >= backoffs[0]


def test_a_400_is_not_retried(monkeypatch):
    _slept(monkeypatch)
    calls = []

    async def call():
        calls.append(1)
        raise _Status(400)

    try:
        asyncio.run(retry.resilient(call, GOOGLE))
    except _Status:
        pass
    assert calls == [1]


def test_a_gemini_429_that_gives_its_wait_in_the_body_is_waited_for(monkeypatch):
    """Gemini names the wait in the error's RetryInfo (`retryDelay`), or in its message ("Please retry in 7.5s"), not in a header."""
    info = {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"}]}}
    in_details = _Status(429)
    in_details.details = info
    in_message = _Status(429)
    in_message.args = ("429 RESOURCE_EXHAUSTED. Please retry in 7.5s.",)
    assert cb.retry_after_seconds(in_details) == 34.0
    assert cb.retry_after_seconds(in_message) == 7.5
    assert cb.retry_after_seconds(_Status(429)) is None
    waits = _slept(monkeypatch)
    answers = [in_details, "read"]

    async def call():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert asyncio.run(retry.resilient(call, GOOGLE)) == "read" and max(waits) >= 34
