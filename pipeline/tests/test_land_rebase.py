"""pipeline.land-rebases-and-reuses-the-review: a moved base is rebased onto; the same patch-id reuses the review."""
from __future__ import annotations

from pipeline import core, runner
from pipeline.tests.conftest import git
from pipeline.tests.test_runner import origin_head, reviewed_item


def move_base(scratch, name="x.txt", text="x"):
    other = scratch["tmp"] / f"other-{name}"
    git(scratch["tmp"], "clone", "-q", str(scratch["origin"]), str(other))
    (other / name).write_text(text)
    git(other, "add", ".")
    git(other, "-c", "user.name=M", "-c", "user.email=m@example.com", "commit", "-qm", f"moved {name}")
    git(other, "push", "-q", "origin", "HEAD:integration")
    return origin_head(scratch)


def test_a_moved_base_is_rebased_the_review_reused_and_the_item_lands(scratch, issues, fake_coder, monkeypatch):
    old = reviewed_item(scratch, fake_coder, monkeypatch)["sha"]
    moved = move_base(scratch)
    monkeypatch.setattr(core, "DRY_RUN", False)
    monkeypatch.setattr(core, "review", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the review must be reused, not rerun")))
    out = runner.land("1001")
    it = core.state()["items"]["1001"]
    assert out["landed"] is True and out["sha"] != old and it["state"] == "pushed"
    assert origin_head(scratch) == out["sha"] and git(scratch["origin"], "rev-parse", f"{out['sha']}^") == moved


def test_a_changed_patch_goes_back_to_review_and_does_not_land(scratch, issues, fake_coder, monkeypatch):
    reviewed_item(scratch, fake_coder, monkeypatch)
    moved = move_base(scratch)
    monkeypatch.setattr(core, "DRY_RUN", False)
    monkeypatch.setattr(runner, "_patch_id", lambda wt, lo, hi: f"{lo}{hi}")  # every diff differs
    out = runner.land("1001")
    assert out["landed"] is False and core.state()["items"]["1001"]["state"] == "checked" and origin_head(scratch) == moved


def test_a_rebase_conflict_is_sent_back_to_the_coder(scratch, issues, fake_coder, monkeypatch):
    it = reviewed_item(scratch, fake_coder, monkeypatch)
    changed = git(scratch["tmp"], "-C", str(scratch["repo"]), "diff", "--name-only", "origin/integration", it["sha"]).split()[0]
    moved = move_base(scratch, changed, "conflicting\n")
    monkeypatch.setattr(core, "DRY_RUN", False)
    out = runner.land("1001")
    st = core.state()["items"]["1001"]
    assert out["landed"] is False and st["state"] == "coding" and "rebase" in st["retry_text"] and origin_head(scratch) == moved
