"""Regression tests for #933 — Reset AI Defaults must repopulate with
Apple Intelligence baseline (not leave fields blank) AND must NOT
touch the providers / models tables.

Pre-fix: reset_ai_defaults() just deleted all default_* keys. The
user was left with empty fields; the next Catalogue run failed with
the same first-run blocker that #932 fixed for fresh launches,
regressing on every Reset click.

Post-fix: reset_ai_defaults() deletes the bag AND immediately
re-seeds Apple Intelligence factory defaults across the AI tier
keys the resolver consumes. Providers and Models tables untouched.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from fichero_server.db.app import AppDatabase
from fichero_server.api.main import _ensure_default_ai_defaults, _repair_known_bad_ai_defaults
from fichero_server.models import Provider, Model
from fichero_server.llm.providers import ProviderType


@pytest.fixture
def app_db(tmp_path: Path) -> AppDatabase:
    return AppDatabase(tmp_path / "reset_test.duckdb")


class TestResetAIDefaults:
    def test_reset_repopulates_with_apple_baseline(self, app_db):
        # Simulate prior state — user has custom defaults
        app_db.set_setting("default_text_provider", "openai")
        app_db.set_setting("default_text_model", "gpt-4o")
        app_db.set_setting("default_small_provider", "anthropic")
        app_db.set_setting("default_small_model", "claude-haiku")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        assert defaults["default_text_provider"] == "apple"
        assert defaults["default_text_model"] == "apple-intelligence"
        assert defaults["default_small_provider"] == "apple"
        assert defaults["default_small_model"] == "apple-intelligence"
        assert defaults["default_medium_provider"] == "apple"
        assert defaults["default_medium_model"] == "apple-intelligence"
        assert defaults["default_vision_provider"] == "apple"
        assert defaults["default_vision_model"] == "apple-vision"
        for tier in ("small", "medium", "large"):
            assert defaults[f"default_vision_{tier}_provider"] == "apple"
            assert defaults[f"default_vision_{tier}_model"] == "apple-vision"
        assert defaults["default_audio_provider"] == "apple"
        assert defaults["default_audio_model"] == "apple-speech"

    def test_reset_populates_all_tiers_text_small_large(self, app_db):
        """The LLM tiers the resolver actually consumes today (text,
        small, medium, large) need defaults so workflow placeholders
        resolve. Every tier seeds ON-DEVICE so a keyless fresh install
        runs every default workflow (#4325).
        """
        app_db.reset_ai_defaults()
        defaults = app_db.get_ai_defaults()
        for tier in ("text", "small", "medium", "large"):
            assert defaults.get(f"default_{tier}_provider") == "apple", (
                f"Tier {tier} should be Apple Intelligence after reset"
            )
            assert defaults.get(f"default_{tier}_model") == "apple-intelligence"

    def test_reset_populates_all_vision_tiers(self, app_db):
        """Vision aliases need settings defaults so #2200 preflight can resolve them."""
        app_db.reset_ai_defaults()
        defaults = app_db.get_ai_defaults()
        for tier in ("small", "medium", "large"):
            assert defaults.get(f"default_vision_{tier}_provider") == "apple"
            assert defaults.get(f"default_vision_{tier}_model") == "apple-vision"

    def test_bootstrap_populates_all_vision_tiers_without_overwriting(self, app_db):
        app_db.set_setting("default_vision_large_provider", "openai")
        app_db.set_setting("default_vision_large_model", "gpt-4o")

        _ensure_default_ai_defaults(app_db, "ignored-provider-id")

        defaults = app_db.get_ai_defaults()
        assert defaults["default_vision_small_provider"] == "apple"
        assert defaults["default_vision_small_model"] == "apple-vision"
        assert defaults["default_vision_medium_provider"] == "apple"
        assert defaults["default_vision_medium_model"] == "apple-vision"
        assert defaults["default_vision_large_provider"] == "openai"
        assert defaults["default_vision_large_model"] == "gpt-4o"

    def test_repair_known_bad_large_default_rewrites_openrouter_free(self, app_db):
        app_db.set_setting("default_large_provider", "openrouter")
        app_db.set_setting("default_large_model", "openrouter/free")

        _repair_known_bad_ai_defaults(app_db)

        defaults = app_db.get_ai_defaults()
        assert defaults["default_large_provider"] == "apple"
        assert defaults["default_large_model"] == "apple-intelligence"

    def test_repair_rewrites_keyless_openrouter_medium_seed(self, app_db, monkeypatch):
        """#4325: the legacy seeded $medium (openrouter/openai/gpt-4o-mini)
        fails mid-run on a keyless install — repaired to on-device when no
        OpenRouter credential exists."""
        app_db.set_setting("default_medium_provider", "openrouter")
        app_db.set_setting("default_medium_model", "openai/gpt-4o-mini")
        monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: None)

        _repair_known_bad_ai_defaults(app_db)

        defaults = app_db.get_ai_defaults()
        assert defaults["default_medium_provider"] == "apple"
        assert defaults["default_medium_model"] == "apple-intelligence"

    def test_repair_keeps_openrouter_medium_when_key_present(self, app_db, monkeypatch):
        app_db.set_setting("default_medium_provider", "openrouter")
        app_db.set_setting("default_medium_model", "openai/gpt-4o-mini")
        monkeypatch.setattr(
            "fichero_server.llm.get_api_key", lambda provider: "sk-or-test"
        )

        _repair_known_bad_ai_defaults(app_db)

        defaults = app_db.get_ai_defaults()
        assert defaults["default_medium_provider"] == "openrouter"
        assert defaults["default_medium_model"] == "openai/gpt-4o-mini"

    def test_repair_never_touches_a_user_chosen_medium(self, app_db, monkeypatch):
        """Only the exact legacy seeded pairing is repaired."""
        app_db.set_setting("default_medium_provider", "openrouter")
        app_db.set_setting("default_medium_model", "anthropic/claude-sonnet-4")
        monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: None)

        _repair_known_bad_ai_defaults(app_db)

        defaults = app_db.get_ai_defaults()
        assert defaults["default_medium_model"] == "anthropic/claude-sonnet-4"

    def test_factory_table_is_fully_on_device(self):
        """#4325 acceptance: the single tier-default table must contain no
        provider that needs an API key, so a keyless fresh install passes
        preflight for every tier alias."""
        from fichero_server.db.app import FACTORY_AI_DEFAULTS
        from fichero_server.llm.providers import get_provider_info

        providers = {
            value
            for key, value in FACTORY_AI_DEFAULTS.items()
            if key.endswith("_provider")
        }
        for provider in providers:
            info = get_provider_info(provider)
            assert info is not None and (info.is_local or info.is_builtin), (
                f"factory default provider {provider!r} requires configuration"
            )

    def test_bootstrap_and_reset_share_the_factory_table(self, app_db):
        """The bootstrap seed and reset must write identical values (the
        triplicated-table drift this test now prevents, #4325)."""
        from fichero_server.db.app import FACTORY_AI_DEFAULTS

        _ensure_default_ai_defaults(app_db, "ignored-provider-id")
        seeded = {k: app_db.get_setting(k) for k in FACTORY_AI_DEFAULTS}

        app_db.reset_ai_defaults()
        reset = {k: app_db.get_setting(k) for k in FACTORY_AI_DEFAULTS}

        assert seeded == reset == FACTORY_AI_DEFAULTS

    def test_repair_rewrites_text_only_vision_tiers(self, app_db):
        # Legacy seeds (pre vision-tier split) pointed vision tiers at
        # apple-intelligence — TEXT-ONLY by design, so every default vision
        # node failed "not marked as vision-capable" (Daniel, 2026-07-27).
        for tier in ("vision", "vision_small", "vision_medium", "vision_large"):
            app_db.set_setting(f"default_{tier}_provider", "apple")
            app_db.set_setting(f"default_{tier}_model", "apple-intelligence")
        # A non-apple vision choice is a real user decision — untouched.
        app_db.set_setting("default_vision_medium_provider", "openrouter")
        app_db.set_setting("default_vision_medium_model", "openai/gpt-4o")

        _repair_known_bad_ai_defaults(app_db)

        defaults = app_db.get_ai_defaults()
        for tier in ("vision", "vision_small", "vision_large"):
            assert defaults[f"default_{tier}_model"] == "apple-vision", tier
        assert defaults["default_vision_medium_model"] == "openai/gpt-4o"

    def test_reset_does_not_touch_providers(self, app_db):
        """The #933 scope guarantee: Reset Defaults must leave the
        Providers / Models tables alone. A user with a configured
        OpenAI provider + API key shouldn't lose it on Reset.
        """
        # Seed a user-added provider
        custom = Provider(
            provider_type=ProviderType.openai,
            name="My OpenAI",
        )
        custom = app_db.save_provider(custom)
        # And a model attached to it
        custom_model = Model(
            id=str(uuid.uuid4()),
            provider_id=custom.id,
            name="gpt-4o",
            model_id="gpt-4o",
            capabilities=["text"],
        )
        app_db.save_model(custom_model)

        app_db.reset_ai_defaults()

        # Provider still exists
        providers = app_db.list_providers()
        provider_names = {p.name for p in providers}
        assert "My OpenAI" in provider_names

        # Model still exists
        models = app_db.list_models(custom.id)
        model_ids = {m.model_id for m in models}
        assert "gpt-4o" in model_ids

    def test_reset_clears_stale_per_field_overrides(self, app_db):
        """Reset is also delete-first: stale fields the user had
        configured (e.g. an older default_video_provider) should be
        gone, replaced with nothing (no factory default for video).
        """
        # User had video defaults at some point
        app_db.set_setting("default_video_provider", "some-old-provider")
        app_db.set_setting("default_video_model", "some-old-model")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        # Video isn't in the factory baseline → cleared, no value
        assert "default_video_provider" not in defaults
        assert "default_video_model" not in defaults

    def test_reset_clears_primary_language_override(self, app_db):
        app_db.set_setting("default_primary_language", "Spanish")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        assert "default_primary_language" not in defaults


# =============================================================================
# #3905 / #4502 — the vision tiers stay on-device, and the reason is measured
# =============================================================================


class TestTheVisionTiersStayOnDevice:
    """Every existing check compares the seeded settings TO the factory table.

    That is a consistency check, not a values check: flipping
    `FACTORY_AI_DEFAULTS` to a paid provider keeps all of them green while
    silently putting every fresh install on someone's bill. These pin the
    values, and record the measurement that justifies them so a future change
    has to argue with a number rather than an opinion.

    Measured 2026-08-03 on `dialogo_lengua_page_18`, one authorised run of the
    shipped Ensemble preset against openrouter/google/gemini-3-flash-preview
    (accent-blind CER, lower is better):

        free Apple Vision, whole page   0.3571
        free Apple Vision, ensemble tiles 0.4586
        paid ensemble t2 (best tier)    0.3971
        paid ensemble t4 (THE OUTPUT)   0.8814

    t4 is the pass whose text becomes the page. It is 2.47x worse than free
    on-device OCR of the same page, and 1.92x worse than free OCR of the very
    same tiles the paid model was given. Paying for that is paying to be wrong.
    """

    VISION_TIER_KEYS = (
        "default_vision_provider",
        "default_vision_small_provider",
        "default_vision_medium_provider",
        "default_vision_large_provider",
    )

    def test_every_vision_tier_defaults_to_apple(self):
        from fichero_server.db.app import FACTORY_AI_DEFAULTS

        for key in self.VISION_TIER_KEYS:
            assert FACTORY_AI_DEFAULTS[key] == "apple", (
                f"{key} is no longer on-device. A fresh install would send "
                "vision work to a paid provider that measured 0.8814 CER on "
                "the gold page against 0.3571 for free Apple Vision (#3905)"
            )

    def test_every_vision_tier_defaults_to_apple_vision_the_model(self):
        from fichero_server.db.app import FACTORY_AI_DEFAULTS

        for key in (k.replace("_provider", "_model") for k in self.VISION_TIER_KEYS):
            assert FACTORY_AI_DEFAULTS[key] == "apple-vision", (
                f"{key} is not apple-vision — a provider of 'apple' with some "
                "other model would satisfy the check above while still not "
                "being the tier that was measured"
            )

    def test_no_factory_default_names_a_paid_provider(self):
        """The whole table, not just vision. A keyless install must be able to
        run every default workflow (#4325), and any cloud name here breaks
        that as surely as it starts costing money."""
        from fichero_server.db.app import FACTORY_AI_DEFAULTS

        paid = {
            "openrouter", "openai", "anthropic", "google", "groq", "together",
            "deepseek", "mistral", "dashscope", "xai", "perplexity",
            "fireworks", "deepl",
        }
        offenders = {
            key: value
            for key, value in FACTORY_AI_DEFAULTS.items()
            if key.endswith("_provider") and value in paid
        }
        assert not offenders, (
            f"factory defaults name paid providers: {offenders}. A fresh "
            "install with no API keys must still run every default workflow"
        )

    def test_a_reset_puts_a_paid_vision_override_back_on_device(self, app_db):
        """The user-facing recovery path for exactly the state this was found
        in: a stored override had every vision tier on a paid model, so the
        'small' tier a user expects to be free was billing."""
        app_db.set_setting("default_vision_small_provider", "openrouter")
        app_db.set_setting("default_vision_small_model", "google/gemini-3-flash-preview")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        assert defaults["default_vision_small_provider"] == "apple"
        assert defaults["default_vision_small_model"] == "apple-vision"
