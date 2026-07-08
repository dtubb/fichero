from __future__ import annotations

import base64
import ipaddress
import json
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from fichero.remote_access_tls import (
    material_manifest_json,
    prepare_remote_access_tls,
    validate_spki_pin,
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

    assert material.bind_host == "192.168.1.42"
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


def test_prepare_remote_access_tls_adds_subject_alt_hosts(tmp_path: Path) -> None:
    material = prepare_remote_access_tls(
        "https://127.0.0.1:8765",
        storage_root=tmp_path,
        allow_loopback=True,
        subject_alt_hosts=["192.168.1.42"],
    )

    certificate = x509.load_pem_x509_certificate(Path(material.certificate_path).read_bytes())
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert san.get_values_for_type(x509.IPAddress) == [
        ipaddress.ip_address("127.0.0.1"),
        ipaddress.ip_address("192.168.1.42"),
    ]


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


def test_validate_spki_pin_normalizes_valid_base64() -> None:
    assert validate_spki_pin(" c3BraS1waW4= ") == "c3BraS1waW4="


@pytest.mark.parametrize("raw", ["", "%%%not-base64%%%"])
def test_validate_spki_pin_rejects_missing_or_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        validate_spki_pin(raw)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "public_base_url is required"),
        ("   ", "public_base_url is required"),
        ("https://", "public_base_url must include a host name"),
        ("https://fichero-demo.ts.net/serve", "public_base_url must not include a path"),
        ("https://fichero-demo.ts.net?token=leak", "public_base_url must not include a query string"),
        ("https://fichero-demo.ts.net#frag", "public_base_url must not include a fragment"),
    ],
)
def test_public_base_url_grammar_is_enforced(raw: str, message: str) -> None:
    """Every rejection branch of _validate_public_base_url, via a public caller.

    These guards keep an advertised pairing URL down to scheme+host+port. A path,
    query or fragment would let a caller smuggle credentials or a redirect into a
    URL the app hands out and pins a certificate against.
    """
    with pytest.raises(ValueError, match=message):
        validate_tailnet_url(raw)


def test_material_manifest_json_round_trips_with_stable_key_order(tmp_path: Path) -> None:
    material = prepare_remote_access_tls("https://192.168.1.42:9443", storage_root=tmp_path)

    payload = material_manifest_json(material)
    decoded = json.loads(payload)

    assert decoded["bind_host"] == "192.168.1.42"
    assert decoded["spki_pin"] == material.spki_pin
    assert list(decoded) == sorted(decoded), "Swift launcher relies on sorted keys"
    assert json.loads(material_manifest_json(material)) == decoded


def test_subject_alt_hosts_skip_blanks_and_deduplicate_case_insensitively(tmp_path: Path) -> None:
    material = prepare_remote_access_tls(
        "https://127.0.0.1:8765",
        storage_root=tmp_path,
        allow_loopback=True,
        subject_alt_hosts=["", "   ", "127.0.0.1", "192.168.1.42", "192.168.1.42"],
    )

    certificate = x509.load_pem_x509_certificate(Path(material.certificate_path).read_bytes())
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    # primary host is already seeded into `seen`, so the duplicate 127.0.0.1 and the
    # repeated LAN address collapse; blanks never reach the SAN at all.
    assert san.get_values_for_type(x509.IPAddress) == [
        ipaddress.ip_address("127.0.0.1"),
        ipaddress.ip_address("192.168.1.42"),
    ]


def test_dot_local_alt_host_is_encoded_as_a_dns_name(tmp_path: Path) -> None:
    """`.local` hosts are accepted inputs, so they must land in the SAN as DNSName."""
    material = prepare_remote_access_tls(
        "https://192.168.1.42:9443",
        storage_root=tmp_path,
        subject_alt_hosts=["daniels-mac.local"],
    )

    certificate = x509.load_pem_x509_certificate(Path(material.certificate_path).read_bytes())
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert san.get_values_for_type(x509.DNSName) == ["daniels-mac.local"]
    assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("192.168.1.42")]
