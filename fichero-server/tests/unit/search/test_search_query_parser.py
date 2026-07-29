"""Unit tests for the search query parser.

Covers what the parser claims to do: quoted phrases, field scopes,
NOT exclusions, plain free text, and combinations. The parser is
intentionally small — no boolean precedence, no nesting — these tests
fix that surface so the route can rely on it.
"""

from __future__ import annotations

from fichero_server.search.query_parser import parse_query, SearchPlan


class TestEmpty:
    def test_empty_string(self) -> None:
        plan = parse_query("")
        assert plan == SearchPlan(original="")

    def test_whitespace_only(self) -> None:
        plan = parse_query("   \n\t  ")
        assert plan.free_text == ""
        assert not plan.phrases
        assert not plan.scopes
        assert not plan.excludes


class TestPlainText:
    def test_single_word(self) -> None:
        plan = parse_query("Asprilla")
        assert plan.free_text == "Asprilla"
        assert plan.has_freetext_intent

    def test_multi_word(self) -> None:
        plan = parse_query("rivers and water")
        assert plan.free_text == "rivers and water"

    def test_collapses_extra_whitespace(self) -> None:
        plan = parse_query("  foo   bar  ")
        assert plan.free_text == "foo bar"


class TestQuotedPhrases:
    def test_single_phrase(self) -> None:
        plan = parse_query('"el escribano"')
        assert plan.phrases == ["el escribano"]
        assert plan.free_text == ""

    def test_phrase_plus_freetext(self) -> None:
        plan = parse_query('Asprilla "el escribano"')
        assert plan.phrases == ["el escribano"]
        assert plan.free_text == "Asprilla"

    def test_two_phrases(self) -> None:
        plan = parse_query('"el escribano" "vuestra merced"')
        assert sorted(plan.phrases) == ["el escribano", "vuestra merced"]

    def test_unclosed_quote_treated_as_freetext(self) -> None:
        # Don't break on user typos.
        plan = parse_query('Asprilla "el escribano')
        assert plan.phrases == []
        assert "Asprilla" in plan.free_text


class TestEntityScopes:
    def test_people_scope(self) -> None:
        plan = parse_query("people:Asprilla")
        assert plan.scopes == {"people": ["Asprilla"]}
        assert plan.free_text == ""
        assert not plan.has_freetext_intent

    def test_places_scope(self) -> None:
        plan = parse_query("places:Quibdó")
        assert plan.scopes == {"places": ["Quibdó"]}

    def test_entities_scope(self) -> None:
        plan = parse_query("entities:Asprilla")
        assert plan.scopes == {"entities": ["Asprilla"]}
        assert plan.semantic_scopes == {"entities": ["Asprilla"]}
        assert plan.artifact_scopes == {}

    def test_claims_scope(self) -> None:
        plan = parse_query("claims:mine")
        assert plan.scopes == {"claims": ["mine"]}
        assert plan.semantic_scopes == {"claims": ["mine"]}
        assert plan.artifact_scopes == {}

    def test_scope_with_freetext(self) -> None:
        plan = parse_query("people:Asprilla gold")
        assert plan.scopes == {"people": ["Asprilla"]}
        assert plan.free_text == "gold"

    def test_quoted_scope(self) -> None:
        plan = parse_query('people:"José Antonio"')
        assert plan.scopes == {"people": ["José Antonio"]}

    def test_multiple_scopes_same_type(self) -> None:
        plan = parse_query("people:Asprilla people:Bernal")
        assert plan.scopes == {"people": ["Asprilla", "Bernal"]}

    def test_multiple_scope_types(self) -> None:
        plan = parse_query("people:Asprilla places:Quibdó")
        assert plan.scopes == {
            "people": ["Asprilla"],
            "places": ["Quibdó"],
        }

    def test_unknown_field_treated_as_freetext(self) -> None:
        # 'cars:porsche' is not an entity type — should fall through.
        plan = parse_query("cars:porsche gold")
        assert plan.scopes == {}
        assert "cars:porsche" in plan.free_text or "gold" in plan.free_text


class TestExclusions:
    def test_simple_exclude(self) -> None:
        plan = parse_query("gold -mining")
        assert plan.excludes == ["mining"]
        assert plan.free_text == "gold"

    def test_multiple_excludes(self) -> None:
        plan = parse_query("gold -mining -dredge")
        assert sorted(plan.excludes) == ["dredge", "mining"]

    def test_exclude_only(self) -> None:
        plan = parse_query("-mining")
        assert plan.excludes == ["mining"]
        assert plan.free_text == ""


class TestCombinations:
    def test_phrase_scope_exclude(self) -> None:
        plan = parse_query('"vuestra merced" people:Asprilla -1930')
        assert plan.phrases == ["vuestra merced"]
        assert plan.scopes == {"people": ["Asprilla"]}
        assert plan.excludes == ["1930"]
        assert plan.free_text == ""

    def test_freetext_with_everything(self) -> None:
        plan = parse_query('gold "el escribano" places:Quibdó -dredge')
        assert plan.free_text == "gold"
        assert plan.phrases == ["el escribano"]
        assert plan.scopes == {"places": ["Quibdó"]}
        assert plan.excludes == ["dredge"]


class TestIntentFlags:
    def test_pure_scope_no_freetext_intent(self) -> None:
        plan = parse_query("people:Asprilla")
        assert not plan.has_freetext_intent
        assert plan.has_entity_scope
        assert plan.has_scope

    def test_pure_claim_scope_no_freetext_intent(self) -> None:
        plan = parse_query("claims:mine")
        assert not plan.has_freetext_intent
        assert not plan.has_entity_scope
        assert plan.has_scope

    def test_pure_freetext_no_scope(self) -> None:
        plan = parse_query("Asprilla")
        assert plan.has_freetext_intent
        assert not plan.has_entity_scope

    def test_phrase_alone_is_freetext_intent(self) -> None:
        plan = parse_query('"el escribano"')
        assert plan.has_freetext_intent
