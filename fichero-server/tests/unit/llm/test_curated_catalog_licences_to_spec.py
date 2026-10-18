"""models.curated-catalog-clean-licences (#4611), ruling 2026-10-17: licence decides what ships.

Spec (docs/contributor_manual/specs/ai/ai-settings.md): a model Fichero cannot include by licence is
dropped from the catalogue; every catalogue entry declares its licence; weights are never bundled.
"""

from __future__ import annotations

from fichero_server.llm.local_model_facts import LocalInferenceCapabilities, check_local_model_hardware
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS


def test_nanonets_is_dropped_from_what_ships():
    """Its card declares no licence and its base is research-only: "Not for release in any case"."""
    assert "Nanonets-OCR" not in MANAGED_MLX_MODELS


def test_every_catalogue_entry_declares_its_licence():
    for model_id, spec in MANAGED_MLX_MODELS.items():
        assert spec.licence and spec.licence != "not checked", model_id


def test_chandra_is_kept_with_its_openrail_licence_and_a_memory_floor():
    """Kept (openrail, modified); machine-dependent, so it carries the 16 GB floor."""
    spec = MANAGED_MLX_MODELS["Chandra-OCR"]
    assert spec.licence == "OpenRAIL-M (modified)"
    assert spec.min_memory_bytes == 16 * 1024**3


def _mac(memory_gb: int) -> LocalInferenceCapabilities:
    return LocalInferenceCapabilities(
        system="Darwin", machine="arm64", is_apple_silicon=True,
        physical_memory_bytes=memory_gb * 1024**3,
    )


def test_chandra_is_not_offered_on_an_8_gb_mac_and_says_why():
    """Machine-dependent: offered only where the memory floor is met; below it the reason is shown (#5519)."""
    spec = MANAGED_MLX_MODELS["Chandra-OCR"]
    supported, reason = check_local_model_hardware(
        display_name=spec.display_name, min_memory_bytes=spec.min_memory_bytes, capabilities=_mac(8))
    assert supported is False
    assert "16 GB unified memory" in reason and "8 GB" in reason


def test_chandra_is_offered_on_a_16_gb_mac():
    spec = MANAGED_MLX_MODELS["Chandra-OCR"]
    supported, reason = check_local_model_hardware(
        display_name=spec.display_name, min_memory_bytes=spec.min_memory_bytes, capabilities=_mac(16))
    assert supported is True and reason is None
