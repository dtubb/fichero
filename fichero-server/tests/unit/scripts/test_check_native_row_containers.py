"""Which container the row-stack guard thinks encloses a ForEach.

The rule is sound — a stack of tappable rows should be a `List` — and it was answering from a
regex that could not read a Swift construct head. `identifier(...)?$` with `[^{]*` inside the
parens let an EARLIER call swallow the far-away closing paren, so on

    Divider()

        List(selection: $listSelection) {

it returned `padding` from further up the 200-character lookback. `List` never entered the
chain, and a ForEach inside `VStack { List { Section { … } } }` was reported as a hand-rolled
VStack (ActivityViewHelpers.swift:225).

Forbidding newlines instead breaks the other way: `LazyVGrid(\\n  columns: [GridItem(…)]\\n)`
spans lines and nests parens, and three grids then read as bare ScrollViews. **The loose
version hid three real findings while inventing a false one — too loose and too narrow are the
same defect.** So the name is read by walking back over a balanced paren group, and these tests
pin both failure directions at once.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_native_row_containers.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_native_row_containers", _SCRIPT)
assert _SPEC and _SPEC.loader
rows = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = rows
_SPEC.loader.exec_module(rows)  # type: ignore[attr-defined]


def _name_of_last_brace(source: str) -> str | None:
    return rows._construct_name(source, source.rindex("{"))


class TestTheConstructNameIsReadExactly:
    def test_a_plain_container(self):
        assert _name_of_last_brace("VStack {") == "VStack"

    def test_a_single_line_argument_list(self):
        assert _name_of_last_brace("List(selection: $listSelection) {") == "List"

    def test_an_earlier_call_cannot_claim_the_closing_paren(self):
        """The exact false positive: `padding` was winning over `List`."""
        source = ".padding(8)\n\n            List(selection: $listSelection) {"
        assert _name_of_last_brace(source) == "List"

    def test_a_multi_line_head_with_nested_parens(self):
        """The grids that the tightened-regex version mislabelled as ScrollViews."""
        source = (
            "ScrollView {\n"
            "    LazyVGrid(\n"
            "        columns: [GridItem(.adaptive(minimum: itemMin, maximum: itemMax))],\n"
            "        spacing: 12\n"
            "    ) {"
        )
        assert _name_of_last_brace(source) == "LazyVGrid"

    def test_an_array_argument(self):
        assert _name_of_last_brace("ScrollView([.horizontal, .vertical]) {") == "ScrollView"

    def test_a_trailing_closure_after_a_modifier_chain(self):
        assert _name_of_last_brace("Text(\"x\").frame(width: 10)\nSection(\"Background\") {") == "Section"

    def test_an_unclosed_paren_is_not_guessed_at(self):
        assert rows._construct_name(") {", 2) is None


class TestTheChainStopsAtTheNearestContainer:
    def test_a_list_inside_a_vstack_is_a_list(self):
        """A header above a list is ordinary, and was being read as a hand-rolled stack."""
        source = (
            "VStack(spacing: 0) {\n"
            "    Divider()\n"
            "    List(selection: $sel) {\n"
            "        Section {\n"
            "            ForEach(runs) { run in\n"
            "                Row(run: run).onTapGesture { pick(run) }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}"
        )
        chain = rows._enclosing_chain(source, source.index("ForEach"))
        assert "List" in chain
        assert chain.index("List") < chain.index("VStack"), chain

    def test_a_grid_inside_a_scrollview_is_a_grid(self):
        source = (
            "ScrollView {\n"
            "    LazyVGrid(\n"
            "        columns: [GridItem(.adaptive(minimum: 140, maximum: 180))]\n"
            "    ) {\n"
            "        ForEach(items) { item in\n"
            "            Tile(item).onTapGesture { open(item) }\n"
            "        }\n"
            "    }\n"
            "}"
        )
        chain = rows._enclosing_chain(source, source.index("ForEach"))
        assert chain.index("LazyVGrid") < chain.index("ScrollView"), chain


class TestTheGuardStillFiresOnARealHandRolledStack:
    def test_a_tappable_row_stack_in_a_bare_vstack_is_reported(self, tmp_path):
        """Fixing a chain walk is exactly how a guard goes quiet; this is the check on that."""
        views = tmp_path / "Views"
        (views / "Thing").mkdir(parents=True)
        (views / "Thing" / "ThingList.swift").write_text(
            "import SwiftUI\n"
            "struct ThingList: View {\n"
            "    var body: some View {\n"
            "        VStack(spacing: 0) {\n"
            "            ForEach(things) { thing in\n"
            "                ThingRow(thing: thing)\n"
            "                    .onTapGesture { select(thing) }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        offenders, _scanned, _seen = rows.scan(views)
        assert [o["key"] for o in offenders] == ["Thing/ThingList.swift"]
        assert offenders[0]["container"] == "VStack"

    def test_the_repo_passes_with_every_exception_reasoned(self):
        """ALLOWLIST is a PATH on this module, not the loaded dict — read it, don't index it."""
        import json

        allowed = json.loads(rows.ALLOWLIST.read_text())
        offenders, _scanned, _seen = rows.scan(rows.VIEWS_DIR)
        unaccounted = [o["key"] for o in offenders if o["key"] not in allowed]
        assert unaccounted == [], unaccounted
        assert all(reason.strip() for reason in allowed.values()), "an exception must say why"
