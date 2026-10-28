"""#6236: a page's names step slowed past its 300 s limit late in a long run (page 87 alone took seconds).

Every new name scored itself against every stored entity of its type, re-folding each stored name and running a
full SequenceMatcher per pair, so each page cost more than the last. One more name against a few thousand stored
entities, many of them the same name under two types, stays well under a bound.
"""

from __future__ import annotations

import random
import time

from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.workflows.tools._entity_writer import _fuzzy_match_existing

_SYLLABLES = ["ma", "ri", "co", "ni", "cho", "lau", "sol", "pe", "dro", "fer", "nan", "dez", "gon", "za", "lo", "ã", "m̃"]


def _name(rng: random.Random) -> str:
    return " ".join(
        "".join(rng.choice(_SYLLABLES) for _ in range(rng.randint(2, 4))).capitalize() for _ in range(rng.randint(1, 3))
    )


def test_one_more_name_stays_under_a_bound_as_the_entities_grow_6236():
    rng = random.Random(6236)
    stored = [KnowledgeEntity(canonical_name=f"{_name(rng)} {i}", entity_type=EntityType.person) for i in range(5000)]
    needles = [_name(rng) for _ in range(20)]
    _fuzzy_match_existing(stored, needles[0])  # the stored names' keys, as a run builds them up page by page

    started = time.perf_counter()
    for needle in needles:
        _fuzzy_match_existing(stored, needle)
    per_name = (time.perf_counter() - started) / len(needles)

    assert per_name < 0.1, f"one name took {per_name:.3f} s against 5000 stored entities"


def test_the_bounds_never_change_the_match_6236():
    stored = [KnowledgeEntity(canonical_name=n, entity_type=EntityType.person) for n in
              ["Pedro Nieto", "Eugenio Córdoba", "Nicholau Ferrer", "Com̃o", "Consols"]]
    assert _fuzzy_match_existing(stored, "Eugenio Cordova").canonical_name == "Eugenio Córdoba"
    assert _fuzzy_match_existing(stored, "Nicolau Ferrer").canonical_name == "Nicholau Ferrer"
    assert _fuzzy_match_existing(stored, "Sergio Ramírez") is None
