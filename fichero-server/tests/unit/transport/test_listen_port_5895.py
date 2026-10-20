"""`transport.listen-port-is-chosen-in-dev-and-test-only` (#5895): one place decides the engine's TCP port.

WHY: the listener and its start-up check were fixed at 8765, so on a Mac where the app runs a second engine (the pairs
check) could not listen. The shipped port stays 8765; a dev or test engine may name another.
"""
from __future__ import annotations

import pytest

from fichero_server.security.bind_host import listen_port


def test_the_shipped_port_is_8765():
    assert listen_port({}) == 8765
    assert listen_port({"FICHERO_ENV": "production"}) == 8765


def test_the_variable_alone_changes_nothing_a_release_app_that_sets_nothing_keeps_8765():
    assert listen_port({"FICHERO_TCP_PORT": "18765"}) == 8765
    assert listen_port({"FICHERO_ENV": "production", "FICHERO_TCP_PORT": "18765"}) == 8765
    assert listen_port({"FICHERO_ENV": "staging", "FICHERO_TCP_PORT": "18765"}) == 8765


@pytest.mark.parametrize("env", ["development", "test", " Test "])
def test_only_an_environment_that_says_dev_or_test_explicitly_may_choose_its_port(env):
    assert listen_port({"FICHERO_ENV": env, "FICHERO_TCP_PORT": "18765"}) == 18765


@pytest.mark.parametrize("raw", ["abc", "0", "70000", "-5", "87 65"])
def test_a_value_that_is_not_a_port_refuses_in_words(raw):
    with pytest.raises(SystemExit, match="FICHERO_TCP_PORT"):
        listen_port({"FICHERO_ENV": "test", "FICHERO_TCP_PORT": raw})


def test_the_bonjour_advert_follows_the_one_port():
    from fichero_server.security.discovery import build_bonjour_config

    assert build_bonjour_config({"FICHERO_TCP_PORT": "18765", "FICHERO_ENV": "test"}, host="192.0.2.1").port == 18765
    assert build_bonjour_config({"FICHERO_TCP_PORT": "18765", "FICHERO_ENV": "production"}, host="192.0.2.1").port == 8765


def test_the_bonjour_ports_own_variable_is_gated_like_the_listeners():
    from fichero_server.security.discovery import build_bonjour_config

    assert build_bonjour_config({"FICHERO_BONJOUR_PORT": "19999"}, host="192.0.2.1").port == 8765
    assert build_bonjour_config({"FICHERO_ENV": "production", "FICHERO_BONJOUR_PORT": "19999"}, host="192.0.2.1").port == 8765
    assert build_bonjour_config({"FICHERO_ENV": "test", "FICHERO_BONJOUR_PORT": "19999"}, host="192.0.2.1").port == 19999
