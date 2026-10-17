"""models.curated-catalog-clean-licences (#4611), ruling 2026-10-17: licence decides what ships.

Spec (docs/contributor_manual/specs/ai/ai-settings.md): a model Fichero cannot include by licence is
dropped from the catalogue; every catalogue entry declares its licence; weights are never bundled.
"""

from __future__ import annotations

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
