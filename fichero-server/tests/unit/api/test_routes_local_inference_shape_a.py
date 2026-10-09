"""The local catalogue lists every local runtime (Shape A); a download goes through the one path,
POST /api/local-models/download (#5620), tested in tests/unit/llm/test_one_download_path_5620.py.

/api/local-inference/catalog lists MLX + spaCy + Kraken + Whisper. These tests pin
the catalogue and the honest delete behaviour without touching a real runtime.
"""

from __future__ import annotations


class TestUnifiedCatalog:
    def test_catalog_lists_all_four_runtimes(self, client):
        r = client.get("/api/local-inference/catalog")
        assert r.status_code == 200
        providers = {item["provider_type"] for item in r.json()["items"]}
        # MLX is "omlx"; the three folded-in runtimes carry their own types.
        assert {"spacy", "kraken", "whisper"} <= providers

    def test_kraken_lists_segmenter_and_recognition_models(self, client):
        r = client.get("/api/local-inference/catalog")
        kraken = {
            i["model_id"] for i in r.json()["items"] if i["provider_type"] == "kraken"
        }
        # The segmenter plus the known-good HTR models — the picker is populated.
        assert "kraken-blla" in kraken
        assert "kraken-mccatmus" in kraken
        assert "kraken-catmus-medieval" in kraken


class TestDeleteDispatch:
    def test_deleting_a_bundled_spacy_model_refuses(self, client):
        # No patch: a bundled spaCy pipeline ships in the app (runtime.spacy.pipelines-download-as-data), so its
        # delete honestly refuses, which the route surfaces as a 409 rather than a fake success.
        r = client.delete("/api/local-inference/models/es_core_news_sm")
        assert r.status_code == 409
        assert "bundled with the app" in r.json()["detail"]
