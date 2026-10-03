"""A run can choose its Kraken reader, through the same override path as a language model (#4951).

Why it matters: Transcribe (Kraken) names one reader in its graph. Without a run-level choice, a
recipe pinned to another reader would either never run or be read by the graph's reader behind the
person's back. The choice must reach only a node that reads lines with Kraken, and a run that asks
for a reader on a workflow with no such node is refused, not silently ignored (#3804's shape).
"""
from __future__ import annotations

from fichero_server.workflows.validation import (
    apply_run_model_override,
    validate_run_eligibility,
)


def _nodes():
    return [
        {"id": "files", "tool": "files", "config": {}},
        {"id": "read", "tool": "transcribe",
         "config": {"vision_mode": "kraken", "kraken_model": "kraken-mccatmus", "language": "auto"}},
        {"id": "llm", "tool": "transcribe", "config": {"vision_mode": "llm"}},
    ]


def test_the_reader_reaches_only_the_kraken_reading_node():
    nodes = _nodes()
    reached = apply_run_model_override(nodes, "kraken", "kraken-catmus-medieval")
    assert reached == ["read"]
    assert nodes[1]["config"]["kraken_model"] == "kraken-catmus-medieval"
    assert nodes[1]["config"]["language"] == "auto"           # the rest of its config is kept
    assert "provider_name" not in nodes[1] and "model_name" not in nodes[1]
    assert nodes[2]["config"] == {"vision_mode": "llm"}      # a language-model reader is untouched


def test_a_reader_asked_of_a_workflow_with_no_kraken_reader_is_refused():
    errors = validate_run_eligibility(name="Translate", config={}, nodes=[_nodes()[2]],
                                      provider_override="kraken", model_override="kraken-mccatmus")
    assert errors and "Kraken reader" in errors[0]
    assert validate_run_eligibility(name="Transcribe (Kraken)", config={}, nodes=_nodes(),
                                    provider_override="kraken", model_override="kraken-mccatmus") == []
