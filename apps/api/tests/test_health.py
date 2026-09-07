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


def test_metrics():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "oc_upload_orphan_cleanup_total" in r.text
    assert "oc_queue_depth" in r.text


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


def test_image_to_pdf_requires_inputs():
    r = client.post(
        "/v1/tasks",
        json={"type": "image_to_pdf", "inputs": []},
        headers={"Idempotency-Key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
    )
    assert r.json()["code"] == 40001


def test_office_to_pdf_rejects_bad_ext():
    r = client.post(
        "/v1/tasks",
        json={
            "type": "office_to_pdf",
            "inputs": [{"cosKey": "x/y/z.txt", "filename": "z.txt"}],
        },
        headers={"Idempotency-Key": "bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
    )
    assert r.json()["code"] == 40001


def test_pdf_compress_requires_pdf_and_quality():
    headers = {"Idempotency-Key": "cccccccc-bbbb-4ccc-8ddd-eeeeeeeeeeee"}
    empty = client.post(
        "/v1/tasks",
        json={"type": "pdf_compress", "inputs": [], "params": {"quality": "standard"}},
        headers=headers,
    )
    assert empty.json()["code"] == 40001
    bad_q = client.post(
        "/v1/tasks",
        json={
            "type": "pdf_compress",
            "inputs": [{"cosKey": "a/b.pdf", "filename": "a.pdf"}],
            "params": {"quality": "ultra"},
        },
        headers={"Idempotency-Key": "dddddddd-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
    )
    assert bad_q.json()["code"] == 40001


def test_pdf_merge_requires_two_pdfs():
    r = client.post(
        "/v1/tasks",
        json={
            "type": "pdf_merge",
            "inputs": [{"cosKey": "a/b.pdf", "filename": "a.pdf"}],
        },
        headers={"Idempotency-Key": "eeeeeeee-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
    )
    assert r.json()["code"] == 40001
