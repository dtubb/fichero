"""A read flag of any kind reaches the app with its reason in words (`source.read.flag-reason-in-words`, review ## 911)."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.llm.read_guard import ReadFlag, flag_words, read_flag_of


def test_a_flag_of_a_kind_nobody_wrote_words_for_gets_a_sentence_from_its_kind():
    got = flag_words({"kind": "needs-re-reading", "measure": {}})
    assert got["kind"] == "needs-re-reading" and "look it over" in got["reason"]
    assert "needs-re-reading" not in got["reason"], "never the kind's id"
    assert flag_words({})["reason"] == got["reason"]


def test_a_reason_already_in_words_is_kept_and_the_flag_is_not_changed():
    flag = {"kind": "repetition", "reason": "the model repeated itself", "measure": {}}
    assert flag_words(flag) is flag


def test_read_flag_of_returns_words_for_an_artifact_a_box_and_a_dict():
    bare = {"read_flag": {"kind": "something-new"}}
    for holder in (SimpleNamespace(data=bare), SimpleNamespace(metadata=bare), bare):
        assert "look it over" in read_flag_of(holder)["reason"] and "something" not in read_flag_of(holder)["reason"]


def test_as_data_always_carries_a_reason():
    assert "look it over" in ReadFlag("odd", "", {}).as_data()["reason"]
