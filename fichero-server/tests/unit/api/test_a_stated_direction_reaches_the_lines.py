"""A direction stated on a source reaches its lines through the cascade (#5147, the Genji).

WHY: the Digital Genji is vertical print, and nothing in the file says so -- no `style` or `rend`
writing-mode (checked below with lxml) -- and its lines have no shape of their own (each takes
its page's zone), so neither the file nor the line shapes can decide. The slice-9 cascade is how a
person states it: `ttb` on the source. If that statement stops reaching the lines, the Genji can
never be read top to bottom, whatever anyone says.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from tests.unit.api.test_page_text_follows_the_file import _import

GENJI = (Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
         / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml")
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _directions(client, doc_id: str) -> set[str]:
    blocks = client.get(f"/api/segments/document/{doc_id}/text").json()["blocks"]
    return {b["direction"] for b in blocks if b.get("spans")}


def test_the_file_states_no_writing_mode():
    root = etree.parse(str(GENJI)).getroot()
    stated = [el for el in root.iter() if isinstance(el.tag, str)
              and any("vertical" in (el.get(a) or "") or "writing-mode" in (el.get(a) or "")
                      for a in ("style", "rend"))]
    assert stated == []


def test_unstated_it_reads_left_to_right_and_stated_ttb_it_reads_top_to_bottom(db, client):
    doc_id = _import(db, GENJI)
    assert _directions(client, doc_id) == {"ltr"}

    registry.invoke(
        db, "source_setting.set",
        {"level": "node", "key": "direction", "value": "ttb", "target_id": doc_id}, PERSON,
    )
    assert _directions(client, doc_id) == {"ttb"}
