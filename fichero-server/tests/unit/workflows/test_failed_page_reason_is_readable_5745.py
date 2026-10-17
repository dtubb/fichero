"""#5745: a page that failed showed the bare key 'CGImageGetWidth' as its reason. A failed page's
reason is a sentence a person can read; a reason already in words is left alone."""
from fichero_server.workflows.run_progress import item_error


def test_a_bare_key_becomes_a_sentence():
    for bare in ("'CGImageGetWidth'", "CGImageGetWidth", "KeyError('CGImageGetWidth')"):
        why = item_error({"error": bare})
        assert " " in why.strip() and why.endswith("."), why
        assert "read" in why.lower()


def test_a_reason_in_words_is_unchanged():
    assert item_error({"error": "The model gave no words for this page."}) == "The model gave no words for this page."
    assert item_error({"success": False}) == "failed"
    assert item_error({"success": True}) is None
