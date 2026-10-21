"""sharing.share-sheet-chooses-what (#5967, release bar #5910 item 9): the owner shares a project or a FOLDER of it; a person
shared a folder reaches that folder and everything under it, nothing beside it; the engine checks it on every request; a person-bound
invitation can name the folder. A grant is (person, project, folder, role); a folder covers its own items by ancestry."""

import pytest

from fichero_server.api.routes.auth import pairing
from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document
from fichero_server.security import authz
from tests.route_inventory import api_routes
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
    assert refused.status_code == 400 and "choose a folder of this project" in refused.json()["detail"]


def test_a_folder_is_shared_with_a_named_person(project):
    refused = _as(project.harness, "owner").post("/api/pair/code", json={"folder_id": project.ids["A"]})
    assert refused.status_code == 400 and "named person" in refused.json()["detail"]


def test_the_folder_is_in_the_mint_audit(project):
    _invite(project.harness, "hana", folder_id=project.ids["A"])
    rows = [a for a in project.harness.app_db.list_action_audits() if a.action_name == "invite.mint"]
    assert rows and rows[-1].params["folder_id"] == project.ids["A"]


def test_only_the_owner_may_share_a_folder(project):
    refused = _invite(project.harness, "ivan", client=_as(project.harness, "alice"), folder_id=project.ids["A"])
    assert refused.status_code == 403


# -- review 704: a person shared one folder never reads the whole project through a library-level route ---------------------
def _app():  # api_routes(_app()) is every served route: FastAPI 0.141 keeps included routers whole in app.routes
    import importlib

    return importlib.import_module("fichero_server.api.main").app


def _walk(dependant):
    yield dependant
    for sub in dependant.dependencies:
        yield from _walk(sub)


def _library_level_get_routes():
    """(route, endpoint id) of every GET route that opens the library through the shared dependency and names no id."""
    from fastapi.routing import APIRoute

    found = []
    for route in api_routes(_app()):
        if not isinstance(route, APIRoute) or "GET" not in route.methods or "{" in route.path:
            continue
        names = {getattr(d.call, "__name__", "") for d in _walk(route.dependant)}
        if names & {"get_library_database", "get_library_database_for_write"}:
            found.append((route, f"{route.endpoint.__module__}:{route.endpoint.__name__}"))
    return found


def test_every_listed_route_exists_and_filters_its_rows():
    import inspect

    by_id = {}
    for route in api_routes(_app()):
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            by_id[f"{endpoint.__module__}:{endpoint.__name__}"] = route
    missing = sorted(authz.SCOPED_LIBRARY_READ_ROUTES - by_id.keys())
    assert not missing, f"listed but not a route (renamed?): {missing}"
    for name in authz.SCOPED_LIBRARY_READ_ROUTES:
        route = by_id[name]
        filters = ("readable_documents" in inspect.getsource(route.endpoint)
                   or any(getattr(d.call, "__name__", "") == "readable_rows" for d in _walk(route.dependant)))
        assert filters, f"{name} is on the scoped list but does not filter per row"


def test_a_scoped_person_is_refused_every_library_level_route_that_is_not_listed(project):
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"],
                       role="viewer")
    client = _as(project.harness, "carla")
    leaked = []
    for route, name in _library_level_get_routes():
        if name in authz.SCOPED_LIBRARY_READ_ROUTES:
            continue
        got = client.get(route.path)
        if got.status_code == 200:
            leaked.append(route.path)
    assert not leaked, f"a person shared one folder reads the whole project through: {leaked}"


def test_search_is_refused_in_words_that_name_nothing(project):
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"],
                       role="viewer")
    got = _as(project.harness, "carla").post("/api/search", json={"query": "Page b1"})
    assert got.status_code in (401, 403) and "Page b1" not in got.text and "Folder B" not in got.text


def test_a_listed_route_shows_only_the_folder(project):
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"],
                       role="viewer")
    got = _as(project.harness, "carla").get("/api/documents")
    assert got.status_code == 200, got.text
    text = got.text
    assert "Page a1" in text and "Page b1" not in text and "Page r1" not in text and "Folder B" not in text


def test_the_owner_still_reads_every_library_level_route_the_scoped_person_cannot(project):
    client = _as(project.harness, "owner")
    assert client.get("/api/documents").status_code == 200


def test_an_item_moved_out_of_the_granted_folder_disappears_for_the_person(project):
    carla = _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"],
                       role="viewer")
    assert authz.can_read(carla, project.library, project.ids["a1"])
    db = db_manager.get_database(project.harness.library)
    row = db.get(Document, project.ids["a1"])
    row.parent_id = project.ids["B"]
    db.save(row)
    assert not authz.can_read(carla, project.library, project.ids["a1"])


def test_an_editor_invited_to_view_a_folder_is_told_they_already_have_more(project):
    refused = _invite(project.harness, "alice", folder_id=project.ids["A"], role="viewer")
    assert refused.status_code == 409
    assert "already has more access" in refused.json()["detail"] and "editor" in refused.json()["detail"]
    assert "Folder A" not in refused.json()["detail"]


# -- review 705: streams and runs go round the per-row filter; they fail closed too ----------------------------------------
def _scoped_client(project, role="viewer"):
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"],
                       role=role)
    return _as(project.harness, "carla")


def _status(client, method, path):
    """The status only: a leaked event stream never ends, so the body is never read."""
    with client.stream(method, path) as response:
        return response.status_code


def _paths(suffix):
    from fastapi.routing import APIRoute

    return [route.path for route in api_routes(_app()) if isinstance(route, APIRoute) and route.path.endswith(suffix)]


@pytest.mark.parametrize("suffix", ["/activity/stream", "/changes/stream"])
def test_a_person_shared_a_folder_is_refused_the_library_wide_event_streams(project, suffix):
    client = _scoped_client(project)
    paths = _paths(suffix)
    assert paths, f"no route ends {suffix}"
    for path in paths:
        got = _status(client, "GET", path)
        assert got in (401, 403), f"{path} answered a person shared one folder with {got}"


def test_a_scoped_editor_cannot_start_a_run_or_any_library_level_write(project):
    """A folder to edit lets them edit THERE; a route that writes the library as a whole (a run over the project, a reindex,
    a batch) is refused, so a run they start can touch only what a path id names inside their grants."""
    from fastapi.routing import APIRoute

    client = _scoped_client(project, role="editor")
    started = []
    for route in api_routes(_app()):
        if not isinstance(route, APIRoute) or "{" in route.path or not (route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if "get_library_database_for_write" not in {getattr(d.call, "__name__", "") for d in _walk(route.dependant)}:
            continue
        for method in sorted(route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            if client.request(method, route.path, json={}).status_code < 300:
                started.append(f"{method} {route.path}")
    assert not started, f"a person shared one folder to edit changed the whole project through: {started}"


# -- review 707: a run's stream is checked against the RUN's library, whatever header (or none) the caller sends -----------
@pytest.fixture
def live_run(project):
    from pathlib import Path

    from fichero_server.execution import runner

    thread = "run-5967-stream"
    hub = runner.WorkflowEventHub()
    runner._set_workflow_state(thread, {"workflow_id": "w", "workflow_name": "w", "db_path": str(Path(project.library) / "fichero.duckdb"),
                                        "documents": [], "reader": "r", "status": "running", "events": hub, "error": None,
                                        "final_state": None})
    yield thread
    hub.put(None)
    runner._remove_workflow_state(thread)


def _stream_path(thread):
    return _paths("/stream/{thread_id}")[0].replace("{thread_id}", thread)


def test_a_run_stream_is_refused_to_a_scoped_person_who_sends_no_library_header(project, live_run):
    client = _scoped_client(project)
    client.headers.pop("X-Fichero-Library-Path", None)
    assert _status(client, "GET", _stream_path(live_run)) in (401, 403)


def test_a_run_stream_is_refused_to_someone_with_no_role_on_the_runs_library(project, live_run):
    _person(project.harness, "mallory")  # a member of nothing here (another project's person)
    client = _as(project.harness, "mallory", library=False)
    assert _status(client, "GET", _stream_path(live_run)) in (401, 403)


def test_a_run_stream_naming_another_library_is_refused(project, live_run, tmp_path):
    client = _as(project.harness, "owner")
    client.headers["X-Fichero-Library-Path"] = str(tmp_path / "other.fichero")
    assert _status(client, "GET", _stream_path(live_run)) in (400, 403, 404)


def test_the_owner_still_follows_a_run_with_or_without_the_header(project, live_run):
    import threading

    from fichero_server.execution import runner

    hub = runner._get_workflow_state(live_run)["events"]
    for library in (True, False):
        # an open stream never ends by itself and closing the client waits for it: end it a moment after the status
        threading.Timer(1.0, hub.put, [None]).start()
        assert _status(_as(project.harness, "owner", library=library), "GET", _stream_path(live_run)) == 200


def test_an_unknown_run_is_not_found_for_anyone(project):
    assert _status(_as(project.harness, "owner"), "GET", _stream_path("no-such-run")) == 404
