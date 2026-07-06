"""Regression tests for embedded local-model discovery contracts (#2615)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero.llm import _FM_BRIDGE_MISSING_MESSAGE, probe_apple_intelligence_bridge


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes) -> None:
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_probe_apple_bridge_returns_unavailable_reason_without_spawning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "fichero.llm._fm_bridge_unavailable_reason",
        lambda: "Apple Intelligence is not available on this device",
    )
    monkeypatch.setattr(
        "fichero.llm._find_fm_bridge_binary",
        lambda: pytest.fail("probe should not look for fm-bridge when subprocesses are unavailable"),
    )

    available, reason = await probe_apple_intelligence_bridge()

    assert available is False
    assert reason == "Apple Intelligence is not available on this device"


@pytest.mark.asyncio
async def test_probe_apple_bridge_reports_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("fichero.llm._fm_bridge_unavailable_reason", lambda: None)
    monkeypatch.setattr("fichero.llm._find_fm_bridge_binary", lambda: None)

    available, reason = await probe_apple_intelligence_bridge()

    assert available is False
    assert reason == _FM_BRIDGE_MISSING_MESSAGE


@pytest.mark.asyncio
async def test_probe_apple_bridge_reports_subprocess_launch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("fichero.llm._fm_bridge_unavailable_reason", lambda: None)
    monkeypatch.setattr("fichero.llm._find_fm_bridge_binary", lambda: "/tmp/fm-bridge")
    monkeypatch.setattr("asyncio.create_subprocess_exec", boom)

    available, reason = await probe_apple_intelligence_bridge()

    assert available is False
    assert reason == "Couldn't run fm-bridge: boom"


@pytest.mark.asyncio
async def test_probe_apple_bridge_reports_invalid_json_from_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_exec(*_args, **_kwargs):
        return _FakeProc(b"not-json", b"bridge stderr")

    monkeypatch.setattr("fichero.llm._fm_bridge_unavailable_reason", lambda: None)
    monkeypatch.setattr("fichero.llm._find_fm_bridge_binary", lambda: "/tmp/fm-bridge")
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    available, reason = await probe_apple_intelligence_bridge()

    assert available is False
    assert reason == "bridge stderr"


@pytest.mark.asyncio
async def test_probe_apple_bridge_returns_probe_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_exec(*_args, **_kwargs):
        return _FakeProc(b'{"available": true, "reason": null}', b"")

    monkeypatch.setattr("fichero.llm._fm_bridge_unavailable_reason", lambda: None)
    monkeypatch.setattr("fichero.llm._find_fm_bridge_binary", lambda: "/tmp/fm-bridge")
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    available, reason = await probe_apple_intelligence_bridge()

    assert available is True
    assert reason is None
