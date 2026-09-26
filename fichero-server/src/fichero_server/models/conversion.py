"""Source-model slice 8b (#4924) — the record of one whole-project conversion.

Spec: `segments-and-geometry.md`, "Converting a whole project: the rules", and
`build-notes-readings-cascade-orders.md`, "Slice 8b".

**Where the report lives, and why not the activity record.** The build notes
call this "the build lane's first question: one home, not both". It is its own
table in the LIBRARY database, and the activity record is the wrong home for
four reasons, each checked on disk rather than assumed:

1. **Activities are deleted by age.** `ActivityStore.delete_old(older_than)`
   exists and is used. The rule says the report is "shown once, **kept**". A
   record that must persist does not belong in a store built to be pruned.
2. **Activities live in a different database file** (`ActivityStore` opens its
   own `db_path`). This report names a snapshot of THIS library and is the
   account of what happened to THIS library's data; it has to travel with the
   library. Move the `.fichero` package to another machine and an activity log
   left behind takes the only record of the conversion with it.
3. **The report has mutable state, and activities are append-only events.**
   `seen_at` gates un-pinning the snapshot: the snapshot is exempt from
   retention *until the run has finished and a person has seen the report*.
   That is a field that changes after the fact, which an event stream is the
   wrong shape for.
4. **It has to be queryable by its parts.** "Which projects refused for disk,
   and how much did they need" is a column query here and a JSON scan there.

Neither the runner nor this record is a route. Nothing here converts anything;
it only says what happened.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fichero_server.core.timeutil import utc_now


def _new_id() -> str:
    return uuid.uuid4().hex


class UnconvertedScope(BaseModel):
    """How much of a project still has stored geometry rather than records.

    The answer to "is there anything to do?", and the input to the disk
    estimate. All three numbers come from ONE query over the conversion markers
    (`Database.unconverted_geometry_scope`), because this is asked at every
    project open and a project of twenty thousand pages must not pay for a scan
    that loads every geometry blob to count it.

    There is no cursor anywhere in this design: what is left is always asked of
    the database, so a quit, a crash or a second run cannot make it wrong.
    """

    model_config = ConfigDict(extra="forbid")

    #: Results with boxes and no conversion marker.
    results: int = 0
    #: Distinct documents those results sit on.
    documents: int = 0
    #: Total boxes across them — what the new records will cost.
    boxes: int = 0


class ConversionVerdict(str, Enum):
    """How a conversion run ended, or why it never began.

    A REFUSAL IS A RESULT, not an error. Every refusal below means the same
    thing about the library: nothing was converted, nothing is half done, and
    the next open will try again. That is the property the whole design exists
    to protect — "a conversion that half-succeeds and leaves a library in a
    state nobody chose" is the failure that matters, not a slow one.
    """

    #: Nothing to convert. Written NOWHERE -- not even a report row. This is
    #: what makes every later open free, so the verdict exists for the
    #: in-memory answer only.
    nothing_to_do = "nothing_to_do"
    #: The disk cannot hold the snapshot plus the new records with room to
    #: spare. Reported with the numbers; retried at the next open.
    refused_disk = "refused_disk"
    #: No snapshot could be taken, or the one taken could not be read back, or
    #: its row counts disagree with the project's. No snapshot, no conversion.
    refused_snapshot = "refused_snapshot"
    #: Preflight passed and the snapshot is proved. Pages may convert.
    ready = "ready"
    #: Every page was attempted. Some may have failed; those are listed.
    completed = "completed"
    #: The runner itself stopped for a reason that is not a page's fault.
    failed = "failed"


class ConversionFailure(BaseModel):
    """One page that could not convert, and why.

    A page that cannot convert is recorded and SKIPPED: it does not stop the
    others, and it still reads, from its block, exactly as before. So this is
    not an error report — it is the list of pages that stayed as they were.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    #: The result that could not become a pass, when one result is to blame.
    artifact_id: str | None = None
    #: The refusal's own words. A typed refusal's message, never a traceback.
    reason: str


class ConversionRun(BaseModel):
    """One whole-project conversion, and what became of it.

    Table `conversionruns`, in the library's own database. One row per run that
    got as far as taking a snapshot or refusing — a run with nothing to do
    writes no row at all.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    #: The `run_id` handed to every page action of this run, so the audit rows
    #: of a conversion can be found from its report and the report from them.
    run_id: str = Field(default_factory=_new_id)
    verdict: ConversionVerdict
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    #: Where the way back is. `snapshot_id` is pinned -- exempt from
    #: `_enforce_retention` -- until `finished_at` and `seen_at` are both set.
    snapshot_id: str | None = None
    snapshot_path: str | None = None
    #: The proof, not the intention: the table-by-table row-count comparison
    #: that showed the snapshot reads back. `{}` when no snapshot was proved.
    snapshot_proof: dict[str, Any] = Field(default_factory=dict)

    #: What preflight measured. Kept even on success, because "it fitted" is
    #: worth as much as "it did not" when someone asks why a conversion ran
    #: on a nearly full disk.
    results_to_convert: int = 0
    documents_to_convert: int = 0
    #: Bytes. Plain `int` since #5059 made the type map emit BIGINT and widen
    #: existing INTEGER columns on open: a field that means bytes should not have
    #: to know about a storage ceiling the model never mentions. This pair is
    #: what found that ceiling — a disk with 20 GB free is 20,688,982,016, and
    #: saving this record used to fail outright.
    disk_required_bytes: int | None = None
    disk_available_bytes: int | None = None

    pages_converted: int = 0
    #: A page an edit converted first, or that had nothing to convert. NOT a
    #: failure: `AlreadyConverted` and `NothingToConvert` mean somebody got
    #: there ahead of the runner, which is the design working.
    pages_skipped: int = 0
    failures: list[ConversionFailure] = Field(default_factory=list)
    seconds: float | None = None

    #: When a person was shown this report. Until it is set, the snapshot
    #: stays pinned: the way back from a conversion nobody has looked at yet
    #: must not be tidied away by a retention rule.
    seen_at: datetime | None = None

    #: THE LOCK (slice 8b part 3). An unfinished run with a RECENT heartbeat is
    #: a runner that is working, and a second opening must not start another:
    #: "a project has one engine, so one runner".
    #:
    #: Why a heartbeat and not simply the row's existence. A lock that is only
    #: "an unfinished row exists" wedges the project forever the first time an
    #: app is force-quit mid-conversion — and the rules REQUIRE the next open to
    #: carry on, so a lock nobody can reclaim would contradict the design it is
    #: meant to protect. Stamped after each page, which is the same boundary
    #: everything else in this runner uses.
    #:
    #: It is not a liveness guarantee and does not pretend to be: a stale
    #: heartbeat means "no runner has touched this for a while", and taking over
    #: is safe because converting again can only write the same records —
    #: `converted_segment_id` makes every id follow from its result and position.
    #: That property is what lets the lock be advisory rather than exclusive.
    heartbeat_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        """A claim that has neither finished nor been abandoned."""
        return self.verdict is ConversionVerdict.ready and self.finished_at is None

    @property
    def snapshot_may_be_unpinned(self) -> bool:
        """The snapshot is only ordinary once the run is done AND seen."""
        return self.finished_at is not None and self.seen_at is not None
