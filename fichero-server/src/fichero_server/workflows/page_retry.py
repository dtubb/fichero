"""Which page failures pass by themselves, so the page is read once more before it counts as failed (#5555).

On the 8 GB Air three pages of a ten-page run failed "local model unavailable" while the model was loading
or memory was short, and nobody read them again. A page whose failure names a passing cause is read a
second time, once, after a short pause (`builder._make_parallel_node_function`); a second failure is the
page's failure, with its reason, and the run's account offers to read the failed pages as one action.

Passing causes: the model is still loading or its server is starting or not ready, memory was short (a
memory wait that ran out, #5537), the connection to the model server dropped, or the local model server
stopped while reading (#5537: read again once the server has restarted), or the model stopped answering
(nothing new for the no-progress window, #5537). Never a cause that a
second try cannot change: a model too big for this Mac, a model not installed, a refusal, a bad request.
"""
from __future__ import annotations

import re

#: Seconds before the second read: long enough for a model server to come up.
RETRY_AFTER_SECONDS = 10.0

_PASSING = re.compile(
    r"not ready|still loading|is loading|model (?:is )?loading|loading the model|is starting|starting up"
    r"|did not start .* in time|stopped before it was ready"
    r"|memory is tight|waited \d+ minutes? for memory|connection (?:refused|reset|error)|server disconnected"
    r"|temporarily unavailable|server stopped while reading|model stopped answering",
    re.IGNORECASE,
)
#: Causes another try cannot change, even when their words also match the above.
_LASTING = re.compile(
    r"more than this mac's|not installed|use a smaller model|unknown provider|invalid|refused this", re.IGNORECASE)


def is_passing_cause(cause: object) -> bool:
    """True when a page's failure names a cause that passes by itself."""
    text = str(cause or "")
    return bool(text) and bool(_PASSING.search(text)) and not _LASTING.search(text)
