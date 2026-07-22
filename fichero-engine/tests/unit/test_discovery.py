from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from fichero.security import discovery
from fichero.api import main as api_main


class FakeServiceInfo:
    def __init__(
        self,
        type_: str,
        name: str,
        *,
        addresses: list[bytes],
        port: int,
        properties: dict[str, str],
        server: str,
    ) -> None:
        self.type = type_
        self.name = name
        self.addresses = addresses
        self.port = port
        self.properties = properties
        self.server = server


class FakeZeroconf:
    instances: list["FakeZeroconf"] = []

    def __init__(self) -> None:
        self.registered: list[FakeServiceInfo] = []
        self.unregistered: list[FakeServiceInfo] = []
        self.closed = False
        FakeZeroconf.instances.append(self)

    def register_service(self, info: FakeServiceInfo) -> None:
        self.registered.append(info)

    def unregister_service(self, info: FakeServiceInfo) -> None:
        self.unregistered.append(info)

    def close(self) -> None:
        self.closed = True


def test_build_service_info_uses_fichero_type_port_and_txt() -> None:
    config = discovery.BonjourConfig(
        enabled=True,
        host="127.0.0.1",
        port=8765,
        service_name="Fichero Test",
        version="0.1.test",
        spki_hash="abc123",
        public_url="https://fichero.example.ts.net",
    )

    info = discovery.build_service_info(config, service_info_cls=FakeServiceInfo)

    assert info.type == "_fichero._tcp.local."
    assert info.name == "Fichero Test._fichero._tcp.local."
    assert info.port == 8765
    assert info.addresses == [b"\x7f\x00\x00\x01"]
    assert info.properties == {
        "version": "0.1.test",
        "api": "1",
        "spki": "",
        "public_url": "https://fichero.example.ts.net",
    }


def test_spki_txt_is_always_redacted_even_when_tls_is_configured() -> None:
    config = discovery.BonjourConfig(
        enabled=True,
        host="127.0.0.1",
        port=8765,
        service_name="Fichero Test",
        version="0.1.test",
        spki_hash="",
        public_url="",
    )

    info = discovery.build_service_info(config, service_info_cls=FakeServiceInfo)

    assert info.properties["spki"] == ""


def test_env_gating_keeps_bonjour_off_by_default() -> None:
    FakeZeroconf.instances.clear()

    advertiser = discovery.start_bonjour_advertiser(
        {"FICHERO_BIND_HOST": "0.0.0.0", "FICHERO_BONJOUR_PORT": "not-a-port"},
        zeroconf_cls=FakeZeroconf,
        service_info_cls=FakeServiceInfo,
    )

    assert advertiser is None
    assert FakeZeroconf.instances == []


def test_enabled_bonjour_registers_and_stops_without_real_network() -> None:
    FakeZeroconf.instances.clear()

    advertiser = discovery.start_bonjour_advertiser(
        {
            "FICHERO_ENABLE_BONJOUR": "1",
            "FICHERO_BONJOUR_NAME": "Fichero Dev",
            "FICHERO_TLS_SPKI_HASH": "hash-value",
        },
        zeroconf_cls=FakeZeroconf,
        service_info_cls=FakeServiceInfo,
    )

    assert advertiser is not None
    zc = FakeZeroconf.instances[-1]
    assert zc.registered[0].name == "Fichero Dev._fichero._tcp.local."
    assert zc.registered[0].properties["spki"] == ""

    advertiser.stop()

    assert zc.unregistered == zc.registered
    assert zc.closed is True


def test_missing_zeroconf_dependency_disables_bonjour(monkeypatch, caplog) -> None:
    def missing() -> tuple[type[object], type[object]]:
        raise discovery.BonjourUnavailable("zeroconf missing")

    monkeypatch.setattr(discovery, "_load_zeroconf_classes", missing)

    with caplog.at_level(logging.WARNING):
        advertiser = discovery.start_bonjour_advertiser({"FICHERO_ENABLE_BONJOUR": "1"})

    assert advertiser is None
    assert "Bonjour discovery disabled" in caplog.text


def test_enabled_bonjour_invalid_config_does_not_start_or_break_startup(caplog) -> None:
    FakeZeroconf.instances.clear()

    with caplog.at_level(logging.WARNING):
        advertiser = discovery.start_bonjour_advertiser(
            {
                "FICHERO_ENABLE_BONJOUR": "1",
                "FICHERO_BONJOUR_PORT": "not-a-port",
            },
            zeroconf_cls=FakeZeroconf,
            service_info_cls=FakeServiceInfo,
        )

    assert advertiser is None
    assert FakeZeroconf.instances == []
    assert "Bonjour discovery disabled by invalid configuration" in caplog.text


def test_invalid_public_url_disables_bonjour_fail_closed(caplog) -> None:
    FakeZeroconf.instances.clear()

    with caplog.at_level(logging.WARNING):
        advertiser = discovery.start_bonjour_advertiser(
            {
                "FICHERO_ENABLE_BONJOUR": "1",
                "FICHERO_PUBLIC_BASE_URL": "http://attacker.invalid",
            },
            zeroconf_cls=FakeZeroconf,
            service_info_cls=FakeServiceInfo,
        )

    assert advertiser is None
    assert FakeZeroconf.instances == []
    assert "Bonjour discovery disabled by invalid configuration" in caplog.text


def test_lifespan_starts_and_stops_bonjour_when_env_enabled(monkeypatch) -> None:
    calls: list[str] = []

    class FakeAdvertiser:
        def stop(self) -> None:
            calls.append("stop")

    def start_fake(*, log: logging.Logger) -> FakeAdvertiser:
        calls.append("start")
        return FakeAdvertiser()

    monkeypatch.setenv("FICHERO_ENABLE_BONJOUR", "1")
    monkeypatch.setattr(api_main, "start_bonjour_advertiser", start_fake)
    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_watch_parent_process", _never_runs)
    monkeypatch.setattr(api_main, "start_periodic_snapshot_task", lambda: None)

    async def stop_snapshot(task: object) -> None:
        calls.append("snapshot-stop")

    monkeypatch.setattr(api_main, "stop_periodic_snapshot_task", stop_snapshot)

    with TestClient(api_main.app):
        # NOT asserted here any more (#3920): Bonjour registration is blocking
        # i/o, so it now runs in an executor instead of on the loop thread before
        # the yield — the socket must not wait on a service discovery broadcast.
        # Whether it has landed by the time startup completes is deliberately
        # unspecified; what IS guaranteed is that it starts, and that shutdown
        # awaits that start before stopping it (no zombie advertiser).
        pass

    assert calls == ["start", "snapshot-stop", "stop"]


async def _never_runs() -> None:
    return None


async def _recover_none() -> int:
    return 0
