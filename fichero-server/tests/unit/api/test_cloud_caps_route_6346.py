"""`ai.cloud.caps-are-one-audited-action` (#6346): the app-wide caps are read and set through `/api/ai/cloud-caps`, audited
first; set back to the `from` figure undoes it; below 0 is refused."""
from fichero_server.llm import spend
from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401


def _owner(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    return harness.client(), signed_in_client(harness, users["owner"]).headers



def test_default_then_set_read_back_audited_and_undone(harness, monkeypatch):
    client, h = _owner(harness, monkeypatch)
    first = client.get("/api/ai/cloud-caps", headers=h)
    assert first.status_code == 200, first.text
    assert first.json() == {"monthly_cap_usd": 10.0, "daily_cap_usd": None}

    put = client.put("/api/ai/cloud-caps", json={"which": "monthly", "cap_usd": 40}, headers=h)
    assert put.status_code == 200, put.text
    assert client.put("/api/ai/cloud-caps", json={"which": "daily", "cap_usd": 5}, headers=h).status_code == 200
    assert client.get("/api/ai/cloud-caps", headers=h).json() == {"monthly_cap_usd": 40.0, "daily_cap_usd": 5.0}
    assert spend.app_cap_usd(spend.APP_MONTHLY_KEY) == 40.0

    rows = [a for a in harness.app_db.list_action_audits() if a.action_name == "app.set_cloud_cap"]
    assert len(rows) == 2
    monthly = next(r for r in rows if r.after["which"] == "monthly")
    assert monthly.before == {"which": "monthly", "cap_usd": None} and monthly.after["cap_usd"] == 40.0

    client.put("/api/ai/cloud-caps", json={"which": "monthly", "cap_usd": None}, headers=h)  # undo: back to the `from` figure
    client.put("/api/ai/cloud-caps", json={"which": "daily", "cap_usd": None}, headers=h)
    assert client.get("/api/ai/cloud-caps", headers=h).json() == {"monthly_cap_usd": 10.0, "daily_cap_usd": None}


def test_below_zero_is_refused_and_nothing_changes(harness, monkeypatch):
    client, h = _owner(harness, monkeypatch)
    assert client.put("/api/ai/cloud-caps", json={"which": "monthly", "cap_usd": -1}, headers=h).status_code == 422
    assert client.get("/api/ai/cloud-caps", headers=h).json()["monthly_cap_usd"] == 10.0
    assert not [a for a in harness.app_db.list_action_audits() if a.action_name == "app.set_cloud_cap"]
