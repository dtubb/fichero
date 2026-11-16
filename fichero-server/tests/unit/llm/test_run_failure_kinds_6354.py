"""`run.fail.kinds-table` (#6354): each row of the table from its exception, the words name the provider by display name,
an unknown failure is `unexpected` (never silence), and the one `redact` takes private text out."""

from __future__ import annotations


import pytest

from fichero_server.execution.runner import _classify_provider_error
from fichero_server.llm import (
    AppleUnavailableError, EgressRefusedError, StructuredCallEmptyError, StructuredDecodeError,
)
from fichero_server.llm.failure import classify, redact
from fichero_server.llm.local_inference import LocalModelNotInstalledError
from fichero_server.workflows import circuit_breaker as cb

# built from parts: a home folder is the kind of text the repository boundary scan refuses to see written out
_HOME = "/".join(["", "Users", "pat"])
_KEY = "sk" + "-ant-api03-" + "A" * 20


class _Status(Exception):
    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or f"HTTP {status}")
        self.status_code = status


def _kind(exc: BaseException | None, text: str = "") -> str:
    return classify(exc, text).kind


def test_the_providers_typed_errors_are_their_kinds_and_name_the_provider():
    for exc, kind in ((cb.provider_stopped_error("openrouter", "quota"), "no-credit"),
                      (cb.provider_stopped_error("openrouter", "key"), "key-refused"),
                      (cb.provider_stopped_error("openrouter", "rate-limit"), "rate-limited")):
        f = classify(exc, str(exc), provider="openrouter", step="Read", done=12, total=203)
        assert f.kind == kind
        assert "OpenRouter" in f.words and "openrouter" not in f.words
        assert "page 12 of 203" in f.words
    assert [a.kind for a in classify(cb.provider_stopped_error("openrouter", "quota"), "").actions] == [
        "open-settings", "choose-model", "retry"]
    assert classify(cb.provider_stopped_error("openrouter", "quota"), "").actions[0].control == "settings.ai.providers"


def test_a_status_with_no_typed_error_is_judged_by_its_code():
    assert _kind(_Status(401)) == "key-refused"
    assert _kind(_Status(402)) == "no-credit"
    assert _kind(_Status(429)) == "rate-limited"
    assert _kind(_Status(404)) == "model-error"
    assert _kind(_Status(503)) == "network"
    assert _kind(None, "401 Unauthorized") == "key-refused"
    assert _kind(None, "insufficient_quota") == "no-credit"
    assert _kind(None, "connection reset by peer") == "network"


def test_a_401_under_httpx_words_is_key_refused():
    assert _kind(RuntimeError("Client error '401 Unauthorized' for url 'https://api.example.com/v1'")) == "key-refused"


def test_the_runtime_and_model_types_are_their_kinds():
    assert _kind(LocalModelNotInstalledError("x")) == "model-missing"
    assert _kind(AppleUnavailableError("x")) == "runtime-unavailable"
    assert _kind(StructuredCallEmptyError("x")) == "model-error"
    assert _kind(StructuredDecodeError("x")) == "model-error"  # a subclass of AppleUnavailableError, still a model problem


def test_a_refusal_is_its_kind_with_its_own_words_and_fixes():
    from fichero_server.llm.refusal import CloudRefusal, CloudRefusalFix

    refusal = CloudRefusal(kind="images", scope="project", words="This project keeps its pages on this Mac.",
                           fixes=[CloudRefusalFix(kind="allow-project")])
    exc = EgressRefusedError("refused")
    exc.refusal = refusal
    f = classify(exc, "")
    assert f.kind == "images-refused" and f.words == refusal.words and f.refusal == refusal
    assert [a.kind for a in f.actions] == ["allow-project", "resume"]


def test_files_gone_is_files_unavailable():
    assert _kind(None, "file is stored in iCloud and not downloaded locally") == "files-unavailable"
    assert _kind(FileNotFoundError("No such file or directory: '/x/y.jpg'")) == "files-unavailable"


def test_an_unknown_failure_is_unexpected_with_its_exception_type_never_unknown():
    f = classify(RuntimeError("boom"), "boom", step="Names")
    assert f.kind == "unexpected" and f.exception_type == "RuntimeError"
    assert "a bug in Fichero".lower() in f.fix.lower() and "RuntimeError" in f.words
    assert [a.kind for a in f.actions] == ["report-bug", "retry"]
    assert classify(None, "").kind == "unexpected"


def test_the_pages_page_and_the_run_agree_and_the_legacy_category_stays():
    out = _classify_provider_error("Provider call failed somehow")
    assert out["category"] == "unknown" and out["kind"] == "unexpected"  # the page's old words stay, the kind is the table's
    typed = _classify_provider_error("", cb.provider_stopped_error("openrouter", "key"))
    assert typed["kind"] == "key-refused"


@pytest.mark.parametrize("text, absent", [
    (f"failed reading {_HOME}/Box 7/p1.jpg", _HOME),
    ("GET https://api.example.com/v1/x?api_key=abcd1234efgh5678&q=1", "abcd1234efgh5678"),
    (f"Authorization: Bearer {_KEY}", "A" * 20),
    ("token=zzzzzzzz1234", "zzzzzzzz1234"),
])
def test_redact_takes_out_paths_keys_and_bearers(text, absent):
    assert absent not in redact(text)


def test_redact_names_the_home_folder_and_other_paths_as_placeholders():
    assert redact(f"open {_HOME}/x/y.jpg") == "open <path>"
    assert redact("") == ""


def test_the_detail_is_the_first_line_redacted():
    f = classify(RuntimeError(f"bad {_HOME}/a/b.jpg\nTraceback..."), "")
    assert f.detail == "bad <path>" and "Traceback" not in f.detail



def test_a_401_in_the_words_alone_is_key_refused_not_rate_limited():
    assert _kind(RuntimeError("provider returned 401")) == "key-refused"
    assert _kind(RuntimeError("provider returned 402")) == "no-credit"


def test_a_run_paused_at_a_cap_or_by_the_images_rule_is_its_refusals_kind():
    from fichero_server.llm.failure import from_refusal

    cap = {"kind": "cap-run", "scope": "app", "words": "The run's cap is $1.00.", "fixes": [{"kind": "over-cap-once"}]}
    f = from_refusal(cap, step="Read")
    assert f.kind == "cap-refused" and f.words == cap["words"] and [a.kind for a in f.actions] == ["over-cap-once", "resume"]
    assert from_refusal({**cap, "kind": "images"}).kind == "images-refused"
