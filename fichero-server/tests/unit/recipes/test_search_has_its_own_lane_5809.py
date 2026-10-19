"""Searching for models never queues behind a download (#5809).

Live 2026-10-19: "Searching online... Waiting for the network lane: Download a model is running." Search is a few small
metadata calls; a 5.7 GB download held the network lane (four wide, one job per model) and the search waited behind it.
"""

from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.llm import local_models
from fichero_server.recipes import discovery


def _lane_of(kind: str) -> str:
    return jobs.KINDS[kind].lane


def test_the_model_search_is_on_a_lane_no_download_uses():
    discovery.register_job_kinds()
    local_models.register_job_kinds()
    assert _lane_of(discovery.SEARCH_KIND) != _lane_of(local_models.DOWNLOAD_KIND)
    assert jobs.LANES[_lane_of(discovery.SEARCH_KIND)] >= 1


def test_a_waiting_row_names_the_search_lane_in_words():
    discovery.register_job_kinds()
    assert _lane_of(discovery.SEARCH_KIND) in jobs.LANE_WORDS
