"""Extra coverage for storage put/get/presign and uploads credential."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from oc_api.main import create_app
from oc_core.storage import ensure_bucket, get_bytes, presign_get, put_bytes


def test_storage_put_get_presign_ensure(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("oc_core.storage.get_s3_client", lambda: client)
    monkeypatch.setattr("oc_core.storage.bucket_name", lambda: "office-craft")

    client.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "Head")
    client.create_bucket.return_value = {}
    ensure_bucket()
    client.create_bucket.assert_called()

    client.head_bucket.side_effect = None
    client.head_bucket.return_value = {}
    ensure_bucket()

    put_bytes("k", b"abc", content_type="application/pdf")
    client.put_object.assert_called()

    body = MagicMock()
    body.read.return_value = b"xyz"
    client.get_object.return_value = {"Body": body}
    assert get_bytes("k") == b"xyz"

    client.generate_presigned_url.return_value = "https://example/signed"
    assert presign_get("k").startswith("https://")


def test_uploads_credential_ok():
    c = TestClient(create_app())
    body = c.post(
        "/v1/uploads/credential",
        json={"taskType": "pdf_compress", "fileCount": 1},
    ).json()
    assert body["code"] == 0
    assert body["data"]["uploadId"]


def test_uploads_credential_rejects_bad_count():
    c = TestClient(create_app())
    body = c.post(
        "/v1/uploads/credential",
        json={"taskType": "pdf_merge", "fileCount": 1},
    ).json()
    assert body["code"] == 40001


def test_office_pdf_missing_soffice(monkeypatch, tmp_path):
    from oc_core.converters.office_pdf import OfficeConvertError, office_to_pdf

    monkeypatch.setattr("oc_core.converters.office_pdf.find_soffice", lambda: None)
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK")
    try:
        office_to_pdf(src, tmp_path / "out")
        raised = False
    except OfficeConvertError as e:
        raised = True
        assert "not installed" in str(e)
    assert raised


def test_upload_object_pdf_ok(monkeypatch):
    monkeypatch.setattr("oc_api.routers.uploads.put_bytes", lambda *a, **k: None)
    c = TestClient(create_app())
    r = c.post(
        "/v1/uploads/upl_testhost123456/objects",
        files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        data={"index": "0", "taskType": "pdf_compress"},
    )
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["cosKey"].endswith("0_a.pdf")


def test_upload_object_rejects_bad_ext(monkeypatch):
    monkeypatch.setattr("oc_api.routers.uploads.put_bytes", lambda *a, **k: None)
    c = TestClient(create_app())
    body = c.post(
        "/v1/uploads/upl_testhost123456/objects",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={"index": "0", "taskType": "pdf_merge"},
    ).json()
    assert body["code"] == 40001


def test_upload_object_bad_upload_id():
    c = TestClient(create_app())
    body = c.post(
        "/v1/uploads/not_an_upl/objects",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
        data={"index": "0", "taskType": "pdf_compress"},
    ).json()
    assert body["code"] == 40001
