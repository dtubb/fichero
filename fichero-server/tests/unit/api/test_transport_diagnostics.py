"""The engine names its transport, and who can dial it (#4222).

`start_backend.sh --uds` and `Fichero (Dev Local)` can disagree about
transport. Neither half is wrong — only `.releaseEmbedded` resolves to UDS,
and `debugExternal -> https` is correct — but the app showed "Failed to
connect to the engine", the same message as a down engine, a wrong host, or a
firewall. These tests pin the diagnostic that makes the disagreement readable
without opening Swift source.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from fichero_server.api.transport_diagnostics import (
    APP_LOOPBACK_URL,
    describe_transport,
    log_transport_banner,
    transport_banner,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
START_BACKEND_SH = REPO_ROOT / "fichero-server" / "scripts" / "start_backend.sh"


class TestDescribeTransport:
    def test_a_socket_path_is_uds(self):
        binding = describe_transport(uds_path="/tmp/fichero.sock")

        assert binding.kind == "uds"
        assert binding.address == "unix:/tmp/fichero.sock"
        assert binding.is_uds

    def test_uds_wins_over_a_host_and_port(self):
        """The launcher binds ONE of them; a socket path means the socket."""
        binding = describe_transport(
            uds_path="/tmp/fichero.sock", host="127.0.0.1", port=8765, tls=True
        )

        assert binding.is_uds

    def test_a_blank_socket_path_is_not_uds(self):
        """FICHERO_UDS_PATH="" is unset, not a socket named empty string."""
        binding = describe_transport(uds_path="  ", host="127.0.0.1", port=8765, tls=True)

        assert binding.kind == "https"

    def test_tls_and_plain_are_distinguished(self):
        assert describe_transport(host="127.0.0.1", port=8765, tls=True).address == (
            "https://127.0.0.1:8765"
        )
        assert describe_transport(host="127.0.0.1", port=8765, tls=False).address == (
            "http://127.0.0.1:8765"
        )

    def test_a_non_uds_binding_without_a_port_is_refused(self):
        """Raise rather than invent a port — a wrong one is worse than none."""
        with pytest.raises(ValueError):
            describe_transport(host="127.0.0.1")


class TestTheUDSBannerNamesWhoCannotReachIt:
    @pytest.fixture()
    def banner(self) -> str:
        return transport_banner(describe_transport(uds_path="/tmp/fichero.sock"))

    def test_it_says_what_it_bound_and_where(self, banner):
        assert "UDS" in banner
        assert "unix:/tmp/fichero.sock" in banner

    def test_it_names_the_variable_a_client_must_set(self, banner):
        assert "FICHERO_FORCE_UDS_PATH=/tmp/fichero.sock" in banner

    def test_it_names_dev_local_as_the_one_that_cannot_reach_it(self, banner):
        """The whole point: the flag most likely to be copied from the help
        text is the one that breaks the DEFAULT scheme."""
        assert "Dev Local" in banner
        assert APP_LOOPBACK_URL in banner

    def test_it_says_how_to_get_back_to_dev_local(self, banner):
        assert "--uds" in banner


class TestTheHTTPSBannerNamesTheOtherDirection:
    @pytest.fixture()
    def banner(self) -> str:
        return transport_banner(describe_transport(host="127.0.0.1", port=8765, tls=True))

    def test_it_names_the_endpoint(self, banner):
        assert "https://127.0.0.1:8765" in banner

    def test_it_says_a_force_uds_scheme_will_not_reach_it(self, banner):
        assert "FICHERO_FORCE_UDS_PATH" in banner

    def test_no_plain_http_warning_when_serving_tls(self, banner):
        assert "PLAIN HTTP" not in banner


class TestPlainHTTPOnThePinnedPort:
    def test_it_is_called_out_as_unreachable(self):
        banner = transport_banner(describe_transport(host="127.0.0.1", port=8765))

        assert "PLAIN HTTP" in banner
        assert "#2538" in banner

    def test_another_port_is_not_flagged(self):
        banner = transport_banner(describe_transport(host="127.0.0.1", port=9000))

        assert "PLAIN HTTP" not in banner


class TestItActuallyGetsLogged:
    def test_log_transport_banner_emits_every_line(self, caplog):
        with caplog.at_level(logging.INFO, logger="fichero_server.api.transport_diagnostics"):
            binding = log_transport_banner(uds_path="/tmp/fichero.sock")

        assert binding.is_uds
        assert "FICHERO_FORCE_UDS_PATH" in caplog.text
        assert "Dev Local" in caplog.text


class TestTheScriptsSayItToo:
    """A diagnostic only the Python launcher prints misses the --uds branch,
    which execs uvicorn directly and never reaches it."""

    def test_the_uds_help_names_the_scheme_that_cannot_dial_it(self):
        help_text = subprocess.run(
            ["bash", str(START_BACKEND_SH), "--help"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        assert "FICHERO_FORCE_UDS_PATH" in help_text
        assert "Dev Local" in help_text
        assert "https://127.0.0.1:8765" in help_text

    def test_the_uds_branch_prints_the_shared_banner(self):
        source = START_BACKEND_SH.read_text()

        assert "transport_diagnostics" in source, (
            "the --uds branch must print the same banner, not a hand-rolled echo"
        )

    def test_the_python_launcher_prints_it_on_both_paths(self):
        source = (REPO_ROOT / "fichero-server" / "scripts" / "start_backend.py").read_text()

        # Both call sites by shape, not by a count: the launcher has two
        # mutually exclusive branches and a banner on only one of them is the
        # bug this issue is about.
        assert "log_transport_banner(uds_path=" in source
        assert "log_transport_banner(host=" in source
