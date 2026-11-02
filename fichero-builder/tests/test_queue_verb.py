"""dev-workflows.tool.queue: `builder queue` works a queue of briefs with no manager in the loop: the next satisfied item
starts as one `builder work` process (at most [queue].workers), exit 0 -> `builder landed` -> landed, a QUESTION -> question
with the line in a file, anything else -> blocked; every transition a journal row. The processes are fakes."""
from __future__ import annotations

import json

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue


class Fake:
    """Scripted ends per item id: (rc, output); landed rc per head; which shas are on origin."""

    def __init__(self, ends: dict, landed_rc: int = 0, on_origin=()):
        self.ends, self.landed_rc, self.origin = ends, landed_rc, set(on_origin)
        self.started, self.landed_calls, self.polled = [], [], {}
        self.procs = queue.Procs(start=self.start, poll=self.poll, landed=self.landed, origin_head=lambda: "0ri9in000",
                                 on_origin=lambda sha: sha in self.origin, head_of=lambda item: "head-" + item["id"], sleep=lambda s: None)

    def start(self, item, base):
        self.started.append((item["id"], base))
        return item["id"]

    def poll(self, h):  # ends on the second poll
        self.polled[h] = self.polled.get(h, 0) + 1
        return self.ends[h] if self.polled[h] >= 2 else None

    def landed(self, item, push):
        self.landed_calls.append((item["head"], push))
        if self.landed_rc == 0:
            self.origin.add(item["head"])
        return self.landed_rc, "landed" if self.landed_rc == 0 else "REFUSED (verdict): no READY"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[queue]\nworkers = 2\n')
    return tmp_path


def rows():
    return [(r["id"], r["state"]) for r in journal.read() if r["event"] == "queue"]


def test_add_writes_a_queued_row_and_refuses_a_running_duplicate(state, capsys):
    assert cli.main(["queue", "add", "--id", "step-1.1", "--brief", "/b/1", "--worktree", "/w/1", "--issues", "7", "8", "--state", str(state / "s")]) == 0
    assert queue.load()[0] == {"id": "step-1.1", "brief": "/b/1", "worktree": "/w/1", "base": "", "depends_on": [], "issues": [7, 8],
                               "state": "queued", "head": "", "why": ""}
    assert rows() == [("step-1.1", "queued")]
    items = queue.load()
    items[0]["state"] = "running"
    queue.save(items)
    assert cli.main(["queue", "add", "--id", "step-1.1", "--brief", "/b/1", "--worktree", "/w/1", "--issues", "7", "--state", str(state / "s")]) == 1
    assert "already running" in capsys.readouterr().out


def test_the_loop_starts_satisfied_items_up_to_the_worker_cap_lands_a_green_one_and_blocks_or_questions_the_rest(state):
    queue.add("a", "/b/a", "/w/a", [1])
    queue.add("b", "/b/b", "/w/b", [2], depends_on=["a"])                 # waits for a to land
    queue.add("c", "/b/c", "/w/c", [3], depends_on=["deadbeef1"])          # a sha already on origin
    queue.add("d", "/b/d", "/w/d", [4])
    fake = Fake(ends={"a": (0, "READY TO LAND"), "b": (2, "QUESTION: the check is red at head-b"), "c": (1, "Traceback"), "d": (0, "ok")},
                on_origin=["deadbeef1"])
    said = []
    assert queue.run(fake.procs, workers_n=2, push=False, out=said.append) == 0
    assert [s[0] for s in fake.started] == ["a", "c", "b", "d"], "two at a time, in file order; b only once a has landed"
    assert all(base == "0ri9in000" for _, base in fake.started), "each start names the current origin head as the base"
    by = {i["id"]: i for i in queue.load()}
    assert by["a"]["state"] == "landed" and by["d"]["state"] == "landed" and fake.landed_calls == [("head-a", False), ("head-d", False)]
    assert by["b"]["state"] == "question" and (state / "s" / "question-b.txt").read_text() == "QUESTION: the check is red at head-b\n"
    assert by["c"]["state"] == "blocked" and "work exited 1" in by["c"]["why"]
    assert rows()[4:] == [("a", "running"), ("c", "running"), ("a", "landing"), ("a", "landed"), ("c", "blocked"), ("b", "running"),
                          ("d", "running"), ("b", "question"), ("d", "landing"), ("d", "landed")]
    assert any("b: question" in s for s in said)


def test_a_refused_landing_blocks_the_item_with_the_reason_and_push_is_passed_through(state):
    queue.add("a", "/b/a", "/w/a", [1])
    fake = Fake(ends={"a": (0, "READY")}, landed_rc=1)
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    item = queue.load()[0]
    assert item["state"] == "blocked" and "no READY" in item["why"] and fake.landed_calls == [("head-a", True)]


def test_once_does_one_pass_and_the_verb_prints_the_table(state, capsys):
    queue.add("a", "/b/a", "/w/a", [1])
    fake = Fake(ends={"a": (0, "")})
    assert queue.run(fake.procs, workers_n=1, push=False, once=True, out=lambda s: None) == 0
    assert queue.load()[0]["state"] == "running", "one tick only"
    assert cli.main(["queue", "--state", str(state / "s")]) == 0
    assert capsys.readouterr().out.startswith("a\trunning\t#1\t-\t-\t")


def test_workers_comes_from_the_rules_file_and_defaults_to_one(state, tmp_path):
    assert queue.workers(state) == 2 and queue.workers(tmp_path / "nowhere") == 1


def test_the_real_landed_call_names_the_items_own_verdict_store(state):
    """`builder work --name <id>` writes verdicts-<id>.json; the landing must read that one, not a shared verdicts.json."""
    argv = queue.landed_argv(state, {"id": "step-1.1", "head": "abc1234def"}, True)
    assert argv[3:5] == ["landed", "abc1234def"] and argv[argv.index("--verdicts") + 1] == str(state / "s" / "verdicts-step-1.1.json") and argv[-1] == "--push"


def test_the_watch_page_shows_the_queue(state):
    from fichero_builder import watch

    queue.add("step-2.1", "/b", "/w", [9], depends_on=["step-1.1"])
    html = watch.render(journal.read())
    assert "step-2.1" in html and ">queued<" in html and "step-1.1" in html and "#9" in html
    json.loads(queue.path().read_text())
