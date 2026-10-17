"""sharing.remote-run-in-host-activity (#5732): a run started from a paired Mac names its person AND device.

Every run starter takes `started_by` from `started_by_for(ctx)`, so the host's Activity row (which shows
`started_by`) reads "alice on Alice's Mac" for a remote start and just the person for a local one.
"""

from pathlib import Path

from fichero_server.actions.registry import ActionContext, started_by_for


def test_a_remote_start_names_the_person_and_the_device():
    ctx = ActionContext(actor="alice", device={"id": "d1", "name": "Alice's Mac"})
    assert started_by_for(ctx) == "alice on Alice's Mac"


def test_a_local_start_is_just_the_person_and_no_actor_is_the_owner():
    assert started_by_for(ActionContext(actor="alice")) == "alice"
    assert started_by_for(ActionContext(actor="")) == "owner"


def test_no_route_still_builds_started_by_from_the_bare_actor():
    routes = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "api" / "routes"
    offenders = [str(p.relative_to(routes)) for p in routes.rglob("*.py")
                 if 'started_by=ctx.actor or "owner"' in p.read_text()]
    assert offenders == []
