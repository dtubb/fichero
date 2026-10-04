"""A read package: what a reading job off the Mac needs, and nothing else (#5398 slice 2).

`compute.package.*`: the pages to read, by document id, each either an image file carried in the package
(named by its sha256) or a IIIF Image API service to fetch from (`fetch.longest` pixels on its longer
side, so images of an archive never pass through the Mac); the reading step and its model, by card;
the shards (fixed groups of sources, one job or Slurm array task each, `compute.job.array-by-shard`);
and Fichero's own runner (`remote_read/runner.py`) with the polite fetcher beside it.

* No path from the Mac crosses (`compute.package.no-paths-cross`): sources are document ids, files are
  `images/<sha256>.<ext>`.
* No key or token (`compute.package.no-secrets`): a step that needs a provider's key cannot be sent.
* The same project state and request make a byte-identical package (`compute.package.is-a-projection`):
  no timestamps, sorted keys.
* `manifest.json` is a `SyncManifest` of the package's objects with sha256 and size
  (`compute.package.is-a-sync-manifest`), so a second send carries only what is missing.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMAT = "fichero-read-package-v1"
#: Sources per shard: the spec's default (jobs-and-fine-tuning.md, open question 3), to be re-set from a
#: measurement. One process start per shard, not per page.
SHARD_SIZE = 50
#: Pixels on the longer side a reader is given; an archive's image is scaled on its server to this.
FETCH_LONGEST = 2000
RUNNER = Path(__file__).with_name("runner.py")


class NotSendable(ValueError):
    """The step cannot run off the Mac (it needs a key that never leaves it, or names no model)."""


@dataclass(frozen=True)
class ReadStep:
    """The reading a package runs: Kraken's line finder, then a reader for each line.

    `reader` is `kraken` (a Kraken recognition model, carried in the package) or `vlm` (a vision model
    in standard Hugging Face form, named by `model` and fetched where the job runs, e.g. a trained
    student's `hf` build in the person's bucket or a Hub repo).
    """

    reader: str
    card: str
    model_file: str | None = None  # kraken: the reader's file on this Mac (carried in the package)
    model: str | None = None  # vlm: where the Job finds the weights (Hub repo or bucket path)
    prompt: str | None = None
    lines_per_call: int = 1
    language: str | None = None

    def describe(self) -> dict[str, Any]:
        out = {"reader": self.reader, "card": self.card, "lines_per_call": self.lines_per_call}
        if self.reader == "kraken":
            out["model_file"] = f"models/{Path(self.model_file or '').name}"
        else:
            out.update({"model": self.model, "prompt": self.prompt, "language": self.language})
        return out


@dataclass
class ReadPackage:
    job_id: str
    sources: list[dict[str, Any]]
    shards: list[list[int]]
    skipped: list[dict[str, str]] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pages_to_read(db: Any, scope_ids: list[str]) -> list[Any]:
    """Pages under the named documents and folders, in their stored order: files and pages with an
    image here, or a IIIF service to fetch from."""
    from fichero_server.models import Document

    seen: set[str] = set()
    pages: list[Any] = []

    def visit(doc: Any) -> None:
        if doc is None or doc.id in seen or getattr(doc, "deleted_at", None):
            return
        seen.add(doc.id)
        kind = getattr(doc.doc_type, "value", doc.doc_type)
        meta = doc.metadata if isinstance(doc.metadata, dict) else {}
        if kind in ("file", "page") and (doc.path or meta.get("iiif_service")):
            pages.append(doc)
        children = sorted(db.query(Document, parent_id=doc.id),
                          key=lambda d: (d.sequence if d.sequence is not None else 1 << 30, d.name or "", d.id))
        for child in children:
            visit(child)

    for doc_id in scope_ids:
        visit(db.get(Document, doc_id))
    return pages


def build_read_package(db: Any, *, job_id: str, scope_ids: list[str], step: ReadStep, out_dir: str | Path,
                       shard_size: int = SHARD_SIZE, longest: int = FETCH_LONGEST,
                       library_root: Path | None = None) -> ReadPackage:
    """Write the package under `out_dir` (job.json, manifest.json, images/, models/, _fichero/)."""
    from fichero_server.db.storage import resolve_source
    from fichero_server.workflows.library_sync import SyncManifest, SyncObject

    if step.reader not in ("kraken", "vlm"):
        raise NotSendable(f"no reader {step.reader!r}: kraken or vlm")
    if step.reader == "kraken" and not (step.model_file and Path(step.model_file).is_file()):
        raise NotSendable(f"the Kraken reader {step.card} is not on this Mac")
    if step.reader == "vlm" and not step.model:
        raise NotSendable("a vision-model step must name where the job finds its weights")
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    objects: dict[str, Any] = {}
    sources: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for page in pages_to_read(db, scope_ids):
        meta = page.metadata if isinstance(page.metadata, dict) else {}
        if meta.get("iiif_service"):
            sources.append({"id": page.id, "iiif_service": meta["iiif_service"],
                            "canvas": [meta.get("width"), meta.get("height")]})
            continue
        local = resolve_source(page, library_root=library_root)
        if local is None:
            skipped.append({"id": page.id, "why": "its image is not on this Mac"})
            continue
        sha = _sha256(local)
        rel = f"images/{sha}{local.suffix.lower()}"
        if rel not in objects:
            shutil.copy2(local, out / rel)
            objects[rel] = SyncObject(rel=rel, sha256=sha, size=(out / rel).stat().st_size)
        sources.append({"id": page.id, "image": rel})
    if not sources:
        raise NotSendable("nothing in scope has an image here or a IIIF service to fetch from")
    if step.reader == "kraken":
        (out / "models").mkdir()
        model_rel = step.describe()["model_file"]
        shutil.copy2(step.model_file, out / model_rel)
        objects[model_rel] = SyncObject(rel=model_rel, sha256=_sha256(out / model_rel),
                                        size=(out / model_rel).stat().st_size)
    (out / "_fichero").mkdir()
    for helper in (RUNNER, Path(__file__).parent.parent / "media" / "iiif_fetch.py"):
        shutil.copy2(helper, out / "_fichero" / helper.name)
    shards = [list(range(i, min(i + shard_size, len(sources)))) for i in range(0, len(sources), shard_size)]
    job = {"format": FORMAT, "job_id": job_id, "step": step.describe(), "fetch": {"longest": longest},
           "shards": shards, "sources": sources}
    (out / "job.json").write_text(json.dumps(job, indent=1, sort_keys=True), encoding="utf-8")
    manifest = SyncManifest(library_id=job_id, generation=0,
                            objects=tuple(objects[k] for k in sorted(objects)), produced_at="")
    (out / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    return ReadPackage(job_id=job_id, sources=sources, shards=shards, skipped=skipped)
