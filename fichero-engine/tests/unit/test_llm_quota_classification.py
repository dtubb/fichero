"""Tests for #2227: _is_provider_quota_error must not misclassify context-length errors."""


from fichero.llm import _is_provider_quota_error


class _StatusExc(Exception):
    def __init__(self, msg: str, status_code: int | None = None) -> None:
        super().__init__(msg)
        if status_code is not None:
            self.status_code = status_code


def test_context_length_not_classified_as_quota_openai_style() -> None:
    exc = _StatusExc(
        "This model's maximum context length is 128000 tokens. "
        "However, you requested 150000 tokens in the input.",
        status_code=400,
    )
    is_quota, code, _ = _is_provider_quota_error(exc)
    assert not is_quota, "Context-length error should not be quota"
    assert code == 400


def test_context_length_not_classified_as_quota_anthropic_style() -> None:
    exc = _StatusExc(
        "prompt is too long: 200000 tokens > maximum context window of 100000",
        status_code=400,
    )
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert not is_quota


def test_context_window_phrase_not_classified_as_quota() -> None:
    exc = _StatusExc("exceeded context window limit", status_code=400)
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert not is_quota


def test_maximum_length_phrase_not_classified_as_quota() -> None:
    exc = _StatusExc("Input exceeds maximum length for this model", status_code=400)
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert not is_quota


def test_too_long_for_phrase_not_classified_as_quota() -> None:
    exc = _StatusExc("prompt is too long for this model", status_code=400)
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert not is_quota


# --- Real quota errors must still be detected ---


def test_real_rate_limit_classified_as_quota_429() -> None:
    exc = _StatusExc("rate limit exceeded", status_code=429)
    is_quota, code, _ = _is_provider_quota_error(exc)
    assert is_quota
    assert code == 429


def test_real_quota_exceeded_classified_as_quota() -> None:
    exc = _StatusExc("insufficient_quota: you have exceeded your plan", status_code=403)
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert is_quota


def test_too_many_requests_classified_as_quota() -> None:
    exc = _StatusExc("too many requests", status_code=429)
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert is_quota


def test_payment_required_classified_as_quota() -> None:
    exc = _StatusExc("billing limit exceeded", status_code=402)
    is_quota, code, _ = _is_provider_quota_error(exc)
    assert is_quota
    assert code == 402


def test_non_error_returns_false() -> None:
    exc = _StatusExc("unexpected server error", status_code=500)
    is_quota, _, _ = _is_provider_quota_error(exc)
    assert not is_quota
