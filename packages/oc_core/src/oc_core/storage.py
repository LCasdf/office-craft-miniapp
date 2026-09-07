"""S3-compatible object storage (MinIO locally, COS later)."""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from oc_core.config import get_settings


@lru_cache
def get_s3_client() -> BaseClient:
    settings = get_settings()
    kwargs: dict = {
        "service_name": "s3",
        "aws_access_key_id": settings.s3_access_key or settings.cos_secret_id or "minioadmin",
        "aws_secret_access_key": settings.s3_secret_key or settings.cos_secret_key or "minioadmin",
        "region_name": settings.s3_region or settings.cos_region or "us-east-1",
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client(**kwargs)


def bucket_name() -> str:
    settings = get_settings()
    return settings.cos_bucket or "office-craft"


def ensure_bucket() -> None:
    client = get_s3_client()
    name = bucket_name()
    try:
        client.head_bucket(Bucket=name)
    except ClientError:
        try:
            client.create_bucket(Bucket=name)
        except ClientError:
            # race or already exists under another account — ignore if subsequent ops work
            pass


def put_bytes(key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
    ensure_bucket()
    get_s3_client().put_object(
        Bucket=bucket_name(),
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def get_bytes(key: str) -> bytes:
    resp = get_s3_client().get_object(Bucket=bucket_name(), Key=key)
    return resp["Body"].read()


def delete_object(key: str) -> bool:
    """Delete one object. Returns False if missing/errors (best-effort)."""
    try:
        get_s3_client().delete_object(Bucket=bucket_name(), Key=key)
        return True
    except ClientError:
        return False


def list_objects(prefix: str, *, max_keys: int = 1000) -> list[dict]:
    """List objects under prefix. Each item: {key, last_modified, size}."""
    ensure_bucket()
    client = get_s3_client()
    out: list[dict] = []
    token: str | None = None
    while True:
        kwargs: dict = {"Bucket": bucket_name(), "Prefix": prefix, "MaxKeys": min(max_keys, 1000)}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            out.append(
                {
                    "key": obj["Key"],
                    "last_modified": obj["LastModified"],
                    "size": int(obj.get("Size") or 0),
                }
            )
            if len(out) >= max_keys:
                return out
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return out


def delete_prefix(prefix: str, *, max_keys: int = 1000) -> int:
    """Delete all objects under prefix. Returns deleted count."""
    objs = list_objects(prefix, max_keys=max_keys)
    n = 0
    for obj in objs:
        if delete_object(obj["key"]):
            n += 1
    return n


def presign_get(key: str, *, expires_in: int | None = None) -> str:
    settings = get_settings()
    ttl = expires_in or settings.download_url_ttl_seconds
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name(), "Key": key},
        ExpiresIn=ttl,
    )


def upload_path_prefix(*, env: str, user_id: str, upload_id: str) -> str:
    return f"{env}/{user_id}/uploads/{upload_id}/"


def result_object_key(*, env: str, user_id: str, task_id: str, filename: str = "result.pdf") -> str:
    return f"{env}/{user_id}/results/{task_id}/{filename}"
