"""Regression test for #937 — save_model is idempotent on
(provider_id, model_id).

Pre-fix: calling save_model twice with the same provider_id +
model_id but different row ids would insert two rows. Settings →
Providers' '+ Add Model' button was hitting this — Daniel
demoed the bug by re-adding Apple Vision and getting duplicate
entries.

Post-fix: save_model detects the conflict and updates the
existing row instead of inserting a duplicate.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from fichero_server.db.app import AppDatabase
from fichero_server.models import Provider, Model
from fichero_server.llm.providers import ProviderType


@pytest.fixture
def app_db(tmp_path: Path) -> AppDatabase:
    db = AppDatabase(tmp_path / "test_app.duckdb")
    return db


@pytest.fixture
def apple_provider(app_db: AppDatabase) -> Provider:
    p = Provider(
        provider_type=ProviderType.apple,
        name="Apple Intelligence",
    )
    return app_db.save_provider(p)


class TestSaveModelDedup:
    def test_re_adding_same_model_id_updates_existing_row(
        self, app_db, apple_provider,
    ):
        """The #937 fix: a second save_model with the same
        (provider_id, model_id) but a fresh row id should redirect
        to the existing row instead of inserting a duplicate.
        """
        first = Model(
            id=str(uuid.uuid4()),
            provider_id=apple_provider.id,
            name="Apple Vision (OCR)",
            model_id="apple-vision",
            capabilities=["vision"],
        )
        app_db.save_model(first)

        # User clicks '+ Add Model' again with a fresh row id but
        # same model_id — pre-fix this inserted a second row.
        duplicate = Model(
            id=str(uuid.uuid4()),  # different id
            provider_id=apple_provider.id,
            name="Apple Vision (OCR)",  # same name
            model_id="apple-vision",     # same model_id
            capabilities=["vision"],
        )
        app_db.save_model(duplicate)

        rows = app_db.list_models(apple_provider.id)
        ids = [m.model_id for m in rows]
        # Only ONE row with model_id="apple-vision" should exist
        assert ids.count("apple-vision") == 1, (
            f"Expected exactly one apple-vision row, got {ids}"
        )

    def test_re_save_with_new_capabilities_updates_existing(
        self, app_db, apple_provider,
    ):
        """Idempotency should NOT silently discard updates. When
        re-saving with the same (provider_id, model_id) but new
        capabilities, the existing row should be updated with the
        new caps.
        """
        first = Model(
            id=str(uuid.uuid4()),
            provider_id=apple_provider.id,
            name="Apple Vision",
            model_id="apple-vision",
            capabilities=["vision"],
        )
        first_saved = app_db.save_model(first)

        updated = Model(
            id=str(uuid.uuid4()),  # different id
            provider_id=apple_provider.id,
            name="Apple Vision (OCR)",  # updated name
            model_id="apple-vision",
            capabilities=["vision", "ocr"],  # added capability
        )
        app_db.save_model(updated)

        rows = app_db.list_models(apple_provider.id)
        assert len(rows) == 1
        row = rows[0]
        # The existing row's id should win (so other tables FK'd
        # to it stay valid), but the name + capabilities should
        # reflect the second save.
        assert row.id == first_saved.id
        assert row.name == "Apple Vision (OCR)"
        assert set(row.capabilities) == {"vision", "ocr"}

    def test_empty_caps_on_resave_preserves_existing_caps(
        self, app_db, apple_provider,
    ):
        """#939 belt-and-braces: when the seeded row has caps and a
        re-save (e.g. from the +Add Model button) comes through with
        capabilities=[], the existing caps win. Prevents the
        inspector's capability badges from disappearing after the
        user deletes a built-in row and adds it back.

        The providers route still does the canonical-caps lookup so
        this rarely fires in practice — but it's the safety net for
        any other caller that forgets to set capabilities.
        """
        seeded = Model(
            id=str(uuid.uuid4()),
            provider_id=apple_provider.id,
            name="Apple Vision (OCR)",
            model_id="apple-vision",
            capabilities=["vision"],
        )
        app_db.save_model(seeded)

        # User re-add via a UI that didn't set capabilities
        readded = Model(
            id=str(uuid.uuid4()),
            provider_id=apple_provider.id,
            name="Apple Vision (OCR)",
            model_id="apple-vision",
            capabilities=[],  # the bug case
        )
        app_db.save_model(readded)

        rows = app_db.list_models(apple_provider.id)
        assert len(rows) == 1
        # Caps preserved from the original save
        assert rows[0].capabilities == ["vision"]

    def test_different_model_ids_on_same_provider_coexist(
        self, app_db, apple_provider,
    ):
        """The dedup is on (provider_id, model_id) NOT just
        provider_id. Two distinct model_ids on the same provider
        should both insert as separate rows.
        """
        a = Model(
            id=str(uuid.uuid4()),
            provider_id=apple_provider.id,
            name="Apple Intelligence",
            model_id="apple-intelligence",
            capabilities=["text"],
        )
        b = Model(
            id=str(uuid.uuid4()),
            provider_id=apple_provider.id,
            name="Apple Vision",
            model_id="apple-vision",
            capabilities=["vision"],
        )
        app_db.save_model(a)
        app_db.save_model(b)

        rows = app_db.list_models(apple_provider.id)
        model_ids = sorted(m.model_id for m in rows)
        assert model_ids == ["apple-intelligence", "apple-vision"]
