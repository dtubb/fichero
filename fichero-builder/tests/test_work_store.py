"""builder-console.work-store.host-agnostic: milestones, issues, comments and labels go through one interface; the GitHub store runs `gh`."""
from __future__ import annotations

import json

import pytest

from fichero_builder import work_store


class FakeGh:
    def __init__(self, out: str = "[]", fail: str = ""):
        self.calls, self.out, self.fail = [], out, fail

    def __call__(self, *args: str) -> str:
        self.calls.append(list(args))
        if self.fail:
            raise work_store.StoreError(self.fail)
        return self.out


def test_the_github_store_is_a_work_store():
    assert isinstance(work_store.GithubStore(run=FakeGh()), work_store.WorkStore)


def test_milestones_and_issues_are_read_through_gh():
    gh = FakeGh(json.dumps([{"number": 7, "title": "t", "body": "b", "labels": [{"name": "x"}]}]))
    s = work_store.GithubStore(run=gh)
    assert s.issues("Builder") == [{"number": 7, "title": "t", "body": "b", "labels": ["x"]}]
    assert gh.calls[0][:4] == ["issue", "list", "--milestone", "Builder"] and "--state" in gh.calls[0]
    gh.out = json.dumps([{"title": "Builder", "open_issues": 3, "closed_issues": 4}])
    assert s.milestones() == [{"title": "Builder", "open": 3, "closed": 4}]
    assert gh.calls[1] == ["api", "repos/{owner}/{repo}/milestones?state=all&per_page=100", "--paginate"]


def test_comment_label_close_and_create_write_through_gh():
    gh = FakeGh("https://example.invalid/issues/9\n")
    s = work_store.GithubStore(run=gh)
    s.comment(7, "hello")
    s.label(7, add=["a"], remove=["b"])
    s.close(7, "landed in abc")
    assert s.create("Builder", "title", "body", ["l1", "l2"]) == 9
    assert gh.calls == [
        ["issue", "comment", "7", "--body", "hello"],
        ["issue", "edit", "7", "--add-label", "a", "--remove-label", "b"],
        ["issue", "close", "7", "--comment", "landed in abc"],
        ["issue", "create", "--milestone", "Builder", "--title", "title", "--body", "body", "--label", "l1", "--label", "l2"],
    ]


def test_a_gh_failure_is_an_error_not_an_empty_answer():
    s = work_store.GithubStore(run=FakeGh(fail="gh issue list: no network"))
    with pytest.raises(work_store.StoreError, match="no network"):
        s.issues("Builder")


def test_the_store_is_chosen_by_name_and_an_unbuilt_or_unknown_name_refuses():
    assert isinstance(work_store.open_store("github", run=FakeGh()), work_store.GithubStore)
    for name in ("github-private", "fichero", "nope"):
        with pytest.raises(work_store.StoreError, match=name):
            work_store.open_store(name)
