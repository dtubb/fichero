"""One typed link record, one vocabulary (#4931, slice 10).

`source.link.typed`, `source.link.both-ways`.

**NOT `source.link.any-depth`**, which this file cited by mistake until 2026-09-27. That behaviour
says links *chain* (a comment on a comment) and *cross sources*; what is tested below is that a link
joins segments of any GRANULARITY, which is a different claim and belongs to `source.link.typed`.
Chaining needs `LinkEndKind.link`, which does not exist. Rule (i) flagged the citation and the tag
turned out to be right.

The vocabulary is the interesting half. Four records already hold "this relates to
that", each with its own word list, and the record built to remove four
vocabularies must not ship a fifth that disagrees with the one two of them already
share. So the seed is assembled from every set that holds the idea, with the
overlap collapsed — and the guard in `TestTheVocabularyHasNoNearMisses` is what
stops the next person re-adding a word that differs from an existing one by a
letter.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.typed_links import (
    SYMMETRIC_LINK_TYPES,
    assert_known_link_type,
    link_types,
)
from fichero_server.models import Document, DocType, FileType, Segment, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ClaimRelationType, ProvenanceKind
from fichero_server.models.segments import SegmentPass
from fichero_server.models.typed_links import (
    KG_LINK_TYPES,
    LINK_TYPE_ALIASES,
    LibraryLinkType,
    TypedLink,
    UnknownLinkType,
    builtin_link_types,
    resolve_link_type,
)

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", is_bootstrap=True)


def _two_segments(db, kind: str = "line") -> tuple[Segment, Segment]:
    doc = Document(
        name="linked.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/linked.jpg", status=Status.completed,
    )
    db.save(doc)
    pass_row = SegmentPass(
        document_id=doc.id, name="hand", provenance_kind=ProvenanceKind.human
    )
    db.save(pass_row)
    made = []
    for y in (0.2, 0.6):
        row = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind=kind,
            doc_kind=f"{doc.id}:{kind}",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, y, 0.4, 0.04]),
            bbox_x=0.1, bbox_y=y, bbox_w=0.4, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(row)
        made.append(row)
    return made[0], made[1]


def _link(db, one, other, link_type: str = "glosses", **extra):
    return registry.invoke(
        db,
        "typed_link.create",
        {"from_id": one.id, "to_id": other.id, "link_type": link_type, **extra},
        _person(),
    ).result


class TestTheVocabularyIsOneList:
    def test_the_kg_words_are_reused_not_respelled(self, db):
        keys = {key for key, _label, _inverse in builtin_link_types()}

        for value in ClaimRelationType:
            assert value.value in keys, f"the KG's {value.value} is missing"

    def test_the_four_duplicates_appear_once_each(self, db):
        """`follows`, `refines`, `supports`, `contradicts` are in the KG's
        vocabulary AND in the existing records' word lists. One key each, in the
        KG's spelling: where a plan and stored data disagree, the stored data
        wins."""
        keys = [key for key, _label, _inverse in builtin_link_types()]

        for shared in ("follows", "refines", "supports", "contradicts"):
            assert keys.count(shared) == 1, f"{shared} was seeded twice"

    def test_the_manuscript_words_the_kg_lacks_are_there(self, db):
        keys = {key for key, _label, _inverse in builtin_link_types()}

        for word in ("glosses", "comments_on", "quotes", "continues", "translates"):
            assert word in keys
            assert word not in KG_LINK_TYPES, f"{word} is the KG's after all"

    def test_every_key_is_seeded_into_a_library_on_open(self, db):
        seeded = {row.key for row in db.query(LibraryLinkType)}

        assert seeded == {key for key, _label, _inverse in builtin_link_types()}
        assert all(row.builtin for row in db.query(LibraryLinkType))

    def test_seeding_is_idempotent_and_keeps_a_relabelled_type(self, db):
        row = next(r for r in db.query(LibraryLinkType) if r.key == "glosses")
        row.label = "Glosses (our word)"
        db.save(row)

        db._seed_builtin_link_types()

        again = [r for r in db.query(LibraryLinkType) if r.key == "glosses"]
        assert len(again) == 1
        assert again[0].label == "Glosses (our word)"

    def test_a_project_can_add_a_key_and_it_is_as_real_as_a_shipped_one(self, db):
        db.save(
            LibraryLinkType(
                key="rubricates", label="Rubricates", inverse_label="Is rubricated by"
            )
        )

        assert "rubricates" in link_types(db)
        assert assert_known_link_type(db, "rubricates") == "rubricates"


class TestTheVocabularyHasNoNearMisses:
    """THE GUARD. `derived_from` against `derives_from` is two keys, one relation,
    one letter apart — a query for one silently misses the other and looks like an
    answer. A list nobody re-checks drifts the first time someone adds a word, so
    this checks the shape of the list rather than the words in it."""

    @staticmethod
    def _normalised(key: str) -> str:
        """Strip what a near-miss differs by: underscores and an inflection."""
        bare = key.replace("_", "")
        for suffix in ("s", "es", "ed", "d"):
            if bare.endswith(suffix) and len(bare) > len(suffix) + 2:
                return bare[: -len(suffix)]
        return bare

    def test_no_two_keys_differ_only_by_inflection_or_underscore(self):
        keys = [key for key, _label, _inverse in builtin_link_types()]
        buckets: dict[str, list[str]] = {}
        for key in keys:
            buckets.setdefault(self._normalised(key), []).append(key)

        collisions = {shape: words for shape, words in buckets.items() if len(words) > 1}
        assert not collisions, (
            "two keys differ only by inflection or underscore, which is the "
            f"`derives_from`/`derived_from` hazard: {collisions}"
        )

    def test_the_near_miss_that_prompted_this_is_an_alias_not_a_key(self):
        keys = {key for key, _label, _inverse in builtin_link_types()}

        assert "derives_from" in keys
        assert "derived_from" not in keys
        assert resolve_link_type("derived_from") == "derives_from"

    def test_no_seeded_key_collides_with_a_kg_value_by_inflection(self):
        """The cross-set version: a manuscript word that is a near-miss for a KG
        word is the same hazard from the other direction."""
        kg_shapes = {self._normalised(value) for value in KG_LINK_TYPES}
        for key, _label, _inverse in builtin_link_types():
            if key in KG_LINK_TYPES:
                continue
            assert self._normalised(key) not in kg_shapes, (
                f"{key} differs from a KG relation only by inflection"
            )


class TestTheAlias:
    def test_references_resolves_to_cites_and_is_not_a_key(self, db):
        keys = link_types(db)

        assert "cites" in keys
        assert "references" not in keys
        assert assert_known_link_type(db, "references") == "cites"

    def test_a_link_written_as_references_is_stored_as_cites(self, db):
        one, other = _two_segments(db)

        result = _link(db, one, other, link_type="references")

        assert result["link_type"] == "cites"
        assert db.get(TypedLink, result["link_id"]).link_type == "cites"

    def test_the_alias_is_reported_so_a_client_holds_no_list_of_its_own(self, db, client):
        response = client.get("/api/links/types")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["aliases"]["references"] == "cites"
        assert "cites" in {row["key"] for row in body["types"]}


class TestLinkingSegments:
    def test_a_link_is_reachable_from_either_end(self, db, client):
        """`source.link.both-ways` — the same row, read from both sides, with the
        sentence running the right way each time."""
        one, other = _two_segments(db)
        _link(db, one, other, link_type="glosses")

        outbound = client.get(f"/api/links/of/{one.id}").json()["links"]
        inbound = client.get(f"/api/links/of/{other.id}").json()["links"]

        assert len(outbound) == len(inbound) == 1
        assert outbound[0]["id"] == inbound[0]["id"], "not the same row"
        assert outbound[0]["inbound"] is False
        assert inbound[0]["inbound"] is True
        # A glosses B; B is glossed by A. Showing `link_type` from both ends would
        # tell a reader the wrong sentence half the time.
        assert outbound[0]["label"] == "Glosses"
        assert inbound[0]["label"] == "Is glossed by"
        assert inbound[0]["other_id"] == one.id

    def test_a_symmetric_relation_reads_the_same_from_both_ends(self, db, client):
        one, other = _two_segments(db)
        _link(db, one, other, link_type="same_as")

        outbound = client.get(f"/api/links/of/{one.id}").json()["links"][0]
        inbound = client.get(f"/api/links/of/{other.id}").json()["links"][0]

        assert outbound["directed"] is False
        assert outbound["label"] == inbound["label"]
        assert "same_as" in SYMMETRIC_LINK_TYPES

    def test_links_join_segments_of_any_granularity(self, db):
        """Any GRANULARITY — part of `source.link.typed`, not `any-depth` (which is
        about chaining and crossing sources). Nothing reads the granularity, which is what
        makes this true rather than intended: a link between two characters is the
        same row as one between two regions."""
        words = _two_segments(db, kind="word")
        regions = _two_segments(db, kind="region")

        assert _link(db, words[0], words[1], link_type="quotes")["link_id"]
        assert _link(db, regions[0], regions[1], link_type="quotes")["link_id"]

    def test_an_unknown_type_is_refused_and_the_list_is_named(self, db):
        one, other = _two_segments(db)

        with pytest.raises(HTTPException) as raised:
            _link(db, one, other, link_type="rhymes_with")
        assert raised.value.status_code == 422
        assert "glosses" in str(raised.value.detail)

    def test_a_link_to_itself_is_refused(self, db):
        one, _other = _two_segments(db)

        with pytest.raises(HTTPException) as raised:
            registry.invoke(
                db,
                "typed_link.create",
                {"from_id": one.id, "to_id": one.id, "link_type": "glosses"},
                _person(),
            )
        assert raised.value.status_code == 422

    def test_a_missing_segment_is_a_404(self, db):
        one, _other = _two_segments(db)

        with pytest.raises(HTTPException) as raised:
            registry.invoke(
                db,
                "typed_link.create",
                {"from_id": one.id, "to_id": "no-such-segment", "link_type": "glosses"},
                _person(),
            )
        assert raised.value.status_code == 404

    def test_a_provisional_id_is_refused(self, db):
        one, _other = _two_segments(db)

        with pytest.raises(Exception):
            registry.invoke(
                db,
                "typed_link.create",
                {"from_id": one.id, "to_id": "legacy:abc:0", "link_type": "glosses"},
                _person(),
            )

    def test_the_maker_is_the_engines_answer_not_the_callers(self, db):
        one, other = _two_segments(db)

        result = registry.invoke(
            db,
            "typed_link.create",
            {"from_id": one.id, "to_id": other.id, "link_type": "glosses"},
            ActionContext(actor="runner", run_id="run-1", is_bootstrap=True),
        ).result

        stored = db.get(TypedLink, result["link_id"])
        assert stored.provenance_kind != ProvenanceKind.human


class TestWithdrawingALink:
    def test_a_deleted_link_disappears_from_both_ends_but_stays_auditable(self, db, client):
        one, other = _two_segments(db)
        result = _link(db, one, other)

        registry.invoke(db, "typed_link.delete", {"link_id": result["link_id"]}, _person())

        assert client.get(f"/api/links/of/{one.id}").json()["links"] == []
        assert client.get(f"/api/links/of/{other.id}").json()["links"] == []
        # Soft: the row is still there, so a withdrawn relation can be explained.
        assert db.get(TypedLink, result["link_id"]).deleted_at is not None
        with_deleted = client.get(
            f"/api/links/of/{one.id}?include_deleted=true"
        ).json()["links"]
        assert len(with_deleted) == 1

    def test_undoing_a_delete_brings_the_link_back(self, db, client):
        one, other = _two_segments(db)
        result = _link(db, one, other)
        registry.invoke(db, "typed_link.delete", {"link_id": result["link_id"]}, _person())

        registry.invoke(db, "typed_link.restore", {"link_id": result["link_id"]}, _person())

        assert len(client.get(f"/api/links/of/{one.id}").json()["links"]) == 1


class TestTheOtherFourRecordsAreNotMoved:
    def test_this_slice_leaves_the_existing_link_records_alone(self):
        """The slice makes the one record and puts segments on it. Moving notes,
        the canvas's two, or the prediction metadata value is each its own later
        slice — and a half-moved record would leave two homes for one relation,
        which is the thing this record exists to end."""
        from fichero_server.models import canvas, knowledge

        assert hasattr(knowledge, "NoteLink")
        assert hasattr(canvas, "SpatialConnection")
        assert hasattr(knowledge, "PredictionLink")

    def test_the_kg_link_record_still_uses_its_own_vocabulary(self):
        """`KnowledgeClaimLink` keeps `ClaimRelationType`; the link table SHARES
        those words rather than replacing them. Sharing a vocabulary is not the
        same as moving a record."""
        from fichero_server.models import knowledge

        assert hasattr(knowledge, "KnowledgeClaimLink")
        assert set(KG_LINK_TYPES) == {value.value for value in ClaimRelationType}


class TestTheAliasesAreNotASecondVocabulary:
    def test_every_alias_points_at_a_real_key(self, db):
        keys = set(link_types(db))

        for alias, target in LINK_TYPE_ALIASES.items():
            assert target in keys, f"{alias} points at {target}, which is not a key"
            assert alias not in keys, f"{alias} is an alias AND a key"

    def test_an_unknown_alias_target_would_fail_loudly(self, db):
        """The failure mode this guards: an alias whose target was renamed becomes
        a word that resolves to nothing and refuses every write silently blamed on
        the caller."""
        with pytest.raises(UnknownLinkType):
            assert_known_link_type(db, "not_a_word_at_all")
