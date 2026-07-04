from __future__ import annotations

import base64
import ipaddress
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from fichero.remote_access_tls import (
    prepare_remote_access_tls,
    validate_tailnet_url,
    uvicorn_ssl_kwargs_from_env,
)


def test_prepare_remote_access_tls_creates_reusable_material(tmp_path: Path) -> None:
    material = prepare_remote_access_tls(
        "https://192.168.1.42:9443",
        storage_root=tmp_path,
    )

    certificate_path = Path(material.certificate_path)
    key_path = Path(material.key_path)

    assert material.bind_host == "0.0.0.0"
    assert certificate_path.exists()
    assert key_path.exists()

    certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("192.168.1.42")]

    expected_spki = base64.b64encode(
        certificate.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("ascii")
    assert material.spki_pin == expected_spki

    reused = prepare_remote_access_tls(
        "https://192.168.1.42:9443",
        storage_root=tmp_path,
    )
    assert reused == material


def test_prepare_remote_access_tls_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="localhost"):
        prepare_remote_access_tls("https://localhost:9443")


def test_prepare_remote_access_tls_allows_loopback_when_explicit(tmp_path: Path) -> None:
    material = prepare_remote_access_tls(
        "https://127.0.0.1:8765",
        storage_root=tmp_path,
        allow_loopback=True,
    )

    certificate = x509.load_pem_x509_certificate(Path(material.certificate_path).read_bytes())
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert material.bind_host == "127.0.0.1"
    assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("127.0.0.1")]
    assert Path(material.key_path).exists()
    assert material.spki_pin


def test_prepare_remote_access_tls_rejects_dns_host_names() -> None:
    with pytest.raises(ValueError, match="literal IP address or .local"):
        prepare_remote_access_tls("https://pairing.example.com:9443")


def test_uvicorn_ssl_kwargs_from_env_requires_both_paths() -> None:
    assert uvicorn_ssl_kwargs_from_env({}) == {}

    with pytest.raises(ValueError, match="Both"):
        uvicorn_ssl_kwargs_from_env({"FICHERO_TLS_CERTFILE": "/tmp/cert.pem"})


def test_validate_tailnet_url_accepts_https_ts_net_host() -> None:
    assert validate_tailnet_url("https://fichero-demo.ts.net") == "https://fichero-demo.ts.net"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("http://fichero-demo.ts.net", "public_base_url must use https"),
        ("https://127.0.0.1:8765", "tailnet_url must use a .ts.net host"),
        ("https://localhost:8765", "tailnet_url must use a .ts.net host"),
    ],
)
def test_validate_tailnet_url_rejects_non_tailnet_or_insecure_urls(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_tailnet_url(raw)
