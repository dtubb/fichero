"""#4276 — provider mutations must reach every window's change stream.

Providers (and their API keys / model lists) are app-wide, but the change
stream is library-keyed — before this, NOTHING invalidated a client's
provider-derived caches when a provider landed from another window, another
device, or the CLI, so the Run Workflow submenu stayed stale until restart.

Pins: (1) `emit_change_all_libraries` fans one `provider.*` event out to
every live subscriber key; (2) every mutating provider / key / model / ref
route calls the broadcast.
"""

import inspect

from fichero_server.api import change_stream as cs
from fichero_server.api.change_stream import (
    _ChangeHub,
    emit_change_all_libraries,
)

LIB_A = "/lib/A.fichero"
LIB_B = "/lib/B.fichero"


class TestEmitChangeAllLibraries:
    def test_reaches_every_subscribed_library(self, monkeypatch):
        hub = _ChangeHub()
        monkeypatch.setattr(cs, "_change_hub", hub)
        qa = hub.subscribe(LIB_A)
        qb = hub.subscribe(LIB_B)

        reached = emit_change_all_libraries(type="provider.created")

        assert reached == 2
        ev_a = qa.get_nowait()
        ev_b = qb.get_nowait()
        assert ev_a.type == "provider.created"
        assert ev_b.type == "provider.created"
        # Independent per-library event objects — per-library id/replay
        # bookkeeping must not share one mutated instance.
        assert ev_a is not ev_b

    def test_no_subscribers_is_a_safe_noop(self, monkeypatch):
        monkeypatch.setattr(cs, "_change_hub", _ChangeHub())
        assert emit_change_all_libraries(type="provider.updated") == 0

    def test_never_raises(self, monkeypatch):
        monkeypatch.setattr(cs, "_change_hub", object())  # no ._lock at all
        assert emit_change_all_libraries(type="provider.updated") == 0


class TestProviderRoutesBroadcast:
    """Every provider-affecting mutation route must fan the change out."""

    def test_provider_crud_and_model_and_ref_routes_broadcast(self):
        from fichero_server.api.routes.ai import providers

        for route_fn in (
            providers.create_provider,
            providers.update_provider,
            providers.delete_provider,
            providers.add_model_to_provider,
            providers.remove_model_from_provider,
            providers.add_provider_ref,
            providers.update_provider_ref,
            providers.delete_provider_ref,
        ):
            source = inspect.getsource(route_fn)
            assert "_broadcast_provider_change" in source, (
                f"{route_fn.__name__} must broadcast a provider.* change "
                "so other windows drop their provider caches (#4276)"
            )

    def test_api_key_routes_broadcast(self):
        from fichero_server.api.routes.ai import provider_keys

        for route_fn in (
            provider_keys.set_provider_api_key,
            provider_keys.delete_provider_api_key,
        ):
            source = inspect.getsource(route_fn)
            assert "_broadcast_provider_change" in source, (
                f"{route_fn.__name__} must broadcast — a key landing flips "
                "the provider's availability (#4276)"
            )
