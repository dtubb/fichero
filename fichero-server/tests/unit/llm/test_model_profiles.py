"""Unit coverage for ``fichero_server.llm.model_profiles`` — the named model/provider
profile contracts and the privacy-enforcement helpers. Previously only exercised
indirectly (settings validators / builder config). Pure logic; the provider
catalog lookup is deterministic and needs no network.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.model_profiles import (
    ModelProfile,
    ModelProfileCreate,
    ModelProfileParams,
    ModelProfilePrivacy,
    ModelProfilePrivacyError,
    ModelProfileRole,
    enforce_model_profile_privacy,
    llm_config_from_profile,
    provider_is_local_or_builtin,
)


def _profile(**kw) -> ModelProfile:
    kw.setdefault("name", "p")
    kw.setdefault("provider", "openai")
    kw.setdefault("model", "gpt-4o")
    return ModelProfile(**kw)


# ===========================================================================
# requires_local_provider
# ===========================================================================


def test_requires_local_provider_standard_is_false():
    assert _profile().requires_local_provider is False


@pytest.mark.parametrize(
    "kw",
    [
        {"local_only": True},
        {"privacy": ModelProfilePrivacy.local_only},
        {"privacy": ModelProfilePrivacy.private},
    ],
)
def test_requires_local_provider_true_cases(kw):
    assert _profile(**kw).requires_local_provider is True


# ===========================================================================
# _strip_required_strings validator
# ===========================================================================


def test_required_strings_are_stripped_not_lowercased():
    p = ModelProfile(name="  My Profile ", provider=" OpenAI ", model=" gpt-4o ")
    assert p.name == "My Profile"
    assert p.provider == "OpenAI"  # stripped, case preserved
    assert p.model == "gpt-4o"


# ===========================================================================
# provider_is_local_or_builtin
# ===========================================================================


def test_provider_is_local_or_builtin():
    assert provider_is_local_or_builtin("ollama") is True
    assert provider_is_local_or_builtin("OpenAI") is False  # normalised internally
    assert provider_is_local_or_builtin("") is False
    assert provider_is_local_or_builtin("not-a-provider") is False


# ===========================================================================
# enforce_model_profile_privacy
# ===========================================================================


def test_enforce_raises_for_private_cloud_profile():
    profile = _profile(provider="openai", privacy=ModelProfilePrivacy.private)
    with pytest.raises(ModelProfilePrivacyError) as exc:
        enforce_model_profile_privacy(profile)
    assert exc.value.profile is profile
    assert "openai" in str(exc.value)


def test_enforce_raises_for_local_only_cloud_profile():
    with pytest.raises(ModelProfilePrivacyError):
        enforce_model_profile_privacy(_profile(provider="openai", local_only=True))


def test_enforce_allows_private_local_profile():
    enforce_model_profile_privacy(_profile(provider="ollama", privacy=ModelProfilePrivacy.private))


def test_enforce_allows_standard_cloud_profile():
    enforce_model_profile_privacy(_profile(provider="openai"))  # standard -> no constraint


# ===========================================================================
# ModelProfileCreate.to_profile
# ===========================================================================


def test_to_profile_generates_id_and_defaults():
    profile = ModelProfileCreate(name="c", provider="openai", model="m").to_profile()
    assert len(profile.id) == 32  # generated uuid hex
    assert profile.role is ModelProfileRole.text
    assert profile.privacy is ModelProfilePrivacy.standard


def test_to_profile_respects_explicit_id():
    profile = ModelProfileCreate(id="fixed-id", name="c", provider="p", model="m").to_profile()
    assert profile.id == "fixed-id"


# ===========================================================================
# llm_config_from_profile
# ===========================================================================


def test_llm_config_uses_profile_params():
    profile = _profile(
        provider="ollama", model="llama",
        params=ModelProfileParams(temperature=0.2, max_tokens=100, timeout=15,
                                  reasoning_effort="high"),
        api_base="http://localhost:11434",
        extra={"foo": "bar"},
    )
    config = llm_config_from_profile(profile)
    assert config.provider == "ollama"
    assert config.model == "llama"
    assert config.temperature == 0.2
    assert config.max_tokens == 100
    assert config.timeout == 15
    assert config.reasoning_effort == "high"
    assert config.api_base == "http://localhost:11434"
    assert config.extra["foo"] == "bar"


def test_llm_config_falls_back_to_base_when_params_absent():
    from fichero_server.llm import LLMConfig

    base = LLMConfig(provider="x", model="y", temperature=0.9, max_tokens=999,
                     api_key="secret", extra={"base_key": 1})
    profile = _profile(provider="ollama", model="llama")  # params all None
    config = llm_config_from_profile(profile, base_config=base)
    # Profile identity wins, but unspecified params inherit the base values.
    assert config.provider == "ollama"
    assert config.temperature == 0.9
    assert config.max_tokens == 999
    assert config.api_key == "secret"       # carried from base
    assert config.extra["base_key"] == 1     # base extra merged in
