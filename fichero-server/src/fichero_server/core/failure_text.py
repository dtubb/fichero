"""A failure said in words, never as an empty string (#5534).

Some exceptions carry no message: a bare `TimeoutError()`, `concurrent.futures.CancelledError()`,
an `httpx` error raised with an empty string. `str(exc)` of one is "", and every check downstream
reads the error by its truthiness, so a page whose read failed this way was counted as read: the
log said "Vision processing failed for SM_NPQ_C01_004.jpg: " and the run ended "completed" with
nothing written. This names the failure by its type, and by its cause when it has one.
"""
from __future__ import annotations

#: How many causes deep a message is looked for.
_CHAIN_DEPTH = 3


def failure_text(exc: BaseException) -> str:
    """`str(exc)` when it says something; otherwise the exception's type, and the first cause in
    its chain that says something (`raise … from …`, or the exception it was raised while
    handling). Never empty."""
    said = str(exc).strip()
    if said:
        return said
    text = f"{type(exc).__name__} (no message)"
    cause: BaseException | None = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    for _ in range(_CHAIN_DEPTH):
        if cause is None:
            break
        cause_said = str(cause).strip()
        if cause_said:
            return f"{text}, caused by {type(cause).__name__}: {cause_said}"
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    return text
