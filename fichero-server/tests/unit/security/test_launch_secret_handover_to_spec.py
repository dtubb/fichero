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
    launch_secret.load_at_startup({"FICHERO_ENV": "development", "FICHERO_DEV_LAUNCH_SECRET_FILE": str(path)}, io.StringIO(""))
    assert launch_secret.matches(SECRET)


def test_start_up_with_neither_leaves_first_run_closed():
    launch_secret.load_at_startup({}, io.StringIO(SECRET + "\n"))
    assert not launch_secret.matches(SECRET)


def test_the_secret_never_enters_the_environment(tmp_path):
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, io.StringIO(SECRET + "\n"))
    assert SECRET not in os.environ.values()


@pytest.mark.parametrize("env", [{}, {"FICHERO_ENV": "production"}])
def test_the_dev_file_is_ignored_outside_development(tmp_path, env):
    path = tmp_path / "launch-secret"
    path.write_text(SECRET)
    path.chmod(0o600)
    launch_secret.load_at_startup({**env, "FICHERO_DEV_LAUNCH_SECRET_FILE": str(path)}, io.StringIO(""))
    assert not launch_secret.matches(SECRET)


def test_a_symlinked_secret_file_is_refused(tmp_path):
    real = tmp_path / "real"
    real.write_text(SECRET)
    real.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(OSError):
        launch_secret.read_from_file(str(link))
    assert not launch_secret.matches(SECRET)


@pytest.mark.parametrize("line", ["", "\n", "not-a-secret\n"])
def test_a_missing_or_malformed_stdin_secret_never_stops_start_up(line):
    """#5797: the embedded app's engine must start even when the pipe write failed (EOF) or carried junk."""
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, io.StringIO(line))
    assert not launch_secret.matches(line.strip())


def test_a_pipe_nobody_writes_to_never_blocks_start_up():
    """#5797: an open pipe with nothing on it (the app never delivered) gives up after the timeout."""
    import time

    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd) as stream:
            started = time.monotonic()
            launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, stream, timeout=0.2)
            assert time.monotonic() - started < 2
    finally:
        os.close(write_fd)
    assert not launch_secret.matches(SECRET)


def test_a_pipe_on_a_descriptor_above_1024_still_delivers_the_secret():
    """P0 red: select() refuses a descriptor over 1024 ("filedescriptor out of range"), so a busy engine took no secret and
    first-run stayed closed; the wait uses poll."""
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 1200:
        resource.setrlimit(resource.RLIMIT_NOFILE, (1200 if hard == resource.RLIM_INFINITY else min(1200, hard), hard))
    read_fd, write_fd = os.pipe()
    os.write(write_fd, (SECRET + "\n").encode())
    os.close(write_fd)
    spare = []
    try:
        while True:
            high = os.dup(read_fd)
            spare.append(high)
            if high > 1100:
                break
        os.close(read_fd)
        with os.fdopen(high, "r", closefd=False) as stream:
            launch_secret.set_secret(None)
            launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, stream)
        assert launch_secret.matches(SECRET)
    finally:
        for fd in spare:
            try:
                os.close(fd)
            except OSError:
                pass
        launch_secret.set_secret(None)


def test_an_unreadable_dev_file_never_stops_start_up(tmp_path):
    env = {"FICHERO_DEV_LAUNCH_SECRET_FILE": str(tmp_path / "missing"), "FICHERO_ENV": "development"}
    launch_secret.load_at_startup(env, io.StringIO(""))
    assert not launch_secret.matches(SECRET)


def _pipe_with(data: bytes, *, close_writer: bool = True):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, data)
    if close_writer:
        os.close(write_fd)
    return os.fdopen(read_fd, "r"), write_fd


def test_launch_with_no_secret_and_no_flag_does_not_wait():
    import time

    started = time.monotonic()
    launch_secret.load_at_startup({}, open(os.devnull))
    assert time.monotonic() - started < 0.5
    assert not launch_secret.matches(SECRET)


def test_the_flag_with_stdin_not_a_pipe_does_not_wait():
    import time

    started = time.monotonic()
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, open(os.devnull))
    assert time.monotonic() - started < 0.5
    assert not launch_secret.matches(SECRET)


def test_an_empty_line_on_the_pipe_leaves_first_run_closed_and_returns_at_once():
    import time

    stream, _ = _pipe_with(b"\n")
    started = time.monotonic()
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, stream)
    assert time.monotonic() - started < 0.5
    assert not launch_secret.matches(SECRET)


def test_a_real_pipe_line_is_taken():
    stream, _ = _pipe_with((SECRET + "\n").encode())
    launch_secret.load_at_startup({"FICHERO_LAUNCH_SECRET_STDIN": "1"}, stream)
    assert launch_secret.matches(SECRET)
