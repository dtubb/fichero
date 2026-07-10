"""Remote-access TLS material for secure same-network pairing.

This module owns the local HTTPS identity used by the embedded engine when
Fichero is deliberately exposing a reachable private URL for QR pairing. The
QR still carries the SPKI pin; Bonjour remains discovery only.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import ParseResult, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

DEFAULT_BIND_PORT = 8765
DEFAULT_STORAGE_ROOT = Path.home() / "Library/Application Support/Fichero/Remote Access"
_MAX_CERT_AGE = timedelta(days=3650)


@dataclass(frozen=True)
class RemoteAccessTLSMaterial:
    bind_host: str
    certificate_path: str
    key_path: str
    spki_pin: str


def prepare_remote_access_tls(
    public_base_url: str,
    *,
    storage_root: Path | str | None = None,
    allow_loopback: bool = False,
    subject_alt_hosts: Sequence[str] = (),
) -> RemoteAccessTLSMaterial:
    """Create or reuse the local HTTPS identity for a reachable private URL."""

    parsed = _validate_public_base_url(public_base_url)
    host = parsed.hostname
    if host is None:
        raise ValueError("public_base_url must include a host name")

    if _is_loopback_host(host) and not allow_loopback:
        raise ValueError("public_base_url must not point at localhost")
    bind_host = _bind_host_for_public_host(host)

    port = parsed.port or DEFAULT_BIND_PORT
    root = Path(storage_root).expanduser() if storage_root is not None else DEFAULT_STORAGE_ROOT
    alt_hosts = tuple(_normalized_subject_alt_hosts(subject_alt_hosts, primary_host=host))
    material_dir = _material_directory(
        root,
        host=host,
        port=port,
        url=public_base_url,
        subject_alt_hosts=alt_hosts,
    )
    certificate_path = material_dir / "server.crt"
    key_path = material_dir / "server.key"

    if not certificate_path.exists() or not key_path.exists():
        _generate_material(
            certificate_path=certificate_path,
            key_path=key_path,
            hosts=(host, *alt_hosts),
        )

    spki_pin = _spki_pin_from_certificate(certificate_path)
    return RemoteAccessTLSMaterial(
        bind_host=bind_host,
        certificate_path=str(certificate_path),
        key_path=str(key_path),
        spki_pin=spki_pin,
    )


def material_manifest_json(material: RemoteAccessTLSMaterial) -> str:
    """Serialize a material manifest for the Swift launcher."""

    return json.dumps(asdict(material), sort_keys=True)


def uvicorn_ssl_kwargs_from_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Translate TLS env vars into uvicorn keyword arguments."""

    source = env if env is not None else os.environ
    certfile = source.get("FICHERO_TLS_CERTFILE", "").strip()
    keyfile = source.get("FICHERO_TLS_KEYFILE", "").strip()
    if not certfile and not keyfile:
        return {}
    if not certfile or not keyfile:
        raise ValueError("Both FICHERO_TLS_CERTFILE and FICHERO_TLS_KEYFILE are required")
    return {
        "ssl_certfile": certfile,
        "ssl_keyfile": keyfile,
    }


def _validate_public_base_url(raw: str) -> ParseResult:
    value = raw.strip()
    if not value:
        raise ValueError("public_base_url is required")

    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise ValueError("public_base_url must use https")
    if parsed.hostname is None:
        raise ValueError("public_base_url must include a host name")
    if parsed.path not in ("", "/"):
        raise ValueError("public_base_url must not include a path")
    if parsed.query:
        raise ValueError("public_base_url must not include a query string")
    if parsed.fragment:
        raise ValueError("public_base_url must not include a fragment")
    return parsed


def validate_tailnet_url(raw: str) -> str:
    """Return a normalized tailscale-serve URL safe to advertise for pairing."""
    parsed = _validate_public_base_url(raw)
    host = (parsed.hostname or "").lower()
    if not host.endswith(".ts.net"):
        raise ValueError("tailnet_url must use a .ts.net host")
    if _is_loopback_host(host):
        raise ValueError("tailnet_url must not point at localhost")
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{host}{port}"


def validate_spki_pin(raw: str) -> str:
    """Return a normalized SPKI pin or raise for missing/invalid values."""
    value = raw.strip()
    if not value:
        raise ValueError("spki_pin is required")
    try:
        decoded = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("spki_pin must be valid base64") from exc
    if not decoded:
        raise ValueError("spki_pin is required")
    return base64.b64encode(decoded).decode("ascii")


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _bind_host_for_public_host(host: str) -> str:
    """Return a safe local bind target for a reachable private URL.

    The engine bind stays loopback even when we advertise a reachable remote
    URL. Tailscale serve / the external transport is the network perimeter;
    sharing must not move the app's local listener off 127.0.0.1.
    """

    if _is_loopback_host(host):
        return host

    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not host.lower().endswith(".local"):
            raise ValueError(
                "public_base_url must use a literal IP address or .local host so "
                "the engine can bind to a real local Mac address."
            )

    return "127.0.0.1"


def _normalized_subject_alt_hosts(
    subject_alt_hosts: Sequence[str],
    *,
    primary_host: str,
) -> list[str]:
    normalized: list[str] = []
    seen = {primary_host.lower()}
    for raw_host in subject_alt_hosts:
        host = raw_host.strip()
        if not host:
            continue
        key = host.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(host)
    return normalized


def _material_directory(
    root: Path,
    *,
    host: str,
    port: int,
    url: str,
    subject_alt_hosts: Sequence[str] = (),
) -> Path:
    digest_input = json.dumps(
        {
            "url": url,
            "subject_alt_hosts": list(subject_alt_hosts),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    safe_host = re.sub(r"[^A-Za-z0-9._-]+", "_", host).strip("._-") or "host"
    return root / f"{safe_host}-{port}-{digest}"


def _generate_material(*, certificate_path: Path, key_path: Path, hosts: Sequence[str]) -> None:
    certificate_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(certificate_path.parent, 0o700)

    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + _MAX_CERT_AGE)
        .add_extension(_subject_alt_name(hosts), critical=False)
        .sign(private_key, hashes.SHA256())
    )

    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(certificate_path, 0o600)
    os.chmod(key_path, 0o600)


def _subject_alt_name(hosts: Sequence[str]) -> x509.SubjectAlternativeName:
    names: list[x509.GeneralName] = []
    for host in hosts:
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    return x509.SubjectAlternativeName(names)


def _spki_pin_from_certificate(certificate_path: Path) -> str:
    pem = certificate_path.read_text(encoding="utf-8")
    der = _pem_to_der(pem)
    certificate = x509.load_der_x509_certificate(der)
    spki = certificate.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(spki).decode("ascii")


def _pem_to_der(pem: str) -> bytes:
    body = "".join(
        line.strip()
        for line in pem.splitlines()
        if "BEGIN CERTIFICATE" not in line and "END CERTIFICATE" not in line
    )
    return base64.b64decode(body)
