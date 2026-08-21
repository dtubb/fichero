"""The one definition of rendition order.

Every surface that flips between renditions — the preview's up/down axis, a
canvas card, an icon-view badge — must agree on what "next" means, or the
preview and the card disagree about which image comes after the original and
the user is the one who has to reconcile them. So the order is decided ONCE,
here, engine-side, and shipped in the response.

There is no natural order in the data: `Rendition` rows come back from DuckDB
in insertion order, which is import order, which is an accident. Sorting has
to be imposed, and imposing it in each client is how two clients end up with
two answers.
"""

from __future__ import annotations

from fichero_server.models import RENDITION_ROLE_PREFERENCE, Rendition

#: Anything not in RENDITION_ROLE_PREFERENCE sorts after everything that is.
_UNRANKED = len(RENDITION_ROLE_PREFERENCE)


def _rank(rendition: Rendition) -> int:
    try:
        return RENDITION_ROLE_PREFERENCE.index(rendition.role)
    except ValueError:
        return _UNRANKED


def order_renditions(renditions: list[Rendition]) -> list[Rendition]:
    """Primary first, then role preference, then a deterministic tiebreak.

    The tiebreak is `(role, created_at, id)` rather than "whatever came back
    first". Two renditions with the same role — a re-run that produced a second
    enhanced pass — must not swap places between two calls, or "press down
    twice" stops being a stable gesture.

    A role the preference list has never heard of sorts last rather than
    being dropped: the staging pipeline is allowed to invent roles, and a
    rendition nobody ranked is still a rendition the user can look at.
    Silently hiding it would be the absence-read-as-answer mistake.
    """
    return sorted(
        renditions,
        key=lambda r: (
            not r.is_primary,  # False (0) sorts before True (1)
            _rank(r),
            r.role,
            r.created_at,
            r.id,
        ),
    )


def primary_rendition(renditions: list[Rendition]) -> Rendition | None:
    """The rendition a reader should open on, or None if there are none.

    `is_primary` wins when set. When nothing is marked — which is the norm for
    anything the staging pipeline did not label — the preference order decides,
    and the answer is the first of `order_renditions`.

    Returns None rather than raising: a node with no renditions is ordinary
    (a folder, a node whose bytes were never materialised), not an error. The
    CALLER decides whether that is a problem, because only the caller knows
    whether it was about to render something.
    """
    ordered = order_renditions(renditions)
    return ordered[0] if ordered else None


def displayable(renditions: list[Rendition]) -> list[Rendition]:
    """Ordered renditions whose bytes are expected to exist.

    `materialized is False` means the row references bytes that were never
    written — a referenced-but-absent staging entry. Those are kept in the
    model on purpose (a knowable state beats a path that 404s at render time)
    but a flip sequence should skip them rather than showing the user a
    placeholder every second press.
    """
    return [r for r in order_renditions(renditions) if r.materialized]
