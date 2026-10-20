"""P0 red: DuckDB refuses a CHECKPOINT while another connection's write is open; the conversion waits a little for it to
commit (and still refuses when it stays busy), rather than failing at once."""
import duckdb
import pytest

from fichero_server.maintenance.project_conversion import _checkpoint_when_quiet

BUSY = "TransactionContext Error: Cannot CHECKPOINT: there are other write transactions active."


class _Db:
    def __init__(self, busy_for: int, message: str = BUSY):
        self.busy_for, self.calls, self.message = busy_for, 0, message

    def checkpoint(self):
        self.calls += 1
        if self.calls <= self.busy_for:
            raise duckdb.TransactionException(self.message)


def test_a_writer_that_commits_a_moment_later_does_not_stop_the_conversion():
    db = _Db(busy_for=2)
    _checkpoint_when_quiet(db, seconds=5)
    assert db.calls == 3


def test_a_writer_that_never_commits_still_refuses():
    with pytest.raises(duckdb.TransactionException):
        _checkpoint_when_quiet(_Db(busy_for=10**6), seconds=0.6)


def test_any_other_transaction_error_is_not_waited_on():
    db = _Db(busy_for=10**6, message="something else")
    with pytest.raises(duckdb.TransactionException):
        _checkpoint_when_quiet(db, seconds=5)
    assert db.calls == 1
