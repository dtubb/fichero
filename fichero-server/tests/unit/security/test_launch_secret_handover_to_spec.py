"""multiuser.launch-secret-handover (slice 4, #2403): how the engine receives the per-launch secret.

Spec: docs/contributor_manual/specs/transport/multiuser-always-on.md ("Transports and the two secrets"). The engine takes
the secret on stdin when the app spawned it (a flag says so; the secret itself never rides in the environment). A
`--reload` dev engine cannot inherit stdin, so Debug Dev Local alone reads the 0600 file the dev script wrote.

The held strict xfails of the red commit are gone now the handover is built.
"""

import io
import os

import pytest

from fichero_server.security import launch_secret

SECRET = "0f" * 32


@pytest.fixture(autouse=True)
def _clean():
    launch_secret.set_secret(None)
    yield
    launch_secret.set_secret(None)


def test_the_secret_is_read_from_a_stream_and_matches():
    launch_secret.read_from_stream(io.StringIO(SECRET + "\n"))
    assert launch_secret.matches(SECRET)


@pytest.mark.parametrize("bad", ["", "\n", "abc\n", "zz" * 32 + "\n", "ab" * 31 + "\n", "ab" * 33 + "\n"])
def test_a_malformed_secret_is_refused_and_nothing_is_set(bad):
    with pytest.raises(ValueError):
        launch_secret.read_from_stream(io.StringIO(bad))
    assert not launch_secret.matches(bad.strip())


def test_a_0600_file_is_read_and_left_for_the_app_to_delete(tmp_path):
    path = tmp_path / "launch-secret"
    path.write_text(SECRET)
    path.chmod(0o600)
    launch_secret.read_from_file(str(path))
    assert launch_secret.matches(SECRET)
    assert path.exists()


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o666])
def test_a_file_others_can_read_is_refused(tmp_path, mode):
    path = tmp_path / "launch-secret"
    path.write_text(SECRET)
    path.chmod(mode)
    with pytest.raises(ValueError):
        launch_secret.read_from_file(str(path))
    assert not launch_secret.matches(SECRET)


def test_start_up_prefers_stdin_when_the_flag_says_the_app_spawned_us(tmp_path):
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, io.StringIO(SECRET + "\n"))
    assert launch_secret.matches(SECRET)


def test_start_up_reads_the_dev_file_when_named(tmp_path):
    path = tmp_path / "launch-secret"
    path.write_text(SECRET)
    path.chmod(0o600)
    launch_secret.load_at_startup({"FICHERO_DEV_LAUNCH_SECRET_FILE": str(path)}, io.StringIO(""))
    assert launch_secret.matches(SECRET)


def test_start_up_with_neither_leaves_first_run_closed():
    launch_secret.load_at_startup({}, io.StringIO(SECRET + "\n"))
    assert not launch_secret.matches(SECRET)


def test_the_secret_never_enters_the_environment(tmp_path):
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, io.StringIO(SECRET + "\n"))
    assert SECRET not in os.environ.values()
