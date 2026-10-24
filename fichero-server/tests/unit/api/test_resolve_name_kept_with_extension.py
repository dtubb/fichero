"""A project whose name was kept with its package's extension resolves by the name the sidebar shows (owner 2026-10-24).

WHY: `fichero -l "Test 14"` was answered "No known project is called 'Test 14'. Known: ['Test 14.fichero', …]": the
registry had kept the name as "Test 14.fichero", and the shown name was compared with it unchanged.
"""

from types import SimpleNamespace as NS

from fichero_server.api.routes.library.registry import resolve_known_library


def test_a_name_kept_with_dot_fichero_resolves_without_it():
    lib = NS(name="Test 14.fichero", path="/Users/someone/Fichero Projects/Test 14.fichero")
    db = NS(all=lambda model: [lib])
    assert resolve_known_library("Test 14", db=db) is lib
    assert resolve_known_library("test 14", db=db) is lib
