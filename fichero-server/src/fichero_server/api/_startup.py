"""Side effects that MUST happen before the rest of `api.main` imports (#5051).

These three things ran inline at the top of `api/main.py`, between its imports.
That was correct — each genuinely has to happen before something below it — but
it made every later import an E402 ("module level import not at top of file"),
and eighteen blameless imports were flagged for the sins of the statements above
them. Silencing that with `# noqa` on each would have hidden a real rule behind
noise; moving the statements out removes the cause instead.

Importing this module runs them. `api.main` imports it once, before anything
that could pull in `transformers`, and its own imports are then an unbroken
block.

Nothing here is optional and nothing here is lazy: the whole point is that the
work happens at import, in this order.
"""

from __future__ import annotations

import logging
import os
import time

# Disable tokenizers parallelism so the Rust tokenizer's thread pool doesn't
# deadlock across a fork (subprocess spawns count). MUST be set before any
# import that pulls in transformers / tokenizers — which is why this module
# exists and why `api.main` imports it first.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Route the kreuzberg extraction cache to ~/Library/Caches/ and run the
# one-time legacy-location migration. Imported eagerly (not lazily via loaders)
# so the side effect fires at engine startup regardless of whether the user
# triggers an extraction this session.
from fichero_server.loaders import kreuzberg_cache  # noqa: E402,F401

# Sub-splits within `api.main`'s own import (route imports, tiered-route
# registration, lifespan pre-yield) — see #4690. Relative to that module's
# import start, not `__main__`'s epoch; `__main__`'s "FastAPI app imported"
# stamp already covers the whole of that file's import cost, this just opens
# the interval up.
#
# Stamped from HERE rather than from `api.main`, because this module is the
# first thing it imports: the epoch has to start before the imports it measures,
# and a module cannot time its own import from inside itself.
_API_MAIN_EPOCH = time.monotonic()


def api_stamp(label: str) -> None:
    """Log a millisecond offset from the start of `api.main`'s import."""
    logging.getLogger("fichero_server.api.main").info(
        "engine-launch: %s @ %.0fms (api.main)", label, (time.monotonic() - _API_MAIN_EPOCH) * 1000
    )
