"""Tests for the settings route validators (#1810 settings/ai-defaults gap).

`_validate_provider_updates` and `_validate_profile` guard the AI-defaults PUT
and model-profile writes. They were only exercised indirectly via the route;
these lock each branch directly: unknown providers are rejected, blank/omitted
provider fields are skipped, non-provider fields are ignored, and a profile
needs name/provider/model + a known provider.
"""

from __future__ import annotations

import fastapi
import pytest

from fichero_server.api.routes.system.settings import (
    AIDefaultsUpdate,
    _validate_profile,
    _validate_provider_updates,
)
from fichero_server.llm.model_profiles import ModelProfile


# ---------------------------------------------------------------------------
# _validate_provider_updates
# ---------------------------------------------------------------------------


def test_known_provider_passes() -> None:
    result = _validate_provider_updates(AIDefaultsUpdate(text_provider="openai"))
    assert result is None


def test_unknown_provider_is_422() -> None:
    with pytest.raises(fastapi.HTTPException) as exc:
        _validate_provider_updates(AIDefaultsUpdate(text_provider="not-a-provider"))
    assert exc.value.status_code == 422
    assert "text_provider" in exc.value.detail


def test_blank_provider_fields_are_skipped() -> None:
    assert _validate_provider_updates(AIDefaultsUpdate(text_provider=None)) is None
    assert _validate_provider_updates(AIDefaultsUpdate(vision_provider="")) is None
    assert _validate_provider_updates(AIDefaultsUpdate()) is None


def test_non_provider_fields_are_ignored() -> None:
    # *_model fields are not provider references — a bogus value must not 422.
    result = _validate_provider_updates(AIDefaultsUpdate(text_model="whatever-model"))
    assert result is None


def test_one_bad_provider_among_several_is_rejected() -> None:
    with pytest.raises(fastapi.HTTPException) as exc:
        _validate_provider_updates(
            AIDefaultsUpdate(text_provider="openai", vision_provider="bogus")
        )
    assert exc.value.status_code == 422
    assert "vision_provider" in exc.value.detail


# ---------------------------------------------------------------------------
# _validate_profile
# ---------------------------------------------------------------------------


def test_valid_profile_passes() -> None:
    result = _validate_profile(ModelProfile(name="Default", provider="openai", model="gpt-4"))
    assert result is None


@pytest.mark.parametrize(
    "profile",
    [
        ModelProfile(name="", provider="openai", model="gpt-4"),
        ModelProfile(name="n", provider="", model="gpt-4"),
        ModelProfile(name="n", provider="openai", model=""),
    ],
)
def test_missing_required_field_is_422(profile: ModelProfile) -> None:
    with pytest.raises(fastapi.HTTPException) as exc:
        _validate_profile(profile)
    assert exc.value.status_code == 422


def test_unknown_profile_provider_is_422() -> None:
    with pytest.raises(fastapi.HTTPException) as exc:
        _validate_profile(ModelProfile(name="n", provider="ghost", model="m"))
    assert exc.value.status_code == 422
    assert "provider" in exc.value.detail.lower()
