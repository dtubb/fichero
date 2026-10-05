"""Model cards for the recipe rules, read from the shipped seed (`recipes/seed/cards.yaml`).

`source.model.card-id` (`ai/local-runtimes.md` section 1): every card has one id,
`<runtime>:<source>@<version>`. The seed holds only facts the models' own published cards state;
an unstated fact is empty ("any" or unknown), never guessed. Cards a person or a language model
adds later (the finder) join the same list once a person has confirmed their facts.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fichero_server.recipes.assemble import Card

SEED = Path(__file__).parent / "seed" / "cards.yaml"
CARD_ID = re.compile(r"^[a-z]+:[^@\s]+@[^@\s]+$")
#: Licences that may be used without a deliberate choice (`source.model.licence-class`).
OPEN_LICENCES = frozenset({"Apache-2.0", "MIT", "CC-BY-4.0", "GPL-3.0", "BSD-3-Clause", "system"})


def _set(value) -> frozenset[str] | None:
    return None if value in (None, "any") else frozenset(value)


def kraken_reader_for(pin: dict) -> str | None:
    """The model id under which this Mac fetches and runs the Kraken reader a Zenodo pin names: the
    catalogue's id, or `kraken-zenodo-<n>` for any other reader in Kraken's repository (fetched
    through the same download job, which checks the record is a Kraken recognition model)."""
    from fichero_server.llm.kraken_runtime import KRAKEN_RECOGNITION_MODELS, reader_id_for_doi

    if not pin.get("zenodo"):
        return None
    return next((rid for rid, row in KRAKEN_RECOGNITION_MODELS.items()
                 if row.get("doi") == pin["zenodo"]), None) or reader_id_for_doi(pin["zenodo"])


def seed_cards() -> tuple[Card, ...]:
    """The cards the rules choose from: only those whose runtime is in this build."""
    return tuple(c for c in all_seed_cards() if c.runs_here)


@lru_cache(maxsize=1)
def all_seed_cards() -> tuple[Card, ...]:
    """Every seed card, those whose runtime is not in this build yet included (`runs_here` False): the
    bake-off names Tesseract for print even before it is bundled, and says why it is not scored."""
    import yaml

    rows = yaml.safe_load(SEED.read_text(encoding="utf-8"))["cards"]
    cards = []
    for row in rows:
        if not CARD_ID.match(row["id"]):
            raise ValueError(f"card id {row['id']!r} is not <runtime>:<source>@<version>")
        cards.append(Card(
            runs_here=row.get("runs_here") is not False,
            id=row["id"],
            pin=dict(row["pin"]),
            jobs=frozenset(row["jobs"]),
            scripts=_set(row.get("scripts")),
            languages=_set(row.get("languages")),
            material=frozenset(row.get("material") or ()),
            runs_on=row.get("runs_on", "this-mac"),
            open_licence=row.get("licence") in OPEN_LICENCES,
            size_gb=float(row.get("size_gb") or 0),
            memory_gb=float(row.get("memory_gb") or 0),
            trainable=bool(row.get("trainable")),
            cer_published=row.get("cer_published"),
            licence=str(row.get("licence") or ""),
            note=str(row.get("note") or ""),
        ))
    return tuple(cards)
