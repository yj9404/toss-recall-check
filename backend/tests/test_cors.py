import pytest

LIVE = "https://recall-check.web.tossmini.com"
PRIVATE = "https://recall-check.private-web.tossmini.com"
LOCAL = "http://localhost:5173"


def _preflight(client, origin):
    return client.options(
        "/api/v1/recalls",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


@pytest.mark.parametrize("origin", [LIVE, PRIVATE])
def test_toss_origins_allowed(make_client, origin):
    client = make_client()
    resp = client.get("/api/v1/recalls", headers={"Origin": origin})
    assert resp.headers["access-control-allow-origin"] == origin
    assert _preflight(client, origin).status_code == 200


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "https://other-app.web.tossmini.com", LOCAL]
)
def test_other_origins_rejected_in_prod(make_client, origin):
    client = make_client()
    resp = client.get("/api/v1/recalls", headers={"Origin": origin})
    assert "access-control-allow-origin" not in resp.headers
    assert _preflight(client, origin).status_code == 400


def test_localhost_allowed_only_in_dev(make_client):
    client = make_client(env="dev")
    resp = client.get("/api/v1/recalls", headers={"Origin": LOCAL})
    assert resp.headers["access-control-allow-origin"] == LOCAL


def test_origins_follow_app_name(make_client):
    client = make_client(app_name="other-app")
    origin = "https://other-app.web.tossmini.com"
    resp = client.get("/api/v1/recalls", headers={"Origin": origin})
    assert resp.headers["access-control-allow-origin"] == origin
    assert (
        "access-control-allow-origin"
        not in client.get("/api/v1/recalls", headers={"Origin": LIVE}).headers
    )
