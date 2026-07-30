"""Tests for multilingual routes.

Multilingual routes provide language detection, transliteration, and
cross-language entity search. Routes live at /api/multilingual/...
(router prefix="/multilingual" mounted at "/api"). Detection and
transliteration functions are mocked to avoid needing real NLP models.
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_detection_result(language: str = "en", confidence: float = 0.9) -> MagicMock:
    result = MagicMock()
    result.language = language
    result.confidence = confidence
    result.is_reliable = True
    return result


# ---------------------------------------------------------------------------
# POST /api/multilingual/detect
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_detects_english(self, client):
        detection = _make_detection_result("en", 0.95)
        with patch("fichero_server.api.routes.ai.multilingual.detect_language", return_value=detection):
            r = client.post("/api/multilingual/detect", json={"text": "Hello world"})
        assert r.status_code == 200
        data = r.json()
        assert data["language"] == "en"
        assert data["language_name"] == "English"
        assert data["confidence"] == 0.95
        assert data["is_reliable"] is True

    def test_detects_french(self, client):
        detection = _make_detection_result("fr", 0.88)
        with patch("fichero_server.api.routes.ai.multilingual.detect_language", return_value=detection):
            r = client.post("/api/multilingual/detect", json={"text": "Bonjour le monde"})
        assert r.status_code == 200
        data = r.json()
        assert data["language"] == "fr"
        assert data["language_name"] == "French"

    def test_unknown_language_code(self, client):
        detection = _make_detection_result("xx", 0.5)
        with patch("fichero_server.api.routes.ai.multilingual.detect_language", return_value=detection):
            r = client.post("/api/multilingual/detect", json={"text": "????"})
        assert r.status_code == 200
        assert r.json()["language_name"] == "Unknown"


# ---------------------------------------------------------------------------
# POST /api/multilingual/transliterate
# ---------------------------------------------------------------------------


class TestTransliterate:
    def test_returns_variants(self, client):
        with patch(
            "fichero_server.api.routes.ai.multilingual.get_transliteration_variants",
            return_value=["Moskva", "Moskwa"],
        ):
            r = client.post("/api/multilingual/transliterate", json={
                "text": "Москва",
                "language": "ru",
            })
        assert r.status_code == 200
        data = r.json()
        assert data["original"] == "Москва"
        assert data["language"] == "ru"
        assert "Moskva" in data["variants"]

    def test_empty_variants(self, client):
        with patch(
            "fichero_server.api.routes.ai.multilingual.get_transliteration_variants",
            return_value=[],
        ):
            r = client.post("/api/multilingual/transliterate", json={
                "text": "test",
                "language": "en",
            })
        assert r.status_code == 200
        assert r.json()["variants"] == []
