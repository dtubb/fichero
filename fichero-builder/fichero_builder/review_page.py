"""The owner's review list (what to test in each build, a verdict per item): `<state>/review.json` = {"items": [...]}, read and written by
`builder review add|set|list` and the console's Review page (GET /review, GET and POST /api/review). Stdlib only.

An item: id, title, area, build, how (steps), why, issue (URL), status, note, order, added, and updatedAt once a verdict is set.
ponytail: one writer at a time is assumed (a person's click or the manager's verb); a lock file comes if two ever race."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from fichero_builder import journal

STATUSES = ("to-test", "works", "polish", "bug", "n/a")
ID = re.compile(r"[a-z0-9][a-z0-9._-]*")


def path() -> Path:
    return journal.STATE / "review.json"


def load() -> dict:
    """{"items": [...]}; no file is an empty list, an unreadable one is refused (never overwritten by the next write)."""
    try:
        data = json.loads(path().read_text())
    except FileNotFoundError:
        return {"items": []}
    except (OSError, ValueError) as e:
        raise ValueError(f"the review file {path().name} is unreadable: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"the review file {path().name} has no items list")
    return data


def _save(data: dict) -> None:
    tmp = path().with_suffix(".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(tmp, path())


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _check_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"status {status!r} is not one of {', '.join(STATUSES)}")


def add(item_id: str, title: str = "", area: str = "", build: str = "", how: list[str] | None = None, why: str = "", issue: str = "",
        status: str = "to-test", order: int | None = None, now: str = "") -> dict:
    """A new item; the order defaults to one above the highest, so it lists first among the to-test."""
    if not ID.fullmatch(item_id or ""):
        raise ValueError(f"id {item_id!r} is not a word of lowercase letters, digits, dots and dashes")
    if not title.strip():
        raise ValueError("an item needs a title")
    _check_status(status)
    data = load()
    if any(i.get("id") == item_id for i in data["items"]):
        raise ValueError(f"review item {item_id} already exists")
    item = {"id": item_id, "title": title.strip(), "area": area, "build": build, "how": list(how or []), "why": why, "issue": issue, "status": status,
            "note": "", "order": max([int(i.get("order", 0)) for i in data["items"]] + [0]) + 1 if order is None else int(order), "added": (now or _now())[:10]}
    data["items"].append(item)
    _save(data)
    return item


def set_item(item_id: str, status: str | None = None, note: str | None = None, now: str = "") -> dict:
    """One verdict: a status, a note or both; stamps updatedAt."""
    if status is not None:
        _check_status(status)
    data = load()
    item = next((i for i in data["items"] if i.get("id") == item_id), None)
    if item is None:
        raise ValueError(f"no review item {item_id}")
    if status is None and note is None:
        raise ValueError("set needs a status or a note")
    broke = status == "bug" and item.get("status") != "bug"
    noted = bool(note and str(note).strip() and str(note) != item.get("note", ""))
    if status is not None:
        item["status"] = status
    if note is not None:
        item["note"] = str(note)
    item["updatedAt"] = now or _now()
    _save(data)
    if broke or noted:
        act(item, broke)
    return item


def _gh(*args: str) -> tuple[int, str]:
    import subprocess
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def act(item: dict, broke: bool) -> None:
    """The owner's verdict reaches the work (2026-11-27: a note only sat in review.json): the note as a comment on the item's issue,
    reopened when marked broken (`bug`); one `review-verdict` row; one manager alert carrying the note."""
    note = item.get("note", "").strip()
    said = []
    if url := item.get("issue", ""):
        text = f"Owner, on the review list ({item['id']}, build {item.get('build') or '-'}): " + ("marked broken. " if broke else "") + (note or "")
        rc, out = _gh("issue", "comment", url, "--body", text.strip())
        said.append("commented" if rc == 0 else f"comment failed: {out[-160:]}")
        if broke:
            rc, out = _gh("issue", "reopen", url)
            said.append("reopened" if rc == 0 else f"reopen failed: {out[-160:]}")
    journal.append("review-verdict", item=item["id"], status=item.get("status"), issue=url, detail=f"{'; '.join(said) or 'no issue'}: {note}"[:500])
    from fichero_builder import queue
    queue.alert("-", f"review-{item['id']}", f"owner review: {item['id']} {'marked broken' if broke else 'has a note'}" + (f": {note}" if note else ""),
                url or str(path()), ["retry"])


def listing(changed_since: str = "") -> list[dict]:
    """To-test first, then the rest; highest order first within a status. `changed_since`: only items whose verdict was set after that ts."""
    items = [i for i in load()["items"] if not changed_since or str(i.get("updatedAt", "")) > changed_since]
    return sorted(items, key=lambda i: (i.get("status") != "to-test", -int(i.get("order", 0))))


def line(i: dict) -> str:
    return f"{i['id']}  [{i.get('status', '?')}]  {i.get('title', '')}" + (f"  note: {i['note']}" if i.get("note") else "") + (f"  (updated {i['updatedAt']})" if i.get("updatedAt") else "")


def main(a) -> int:
    """`builder review add|set|list` (the review page's verbs)."""
    try:
        if a.action == "add":
            if not a.area:
                raise ValueError("add needs an id: builder review add <id> --title ...")
            i = add(a.area, a.title or "", a.where, a.build, a.how, a.why, a.issue, a.status or "to-test", a.order)
            print(f"added {i['id']} (order {i['order']})")
        elif a.action == "set":
            if not a.area:
                raise ValueError("set needs an id: builder review set <id> --status ... [--note ...]")
            print(line(set_item(a.area, a.status, a.note)))
        else:
            for i in listing(a.changed_since or ""):
                print(line(i))
    except ValueError as e:
        print(f"REFUSED: {e}")
        return 1
    return 0
