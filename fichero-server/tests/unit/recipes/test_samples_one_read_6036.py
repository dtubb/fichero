"""#6036: the samples call reads the project's pages in one query, not one per page: mid-import a per-page read outlasts the
client's deadline."""

from fichero_server.recipes import samples


class _CountingDb:
    def __init__(self, n):
        self.n = n
        self.queries = 0
        self.path = "/nowhere/x.fichero/library.duckdb"

    def get(self, *_a):
        raise AssertionError("a per-page read")

    def execute_fetchall(self, *_a, **_k):
        self.queries += 1
        return [(f"p{i}", f"IMG_{i}", None, None, None, i) for i in range(self.n)]

    def unit_of_work_ids(self):
        return [f"p{i}" for i in range(self.n)]


def test_proposing_samples_reads_every_page_in_one_query():
    db = _CountingDb(2000)
    picked = samples.propose(db)
    assert 3 <= len(picked) <= 5
    assert db.queries == 1
