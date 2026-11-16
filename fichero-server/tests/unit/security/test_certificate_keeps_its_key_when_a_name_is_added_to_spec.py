"""`sharing.certificate-names-every-address` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.1).

One key per Mac: a new name or a new LAN address re-issues the certificate but keeps the key, so the pin (the key's SPKI)
and every link and paired device built on it stay valid.
"""
from __future__ import annotations

import stat
from pathlib import Path

from cryptography import x509

from fichero_server.security.remote_access_tls import prepare_remote_access_tls

URL = "https://127.0.0.1:8765"


def _make(root: Path, *alt: str):
    return prepare_remote_access_tls(URL, storage_root=root, allow_loopback=True, subject_alt_hosts=list(alt))


def test_a_grown_name_list_keeps_the_pin(tmp_path: Path) -> None:
    first = _make(tmp_path, "192.168.1.42")
    second = _make(tmp_path, "192.168.1.42", "macbook-air-m1.local")
    third = _make(tmp_path, "192.168.1.77")  # DHCP gave a new address
    assert first.certificate_path != second.certificate_path  # a new certificate...
    assert first.spki_pin == second.spki_pin == third.spki_pin  # ...under the same key
    names = x509.load_pem_x509_certificate(Path(second.certificate_path).read_bytes()).extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    assert "macbook-air-m1.local" in names


def test_the_one_key_is_owner_only_at_the_top_of_the_folder(tmp_path: Path) -> None:
    material = _make(tmp_path)
    assert Path(material.key_path) == tmp_path / "key.pem"
    assert stat.S_IMODE((tmp_path / "key.pem").stat().st_mode) == 0o600


def test_a_folder_made_before_the_shared_key_keeps_its_own_key_and_pin(tmp_path: Path) -> None:
    from fichero_server.security import remote_access_tls as tls

    old = tls._material_directory(tmp_path, host="127.0.0.1", port=8765, url=URL)
    tls._generate_material(certificate_path=old / "server.crt", key_path=old / "server.key", hosts=("127.0.0.1",))
    material = _make(tmp_path)
    assert Path(material.key_path) == old / "server.key"  # its links and pins are not voided
    assert not (tmp_path / "key.pem").exists()
