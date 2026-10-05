"""The topic registry: each topic's and each job's explanation, written once (#5471).

`source.onboard.topics-written-once`, `source.onboard.teaches-the-method`: setup, the Inspector and
Activity all show the same text, read from `recipes/seed/topics.yaml` through `GET /api/topics`.
A recipe job's name and description come from its entry here (`recipes/jobs.py`), so a job has no
second copy of its own words.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SEED = Path(__file__).parent / "seed" / "topics.yaml"
KINDS = frozenset({"job", "topic"})


@dataclass(frozen=True)
class Topic:
    id: str
    kind: str
    title: str
    #: One sentence.
    short: str
    #: A paragraph that follows the short one, never repeating it.
    long: str
    #: What to show from the person's own pages, where there are some.
    example: str | None = None
    #: A path under docs/ when a manual page exists.
    manual: str | None = None

    @property
    def text(self) -> str:
        """The short sentence and the paragraph after it, as one explanation."""
        return f"{self.short} {self.long}".strip()


@lru_cache(maxsize=1)
def _topics() -> dict[str, Topic]:
    import yaml

    topics: dict[str, Topic] = {}
    for row in yaml.safe_load(SEED.read_text(encoding="utf-8"))["topics"]:
        topic = Topic(id=row["id"], kind=row["kind"], title=row["title"].strip(),
                      short=" ".join(row["short"].split()), long=" ".join(row["long"].split()),
                      example=row.get("example"), manual=row.get("manual"))
        if topic.id in topics:
            raise ValueError(f"topic {topic.id!r} is written twice in {SEED.name}")
        if topic.kind not in KINDS:
            raise ValueError(f"topic {topic.id!r} has kind {topic.kind!r}, not one of {sorted(KINDS)}")
        if not (topic.title and topic.short and topic.long):
            raise ValueError(f"topic {topic.id!r} needs a title, a short sentence and a paragraph")
        topics[topic.id] = topic
    return topics


def get_topic(topic_id: str) -> Topic | None:
    return _topics().get(topic_id)


def all_topics() -> list[Topic]:
    return list(_topics().values())
