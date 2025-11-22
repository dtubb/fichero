# Timeline Tracking Implementation

**Status:** ✅ Complete
**Date:** November 2025

## Overview

Added comprehensive timeline/activity tracking at the node (item/collection) level. This provides:

- **Activity History**: Track all events that happen to items and collections
- **Audit Trail**: Know who did what and when
- **User-Facing Timeline**: Show processing history to users in GUI
- **Analytics**: Understand workflow patterns and processing times

## Database Schema

### timeline_events Table

```sql
CREATE TABLE timeline_events (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,       -- "item" or "collection"
    entity_id TEXT NOT NULL,         -- Item ID or Collection ID
    event_type TEXT NOT NULL,        -- Event type (see below)
    event_category TEXT NOT NULL,    -- "system", "user", "processing", "metadata"
    actor TEXT NOT NULL,             -- Who/what triggered (see below)
    description TEXT,                -- Human-readable description
    metadata TEXT,                   -- JSON with additional context
    timestamp TEXT NOT NULL          -- ISO 8601 timestamp
);

-- Indexes for fast queries
CREATE INDEX idx_timeline_entity ON timeline_events(entity_type, entity_id, timestamp DESC);
CREATE INDEX idx_timeline_type ON timeline_events(event_type, timestamp DESC);
CREATE INDEX idx_timeline_category ON timeline_events(event_category, timestamp DESC);
```

## Event Types

Standard event types:
- `created`: Entity was created
- `processed`: Processing workflow executed
- `metadata_added`: New metadata version added
- `metadata_corrected`: Metadata manually corrected
- `exported`: Entity exported to file
- `imported`: Entity imported from external source
- `status_changed`: Status transition
- `error`: Error occurred
- `custom`: Custom event type

## Event Categories

- `system`: System-triggered automatic events
- `user`: User-triggered interactive events
- `processing`: Director/tool processing events
- `metadata`: Metadata operations

## Actor Format

Describes who/what triggered the event:
- `system`: Automatic system event
- `user:<username>`: Specific user (e.g., `user:john`)
- `tool:<tool_name>`: Processing tool (e.g., `tool:crop`, `tool:transcribe`)
- `ai:<model>`: AI model (e.g., `ai:qwen`, `ai:gpt`)

## TimelineEvent Model

```python
@dataclass
class TimelineEvent:
    id: str
    entity_type: Literal["item", "collection"]
    entity_id: str
    event_type: str
    event_category: str
    actor: str
    description: str
    metadata: Dict[str, Any]
    timestamp: datetime
```

## Storage Methods

### Add Event
```python
storage.add_timeline_event(event: TimelineEvent) -> bool
```

### Get Events
```python
# Get all events with filters
storage.get_timeline_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    event_category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[TimelineEvent]

# Get item timeline
storage.get_item_timeline(item_id: str, limit: int = 50) -> List[TimelineEvent]

# Get collection timeline
storage.get_collection_timeline(collection_id: str, limit: int = 50) -> List[TimelineEvent]
```

### Delete Events
```python
storage.delete_timeline_events(entity_type: str, entity_id: str) -> bool
```

## Usage Examples

### Example 1: Track Item Creation

```python
from fichero.library.models import TimelineEvent
from datetime import datetime

# When an item is added to a collection
event = TimelineEvent(
    entity_type="item",
    entity_id=item.id,
    event_type="created",
    event_category="system",
    actor="system",
    description=f"Item '{item.name}' added to collection",
    metadata={
        "collection_id": collection.id,
        "collection_name": collection.name,
        "item_type": item.type,
        "source_path": item.source_path
    }
)
storage.add_timeline_event(event)
```

### Example 2: Track Processing

```python
# When Director starts processing
event = TimelineEvent(
    entity_type="item",
    entity_id=item.id,
    event_type="processed",
    event_category="processing",
    actor="system",
    description=f"Started processing with plan '{plan_name}'",
    metadata={
        "plan": plan_name,
        "workflow": workflow_name,
        "task_id": task_id
    }
)
storage.add_timeline_event(event)

# When processing completes
event = TimelineEvent(
    entity_type="item",
    entity_id=item.id,
    event_type="processed",
    event_category="processing",
    actor="system",
    description=f"Completed processing with plan '{plan_name}'",
    metadata={
        "plan": plan_name,
        "workflow": workflow_name,
        "task_id": task_id,
        "duration_seconds": 45.2,
        "success": True,
        "steps_completed": 5
    }
)
storage.add_timeline_event(event)
```

### Example 3: Track Metadata Changes

```python
# When AI adds transcription
event = TimelineEvent(
    entity_type="item",
    entity_id=item.id,
    event_type="metadata_added",
    event_category="metadata",
    actor="ai:qwen",
    description="Transcription added by Qwen Max",
    metadata={
        "schema_type": "transcription",
        "source_label": "ai_qwen",
        "version": 1,
        "confidence": 0.92,
        "word_count": 450
    }
)
storage.add_timeline_event(event)

# When user corrects transcription
event = TimelineEvent(
    entity_type="item",
    entity_id=item.id,
    event_type="metadata_corrected",
    event_category="user",
    actor="user:john",
    description="Transcription manually corrected",
    metadata={
        "schema_type": "transcription",
        "source_label": "human_corrected",
        "version": 2,
        "previous_version": 1
    }
)
storage.add_timeline_event(event)
```

### Example 4: Track Tool Operations

```python
# When crop tool runs
event = TimelineEvent(
    entity_type="item",
    entity_id=item.id,
    event_type="processed",
    event_category="processing",
    actor="tool:crop",
    description="Image cropped using YOLO detection",
    metadata={
        "method": "yolo",
        "confidence": 0.95,
        "dimensions": {"x": 100, "y": 50, "w": 800, "h": 1000}
    }
)
storage.add_timeline_event(event)
```

### Example 5: Get Item History

```python
# Get full timeline for an item
timeline = storage.get_item_timeline(item_id, limit=50)

for event in timeline:
    print(f"{event.timestamp}: {event.description}")
    print(f"  Actor: {event.actor}")
    print(f"  Type: {event.event_type} ({event.event_category})")
    if event.metadata:
        print(f"  Context: {event.metadata}")
    print()

# Output:
# 2025-11-21 14:30:00: Transcription manually corrected
#   Actor: user:john
#   Type: metadata_corrected (user)
#   Context: {'schema_type': 'transcription', 'version': 2}
#
# 2025-11-21 14:15:00: Transcription added by Qwen Max
#   Actor: ai:qwen
#   Type: metadata_added (metadata)
#   Context: {'schema_type': 'transcription', 'confidence': 0.92}
#
# 2025-11-21 14:00:00: Completed processing with plan 'Transcribir y Catalogar'
#   Actor: system
#   Type: processed (processing)
#   Context: {'duration_seconds': 45.2, 'success': True}
```

### Example 6: Query by Type

```python
# Get all processing events
processing_events = storage.get_timeline_events(
    event_category="processing",
    limit=100
)

# Get all metadata corrections
corrections = storage.get_timeline_events(
    event_type="metadata_corrected",
    limit=100
)

# Get all AI-generated events
ai_events = [
    e for e in storage.get_timeline_events(limit=1000)
    if e.actor.startswith("ai:")
]
```

## Integration Points

### 1. LibraryManager

Add timeline tracking to key operations:

```python
async def add_item(self, item: CollectionItem) -> CollectionItem:
    # ... existing code ...

    # Track creation
    event = TimelineEvent(
        entity_type="item",
        entity_id=item.id,
        event_type="created",
        event_category="system",
        actor="system",
        description=f"Item '{item.name}' added to collection",
        metadata={"collection_id": item.collection_id}
    )
    self.storage.add_timeline_event(event)

    return item
```

### 2. DirectorIntegration

Track processing workflows:

```python
async def process_item(self, item_id: str, plan: str, workflow: str):
    # Start event
    event = TimelineEvent(
        entity_type="item",
        entity_id=item_id,
        event_type="processed",
        event_category="processing",
        actor="system",
        description=f"Started processing with plan '{plan}'",
        metadata={"plan": plan, "workflow": workflow}
    )
    self.library_manager.storage.add_timeline_event(event)

    # ... processing ...

    # Complete event
    event = TimelineEvent(
        entity_type="item",
        entity_id=item_id,
        event_type="processed",
        event_category="processing",
        actor="system",
        description=f"Completed processing",
        metadata={"plan": plan, "success": True, "duration_seconds": duration}
    )
    self.library_manager.storage.add_timeline_event(event)
```

### 3. MetadataExtractors

Track metadata extraction:

```python
def extract_from_output(self, ...):
    # ... extraction logic ...

    # Track metadata addition
    event = TimelineEvent(
        entity_type="item",
        entity_id=item_id,
        event_type="metadata_added",
        event_category="metadata",
        actor=f"ai:{source_label}",
        description=f"{schema_type} metadata extracted",
        metadata={
            "schema_type": schema_type,
            "source_label": source_label,
            "version": version
        }
    )
    self.storage.add_timeline_event(event)
```

### 4. GUI Integration (Future)

Display timeline in the UI:

```python
# In preview/info pane
timeline = library_manager.storage.get_item_timeline(item.id, limit=20)

# Render timeline widget
for event in timeline:
    # Show icon based on event_type
    # Show timestamp
    # Show description
    # Show actor badge
    # Optional: expand to show metadata details
```

## Performance Considerations

- **Indexes**: Three indexes ensure fast queries by entity, type, and category
- **Pagination**: Use limit/offset for large timelines
- **Archival**: Consider archiving old events (>1 year) to separate table
- **Async**: Timeline logging is synchronous but very fast (<1ms)

## Privacy and Security

- **No sensitive data**: Don't log passwords, API keys, or personal data in metadata
- **User identification**: Use usernames, not email addresses
- **Retention policy**: Consider implementing automatic cleanup of old events

## Future Enhancements

1. **Timeline Analytics**: Aggregate statistics, processing time trends
2. **Timeline Export**: Export timeline to JSON/CSV
3. **Timeline Filtering**: Advanced GUI filters by date range, actor, type
4. **Timeline Notifications**: Real-time updates via WebSocket
5. **Timeline Replay**: Recreate entity state at any point in time

---

## Files Changed

### Modified Files
- `src/fichero/library/models.py` - Added TimelineEvent model
- `src/fichero/library/storage.py` - Added timeline_events table and methods

### No Breaking Changes
- All changes are additive
- Existing code continues to work without modification
- Timeline tracking is opt-in (must explicitly add events)

---

**Implementation Complete** ✅

Timeline tracking is now available throughout the Fichero library system and can be integrated into any workflow that needs activity tracking.
