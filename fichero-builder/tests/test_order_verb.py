"""The owner's build order (console Milestones, owner 2026-11-02): one ordered list the owner rearranges; Save is one commit
on branch build-order, queued as a tiny external batch the loop checks and lands; saving until it lands."""
from __future__ import annotations

import subprocess

from fichero_builder import journal, order, queue

TEXT = """# Build order

> header

## In order

1. `alpha` — first. Spec: a.md
2. `beta` — second
3. `gamma` — third

## Parked

- `Bugs - *`, `delta` — buckets.
- `cand 14` — not now.
"""


def test_rewrite_renumbers_parks_and_unparks_keeping_each_lines_text():
    new = order.rewrite(TEXT, ["gamma", "alpha", "delta"], ["beta"], today="2026-11-02")
    assert "1. `gamma` — third\n2. `alpha` — first. Spec: a.md\n3. `delta`\n" in new, new
    assert "- `Bugs - *`, — buckets." not in new and "- `Bugs - *`" in new and "`delta` — buckets" not in new, "delta left its bucket line"
    assert "- `beta` — parked by the owner 2026-11-02." in new and "- `cand 14` — not now." in new
    try:
        order.rewrite(TEXT, ["alpha", "alpha"], [])
        raise AssertionError("a name twice must refuse")
    except ValueError:
        pass


def test_save_commits_on_the_build_order_branch_queues_a_tiny_batch_and_refuses_while_one_is_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")

    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    seed = tmp_path / "seed"
    (seed / "docs/contributor_manual/specs").mkdir(parents=True)
    (seed / order.FILE).write_text(TEXT)
    g(seed, "init", "-q", "-b", "integration"), g(seed, "add", "."), g(seed, "commit", "-qm", "base")
    g(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    root = tmp_path / "checkout"
    g(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(root))
    rc, out = order.save(root, ["beta", "alpha", "gamma"], [])
    assert rc == 0 and "saving" in out, out
    wt = tmp_path / "build-order"
    assert g(wt, "rev-parse", "--abbrev-ref", "HEAD") == "build-order"
    assert "1. `beta` — second" in (wt / order.FILE).read_text()
    msg = g(wt, "log", "-1", "--format=%B")
    assert msg.startswith("docs(build-order): owner reorders: beta, alpha, gamma") and "Directed-By: the maintainer" in msg and "Co-Authored-By: Claude" in msg
    (lane,) = [x for x in queue.load() if x["id"] == "build-order"]
    assert lane["kind"] == "external" and lane["steps"][0]["state"] == "done" and lane["steps"][0]["head"] == g(wt, "rev-parse", "HEAD")
    assert order.pending()
    rc, out = order.save(root, ["alpha", "beta", "gamma"], [])
    assert rc == 1 and "still saving" in out
    assert (root / order.FILE).read_text() == TEXT, "the checkout's own file is untouched: the loop uses the landed order"
