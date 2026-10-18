"""Every Set Up fix either acts or says why not (#5790; `source.onboard.every-setup-button-acts-or-says-why`): the
licence problem carries the licence the "Review the licence…" button opens, and each fix kind a refusal offers has an
action the app calls or a reason it is unavailable."""
from fichero_server.recipes import assemble
from fichero_server.recipes.assemble import Answers, Card, _problem


def _card(**kw) -> Card:
    base = dict(id="reader-a", pin={"model": "a"}, jobs=frozenset({"read-a-line"}), scripts=frozenset({"Latn"}),
                languages=None, material=frozenset({"handwriting"}))
    return Card(**{**base, **kw})


def _answers() -> Answers:
    return Answers(languages=frozenset({"en"}), scripts=frozenset({"Latn"}), material="handwriting")


def test_a_licence_problem_carries_the_licence_to_review():
    p = _problem("read-a-line", [_card(open_licence=False, licence="CC-BY-NC-4.0")], _answers(), "handwriting", "")
    assert p["kind"] == "licence-not-accepted"
    assert p["licence"] == {"card": "reader-a", "name": "CC-BY-NC-4.0",
                            "words": "its licence, CC-BY-NC-4.0, needs accepting: accept it to use it"}


def test_other_problems_carry_no_licence():
    p = _problem("read-a-line", [], _answers(), "handwriting", "")
    assert "licence" not in p


def test_every_fix_a_refusal_offers_acts_or_says_why_not():
    offered = {f for fixes in assemble._FIXES.values() for f in fixes}
    assert offered <= set(assemble.FIX_ACTIONS), offered - set(assemble.FIX_ACTIONS)
    for fix, (acts, why_not) in assemble.FIX_ACTIONS.items():
        assert bool(acts) != bool(why_not), f"{fix}: needs exactly one of an action or a reason"


def test_every_action_names_a_route_that_exists():
    from fichero_server.api.routes.ai.local_models import router as local_models
    from fichero_server.api.routes.system.recipes import router as recipes

    have = {(m, "/api" + r.path) for router in (local_models, recipes) for r in router.routes
            for m in getattr(r, "methods", ()) or ()}
    for fix, (acts, _) in assemble.FIX_ACTIONS.items():
        if acts:
            method, path = acts.split(" ", 1)
            assert (method, path) in have, f"{fix}: {acts} is not a route"
