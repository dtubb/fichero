"""The folder watcher's handler answers watchdog's events without subclassing watchdog at import (#3950, the app's
import budget): a file's event reaches the trigger, a directory's does not, as when it subclassed
`FileSystemEventHandler`. Real watchdog events, no observer started."""

from __future__ import annotations

from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileModifiedEvent, FileMovedEvent

from fichero_server.workflows.file_watcher import (
    FileTrigger,
    FileWatchHandler,
    FilterMode,
    TriggerConfig,
    TriggerEvent,
    TriggerStatus,
)


def test_watchdog_events_reach_the_trigger_through_dispatch(tmp_path):
    trigger = FileTrigger(trigger_id="t", name="t", workflow_id="w", status=TriggerStatus.ACTIVE, config=TriggerConfig(
        watch_path=str(tmp_path), events=[TriggerEvent.ANY], filter_mode=FilterMode.GLOB, debounce_seconds=0))
    seen: list[tuple[str, str]] = []
    handler = FileWatchHandler(trigger, lambda kind, path: seen.append((kind, path)))

    handler.dispatch(FileCreatedEvent(str(tmp_path / "a.jpg")))
    handler.dispatch(DirCreatedEvent(str(tmp_path / "sub")))
    handler.dispatch(FileModifiedEvent(str(tmp_path / "b.jpg")))
    handler.dispatch(FileMovedEvent(str(tmp_path / "c.jpg"), str(tmp_path / "d.jpg")))

    assert seen == [("created", str(tmp_path / "a.jpg")), ("modified", str(tmp_path / "b.jpg")),
                    ("moved", str(tmp_path / "c.jpg"))]
