from fastapi.testclient import TestClient

from oc_api.main import create_app


client = TestClient(create_app())


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert "requestId" in body


def test_wx_login_stub():
    r = client.post("/v1/auth/wx-login", json={"code": "test"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["accessToken"]


def test_create_task_requires_idempotency_key():
    r = client.post("/v1/tasks", json={"type": "pdf_compress", "inputs": []})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 40008
