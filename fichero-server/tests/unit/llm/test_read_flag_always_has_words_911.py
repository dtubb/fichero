"""A read flag of any kind reaches the app with its reason in words (`source.read.flag-reason-in-words`, review ## 911)."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.llm.read_guard import ReadFlag, flag_words, read_flag_of


def test_a_flag_of_a_kind_nobody_wrote_words_for_gets_a_sentence_from_its_kind():
    got = flag_words({"kind": "needs-re-reading", "measure": {}})
    assert got["reason"] == "this reading is flagged (needs re reading)" and got["kind"] == "needs-re-reading"
    assert flag_words({})["reason"] == "this reading is flagged"


def test_a_reason_already_in_words_is_kept_and_the_flag_is_not_changed():
    flag = {"kind": "repetition", "reason": "the model repeated itself", "measure": {}}
    assert flag_words(flag) is flag


def test_read_flag_of_returns_words_for_an_artifact_a_box_and_a_dict():
    bare = {"read_flag": {"kind": "something-new"}}
    for holder in (SimpleNamespace(data=bare), SimpleNamespace(metadata=bare), bare):
        assert read_flag_of(holder)["reason"] == "this reading is flagged (something new)"


def test_as_data_always_carries_a_reason():
    assert ReadFlag("odd", "", {}).as_data()["reason"] == "this reading is flagged (odd)"
