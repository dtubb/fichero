"""#5368: a chat with no model named uses the app's text default (on-device by factory default) and
never quietly falls back to a cloud model.

Why it matters: the old resolver looked for providers in the LIBRARY database, where they never
are, then fell back to openai/gpt-4o-mini, so every chat without an explicit model sent the
person's question and their pages' excerpts to OpenAI. A cloud call is a choice a person makes;
if this goes red, pages are leaving the Mac without one. Do not loosen it to make it pass.
"""
from __future__ import annotations

import pytest

from fichero_server.api.routes.system import chat


@pytest.fixture
def captured(monkeypatch):
    seen = []
    monkeypatch.setattr(chat, "get_langchain_model", lambda config: seen.append(config) or object())
    return seen


def test_no_model_named_uses_the_apps_text_default_not_openai(db, captured, monkeypatch):
    class _AppDB:
        def get_ai_defaults(self):
            return {"default_text_provider": "apple", "default_text_model": "apple-intelligence"}

    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: _AppDB())
    chat._get_langchain_llm(db)
    assert (captured[-1].provider, captured[-1].model) == ("apple", "apple-intelligence")


def test_an_empty_default_still_stays_on_device(db, captured, monkeypatch):
    class _AppDB:
        def get_ai_defaults(self):
            return {}

    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: _AppDB())
    chat._get_langchain_llm(db)
    assert captured[-1].provider == "apple" and "gpt" not in captured[-1].model


def test_a_named_model_is_used_as_named(db, captured):
    chat._get_langchain_llm(db, provider="anthropic", model="claude-x")
    assert (captured[-1].provider, captured[-1].model) == ("anthropic", "claude-x")
