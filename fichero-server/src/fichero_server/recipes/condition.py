"""The condition of the pages: the one list About the Material asks from (`designer.material.condition-asked`, #6052, #6295).

Tick boxes, none ticked by default. The list, the words and the one line of help (what Fichero does about it) are the engine's:
the app shows what `GET /api/recipes/questions` says and invents none. Saved as `answers.condition`, a list of ids."""
from __future__ import annotations

#: (id, name, what Fichero does about it, in one line). Order is the order they are asked in.
CONDITIONS: tuple[tuple[str, str, str], ...] = (
    ("faded", "Faded ink", "Fichero raises the contrast of the faded pages before it finds the lines."),
    ("torn", "Torn or missing parts", "Fichero reads what is there and marks the pages that have gaps for your review."),
    ("stains", "Stains", "Fichero reads through them and asks a second model to check the lines they touch."),
    ("show-through", "Show-through from the other side",
     "Fichero suppresses the ink of the other side before it finds the lines."),
    ("water-damage", "Water damage", "Fichero reads what it can and marks the pages it is unsure of for your review."),
    ("tight-binding", "Tight binding (text curves into the gutter)", "Fichero flattens the curve before it finds the lines."),
    ("ruled-lines", "Ruled or printed lines under the writing", "Fichero removes the ruling before it finds the lines."),
)
IDS: tuple[str, ...] = tuple(c[0] for c in CONDITIONS)


def normalise(value: object) -> tuple[list[str], list[str]]:
    """(the ticked ids in the list's order with unknown ones last, the refusals in words). None or nothing ticked is a list of none."""
    ticked = list(dict.fromkeys(value if isinstance(value, (list, tuple)) else [] if value is None else [value]))
    unknown = [c for c in ticked if c not in IDS]
    refused = [f"A condition of the pages is {', '.join(IDS)}; not {', '.join(map(repr, unknown))}."] if unknown else []
    return [c for c in IDS if c in ticked] + unknown, refused
