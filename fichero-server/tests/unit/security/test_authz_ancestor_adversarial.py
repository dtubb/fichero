from __future__ import annotations

import pytest

from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.models import Document, DocType


def _library_path(db) -> str:
    return str(db.path.parent)


def _editor(app_db, library_path: str, *, username: str = "editor"):
    user = app_db.create_user(
        username=username, display_name=username.title(),
        password_hash=accounts.hash_password("password"),
    )
    app_db.set_library_role(
        user_id=user.id, library_path=authz.normalize_library_path(library_path), role="editor",
    )
    return user


def _make_segment(db, document_id: str):
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor

    pass_row = SegmentPass(document_id=document_id, name="p", provenance_kind=ProvenanceKind.workflow)
    db.save(pass_row)
    anchor = SourceAnchor(document_id=document_id, rect=[0.1, 0.1, 0.1, 0.1])
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    seg = Segment(
        document_id=document_id, pass_id=pass_row.id, kind="word", anchor=anchor,
        bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
        doc_kind=f"{document_id}:word", provenance_kind=ProvenanceKind.workflow,
    )
    db.save(seg)
    return pass_row, seg


class TestSegmentDomainIdsResolveToTheirDocument:
    """#4917: a deny/grant placed on a DOCUMENT (or a folder above it) must
    reach every segment-domain id that belongs to it -- a `Segment`,
    `SegmentPass`, `SegmentMatch`, `SegmentCarry` (via its match),
    `SegmentVersion`, `SegmentForwarding`, and an `Artifact` -- because
    `ActionRegistry.invoke` checks each one of these AS ITS OWN target id,
    never the document. Before the fix, `_target_ancestor_ids` returned
    `[]` for any non-Document id (no exception, just "not a document"),
    which `_matching_override_effect` then replaced with `[target_id]`
    alone -- an override on the document could never match."""

    def test_deny_on_document_reaches_a_segment_and_its_pass_by_id(self, db, app_db, monkeypatch):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Denied Doc")
        db.save(doc)
        pass_row, seg = _make_segment(db, doc.id)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id=doc.id, effect="deny",
        )

        assert authz._target_ancestor_ids(library_path, seg.id) == [seg.id, doc.id]
        assert authz._target_ancestor_ids(library_path, pass_row.id) == [pass_row.id, doc.id]
        assert authz.can_write(user, library_path, seg.id) is False
        assert authz.can_write(user, library_path, pass_row.id) is False
        assert authz.can_read(user, library_path, seg.id) is False

        # Positive control: the SAME user, on a DIFFERENT document's segment,
        # is unaffected -- the deny is document-scoped, not global.
        other_doc = Document(name="Allowed Doc")
        db.save(other_doc)
        _, other_seg = _make_segment(db, other_doc.id)
        assert authz.can_write(user, library_path, other_seg.id) is True

    def test_deny_on_a_folder_above_the_document_reaches_a_segment(self, db, app_db, monkeypatch):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        folder = Document(name="Denied Folder", doc_type=DocType.folder)
        db.save(folder)
        doc = Document(name="Doc In Folder", parent_id=folder.id)
        db.save(doc)
        _, seg = _make_segment(db, doc.id)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id=folder.id, effect="deny",
        )

        assert authz._target_ancestor_ids(library_path, seg.id) == [seg.id, doc.id, folder.id]
        assert authz.can_write(user, library_path, seg.id) is False

    def test_a_grant_on_the_document_overrides_a_deny_on_the_folder_reaching_a_segment(
        self, db, app_db, monkeypatch,
    ):
        """(3): a MORE SPECIFIC override (on the document, closer to the
        segment than the folder) wins -- the existing "first match in the
        ancestor chain wins" rule, now reachable for a segment id too."""
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        folder = Document(name="Denied Folder", doc_type=DocType.folder)
        db.save(folder)
        doc = Document(name="Granted Doc", parent_id=folder.id)
        db.save(doc)
        _, seg = _make_segment(db, doc.id)
        norm = authz.normalize_library_path(library_path)
        app_db.set_library_acl_override(user_id=user.id, library_path=norm, target_id=folder.id, effect="deny")
        app_db.set_library_acl_override(user_id=user.id, library_path=norm, target_id=doc.id, effect="grant")

        assert authz.can_write(user, library_path, seg.id) is True

    def test_deny_on_document_reaches_a_match_and_a_carry_by_id(self, db, app_db, monkeypatch):
        from fichero_server.models.segments import SegmentCarry, SegmentMatch
        from fichero_server.models.knowledge import ProvenanceKind

        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Denied Doc")
        db.save(doc)
        _, seg_a = _make_segment(db, doc.id)
        _, seg_b = _make_segment(db, doc.id)
        match = SegmentMatch(
            document_id=doc.id, from_segment_id=seg_a.id, to_segment_id=seg_b.id,
            proposed_by="daniel", proposed_by_kind=ProvenanceKind.human,
        )
        db.save(match)
        carry = SegmentCarry(match_id=match.id, carried_kind="annotation", original_id=seg_a.id, copy_id=seg_b.id)
        db.save(carry)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id=doc.id, effect="deny",
        )

        assert authz._target_ancestor_ids(library_path, match.id) == [match.id, doc.id]
        # SegmentCarry has no document_id of its own -- resolved via its match.
        assert authz._target_ancestor_ids(library_path, carry.id) == [carry.id, doc.id]
        assert authz.can_write(user, library_path, match.id) is False
        assert authz.can_write(user, library_path, carry.id) is False

    def test_deny_on_document_reaches_an_artifact_by_id(self, db, app_db, monkeypatch):
        from fichero_server.models import Artifact

        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Denied Doc")
        db.save(doc)
        artifact = Artifact(document_id=doc.id, artifact_type="regions", content="x")
        db.save(artifact)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id=doc.id, effect="deny",
        )

        assert authz._target_ancestor_ids(library_path, artifact.id) == [artifact.id, doc.id]
        assert authz.can_read(user, library_path, artifact.id) is False

    def test_an_id_that_matches_no_known_kind_keeps_todays_behaviour(self, db):
        """Not a document, not any segment-domain kind: itself only --
        unchanged from before the fix (an entity/claim id, say)."""
        library_path = _library_path(db)
        assert authz._target_ancestor_ids(library_path, "no-such-id-anywhere") == ["no-such-id-anywhere"]


class TestFailsClosedOnResolutionError:
    """(5): a lookup error must REFUSE, never silently fall back to
    'no ancestors, no restriction' -- the exact shape of today's bug, just
    triggered by an exception instead of a missing-kind miss."""

    def test_a_raising_lookup_denies_rather_than_allows(self, db, app_db, monkeypatch):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Doc")
        db.save(doc)
        _, seg = _make_segment(db, doc.id)
        # Ruling 1 (cost): resolution is skipped entirely when this user has
        # NO overrides at all -- an override must exist for the broken
        # lookup to matter here (an unrelated one is enough; the point is
        # "overrides exist, so resolve", not that this specific one matches).
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id="some-other-document", effect="deny",
        )

        def _boom(*_a, **_k):
            raise RuntimeError("simulated lookup failure")

        monkeypatch.setattr(db, "get", _boom)
        # Route the manager's cached instance to the same broken db so the
        # authz layer (which fetches its OWN handle) hits the failure too.
        from fichero_server.db.manager import db_manager

        monkeypatch.setattr(db_manager, "get_database", lambda *_a, **_k: db)

        with pytest.raises(authz.AuthzResolutionError):
            authz._target_ancestor_ids(library_path, seg.id)
        # An editor, who would otherwise be allowed, is REFUSED -- not
        # silently allowed because the lookup broke.
        assert authz.can_write(user, library_path, seg.id) is False
        assert authz.can_read(user, library_path, seg.id) is False


def test_acl_parent_deny_overrides_child_document_access(
    db,
    app_db,
    monkeypatch,
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    user = app_db.create_user(
        username="editor",
        display_name="Editor",
        password_hash=accounts.hash_password("password"),
    )
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role="editor",
    )
    parent = Document(name="Denied Parent", doc_type=DocType.folder)
    db.save(parent)
    child = Document(name="Child", parent_id=parent.id)
    db.save(child)
    app_db.set_library_acl_override(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        target_id=parent.id,
        effect="deny",
    )

    assert authz.can_read(user, library_path, child.id) is False
    assert authz.can_write(user, library_path, child.id) is False


def test_target_ancestor_ids_terminates_on_parent_cycle(db):
    library_path = _library_path(db)
    first = Document(name="Cycle A", doc_type=DocType.folder)
    second = Document(name="Cycle B", doc_type=DocType.folder, parent_id=first.id)
    first.parent_id = second.id
    db.save(first)
    db.save(second)

    ancestors = authz._target_ancestor_ids(library_path, first.id)

    assert ancestors == [first.id, second.id]


class TestNoOverridesSkipsResolutionEntirely:
    """Ruling 1 (cost, 2026-09-20): with no ACL overrides at all for this
    user/library, no override can ever match -- `_matching_override_effect`
    must return `None` WITHOUT calling `_target_ancestor_ids`, so an
    ordinary write with no overrides in play never pays the resolver's
    per-kind lookups (up to 7 `db.get` calls otherwise, on every id an
    audited action names, including claim/entity/note ids that will never
    resolve to anything)."""

    def test_a_write_with_no_overrides_never_resolves_ancestors(self, db, app_db, monkeypatch):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Doc")
        db.save(doc)
        _, seg = _make_segment(db, doc.id)

        def _boom(*_a, **_k):
            raise AssertionError("resolution must not run when there are no overrides")

        monkeypatch.setattr(authz, "_resolve_owning_document_id", _boom)

        # No overrides exist for this user at all -- an editor's ordinary
        # write succeeds without ever touching the resolver.
        assert authz.can_write(user, library_path, seg.id) is True
        assert authz.can_read(user, library_path, seg.id) is True

    def test_a_write_with_an_unrelated_override_still_resolves(self, db, app_db, monkeypatch):
        """The moment ANY override exists for this user/library, resolution
        runs again -- the short-circuit is "no overrides", not "no
        matching override" (which we cannot know without resolving)."""
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Doc")
        db.save(doc)
        _, seg = _make_segment(db, doc.id)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id="some-unrelated-id", effect="deny",
        )

        calls = []
        original = authz._resolve_owning_document_id

        def _spy(db_arg, target_id):
            calls.append(target_id)
            return original(db_arg, target_id)

        monkeypatch.setattr(authz, "_resolve_owning_document_id", _spy)

        assert authz.can_write(user, library_path, seg.id) is True  # no MATCHING override
        assert calls == [seg.id]


class TestFoundRowWithNoDocumentDeniesRatherThanFallsThrough:
    """F1 (review, 2026-09-20): `_resolve_owning_document_id` used to
    return `None` -- "itself only", i.e. unrestricted -- both when NO
    kind matched `target_id` AND when a kind matched but its document
    could not be established. The second case is the exact silent shape
    this fix exists to remove: a row is found, no override on its
    document (or a folder above it) can ever match it, and nothing
    distinguishes that from "not a segment-domain id at all". Every test
    here sets an override so Ruling 1's short-circuit does not hide the
    failure by skipping resolution entirely."""

    def test_a_carry_whose_match_was_deleted_is_denied(self, db, app_db, monkeypatch):
        from fichero_server.models.segments import SegmentCarry, SegmentMatch
        from fichero_server.models.knowledge import ProvenanceKind

        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Doc")
        db.save(doc)
        _, seg_a = _make_segment(db, doc.id)
        _, seg_b = _make_segment(db, doc.id)
        match = SegmentMatch(
            document_id=doc.id, from_segment_id=seg_a.id, to_segment_id=seg_b.id,
            proposed_by="daniel", proposed_by_kind=ProvenanceKind.human,
        )
        db.save(match)
        carry = SegmentCarry(match_id=match.id, carried_kind="annotation", original_id=seg_a.id, copy_id=seg_b.id)
        db.save(carry)
        db.delete(match)  # the carry's match is now gone
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id="some-other-document", effect="deny",
        )

        with pytest.raises(authz.AuthzResolutionError):
            authz._target_ancestor_ids(library_path, carry.id)
        assert authz.can_write(user, library_path, carry.id) is False
        assert authz.can_read(user, library_path, carry.id) is False

    def test_a_row_with_an_empty_document_id_is_denied(self, db, app_db, monkeypatch):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Doc")
        db.save(doc)
        pass_row, seg = _make_segment(db, doc.id)
        # Hand-corrupt document_id to empty -- bypassing every action, the
        # way a real data problem would look, not something ordinary
        # writes can produce.
        seg.document_id = ""
        db.save(seg)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id="some-other-document", effect="deny",
        )

        with pytest.raises(authz.AuthzResolutionError):
            authz._target_ancestor_ids(library_path, seg.id)
        assert authz.can_write(user, library_path, seg.id) is False

    def test_a_segment_whose_document_row_is_gone_is_denied(self, db, app_db, monkeypatch):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        doc = Document(name="Doc")
        db.save(doc)
        _, seg = _make_segment(db, doc.id)
        db.delete(doc)  # the segment's own document row is gone
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id="some-other-document", effect="deny",
        )

        with pytest.raises(authz.AuthzResolutionError):
            authz._target_ancestor_ids(library_path, seg.id)
        assert authz.can_write(user, library_path, seg.id) is False

    def test_an_id_matching_no_kind_is_still_itself_only_with_an_override_present(
        self, db, app_db, monkeypatch,
    ):
        """The honest "nothing to resolve" case must still behave exactly
        as before -- an override existing elsewhere (so the short-circuit
        does not apply) must not turn "no kind matched" into a denial."""
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = _library_path(db)
        user = _editor(app_db, library_path)
        app_db.set_library_acl_override(
            user_id=user.id, library_path=authz.normalize_library_path(library_path),
            target_id="some-other-document", effect="deny",
        )

        assert authz._target_ancestor_ids(library_path, "no-such-id-anywhere") == ["no-such-id-anywhere"]
        assert authz.can_write(user, library_path, "no-such-id-anywhere") is True
