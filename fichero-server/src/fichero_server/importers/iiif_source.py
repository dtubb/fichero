"""A folder bound to a IIIF source: imported by reference as a job, refreshed, and read at a step's size (#5671).

Spec: `source/iiif.md`, `iiif.folder.source`, `iiif.scale.million-pages`, `iiif.import.as-a-job`,
`iiif.run.local-step-fetches-its-size`.

* **Import is a job** (`import-iiif`, the network lane, in Activity): the manifest or collection is read with the
  polite fetcher (`media.iiif_fetch.PoliteFetcher`: a few requests per host, backoff on 429 and 503), Presentation 2
  or 3 (`iiif_import.parse_iiif_url`), and each canvas becomes a page **by reference**: its canvas id, label, size
  and Image API service, no image fetched. The rows are written 1,000 to an insert straight into the project, in the shape
  the manifest importer gives a page (`manifest_import.document_payload`, one shape), so 30,000 canvases take
  seconds, not a request each.
* **The folder remembers its source** (`metadata.iiif_source`) and is **refreshed** by the same job: a canvas already
  in the folder (by its canvas id) is never made twice, new ones are added in the source's order. A restarted job is
  therefore a resumed one. Canvases the source no longer lists are counted, never deleted (a person's work hangs on
  them).
* **Images are fetched when a step needs them**, at the size it reads (`step_image`): the Image API's own resize,
  through the polite fetcher (so at most a few at once per server), into a bounded cache under the project's storage
  that evicts the oldest past its share.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

IMPORT_KIND = "import-iiif"
BATCH = 1000
#: The longest side a step on this Mac reads a remote page at (a reader's own resize happens after).
STEP_LONGEST = 2400
#: The bounded cache of step-sized images is a share of free disk with a floor (ruled 2026-10-04, #5323).
STEP_CACHE_SHARE = 0.10
STEP_CACHE_FLOOR = 1024**3


def bound_folder(db: Any, url: str) -> Any | None:
    """The live folder bound to this source, if one is."""
    from fichero_server.models import DocType, Document

    return next((d for d in db.query(Document, doc_type=DocType.folder)
                 if d.deleted_at is None and (d.metadata or {}).get("iiif_source") == url), None)


def import_source(db: Any, url: str, *, folder_id: str | None = None, name: str | None = None, fetcher: Any = None,
                  say=lambda words: None, max_manifests: int | None = None) -> dict[str, Any]:
    """Import (or refresh) a IIIF manifest or collection into its bound folder, by reference. Returns what it did."""
    from fichero_server.core.timeutil import utc_now
    from fichero_server.importers.iiif_import import _label_text, parse_iiif_url
    from fichero_server.importers.manifest_import import document_payload
    from fichero_server.models import DocType, Document

    say("Reading the IIIF source")
    parsed = parse_iiif_url(url, fetcher=fetcher, max_manifests=max_manifests)
    collection, canvases = parsed.nodes[0], parsed.nodes[1:]
    if not canvases:
        raise ValueError(f"No canvases found at {url}")
    folder = db.get(Document, folder_id) if folder_id else bound_folder(db, url)
    if folder is None:
        folder = Document(name=name or collection.get("name") or _label_text(collection) or "IIIF",
                          doc_type=DocType.folder, metadata={"iiif_source": url})
        db.save(folder)
    elif (folder.metadata or {}).get("iiif_source") != url:
        folder = folder.model_copy(update={"metadata": {**(folder.metadata or {}), "iiif_source": url}})
        db.save(folder)
    have = {(d.metadata or {}).get("iiif_id") for d in db.query(Document, parent_id=folder.id) if d.deleted_at is None}
    listed = {c["metadata"]["iiif_id"] for c in canvases}
    fresh = [c for c in canvases if c["metadata"]["iiif_id"] not in have]
    total, made = len(fresh), 0
    for start in range(0, total, BATCH):
        made += db.save_many([Document.model_validate({**document_payload(node, folder.id),
                                                      "sequence": node.get("sequence"),
                                                      "page_label": node.get("page_label")})
                              for node in fresh[start:start + BATCH]], new=True)
        say(f"Importing from IIIF: {made:,} of {total:,} new canvases")
    withdrawn = len({h for h in have if h} - listed)
    folder = db.get(Document, folder.id)
    metadata = {**(folder.metadata or {}), "iiif_source": url, "iiif_refreshed_at": utc_now().isoformat(),
                "iiif_canvases": len(listed), "iiif_withdrawn": withdrawn,
                "iiif_rights": collection.get("metadata", {}).get("iiif_rights")}
    db.save(folder.model_copy(update={"metadata": metadata}))
    return {"folder_id": folder.id, "canvases": len(listed), "added": made, "already_here": len(listed) - made,
            "withdrawn": withdrawn, "manifests": parsed.manifests_seen, "warnings": parsed.warnings}


# --- the job ----------------------------------------------------------------------------------------------------


def start(db: Any, url: str, *, folder_id: str | None, started_by: str, max_manifests: int | None = None) -> str:
    """Queue the import (or refresh) as one job in Activity; returns its id."""
    import json
    import uuid

    from fichero_server.execution import jobs

    register_job_kinds()
    return jobs.enqueue(db, IMPORT_KIND, f"iiif:{uuid.uuid4().hex[:12]}", started_by=started_by, watched=True,
                        detail=json.dumps({"url": url, "folder_id": folder_id, "max_manifests": max_manifests}))


def register_job_kinds() -> None:
    from fichero_server.execution import jobs

    if IMPORT_KIND not in jobs.KINDS or jobs.KINDS[IMPORT_KIND].run is None:
        jobs.register_kind(IMPORT_KIND, _run, model=None, lane="network", name="Import from IIIF")


def _run(db: Any, subject: str) -> dict[str, Any]:
    import json

    from fichero_server.execution import jobs

    job_id = jobs.current_job_id() or jobs.job_id_for(db, IMPORT_KIND, subject)
    asked = json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}")
    done = import_source(db, asked["url"], folder_id=asked.get("folder_id"), max_manifests=asked.get("max_manifests"),
                         say=lambda words: jobs.say(db, job_id, words))
    jobs.save_detail(db, job_id, json.dumps({**asked, "result": done}),
                     reason=(f"Imported {done['added']:,} new canvases from IIIF; {done['already_here']:,} were here"
                             + (f"; {done['withdrawn']:,} no longer listed" if done["withdrawn"] else "")))
    return done


# --- a step's image ---------------------------------------------------------------------------------------------


_FETCHER = None


def step_image(doc: Any, package: Path, *, longest: int = STEP_LONGEST, fetcher: Any = None) -> Path | None:
    """A page imported by reference, fetched at the size a step reads it (the Image API's resize), kept in the
    bounded cache; None when it has no service or the server cannot be reached (the step then says the page could
    not be fetched)."""
    global _FETCHER
    service = (doc.metadata or {}).get("iiif_service") if isinstance(doc.metadata, dict) else None
    if not service:
        return None
    from fichero_server.media.iiif_fetch import FetchFailed, PoliteFetcher, image_url, urllib_get

    cache = package / "storage" / "iiif-steps" / str(longest)
    dest = cache / doc.id[:2].lower() / f"{doc.id}.jpg"
    if dest.exists():
        os.utime(dest)  # recently used: kept longest
        return dest
    if fetcher is None:
        if _FETCHER is None:
            _FETCHER = PoliteFetcher(get=urllib_get, retries=3)
        fetcher = _FETCHER
    try:
        data = fetcher.fetch(image_url(str(service), longest=longest))
    except (FetchFailed, OSError):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    _evict(package / "storage" / "iiif-steps")
    return dest


def _evict(root: Path, budget: int | None = None) -> None:
    """Drop the least recently used step images past the budget (a share of free disk, with a floor). ponytail: a
    walk per fetch; keep a running total if the cache ever holds tens of thousands of images."""
    if budget is None:
        import shutil

        budget = max(STEP_CACHE_FLOOR, int(shutil.disk_usage(root).free * STEP_CACHE_SHARE))
    files = sorted((p for p in root.rglob("*.jpg")), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    for path in files:
        if total <= budget:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)
