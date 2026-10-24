"""A file under a folder the owner picked is allowed whichever Unicode form its path arrives in (owner 2026-10-24).

WHY: a folder name with an "ñ" was refused as "not in an allowed location" though its folder was picked: the
grant is kept NFC and Finder may hand the path decomposed (NFD), so the "ñ" in one form never matched the other.
"""

import unicodedata
from pathlib import Path

import fichero_server.security.path_security as path_security

FOLDER = "/Users/someone/Material/1900 Carta de la señora Peña; Ciudad"


def test_a_decomposed_path_under_a_composed_grant_is_allowed(monkeypatch):
    monkeypatch.setattr(path_security, "_OWNER_GRANTED_FOLDERS", {unicodedata.normalize("NFC", FOLDER)})
    monkeypatch.setattr(path_security, "_OWNER_GRANT_LOADER", None)
    nfd = Path(unicodedata.normalize("NFD", FOLDER + "/page 1.jpg"))
    assert str(nfd) != unicodedata.normalize("NFC", str(nfd))  # the test really holds two forms
    assert path_security._within_owner_granted_folder(nfd)


def test_a_path_outside_the_grant_is_still_refused(monkeypatch):
    monkeypatch.setattr(path_security, "_OWNER_GRANTED_FOLDERS", {unicodedata.normalize("NFC", FOLDER)})
    monkeypatch.setattr(path_security, "_OWNER_GRANT_LOADER", None)
    assert not path_security._within_owner_granted_folder(Path("/Users/someone/Fichero Sources/Other/page.jpg"))
