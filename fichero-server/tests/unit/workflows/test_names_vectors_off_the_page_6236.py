"""#6236: a new name's vector is written off the page's thread, once.

WHY: the M4 rerun stalled in the names step at page 77/104 with the step's thread inside upsert_entity ->
entity_vectors.index_entity: a db.get, an embed and a LanceDB delete + add per new name, on the page's own thread,
where the page's time limit (checked between names) cannot cut it. The entity's save already embeds it (the post-save
hook, off-thread when a loop runs), so each name was embedded and written twice, from two Database instances.
"""

from __future__ import annotations

import asyncio
import threading
import time

from fichero_server.db import Database
from fichero_server.models.knowledge import EntityType
from fichero_server.workflows.tools._entity_writer import upsert_entity


def test_a_new_name_is_embedded_once_and_not_on_the_pages_thread_6236(db, monkeypatch):
    embedded_on: list[str] = []

    def slow_embed(self, entities, **kwargs):
        embedded_on.append(threading.current_thread().name)
        time.sleep(1.0)  # an embed + LanceDB write on a grown table
        return len(entities)

    monkeypatch.setattr(Database, "embed_entities", slow_embed)

    async def the_names_step() -> tuple[float, str]:
        upsert_entity(db, canonical_name="Pedro Gonzalez", entity_type=EntityType.person)  # the page's first name
        started = time.monotonic()
        upsert_entity(db, canonical_name="Anna Maria", entity_type=EntityType.person)
        return time.monotonic() - started, threading.current_thread().name

    took, page_thread = asyncio.run(the_names_step())  # run() waits for the background embeds to finish

    assert took < 0.5, f"writing one name waited {took:.2f} s on its vector"
    assert len(embedded_on) == 2, f"two names were embedded {len(embedded_on)} times"
    assert page_thread not in embedded_on
