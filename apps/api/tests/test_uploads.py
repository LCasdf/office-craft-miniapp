from fastapi.testclient import TestClient
from oc_api.main import create_app

client = TestClient(create_app())


def test_upload_credential_stub():
    r = client.post(
        "/v1/uploads/credential",
        json={"taskType": "pdf_compress", "fileCount": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["uploadId"].startswith("upl_")
    assert "expireAt" in data
    assert data["cos"]["pathPrefix"].endswith(f"/{data['uploadId']}/")
    assert data["estimatedCostQuota"] == 1
    assert data["cos"]["credentials"]["expiredTime"] > data["cos"]["credentials"]["startTime"]


def test_upload_credential_rejects_zero_files():
    r = client.post(
        "/v1/uploads/credential",
        json={"taskType": "pdf_compress", "fileCount": 0},
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40001


def test_upload_credential_merge_rejects_one_file():
    r = client.post(
        "/v1/uploads/credential",
        json={"taskType": "pdf_merge", "fileCount": 1},
    )
    assert r.json()["code"] == 40001
