"""Unit tests for the PROVIDER-domain audited actions (EPIC #1848 / sweep #2014).

Every mutating provider route is wrapped by a registered action; this suite
drives each one through ``registry.invoke`` (the single audited choke point) and
asserts, per the test bar:

  (a) the effect lands + an ActionAudit row is written (actor/target/before/after);
  (b) undo reverses it (for undoable actions) — and the restore round-trips;
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id, upsert-not-
      -insert, cross-provider model, api_base null-reset limitation);
  (e) emit fires with the right type (monkeypatched at the change_stream source);
  (f) SECRETS never land in the audit — api_key is excluded from params.

Provider/Model live in the *app-wide* AppDatabase (the action reaches it via
``get_app_db()``, which the ``app_db`` fixture swaps to the test instance); the
library ``db`` only carries the ActionAudit row. ProviderRef is a *library* model
so its actions use ``db`` directly.

The MANAGER runs the suite — workers do not execute pytest (RAM economy).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# Importing the route modules registers the provider.* actions via @action.
import fichero_server.api.routes.providers  # noqa: F401
import fichero_server.api.routes.provider_keys  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, Model, Provider, ProviderRef, ProviderType


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path="/lib/test.fichero")


def _make_provider(
    app_db,
    name: str = "My OpenAI",
    provider_type: str = "openai",
    api_base: str | None = None,
    enabled: bool = True,
) -> Provider:
    provider = Provider(
        name=name,
        provider_type=ProviderType(provider_type),
        api_base=api_base,
        enabled=enabled,
    )
    app_db.save_provider(provider)
    return provider


def _make_model(app_db, provider_id: str, model_id: str = "gpt-4o") -> Model:
    model = Model(
        provider_id=provider_id,
        name=model_id,
        model_id=model_id,
        capabilities=["text"],
    )
    app_db.save_model(model)
    return model


@pytest.fixture
def emit_spy(monkeypatch):
    """Collect emit_change calls fired by the registry (best-effort broadcast)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _emit_types(calls: list[tuple]) -> set[str]:
    return {k.get("type") for _a, k in calls}


# ===========================================================================
# provider.create  (undoable: delete the inserted row; None for an upsert)
# ===========================================================================


class TestProviderCreateAction:
    def test_create_effect_audit_and_emit(self, db, app_db, emit_spy):
        result = registry.invoke(
            db,
            "provider.create",
            {"provider_type": "ollama", "name": "Local Ollama"},
            _ctx(),
        )
        # (a) effect landed in app_db
        assert any(p.name == "Local Ollama" for p in app_db.list_providers())
        # (a) audit row written with the right shape
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "provider.create"
        assert audit.actor == "ui"
        assert audit.after["created"] is True
        assert audit.target_ids == [audit.after["provider_id"]]
        # (e) emit fired with the provider.created type
        assert "provider.created" in _emit_types(emit_spy)

    def test_undo_create_deletes_provider(self, db, app_db, emit_spy):
        result = registry.invoke(
            db, "provider.create", {"provider_type": "ollama", "name": "Temp"}, _ctx()
        )
        pid = result.result["id"]
        assert app_db.get_provider(pid) is not None

        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("provider.create")
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse is not None and inverse[0] == "provider.delete"
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        assert app_db.get_provider(pid) is None

    def test_upsert_update_is_not_undoable(self, db, app_db, emit_spy):
        # First create inserts; the second create on the same (name, type)
        # UPDATES the existing row (#704). Undo must NOT delete that row.
        registry.invoke(
            db, "provider.create", {"provider_type": "ollama", "name": "Dup"}, _ctx()
        )
        result2 = registry.invoke(
            db, "provider.create", {"provider_type": "ollama", "name": "Dup"}, _ctx()
        )
        audit2 = db.get(ActionAudit, result2.audit_id)
        assert audit2.after["created"] is False
        reg = registry.get("provider.create")
        assert reg.invert(audit2.before, audit2.after, _ctx()) is None

    def test_create_param_validation_rejects_missing_type(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "provider.create", {}, _ctx())

    def test_create_unknown_type_raises(self, db, app_db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "provider.create", {"provider_type": "not-a-provider"}, _ctx()
            )
        assert exc.value.status_code == 400

    def test_create_secret_never_lands_in_audit(self, db, app_db, monkeypatch):
        # Cloud provider WITH a key: the keychain write is stubbed, and the audit
        # must NOT contain the api_key.
        monkeypatch.setattr(
            "fichero_server.api.routes.providers.set_api_key", lambda pt, k: True
        )
        result = registry.invoke(
            db,
            "provider.create",
            {"provider_type": "openai", "name": "Keyed", "api_key": "sk-secret"},
            _ctx(),
        )
        audit = db.get(ActionAudit, result.audit_id)
        assert "api_key" not in audit.params
        assert "sk-secret" not in str(audit.params)


# ===========================================================================
# provider.update  (undoable: restore prior config fields)
# ===========================================================================


class TestProviderUpdateAction:
    def test_update_effect_audit_and_undo(self, db, app_db, emit_spy):
        provider = _make_provider(app_db, name="Orig", api_base="https://a")
        result = registry.invoke(
            db,
            "provider.update",
            {"provider_id": provider.id, "name": "Renamed", "enabled": False},
            _ctx(),
        )
        updated = app_db.get_provider(provider.id)
        assert updated.name == "Renamed" and updated.enabled is False

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["name"] == "Orig"
        assert audit.before["enabled"] is True
        assert "provider.updated" in _emit_types(emit_spy)

        reg = registry.get("provider.update")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())
        restored = app_db.get_provider(provider.id)
        assert restored.name == "Orig" and restored.enabled is True

    def test_update_unknown_provider_raises(self, db, app_db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "provider.update", {"provider_id": "nope", "name": "x"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_update_param_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "provider.update", {"name": "x"}, _ctx())

    def test_undo_cannot_reset_a_field_back_to_null(self, db, app_db, emit_spy):
        # Documents the PATCH-semantics limitation: a field that was originally
        # None cannot be reset to None by the inverse (api_key=None / value=None
        # both mean "leave unchanged"). A naive impl might silently claim a full
        # reversal — this pins the real behavior.
        provider = _make_provider(app_db, name="P", api_base=None)
        result = registry.invoke(
            db,
            "provider.update",
            {"provider_id": provider.id, "api_base": "https://set-now"},
            _ctx(),
        )
        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("provider.update")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())
        # api_base stays set — undo restored name/enabled but cannot null it out.
        assert app_db.get_provider(provider.id).api_base == "https://set-now"


# ===========================================================================
# provider.delete  (undoable: restore provider + its cascade-deleted models)
# ===========================================================================


class TestProviderDeleteAction:
    def test_delete_effect_audit_and_restore(self, db, app_db, emit_spy):
        provider = _make_provider(app_db, name="ToDelete")
        model = _make_model(app_db, provider.id)

        result = registry.invoke(
            db, "provider.delete", {"provider_id": provider.id}, _ctx()
        )
        # effect: provider + cascade model gone
        assert app_db.get_provider(provider.id) is None
        assert app_db.get_model(model.id) is None
        # audit snapshot captured the provider AND its models for undo
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["provider"]["id"] == provider.id
        assert len(audit.before["models"]) == 1
        assert "provider.deleted" in _emit_types(emit_spy)

        # undo via provider.restore re-creates provider + model
        reg = registry.get("provider.delete")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse[0] == "provider.restore"
        registry.invoke(db, inverse[0], inverse[1], _ctx())
        restored = app_db.get_provider(provider.id)
        assert restored is not None and restored.name == "ToDelete"
        assert app_db.get_model(model.id) is not None

    def test_delete_unknown_provider_raises(self, db, app_db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "provider.delete", {"provider_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_param_validation(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "provider.delete", {}, _ctx())


# ===========================================================================
# provider.remove_model  (undoable: restore the removed model)
# ===========================================================================


class TestRemoveModelAction:
    def test_remove_effect_audit_and_restore(self, db, app_db, emit_spy):
        provider = _make_provider(app_db)
        model = _make_model(app_db, provider.id)

        result = registry.invoke(
            db,
            "provider.remove_model",
            {"provider_id": provider.id, "model_id": model.id},
            _ctx(),
        )
        assert app_db.get_model(model.id) is None
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["model"]["id"] == model.id
        assert "provider.model_removed" in _emit_types(emit_spy)

        reg = registry.get("provider.remove_model")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse[0] == "provider.restore_model"
        registry.invoke(db, inverse[0], inverse[1], _ctx())
        assert app_db.get_model(model.id) is not None

    def test_remove_unknown_model_raises(self, db, app_db):
        provider = _make_provider(app_db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "provider.remove_model",
                {"provider_id": provider.id, "model_id": "no-model"},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_remove_model_under_wrong_provider_raises(self, db, app_db):
        # The model exists, but not under the provider named in the request —
        # the 404 is keyed on the model belonging to provider_id (route parity).
        p1 = _make_provider(app_db, name="P1")
        p2 = _make_provider(app_db, name="P2", provider_type="anthropic")
        model = _make_model(app_db, p1.id)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "provider.remove_model",
                {"provider_id": p2.id, "model_id": model.id},
                _ctx(),
            )
        assert exc.value.status_code == 404
        # The model was NOT deleted as a side effect of the failed lookup.
        assert app_db.get_model(model.id) is not None


# ===========================================================================
# provider.update_ref / provider.delete_ref  (library ProviderRef)
# ===========================================================================


class TestProviderRefActions:
    def _make_ref(self, db, app_db) -> ProviderRef:
        provider = _make_provider(app_db)
        ref = ProviderRef(provider_id=provider.id, enabled=True, sort_order=0)
        db.save(ref)
        return ref

    def test_update_ref_effect_audit_and_undo(self, db, app_db, emit_spy):
        ref = self._make_ref(db, app_db)
        result = registry.invoke(
            db,
            "provider.update_ref",
            {"ref_id": ref.id, "enabled": False, "sort_order": 5},
            _ctx(),
        )
        reloaded = db.get(ProviderRef, ref.id)
        assert reloaded.enabled is False and reloaded.sort_order == 5

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["enabled"] is True and audit.before["sort_order"] == 0
        assert "provider.ref_updated" in _emit_types(emit_spy)

        # both fields are always captured -> the inverse round-trips exactly
        reg = registry.get("provider.update_ref")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())
        restored = db.get(ProviderRef, ref.id)
        assert restored.enabled is True and restored.sort_order == 0

    def test_update_ref_unknown_raises(self, db, app_db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "provider.update_ref", {"ref_id": "nope", "enabled": False}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_delete_ref_effect_audit_and_restore(self, db, app_db, emit_spy):
        ref = self._make_ref(db, app_db)
        result = registry.invoke(
            db, "provider.delete_ref", {"ref_id": ref.id}, _ctx()
        )
        assert db.get(ProviderRef, ref.id) is None
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["ref"]["id"] == ref.id
        assert "provider.ref_deleted" in _emit_types(emit_spy)

        reg = registry.get("provider.delete_ref")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse[0] == "provider.restore_ref"
        registry.invoke(db, inverse[0], inverse[1], _ctx())
        assert db.get(ProviderRef, ref.id) is not None

    def test_delete_ref_param_validation(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "provider.delete_ref", {}, _ctx())


# ===========================================================================
# provider.set_api_key / provider.delete_api_key  (non-undoable, SECRET-safe)
# ===========================================================================


class TestApiKeyActions:
    def test_set_api_key_stores_without_leaking_secret(self, db, app_db, monkeypatch):
        stored: list[tuple] = []
        emitted: list[tuple] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.provider_keys.keychain_available", lambda: True
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.provider_keys.set_api_key",
            lambda pt, k: stored.append((pt, k)) or True,
        )
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda *a, **k: emitted.append((a, k)),
        )

        result = registry.invoke(
            db,
            "provider.set_api_key",
            {"provider_type": "openai", "api_key": "sk-secret-value"},
            _ctx(),
        )
        # effect: keychain write happened with the real key
        assert stored == [("openai", "sk-secret-value")]
        # (f) audit carries NO secret — only the provider_type
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.params == {"provider_type": "openai"}
        assert "sk-secret-value" not in str(audit.params)
        assert audit.after == {"provider_type": "openai", "has_api_key": True}
        # (e) emit fired
        assert any(k.get("type") == "provider.api_key_set" for _a, k in emitted)

    def test_set_api_key_is_not_undoable(self):
        reg = registry.get("provider.set_api_key")
        assert reg.undoable is False
        assert reg.invert is None

    def test_set_api_key_rejects_bad_format(self, db, app_db, monkeypatch):
        # openai keys must start with sk- — the validator raises -> HTTPException.
        monkeypatch.setattr(
            "fichero_server.api.routes.provider_keys.keychain_available", lambda: True
        )
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "provider.set_api_key",
                {"provider_type": "openai", "api_key": "not-a-key"},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_set_api_key_param_validation(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "provider.set_api_key", {"provider_type": "openai"}, _ctx()
            )

    def test_delete_api_key(self, db, app_db, monkeypatch):
        deleted: list[str] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.provider_keys.keychain_available", lambda: True
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.provider_keys.delete_api_key",
            lambda pt: deleted.append(pt) or True,
        )
        result = registry.invoke(
            db, "provider.delete_api_key", {"provider_type": "openai"}, _ctx()
        )
        assert deleted == ["openai"]
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.after == {"provider_type": "openai", "has_api_key": False}

    def test_delete_api_key_is_not_undoable(self):
        reg = registry.get("provider.delete_api_key")
        assert reg.undoable is False


# ===========================================================================
# Registry advertises the provider actions with the right undoable flags
# ===========================================================================


class TestProviderActionsRegistered:
    def test_all_covered_actions_registered(self):
        names = set(registry.names())
        for name in (
            "provider.create",
            "provider.update",
            "provider.delete",
            "provider.set_api_key",
            "provider.delete_api_key",
            "provider.remove_model",
            "provider.update_ref",
            "provider.delete_ref",
        ):
            assert name in names

    def test_undoable_flags(self):
        assert registry.get("provider.create").undoable is True
        assert registry.get("provider.update").undoable is True
        assert registry.get("provider.delete").undoable is True
        assert registry.get("provider.remove_model").undoable is True
        assert registry.get("provider.update_ref").undoable is True
        assert registry.get("provider.delete_ref").undoable is True
        # secrets are never undoable
        assert registry.get("provider.set_api_key").undoable is False
        assert registry.get("provider.delete_api_key").undoable is False
