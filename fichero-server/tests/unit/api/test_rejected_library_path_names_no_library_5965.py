"""The 403 for a rejected library path is made before authentication, so it names no library of this host (#5965, ## 688,
`sharing.guest-addresses-the-hosts-library`): an unauthenticated caller with any bogus header learns nothing about what is served."""
from __future__ import annotations

from fichero_server.api import main as api_main


def test_the_refusal_points_to_the_signed_in_list_and_names_no_library():
    assert not hasattr(api_main, "_served_library_names"), "the pre-auth refusal must not read the registry"
    payload = api_main._rejected_library_path_payload("/var/mobile/Containers/Data/Application/X/Documents/global.fichero")
    assert "after signing in" in payload["detail"]
    assert "This Mac serves" not in payload["detail"]
    assert payload["code"] == api_main.LIBRARY_OUTSIDE_ALLOWED_LOCATIONS


def test_a_path_that_is_not_a_package_keeps_its_own_sentence():
    payload = api_main._rejected_library_path_payload("/var/mobile/X/notes.txt")
    assert payload["detail"] == api_main._rejected_library_path_detail("/var/mobile/X/notes.txt")
    assert payload["code"] == api_main.LIBRARY_NOT_A_PACKAGE
