"""YOLO's layout model says its size before it is downloaded, and the models catalog lists it (#5654 item 10,
`runtime.yolo.none-yet`).

WHY: on the demo (2026-10-10) `GET /api/local-models?model_type=yolo` listed yolo-doclaynet-11n with
expected_size_mb 0 (its file is about 6 MB), and the models catalog (`GET /api/local-inference/catalog`, the MCP
tool `fichero_models_catalog`) did not list YOLO at all, though it lists Kraken's readers.
"""
from __future__ import annotations

from unittest.mock import patch


def test_a_yolo_model_not_downloaded_says_its_size(client):
    with patch("fichero_server.llm.yolo_runtime.model_path", return_value=None):
        [row] = client.get("/api/local-models?model_type=yolo").json()["models"]
    assert row["model_id"] == "yolo-doclaynet-11n" and not row["is_downloaded"]
    assert row["expected_size_mb"] == 6


def test_the_models_catalog_lists_yolo_as_it_lists_kraken_readers(client, tmp_path):
    with patch("fichero_server.llm.yolo_runtime.model_path", return_value=None):
        items = client.get("/api/local-inference/catalog").json()["items"]
    [yolo] = [i for i in items if i["model_id"] == "yolo-doclaynet-11n"]
    assert yolo["provider_type"] == "yolo"
    assert yolo["capabilities"] == ["regions"]
    assert yolo["installed"] is False and yolo["download_size_bytes"] == 5_558_611
    assert yolo["disk_usage_bytes"] == 0

    weights = tmp_path / "yolov11n-doclaynet.pt"
    weights.write_bytes(b"x" * 10)
    with patch("fichero_server.llm.yolo_runtime.model_path", return_value=weights):
        items = client.get("/api/local-inference/catalog").json()["items"]
    [yolo] = [i for i in items if i["model_id"] == "yolo-doclaynet-11n"]
    assert yolo["installed"] is True and yolo["disk_usage_bytes"] == 10


def test_a_downloaded_yolo_model_is_deleted_from_the_catalog(client, tmp_path):
    """Listed in the catalog, it is removed through the catalog's delete, as a Kraken reader is."""
    weights = tmp_path / "yolov11n-doclaynet.pt"
    weights.write_bytes(b"x" * 10)
    with patch("fichero_server.llm.yolo_runtime.model_path", return_value=weights):
        r = client.delete("/api/local-inference/models/yolo-doclaynet-11n")
    assert r.status_code == 200, r.text
    assert r.json()["freed_bytes"] == 10 and not weights.exists()
