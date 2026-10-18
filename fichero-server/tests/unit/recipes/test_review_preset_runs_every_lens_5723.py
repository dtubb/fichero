"""The review preset makes one pass per lens the profiles define (#5723): a lens added to the profiles with no node
for it would never be asked, and a node naming a lens no profile has would fail at run time."""
import json
from pathlib import Path

from fichero_server.recipes import review_profiles

PRESET = Path(__file__).parents[3] / "src/fichero_server/resources/default_workflows/transcribe_paleography_review.json"


def test_the_review_preset_has_one_review_node_per_lens_and_no_other():
    nodes = json.loads(PRESET.read_text())["nodes"]
    lenses = [n["config"]["lens"] for n in nodes if n.get("tool") == "transcribe_review"]
    assert sorted(lenses) == sorted(review_profiles.lens_ids())
