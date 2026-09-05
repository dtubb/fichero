"""The Apple built-in rows must say the same thing in every place (2026-09-04).

Fichero states what an Apple model can do in three places: the catalog rows
served to the +Add Model browser (`APPLE_BUILTIN_MODELS`), the canonical
capability map a SAVED row is written with (`_CANONICAL_APPLE_CAPABILITIES`),
and the seed that creates those rows on first launch (`api/main.py`). They
drifted: `apple-intelligence` was served with ``supports_vision=True`` while
its canonical capabilities are ``["text"]``.

That drift is not cosmetic. Apple's Foundation Models take no image input —
fm-bridge opens a `SystemLanguageModel` session and there is no image path in
it — so the vision claim was false, and a false vision claim is precisely how
a vision step ends up pointed at a text-only on-device model. Daniel,
2026-09-04: "I think a lot of it is routing to Apple Intelligence."

The general shape is worth naming, because it will recur: **a capability claim
is enforced by nobody.** Nothing checks that a row advertising vision can
actually see — not the catalog, not the provider, and not Apple. The same hole
sits in `FoundationModels.LanguageModelCapabilities` (`.vision`,
`.guidedGeneration`, `.reasoning`, `.toolCalling`), which any third-party
`LanguageModel` declares about ITSELF; if the macOS-27 extensibility seam is
ever taken up, whatever declares those capabilities needs a test of this shape
too. A claim nothing verifies is a claim that drifts.

One fixture per rule, so the rule FIRES when someone adds the next Apple row.
"""

from __future__ import annotations

from fichero_server.api.routes.ai.provider_models import APPLE_BUILTIN_MODELS
from fichero_server.api.routes.ai.providers import _CANONICAL_APPLE_CAPABILITIES


def test_the_population_is_real():
    """Guard the guard: every test below iterates the rows."""
    assert len(APPLE_BUILTIN_MODELS) >= 3
    assert len(_CANONICAL_APPLE_CAPABILITIES) >= 3


def test_every_served_row_has_canonical_capabilities():
    """A row the browser offers must be a row a save can describe."""
    for model in APPLE_BUILTIN_MODELS:
        assert model.model_id in _CANONICAL_APPLE_CAPABILITIES, (
            f"{model.model_id} is offered but has no canonical capabilities — "
            "a user who adds it gets a row with empty badges"
        )


def test_every_canonical_id_is_actually_offered():
    """The other direction: no capability entry for a row nobody can add."""
    served = {model.model_id for model in APPLE_BUILTIN_MODELS}
    assert set(_CANONICAL_APPLE_CAPABILITIES) == served


def test_the_vision_claim_matches_the_capability_map():
    """The drift itself, pinned."""
    for model in APPLE_BUILTIN_MODELS:
        capabilities = _CANONICAL_APPLE_CAPABILITIES[model.model_id]
        assert model.supports_vision == ("vision" in capabilities), (
            f"{model.model_id} is served with supports_vision="
            f"{model.supports_vision} but its capabilities are {capabilities}"
        )


def test_foundation_models_is_text_only():
    """Named explicitly, because this is the row that was wrong.

    If Apple ever ships image input for Foundation Models, this test is the
    place that has to be argued with — and fm-bridge has to grow an image
    path before the flag may flip.
    """
    row = next(m for m in APPLE_BUILTIN_MODELS if m.model_id == "apple-intelligence")
    assert row.supports_vision is False
    assert _CANONICAL_APPLE_CAPABILITIES["apple-intelligence"] == ["text"]


def test_apple_vision_remains_the_vision_row():
    """The fix must not swing the other way and disarm OCR."""
    row = next(m for m in APPLE_BUILTIN_MODELS if m.model_id == "apple-vision")
    assert row.supports_vision is True


def test_every_apple_row_is_free_and_local():
    """The whole point of the on-device stack."""
    for model in APPLE_BUILTIN_MODELS:
        assert model.is_local is True
        assert model.input_cost_per_million == 0
        assert model.output_cost_per_million == 0
