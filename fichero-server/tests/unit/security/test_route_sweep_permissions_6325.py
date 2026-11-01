# ruff: noqa: F811  (fixtures imported from other test modules and taken by name)
"""sharing.every-route-keeps-a-denied-page-private (#6325): fire EVERY served route and action as a person who must not read a seeded secret,
and fail if the secret, or the Mac's own machinery, comes back.

Callers: alice (editor, deny on folder B), bob (viewer, deny on B), carla (editor shared folder A), dana (viewer shared folder A);
carla and dana also with a decoy query parameter (`?x_id=<A>`) that no route declares. Controls: the owner, erin (plain editor), fred
(plain viewer), who must keep working, so over-refusal fails too.

THIS REALLY FIRES destructive routes (the MLX runtime delete, model deletes, snapshots, purges). The module therefore REFUSES to run
unless it is isolated (`_refuse_unless_isolated`): HOME and the MLX runtime point into the test's scratch directory, the network, child
processes, `kill` and every delete outside the scratch directory raise, and the library is a scratch library. Never loosen that.

A known hole is a named strict xfail citing #6325 (HOLES): when its fix lands the xfail passes, and strict makes that a failure, so the
entry has to be deleted. A leak that is in no HOLES entry fails `test_no_unlisted_leak`.
"""
import enum
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import typing
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from fichero_server.db.manager import db_manager
from fichero_server.models import AgentNote, AgentNoteActor, AgentNoteSourceAnchor, Conversation, DocType, Document, FileType, KnowledgeClaim, Status
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.security import authz
from tests.route_inventory import served_routes
from tests.unit.security.test_a_page_deny_reaches_every_record_on_it import Annotation, ContentRepresentation, Note, SourceAnchor, _segment
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401
from tests.unit.transport.test_person_bound_invite_5910 import _as
from tests.unit.transport.test_share_scope_5967 import _person, project  # noqa: F401

#: Streams hang a test client; ending a session ends the caller for every route after it.
SKIP = re.compile(r"stream|/events|/sse|shutdown|/restart|/quit|/ws\b|/mcp\b|/auth/logout|/auth/sign-out|/auth/sessions|/change|revoke-self")
WRITES = {"POST", "PUT", "PATCH", "DELETE"}
DENIED = ("alice", "bob", "carla", "dana")
SCOPED = ("carla", "dana")
#: Who is fired on a change before the controls: the four who must be refused, and the plain viewer.
UNTRUSTED = (*DENIED, "fred")


class Blocked(Exception):
    pass


def _inside(path, root) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(root))
        return True
    except (ValueError, OSError):
        return False


def _refuse_unless_isolated(scratch: Path) -> None:
    """Called before a single route is fired. Raises unless HOME, the MLX runtime and the library are all inside `scratch`."""
    from fichero_server.llm.mlx_runtime import mlx_runtime_dir

    for what, where in (("HOME", os.path.expanduser("~")), ("Path.home()", str(Path.home())), ("the MLX runtime", str(mlx_runtime_dir()))):
        if not _inside(where, scratch):
            raise RuntimeError(f"route sweep refused: {what} is {where!r}, not inside the scratch directory {str(scratch)!r}")
    if not _inside(scratch, tempfile.gettempdir()):
        raise RuntimeError(f"route sweep refused: the scratch directory {str(scratch)!r} is not under the temp directory")


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    """HOME and the MLX runtime in scratch; network, subprocess, kill and deletes outside scratch raise."""
    home = tmp_path / "scratch-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)  # a route given a relative path writes beside the test, not into the checkout (review 6 item 9)
    from fichero_server.llm.mlx_runtime import _RUNTIME_DIRNAME

    (home / _RUNTIME_DIRNAME).mkdir()
    (home / _RUNTIME_DIRNAME / "pyvenv.cfg").write_text("x")
    monkeypatch.setenv("FICHERO_MLX_RUNTIME_DIR", str(home / _RUNTIME_DIRNAME))
    real_connect, real_rmtree, real_remove, real_unlink = socket.socket.connect, shutil.rmtree, os.remove, os.unlink

    def connect(self, addr):
        if isinstance(addr, tuple) and addr[0] not in ("127.0.0.1", "::1", "localhost"):
            raise Blocked(f"net {addr}")
        return real_connect(self, addr)

    def nope(*a, **k):
        raise Blocked(f"exec {a[:1]}")

    def guarded(real):
        def inner(path, *a, **k):
            if "dir_fd" not in k and not (_inside(path, tmp_path) or _inside(path, tempfile.gettempdir())):  # rmtree unlinks by name; libraries make temp dirs
                raise Blocked(f"delete outside the temp directory {path}")
            return real(path, *a, **k)
        return inner

    from fichero_server.importers import derivatives

    monkeypatch.setattr(derivatives, "_embed_stage", lambda doc_id, library: None)  # a saved page queues a model load: not what this proves
    monkeypatch.setattr(socket.socket, "connect", connect)
    for owner, name in ((subprocess, "Popen"), (os, "system"), (os, "kill"), (os, "_exit"), (os, "execv"), (os, "execvp")):
        monkeypatch.setattr(owner, name, nope)
    monkeypatch.setattr(shutil, "rmtree", guarded(real_rmtree))
    monkeypatch.setattr(os, "remove", guarded(real_remove))
    monkeypatch.setattr(os, "unlink", guarded(real_unlink))
    return tmp_path


def test_the_sweep_refuses_to_run_outside_scratch(scratch, monkeypatch):
    _refuse_unless_isolated(scratch)  # the fixture's own isolation passes
    monkeypatch.setenv("HOME", str(Path("/nonexistent/someone")))
    with pytest.raises(RuntimeError, match="refused"):
        _refuse_unless_isolated(scratch)
    monkeypatch.setenv("HOME", str(scratch / "scratch-home"))
    monkeypatch.setenv("FICHERO_MLX_RUNTIME_DIR", "/nonexistent/someone/Library/mlx-runtime")
    with pytest.raises(RuntimeError, match="MLX runtime"):
        _refuse_unless_isolated(scratch)


def test_deletes_outside_scratch_are_blocked(scratch):
    with pytest.raises(Blocked):
        shutil.rmtree(str(Path(tempfile.gettempdir()).parent / "not-scratch-xyz"))
    with pytest.raises(Blocked):
        os.remove("/etc/hosts-not-scratch")


# ---- seeding ---------------------------------------------------------------------------------------------------------------------

def seed(project, scratch_dir):
    """SECRET on the denied folder, its page and every record resting on that page. Returns the records' ids."""
    db = db_manager.get_database(project.harness.library)
    ids = project.ids
    b = db.get(Document, ids["B"])
    b.name = "SECRETFOLDER"
    db.save(b)
    page_file = scratch_dir / "b1.txt"
    page_file.write_text("SECRETTEXT")
    d = db.get(Document, ids["b1"])
    d.name = "SECRETNAME"
    d.page_content = "SECRETTEXT"
    d.attributes = {"secretattr": "SECRETATTR"}
    d.path, d.file_type, d.doc_type, d.status = str(page_file), FileType.text, DocType.file, Status.completed
    db.save(d)
    a = db.get(Document, ids["a1"])
    a.page_content = "PLAINTEXT"
    db.save(a)
    out = {}
    c = KnowledgeClaim(text="SECRETCLAIM", source_document_id=ids["b1"], subject_canonical="Ann", predicate_verb="owned", object_phrase="x", source_excerpt="SECRETEXCERPT")
    db.save(c)
    out["claim_id"] = c.id
    e = KnowledgeEntity(canonical_name="SECRETENTITY", entity_type=EntityType.person, source_document_ids=[ids["b1"]])
    db.save(e)
    out["entity_id"] = e.id
    n = AgentNote(body="SECRETAGENTNOTE", source_anchor=AgentNoteSourceAnchor(document_id=ids["b1"]), actor=AgentNoteActor(actor_id="agent"))
    db.save(n)
    out["agent_note_id"] = n.id
    cv = Conversation(title="SECRETCONV", messages=[{"role": "assistant", "content": "SECRETANSWER"}], scope_document_id=ids["b1"], document_ids=[], metadata={"author": "owner"})
    db.save(cv)
    out["conversation_id"] = cv.id
    free = Conversation(title="SECRETUNSCOPED", messages=[{"role": "user", "content": "SECRETMSG"}], metadata={"author": "owner"})
    db.save(free)
    out["free_conversation_id"] = free.id
    an = Annotation(kind="highlight", document_id=ids["b1"], body="SECRETANNOT") if "body" in Annotation.model_fields else Annotation(kind="highlight", document_id=ids["b1"])
    db.save(an)
    out["annotation_id"] = an.id
    page = Document(name="SECRETPAGE", doc_type=DocType.page, parent_id=ids["b1"])
    db.save(page)
    out["page_id"] = page.id
    nt = Note(page_id=page.id, body="SECRETNOTE")
    db.save(nt)
    out["note_id"] = nt.id
    s = _segment(db, d)
    out["segment_id"] = s.id
    out["pass_id"] = s.pass_id
    r = ContentRepresentation(document_id=ids["b1"], kind="transcription", content="SECRETREADING", source_anchor=SourceAnchor(document_id=ids["b1"]))
    db.save(r)
    out["representation_id"] = r.id
    out.update(_seed_a_run(project))
    return out


def _seed_a_run(project):
    """Two real runs, by the owner: one over a recipe whose folder source is B, one over a `search` source that names no page. Both
    hold the page's text in their state, history and record."""
    owner = _as(project.harness, "owner")

    def run(label, node):
        made = owner.post("/api/workflows", json={"name": label, "edges": [], "nodes": [node]})
        assert made.status_code == 200, made.text
        started = owner.post("/api/workflow-execution/execute", json={"workflow_id": made.json()["id"], "inputs": {}})
        assert started.status_code == 202, started.text
        thread_id = started.json()["thread_id"]
        for _ in range(300):
            if owner.get(f"/api/workflow-execution/threads/{thread_id}/status").json().get("status") in ("completed", "failed"):
                break
            time.sleep(0.2)
        return made.json()["id"], thread_id

    workflow_id, thread_id = run("recipe over B", {"id": "src", "tool": "folder", "label": "F", "inputs": {"folder_id": project.ids["B"], "include_subfolders": True}, "config": {}})
    _, search_thread_id = run("recipe by search", {"id": "src", "tool": "search", "label": "S", "inputs": {"query": "SECRETTEXT", "search_type": "fulltext"}, "config": {}})
    return {"workflow_id": workflow_id, "thread_id": thread_id, "search_thread_id": search_thread_id}


def fill(name, ids, seeded):
    """What an id-like path, query or body field is aimed at; anything else gets a filler."""
    table = {"document_id": ids["b1"], "doc_id": ids["b1"], "parent_id": ids["B"], "folder_id": ids["B"], "root_id": ids["B"], "source_document_id": ids["b1"],
             "page_id": seeded.get("page_id"), "item_id": ids["b1"], "claim_id": seeded["claim_id"], "entity_id": seeded["entity_id"], "note_id": seeded["note_id"],
             "conversation_id": seeded["conversation_id"], "annotation_id": seeded["annotation_id"], "segment_id": seeded.get("segment_id"),
             "pass_id": seeded.get("pass_id"), "representation_id": seeded.get("representation_id"), "reading_id": seeded.get("representation_id"),
             "q": "SECRET", "query": "SECRET", "id": ids["b1"], "workflow_id": seeded.get("workflow_id"), "thread_id": seeded.get("thread_id")}
    n = name.lower()
    return table.get(n) or ("x-" + n)


def model_body(model, ids, seeded, depth=0):
    out = {}
    for name, f in model.model_fields.items():
        if not f.is_required() and name not in ("document_id", "document_ids", "doc_id", "ids", "parent_id"):
            continue
        out[name] = value(f.annotation, name, ids, seeded, depth)
    return out


def value(ann, name, ids, seeded, depth):
    if depth > 4:
        return None
    origin, args = typing.get_origin(ann), typing.get_args(ann)
    if origin is typing.Union or str(origin) == "<class 'types.UnionType'>":
        return value([a for a in args if a is not type(None)][0], name, ids, seeded, depth)
    if origin is typing.Literal:
        return args[0]
    if origin in (list, set, tuple, frozenset):
        if name.endswith("ids") or name == "ids":
            return [ids["b1"]]
        return [value(args[0], name, ids, seeded, depth + 1)] if args else []
    if origin is dict:
        return {}
    if origin is typing.Annotated:
        return value(args[0], name, ids, seeded, depth)
    if isinstance(ann, type):
        if issubclass(ann, BaseModel):
            return model_body(ann, ids, seeded, depth + 1)
        if issubclass(ann, enum.Enum):
            return list(ann)[0].value
        if ann is bool:
            return False
        if ann is int:
            return 1
        if ann is float:
            return 1.0
        if ann in (dict, list):
            return ann()
    return fill(name, ids, seeded)


def route_url(route, ids, seeded, library, decoy):
    url = route.path
    for p in re.findall(r"{([^}:]+)(?::path)?}", route.path):
        url = re.sub(r"{%s(:path)?}" % p, quote(str(fill(p, ids, seeded)), safe=""), url)
    qs = []
    for q in route.dependant.query_params:
        if q.field_info.is_required() or q.name in ("document_id", "doc_id", "document_ids", "parent_id", "folder_id", "q", "query", "library_path"):
            val = library if q.name == "library_path" else fill(q.name, ids, seeded)
            qs.append(f"{q.name}={quote(str(val), safe='')}")
    if decoy:
        qs.append(f"x_id={ids['A']}")
    return url + ("?" + "&".join(qs) if qs else "")


def fire(client, method, path, **kw):
    try:
        r = client.request(method, path, **kw)
        return r.status_code, r.text[:200000]
    except Blocked as b:
        return "BLOCKED", str(b)
    except Exception as b:
        return "EXC", repr(b)[:200]


def _secrets(text):
    """The seeded words in an answer; a bare SECRET is the query echoed back."""
    return sorted(set(re.findall(r"SECRET[A-Z]+", text)))


# ---- the sweep (once per session: the rows are plain data) -------------------------------------------------------------------------

_ROWS: list | None = None
_TIMES: dict = {}


def _people(project):
    lib = authz.normalize_library_path(project.library)
    for name in ("alice", "bob"):
        project.harness.app_db.set_library_acl_override(user_id=project.users[name].id, library_path=lib, target_id=project.ids["B"], effect="deny")
    for name, role in (("carla", "editor"), ("dana", "viewer")):
        _person(project.harness, name)
        authz.grant_folder(actor=project.users["owner"], library=lib, user=name, folder_id=project.ids["A"], role=role)
    for name, role in (("erin", authz.ROLE_EDITOR), ("fred", authz.ROLE_VIEWER)):
        u = _person(project.harness, name)
        project.harness.app_db.set_library_role(user_id=u.id, library_path=lib, role=role)
    return {n: _as(project.harness, n) for n in (*DENIED, "owner", "erin", "fred")}


def _alive(project, seeded):
    """What was seeded, and whether it is still there (not deleted, not trashed)."""
    from fichero_server.llm.mlx_runtime import mlx_runtime_dir

    db = db_manager.get_database(project.harness.library)
    page = db.get(Document, project.ids["b1"])
    kept = {"claim": db.get(KnowledgeClaim, seeded["claim_id"]), "entity": db.get(KnowledgeEntity, seeded["entity_id"]),
            "scoped conversation": db.get(Conversation, seeded["conversation_id"]), "unscoped conversation": db.get(Conversation, seeded["free_conversation_id"]),
            "annotation": db.get(Annotation, seeded["annotation_id"]), "note": db.get(Note, seeded["note_id"]), "agent note": db.get(AgentNote, seeded["agent_note_id"])}
    out = [(label, row is not None) for label, row in kept.items()]
    out += [("page b1", page is not None and page.deleted_at is None), ("MLX runtime", mlx_runtime_dir().exists())]
    return out


def _run_sweep(project, scratch_dir):
    from fichero_server.actions.registry import registry

    _refuse_unless_isolated(scratch_dir)
    started = time.monotonic()
    seeded = seed(project, scratch_dir)
    who = _people(project)
    ids, library = project.ids, project.library
    #: A route or action that names a conversation is fired on the scoped one and on the unscoped one.
    #: A route that names a run is fired on the run over a folder and on the run over a search, which names no page.
    variants = (seeded, {**seeded, "conversation_id": seeded["free_conversation_id"]}, {**seeded, "thread_id": seeded["search_thread_id"]})
    rows = []

    def call(name, surface, ident, method, path, decoy, **kw):
        st, text = fire(who[name], method, path, **kw)
        if st == 401:  # a route ended this caller's session
            who[name] = _as(project.harness, name)
            st, text = fire(who[name], method, path, **kw)
        rows.append({"surface": surface, "ident": ident, "who": name, "decoy": decoy, "status": st, "hits": _secrets(text), "text": text[:120]})

    api = [r for r in served_routes(project.harness.app) if isinstance(r, APIRoute) and not SKIP.search(r.path)]
    for route in api:  # reads first: the writes below delete the seed
        if "GET" in route.methods:
            for name in who:
                for decoy in ((False, True) if name in SCOPED else (False,)):
                    for url in dict.fromkeys(route_url(route, ids, s, library, decoy) for s in variants):
                        call(name, "get", f"GET {route.path}", "GET", url, decoy)
    _TIMES["get"] = time.monotonic() - started

    changing = []
    # read-only actions first; an action another test registered (and left behind) is not the app's
    shipped = ((n, sp) for n, sp in registry._actions.items() if getattr(sp.execute, "__module__", "").startswith("fichero_server"))
    for aname, spec in sorted(shipped, key=lambda kv: (not kv[1].read_only, kv[0])):
        model = getattr(spec, "params_model", None) or getattr(spec, "params", None)
        bodies = []
        for variant in variants:
            try:
                body = model_body(model, ids, variant) if isinstance(model, type) and issubclass(model, BaseModel) else {}
            except Exception:
                body = {}
            if body not in bodies:
                bodies.append(body)
        # An action that changes things is fired by the callers who must be refused first; the controls who may do it go last, in `controls`,
        # because they delete the seed (the owner's `claim.delete` removed the claim a third of the way in, review 6).
        for name in who if spec.read_only else UNTRUSTED:
            for decoy in ((False, True) if name in SCOPED else (False,)):
                for body in bodies:
                    call(name, "action", f"ACTION {aname}", "POST", "/api/actions/invoke" + (f"?x_id={ids['A']}" if decoy else ""), decoy, json={"name": aname, "params": body})
        if not spec.read_only:
            changing.append((aname, bodies))
    _TIMES["action"] = time.monotonic() - started

    controlled = []
    writes = sorted((r for r in api if set(r.methods) & WRITES), key=lambda r: "DELETE" in r.methods)
    for route in writes:  # deletes last
        method = sorted(set(route.methods) & WRITES)[0]
        body = {}
        if route.body_field:
            ann = route.body_field.field_info.annotation
            try:
                mod = [a for a in (ann, *typing.get_args(ann)) if isinstance(a, type) and issubclass(a, BaseModel)]
                body = model_body(mod[0], ids, seeded) if mod else {}
            except Exception:
                body = {}
        for name in UNTRUSTED:
            for decoy in ((False, True) if name in SCOPED else (False,)):
                kw = {"json": body} if route.body_field else {}
                for url in dict.fromkeys(route_url(route, ids, s, library, decoy) for s in variants):
                    call(name, "write", f"{method} {route.path}", method, url, decoy, **kw)
        controlled.append((route, method, body))

    # Acting on a record counts: nothing the callers who must be refused did may have removed what was seeded.
    for label, alive in _alive(project, seeded):
        rows.append({"surface": "state", "ident": label, "who": "refused callers", "decoy": False, "status": 200 if alive else 404, "hits": [], "text": ""})

    # The controls last (they may delete the seed): the plain editor, then the owner, on every change.
    for aname, bodies in changing:
        for name in ("erin", "owner"):
            for body in bodies:
                call(name, "action", f"ACTION {aname}", "POST", "/api/actions/invoke", False, json={"name": aname, "params": body})
    for route, method, body in controlled:
        kw = {"json": body} if route.body_field else {}
        for url in dict.fromkeys(route_url(route, ids, s, library, False) for s in variants):
            call("erin", "write", f"{method} {route.path}", method, url, False, **kw)
    _TIMES["total"] = time.monotonic() - started
    return rows


@pytest.fixture
def sweep(project, scratch):
    global _ROWS
    if _ROWS is None:
        _ROWS = _run_sweep(project, scratch)
    return _ROWS


# ---- what counts as a failure -----------------------------------------------------------------------------------------------------

#: Writes under these prefixes change the owner's Mac (the MLX runtime, local models, machines, registered libraries, chain presets, a path an export writes to).
MACHINE = re.compile(r"^(POST|PUT|PATCH|DELETE) /api/(library(?=$)|local-inference|local-models|machines|registry|chains/presets|export/(jsonl|training|parquet|eleventy-site|markdown-folder|word|excel))\b")
#: Routes that spend the owner's keys or use the network: a caller who can only read (a viewer, a person shared a folder to read) is refused.
SPEND = re.compile(r"^POST /api/(model-comparison/(compare|compare-node)|research/tools/(web-search|browser-navigate))$")
#: Reads a plain editor or viewer is refused on by design.
OWNER_ONLY_GETS = {"/api/auth/invites", "/api/auth/local-clients/requests", "/api/auth/local-clients/switches", "/api/authz/members", "/api/hpc/clusters",
                   "/api/hpc/prompts", "/api/machines", "/api/pair/invites", "/api/users"}


def _owner_only_action(ident: str) -> bool:
    from fichero_server.actions.registry import registry

    return ident.startswith("ACTION ") and ident[7:] in registry._actions and registry.get(ident[7:]).owner_only


def _by(rows):
    out = defaultdict(dict)
    for r in rows:
        out[(r["surface"], r["ident"])][(r["who"], r["decoy"])] = r
    return out


def found(rows) -> dict:
    """{(kind, ident): sorted callers} for everything that must not happen."""
    out = defaultdict(set)
    for key, by in _by(rows).items():
        for (who, decoy), r in by.items():
            if who in DENIED and r["hits"]:
                out[("text", key[1])].add(who + ("+decoy" if decoy else ""))
            if who != "owner" and r["status"] not in (401, 403) and (MACHINE.match(key[1]) or _owner_only_action(key[1])):
                out[("machine", key[1])].add(who)
            if who in ("dana", "fred") and r["status"] not in (401, 403) and SPEND.match(key[1]):
                out[("spend", key[1])].add(who)
            if key[0] == "state" and r["status"] != 200:
                out[("acted", key[1])].add("a caller who must be refused")
        for who in SCOPED:
            plain, decoy = by.get((who, False)), by.get((who, True))
            if plain and decoy and plain["status"] == 403 and decoy["status"] != 403:
                out[("decoy", key[1])].add(who)
    return {k: sorted(v) for k, v in out.items()}


#: Known holes: name -> [(kind, regex of the ident)]. Each is a strict xfail citing #6325: when a fix lands the xfail passes, strict makes
#: that a failure, and the entry is deleted. Anything the sweep finds that no entry covers fails `test_no_unlisted_leak`.
HOLES: dict[str, list] = {
}


def _hits(hole, got):
    return sorted(k for k in got if any(k[0] == kind and re.fullmatch(rx, k[1]) for kind, rx in HOLES[hole]))


def test_no_unlisted_leak(sweep):
    got = found(sweep)
    covered = {k for h in HOLES for k in _hits(h, got)}
    new = {k: v for k, v in got.items() if k not in covered}
    assert not new, "\n".join(f"{kind}: {ident} -> {who}" for (kind, ident), who in sorted(new.items()))


@pytest.mark.parametrize("hole", [pytest.param(h, marks=pytest.mark.xfail(strict=True, reason=f"{h}: stays open under #6325")) for h in HOLES])
def test_known_hole(sweep, hole):
    assert not _hits(hole, found(sweep))


def test_the_seed_is_visible_to_the_owner_and_the_controls_are_not_over_refused(sweep):
    by = _by(sweep)
    seen = {w for key, d in by.items() if key[0] in ("get", "action") for w in d[("owner", False)]["hits"]}
    assert {"SECRETTEXT", "SECRETCLAIM", "SECRETENTITY", "SECRETNAME", "SECRETNOTE", "SECRETAGENTNOTE", "SECRETREADING"} <= set(seen), seen
    refused = []
    for (surface, ident), d in sorted(by.items()):
        if surface not in ("get", "action") or d[("owner", False)]["status"] != 200:
            continue
        for who in ("erin", "fred"):
            if d[(who, False)]["status"] == 403 and not (surface == "action" and who == "fred") and ident.split(" ", 1)[1] not in OWNER_ONLY_GETS and not (surface == "action" and _owner_only_action(ident)):
                refused.append(f"{who}: {ident}")
    assert not refused, refused
    for who in ("erin", "fred"):  # a plain editor and viewer read what the owner reads
        for ident in ("GET /api/documents", "GET /api/entities", "GET /api/claims"):
            if ("get", ident) in by:
                assert by[("get", ident)][(who, False)]["status"] == 200, (who, ident)


def test_report_the_time(sweep):
    assert len(sweep) > 5000, "the sweep fired too little to mean anything"
    print(f"route sweep: {len(sweep)} requests, reads {_TIMES['get']:.0f}s, +actions {_TIMES['action'] - _TIMES['get']:.0f}s, +writes {_TIMES['total'] - _TIMES['action']:.0f}s")


def test_the_owner_keeps_the_machines_own_routes(project, scratch):
    """The control for H6/H9: refused to everyone else, the owner still deletes the runtime (in scratch), reaches the preset and exports."""
    from fichero_server.llm.mlx_runtime import mlx_runtime_dir

    _refuse_unless_isolated(scratch)
    owner = _as(project.harness, "owner")
    assert mlx_runtime_dir().exists()
    assert owner.delete("/api/local-inference/runtime").status_code == 200
    assert not mlx_runtime_dir().exists()
    assert owner.post("/api/chains/presets/paleography").status_code != 403  # 400 here: this scratch library has no paleography recipes
    assert owner.post("/api/export/jsonl", json={"output_path": str(scratch / "out"), "target_id": project.ids["A"]}).status_code == 200
