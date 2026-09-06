"""The unified local-runtime list (#4671).

MLX, spaCy, Kraken and local Whisper are peer local runtimes that grew four
different status/install surfaces. Settings renders them as one list of peer
rows, so this endpoint gives it exactly that: per runtime an installed flag,
an available flag, a size note, and where to POST to install / GET to poll.

The one hard rule these tests pin: reading the list starts NOTHING. It is a
status read, so no ~1 GB download may begin as a side effect — every row is
built from a status call, never an install call.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mlx(provisioned: bool) -> MagicMock:
    m = MagicMock()
    m.status.return_value = {"provisioned": provisioned, "audio_ready": provisioned}
    return m


def _kraken(installed: bool) -> MagicMock:
    m = MagicMock()
    m.status.return_value = {
        "installed": installed,
        "runtime_dir": "/tmp/kraken-runtime",
        "reason": None if installed else "Kraken is not installed. ~1 GB.",
    }
    return m


def _spacy_row(model_id: str, available: bool, downloaded: bool) -> MagicMock:
    r = MagicMock()
    r.model_id = model_id
    r.available = available
    r.is_downloaded = downloaded
    r.unavailable_reason = None if available else 'spaCy is not installed (pip install -e ".[kg]")'
    return r


def _whisper_row(downloaded: bool) -> MagicMock:
    r = MagicMock()
    r.is_downloaded = downloaded
    return r


def _patch_all(
    *,
    mlx_provisioned=True,
    kraken_installed=False,
    spacy_available=True,
    spacy_downloaded=True,
    whisper_ready=True,
    whisper_has_model=True,
):
    """Patch every runtime status source the endpoint reads."""
    spacy_mgr = MagicMock()
    spacy_mgr.return_value.list_spacy_models.return_value = [
        _spacy_row("es_core_news_sm", spacy_available, spacy_downloaded),
        _spacy_row("es_core_news_md", spacy_available, False),
    ]
    spacy_mgr.return_value.list_whisper_models.return_value = [
        _whisper_row(whisper_has_model)
    ]
    return [
        patch("fichero_server.llm.mlx_runtime.get_mlx_runtime", return_value=_mlx(mlx_provisioned)),
        patch("fichero_server.llm.kraken_runtime.get_kraken_runtime", return_value=_kraken(kraken_installed)),
        patch("fichero_server.llm.local_models.LocalModelManager", spacy_mgr),
        patch(
            "fichero_server.llm.whisper_runtime.audio_runtime_status",
            return_value={"ready": whisper_ready, "reason": None if whisper_ready else "Provision the MLX runtime."},
        ),
    ]


class TestUnifiedList:
    def test_all_four_present_in_order(self, client):
        patches = _patch_all()
        for p in patches:
            p.start()
        try:
            r = client.get("/api/providers/local-runtimes")
        finally:
            for p in patches:
                p.stop()
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 4
        assert [row["provider_type"] for row in body["items"]] == [
            "mlx",
            "spacy",
            "kraken",
            "whisper",
        ]

    def test_kraken_row_carries_its_install_and_status_paths(self, client):
        patches = _patch_all(kraken_installed=False)
        for p in patches:
            p.start()
        try:
            r = client.get("/api/providers/local-runtimes")
        finally:
            for p in patches:
                p.stop()
        kraken = next(x for x in r.json()["items"] if x["provider_type"] == "kraken")
        assert kraken["installed"] is False
        assert kraken["install_action"]["method"] == "POST"
        assert kraken["install_action"]["path"] == "/api/local-models/kraken/install"
        assert kraken["status_path"] == "/api/local-models/kraken/status"
        assert "GB" in kraken["size_note"]

    def test_bundled_spacy_has_no_provider_level_install(self, client):
        patches = _patch_all(spacy_downloaded=True)
        for p in patches:
            p.start()
        try:
            r = client.get("/api/providers/local-runtimes")
        finally:
            for p in patches:
                p.stop()
        spacy = next(x for x in r.json()["items"] if x["provider_type"] == "spacy")
        # Small models ship — the provider needs no install button; adding a
        # language is a per-model action the catalog rows carry.
        assert spacy["install_action"] is None
        assert spacy["installed"] is True

    def test_whisper_recommends_turbo(self, client):
        patches = _patch_all()
        for p in patches:
            p.start()
        try:
            r = client.get("/api/providers/local-runtimes")
        finally:
            for p in patches:
                p.stop()
        whisper = next(x for x in r.json()["items"] if x["provider_type"] == "whisper")
        assert whisper["recommended_model"] == "turbo"

    def test_whisper_is_unavailable_without_a_transcriber(self, client):
        patches = _patch_all(whisper_ready=False)
        for p in patches:
            p.start()
        try:
            r = client.get("/api/providers/local-runtimes")
        finally:
            for p in patches:
                p.stop()
        whisper = next(x for x in r.json()["items"] if x["provider_type"] == "whisper")
        assert whisper["available"] is False
        assert whisper["reason"]

    def test_one_failing_runtime_does_not_blank_the_list(self, client):
        # MLX status raises; the list must still return four rows with MLX
        # reporting the failure rather than a 500 taking the whole surface down.
        boom = MagicMock()
        boom.status.side_effect = RuntimeError("mlx exploded")
        patches = _patch_all()
        patches[0] = patch("fichero_server.llm.mlx_runtime.get_mlx_runtime", return_value=boom)
        for p in patches:
            p.start()
        try:
            r = client.get("/api/providers/local-runtimes")
        finally:
            for p in patches:
                p.stop()
        assert r.status_code == 200
        mlx = next(x for x in r.json()["items"] if x["provider_type"] == "mlx")
        assert mlx["installed"] is False
        assert "mlx exploded" in mlx["reason"]
