"""The ceiling run: one frontier cloud model on the open pages (#6978, `hands.ceiling.open-pages-only`).

`read_hand` loads one manifest file through `manifest.load` without `private=True`, so a file holding a licence the
committed manifest does not accept raises `ManifestError`; it does not read the environment variable that names the
private manifest. `refuse_unless_open` raises `CeilingRefused` for a hand whose licence is not open or whose row does
not say the pages may leave this Mac, and it is called before the engine is imported. Each held-out page is then sent
by the engine's `llm.vision` inside `bound_project(project)`, so the engine's egress gate judges the call by the
answers saved in `project` (a scratch project given by the caller).

The cap (`hands.ceiling.cap-is-enforced-by-the-script`): `CAP_USD` is a constant and no argument of `read_hand` names
it, the price table or the ledger. `ceiling_prices.json` beside this file gives, per "provider/model", an estimated
price of one page and the price of an input and an output token; a model that is not in it raises `CeilingRefused`.
`ceiling_ledger.json` beside this file is a list of one entry per request, of every run. Before a request its
estimate is written to the ledger; if the ledger's sum and the estimate would pass the cap, the run exits with
"stopped at the cap: N of M pages read" and the request is not made. After the answer, the entry takes the reading
and the price of the tokens the provider reported; when it reported none, the estimate stays and stays marked. A
request the engine's gate refuses has its estimate removed; any other failure leaves the estimate in the ledger. A page
whose entry for the same model and prompt holds a reading is returned from the ledger and not sent.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path

_spec = importlib.util.spec_from_file_location("blind_hands_manifest", Path(__file__).with_name("manifest.py"))
manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(manifest)

CAP_USD = 25
PRICES = Path(__file__).with_name("ceiling_prices.json")
LEDGER = Path(__file__).with_name("ceiling_ledger.json")
PRICE_KEYS = {"estimated_usd_per_page", "input_usd_per_token", "output_usd_per_token"}


class CeilingRefused(RuntimeError):
    pass


def refuse_unless_open(hand: dict) -> None:
    """Raise CeilingRefused unless the row has an open licence and says its pages may leave this Mac."""
    if hand["licence"] not in manifest.OPEN_LICENCES:
        raise CeilingRefused(f"hand {hand['id']!r} has the licence {hand['licence']!r}, which is not open: no page is sent")
    if hand["may_leave_this_mac"] is not True:
        raise CeilingRefused(f"hand {hand['id']!r} does not say its pages may leave this Mac: no page is sent")


def _price_of(model: str) -> dict:
    price = json.loads(PRICES.read_text()).get(model)
    if not isinstance(price, dict) or PRICE_KEYS - price.keys():
        raise CeilingRefused(f"the model {model!r} has no price in {PRICES.name}: no page is sent")
    return price


def _write_ledger(entries: list[dict]) -> None:
    tmp = LEDGER.with_name(LEDGER.name + ".tmp")
    tmp.write_text(json.dumps(entries, indent=1))
    os.replace(tmp, LEDGER)


def read_hand(hand_id: str, images: dict[str, str], *, project: Path, config, prompt: str,
              manifest_path: Path = manifest.COMMITTED) -> dict[str, str]:
    """`{page id: the model's reading}` for the hand's held-out pages; `images` maps a page id to its image URL."""
    hands = {h["id"]: h for h in manifest.load(manifest_path)["hands"]}
    if hand_id not in hands:
        raise CeilingRefused(f"hand {hand_id!r} is not in the manifest {Path(manifest_path).name}: no page is sent")
    hand = hands[hand_id]
    refuse_unless_open(hand)
    pages = {page: images[page] for page in hand["held_out"]}
    model = f"{config.provider}/{config.model}"
    price = _price_of(model)

    from fichero_server import llm
    from fichero_server.recipes.places import bound_project

    entries: list[dict] = json.loads(LEDGER.read_text()) if LEDGER.exists() else []
    readings: dict[str, str] = {}
    with bound_project(project):
        for page, image in pages.items():
            key = hashlib.sha256(json.dumps([model, prompt, page]).encode()).hexdigest()
            done = [e for e in entries if e["key"] == key and e["reading"] is not None]
            if done:
                readings[page] = done[0]["reading"]
                continue
            if sum(e["usd"] for e in entries) + price["estimated_usd_per_page"] > CAP_USD:
                raise SystemExit(f"stopped at the cap: {len(readings)} of {len(pages)} pages read")
            entry = {"key": key, "page": page, "model": model, "usd": price["estimated_usd_per_page"],
                     "estimated": True, "reading": None}
            entries.append(entry)
            _write_ledger(entries)
            try:
                with llm.collect_usage() as calls:
                    entry["reading"] = readings[page] = str(asyncio.run(llm.vision([image], prompt, config)))
            except llm.LocalOnlyViolationError:  # the gate's refusal: the request was not made, so its estimate goes
                entries.remove(entry)
                _write_ledger(entries)
                raise
            if calls:
                entry["usd"] = sum((u["input_tokens"] or 0) * price["input_usd_per_token"]
                                   + (u["output_tokens"] or 0) * price["output_usd_per_token"] for u in calls)
                entry["estimated"] = False
            _write_ledger(entries)
    return readings
