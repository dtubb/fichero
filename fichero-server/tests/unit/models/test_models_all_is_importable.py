"""`fichero_server.models.__all__` must name only things that exist.

A name in `__all__` with no matching attribute is invisible in every ordinary
import — `from fichero_server.models import Document` works fine — and raises
only on `from fichero_server.models import *`. So it survives indefinitely, and
it surfaces at the moment someone writes the one import form nobody uses in
review.

Live on 2026-09-26, both directions of the same mistake: `Note` was listed and
never imported (pre-existing), and `LEGACY_READING_ID_PREFIX` was added to
`__all__` while its import was left behind, in the same commit that fixed 25
other re-exports. The second was caught by checking rather than by a test,
which is why this exists.
"""

from __future__ import annotations

import fichero_server.models as models


def test_every_name_in_all_resolves() -> None:
    missing = sorted(n for n in models.__all__ if not hasattr(models, n))
    assert not missing, (
        "these names are exported but do not exist, so `from fichero_server.models "
        f"import *` raises: {missing}"
    )


def test_star_import_actually_works() -> None:
    """The assertion above by its real symptom, not by proxy.

    `hasattr` over `__all__` reproduces what a star-import does; running one is
    the artefact rather than the reasoning about it, and costs nothing.
    """
    namespace: dict[str, object] = {}
    exec("from fichero_server.models import *", namespace)  # noqa: S102
    assert "Document" in namespace


def test_all_is_not_empty() -> None:
    """A guard over an empty list passes while proving nothing — and `models` is
    the package's import surface, so an empty `__all__` would be a real defect
    rather than merely an untested one."""
    assert len(models.__all__) > 100
