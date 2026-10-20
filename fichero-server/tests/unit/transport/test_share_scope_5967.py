"""sharing.share-sheet-chooses-what (#5967, release bar #5910 item 9): the owner shares a project or a FOLDER of it; a person
shared a folder reaches that folder and everything under it, nothing beside it; the engine checks it on every request; a person-bound
invitation can name the folder. A grant is (person, project, folder, role); a folder covers its own items by ancestry."""

import pytest

from fichero_server.api.routes.auth import pairing
from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document
from fichero_server.security import authz
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401
from tests.unit.transport.test_person_bound_invite_5910 import _as, _invite, _redeem


@pytest.fixture
def project(harness, monkeypatch):
    """A project with two folders and a loose page: owner, alice (editor of the whole project), bob (viewer of it)."""
    users = _multiuser_on(harness, monkeypatch)
    db = db_manager.get_database(harness.library)
    ids = {}
    for key, kind, parent in (("A", DocType.folder, None), ("B", DocType.folder, None)):
        row = Document(name=f"Folder {key}", doc_type=kind, parent_id=parent)
        db.save(row)
        ids[key] = row.id
    for key, parent in (("a1", ids["A"]), ("b1", ids["B"]), ("r1", None)):
        row = Document(name=f"Page {key}", parent_id=parent)
        db.save(row)
        ids[key] = row.id
    sub = Document(name="Folder A/sub", doc_type=DocType.folder, parent_id=ids["A"])
    db.save(sub)
    deep = Document(name="Page a2", parent_id=sub.id)
    db.save(deep)
    ids["sub"], ids["a2"] = sub.id, deep.id
    return type("Project", (), {"harness": harness, "users": users, "ids": ids, "library": str(harness.library)})


def _person(harness, name):
    from fichero_server.security import accounts

    return harness.app_db.create_user(username=name, display_name=name.title(), password_hash=accounts.hash_password("pw-" + name))


def _reads(user, lib, ids):
    return {k: authz.can_read(user, lib, v) for k, v in ids.items()}


def test_a_person_shared_one_folder_reads_that_folder_and_what_is_under_it_and_nothing_beside_it(project):
    carla = _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"],
                       role="viewer")
    seen = _reads(carla, project.library, project.ids)
    assert seen["A"] and seen["a1"] and seen["sub"] and seen["a2"]  # the folder, its pages, and the folder inside it
    assert not (seen["B"] or seen["b1"] or seen["r1"])  # a sibling folder, its page, a loose page: refused
    assert authz.can_read(carla, project.library, None)  # the project can be opened; every list is filtered to the above
    assert not authz.can_write(carla, project.library, None)  # and nothing is written at project level


def test_a_viewer_of_a_folder_cannot_write_and_an_editor_of_it_writes_only_there(project):
    carla, dave = _person(project.harness, "carla"), _person(project.harness, "dave")
    owner = project.users["owner"]
    authz.grant_folder(actor=owner, library=project.library, user="carla", folder_id=project.ids["A"], role="viewer")
    authz.grant_folder(actor=owner, library=project.library, user="dave", folder_id=project.ids["A"], role="editor")
    assert not authz.can_write(carla, project.library, project.ids["a1"])
    assert authz.can_write(dave, project.library, project.ids["a1"]) and authz.can_write(dave, project.library, project.ids["a2"])
    assert not authz.can_write(dave, project.library, project.ids["b1"])
    assert not authz.can_write(dave, project.library, project.ids["r1"])
    assert not authz.can_read(dave, project.library, project.ids["b1"])


def test_a_viewer_of_the_project_shared_a_folder_to_edit_writes_there_and_nowhere_else(project):
    bob = project.users["bob"]  # viewer of the whole project
    assert not authz.can_write(bob, project.library, project.ids["a1"])
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="bob", folder_id=project.ids["A"], role="editor")
    assert authz.can_write(bob, project.library, project.ids["a1"])
    assert not authz.can_write(bob, project.library, project.ids["b1"])
    assert authz.can_read(bob, project.library, project.ids["b1"])  # the project role is kept


def test_the_owner_and_the_people_of_the_whole_project_still_see_everything(project):
    for name in ("owner", "alice", "bob"):
        assert all(_reads(project.users[name], project.library, project.ids).values()), name


def test_a_list_shows_only_what_the_person_may_open(project):
    from fichero_server.api.main import readable_documents

    carla = _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"], role="viewer")
    request = type("R", (), {"state": type("S", (), {"bootstrap_auth": False, "user": carla})()})()
    scope = [project.ids[k] for k in ("A", "B", "a1", "b1", "r1", "sub", "a2")]
    kept = readable_documents(request, project.library, scope)
    assert kept == [project.ids[k] for k in ("A", "a1", "sub", "a2")]


def test_a_refusal_names_nothing_the_person_may_not_see(project):
    carla = _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"], role="viewer")
    for target, kind in ((project.ids["b1"], "read"), (project.ids["B"], "read")):
        with pytest.raises(authz.AuthorizationError) as refused:
            authz.assert_can_read(carla, project.library, target)
        text = str(refused.value)
        assert text == "read access denied" and "Folder B" not in text and "Page b1" not in text and target not in text
    with pytest.raises(authz.AuthorizationError) as refused:
        authz.assert_can_write(carla, project.library, project.ids["a1"])
    assert "Folder" not in str(refused.value) and project.ids["a1"] not in str(refused.value)


def test_only_a_folder_of_this_project_can_be_shared(project):
    _person(project.harness, "carla")
    owner = project.users["owner"]
    for bad in (project.ids["a1"], "no-such-id"):  # a page, and nothing at all
        with pytest.raises(ValueError, match="choose a folder of this project"):
            authz.grant_folder(actor=owner, library=project.library, user="carla", folder_id=bad, role="viewer")
    with pytest.raises(ValueError):
        authz.grant_folder(actor=owner, library=project.library, user="carla", folder_id=project.ids["A"], role="owner")
    with pytest.raises(authz.AuthorizationError):  # only the project's owner shares it
        authz.grant_folder(actor=project.users["alice"], library=project.library, user="carla", folder_id=project.ids["A"],
                           role="viewer")


# -- the invitation names the folder --------------------------------------------------------------------------------------
def test_an_invitation_to_a_folder_makes_a_scoped_member_who_reaches_only_that_folder(project):
    minted = _invite(project.harness, "erin", folder_id=project.ids["A"], role="viewer")
    assert minted.status_code == 200, minted.text
    listed = _as(project.harness, "owner").get("/api/pair/invites").json()
    assert [row["folder_id"] for row in listed] == [project.ids["A"]]
    paired = _redeem(project.harness, minted.json()["code"], new_password="a-long-password")
    assert paired.status_code == 200, paired.text
    erin = project.harness.app_db.get_user_by_username("erin")
    assert project.harness.app_db.get_library_role(erin.id, authz.normalize_library_path(project.library)).role == "scoped"
    seen = _reads(erin, project.library, project.ids)
    assert seen["a1"] and seen["a2"] and not (seen["b1"] or seen["r1"] or seen["B"])
    assert not authz.can_write(erin, project.library, project.ids["a1"])  # a viewer by default


def test_an_invitation_to_edit_a_folder_lets_the_person_write_there_only(project):
    minted = _invite(project.harness, "frank", folder_id=project.ids["B"], role="editor")
    _redeem(project.harness, minted.json()["code"], new_password="a-long-password")
    frank = project.harness.app_db.get_user_by_username("frank")
    assert authz.can_write(frank, project.library, project.ids["b1"])
    assert not authz.can_read(frank, project.library, project.ids["a1"])


def test_an_existing_person_invited_to_a_folder_gains_it_and_keeps_the_project_role(project):
    minted = _invite(project.harness, "bob", folder_id=project.ids["A"], role="editor")
    assert minted.status_code == 200, minted.text
    assert _redeem(project.harness, minted.json()["code"]).status_code == 200
    bob = project.users["bob"]
    assert authz.can_write(bob, project.library, project.ids["a1"]) and not authz.can_write(bob, project.library, project.ids["b1"])
    assert project.harness.app_db.get_library_role(bob.id, authz.normalize_library_path(project.library)).role == "viewer"


@pytest.mark.parametrize("folder", ["a1", "missing"])
def test_an_invitation_names_a_real_folder_or_is_refused_in_words(project, folder):
    target = project.ids["a1"] if folder == "a1" else "no-such-folder"
    refused = _invite(project.harness, "gina", folder_id=target)
    assert refused.status_code == 422 and "choose a folder of this project" in refused.json()["detail"]


def test_a_folder_is_shared_with_a_named_person(project):
    refused = _as(project.harness, "owner").post("/api/pair/code", json={"folder_id": project.ids["A"]})
    assert refused.status_code == 422 and "named person" in refused.json()["detail"]


def test_the_folder_is_in_the_mint_audit(project):
    from fichero_server.models import ActionAudit

    _invite(project.harness, "hana", folder_id=project.ids["A"])
    rows = [a for a in project.harness.app_db.query(ActionAudit) if a.action_name == "invite.mint"]
    assert rows and rows[-1].params["folder_id"] == project.ids["A"]


def test_only_the_owner_may_share_a_folder(project):
    refused = _invite(project.harness, "ivan", client=_as(project.harness, "alice"), folder_id=project.ids["A"])
    assert refused.status_code == 403
