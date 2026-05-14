"""Startup-side effects of fichero.api.main.

These are module-level side effects (env vars, warnings filters) that
must be in place before the app handles any request — verified here so
a refactor doesn't silently drop them.
"""

from __future__ import annotations

import os
import warnings


def test_lance_fork_warning_is_suppressed() -> None:
    """_install_warning_filters() silences lancedb's over-broad "lance
    is not fork-safe" advisory — it fires on every fork (including
    benign subprocess fork+exec) but the engine never
    forks-and-keeps-running-Python with lancedb open. Unrelated
    warnings still surface. (#1028)"""
    from fichero.api.main import _install_warning_filters

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _install_warning_filters()
        warnings.warn(
            "lance is not fork-safe. If you are using multiprocessing, "
            "use spawn instead.",
            UserWarning,
        )
        warnings.warn("an unrelated advisory", UserWarning)

    messages = [str(w.message) for w in caught]
    assert not any("fork-safe" in m for m in messages), (
        "the lance fork-safety warning should be suppressed"
    )
    assert any("unrelated advisory" in m for m in messages), (
        "unrelated warnings must still surface"
    )


def test_tokenizers_parallelism_disabled() -> None:
    """main.py disables the Rust tokenizer thread pool so it can't
    deadlock across a fork. (#1028 context)"""
    import fichero.api.main  # noqa: F401 — import triggers the setdefault

    assert os.environ.get("TOKENIZERS_PARALLELISM") == "false"
