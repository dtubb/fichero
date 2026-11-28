"""The ceiling run: one frontier cloud model on the open pages (#6978, `hands.ceiling.open-pages-only`).

`read_hand` loads one manifest file through `manifest.load` without `private=True`, so a file holding a licence the
committed manifest does not accept raises `ManifestError`; it does not read the environment variable that names the
private manifest. `refuse_unless_open` raises `CeilingRefused` for a hand whose licence is not open or whose row does
not say the pages may leave this Mac, and it is called before the engine is imported. Each held-out page is then sent
by the engine's `llm.vision` inside `bound_project(project)`, so the engine's egress gate judges the call by the
answers saved in `project` (a scratch project given by the caller).
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("blind_hands_manifest", Path(__file__).with_name("manifest.py"))
manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(manifest)


class CeilingRefused(RuntimeError):
    pass


def refuse_unless_open(hand: dict) -> None:
    """Raise CeilingRefused unless the row has an open licence and says its pages may leave this Mac."""
    if hand["licence"] not in manifest.OPEN_LICENCES:
        raise CeilingRefused(f"hand {hand['id']!r} has the licence {hand['licence']!r}, which is not open: no page is sent")
    if hand["may_leave_this_mac"] is not True:
        raise CeilingRefused(f"hand {hand['id']!r} does not say its pages may leave this Mac: no page is sent")


def read_hand(hand_id: str, images: dict[str, str], *, project: Path, config, prompt: str,
              manifest_path: Path = manifest.COMMITTED) -> dict[str, str]:
    """`{page id: the model's reading}` for the hand's held-out pages; `images` maps a page id to its image URL."""
    hands = {h["id"]: h for h in manifest.load(manifest_path)["hands"]}
    if hand_id not in hands:
        raise CeilingRefused(f"hand {hand_id!r} is not in the manifest {Path(manifest_path).name}: no page is sent")
    hand = hands[hand_id]
    refuse_unless_open(hand)
    pages = {page: images[page] for page in hand["held_out"]}

    from fichero_server import llm
    from fichero_server.recipes.places import bound_project

    readings: dict[str, str] = {}
    with bound_project(project):
        for page, image in pages.items():
            readings[page] = str(asyncio.run(llm.vision([image], prompt, config)))
    return readings
