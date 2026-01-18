from __future__ import annotations

import boto3
from botocore.client import Config
from kbeton.core.config import settings

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )

def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    c = s3_client()
    c.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)

def get_bytes(key: str) -> bytes:
    c = s3_client()
    obj = c.get_object(Bucket=settings.s3_bucket, Key=key)
    return obj["Body"].read()
