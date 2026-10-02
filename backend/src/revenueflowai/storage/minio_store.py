"""MinIO (S3-compatible) implementation of ObjectStore, for local/dev Compose use."""

import aioboto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from revenueflowai.config import get_settings
from revenueflowai.storage.base import ObjectStore


class MinioObjectStore(ObjectStore):
    def __init__(self) -> None:
        settings = get_settings()
        self._session = aioboto3.Session()
        self._endpoint_url = settings.s3_endpoint_url
        self._access_key = settings.s3_access_key
        self._secret_key = settings.s3_secret_key
        self._region = settings.s3_region

    def _client_ctx(self):
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=BotoConfig(signature_version="s3v4"),
        )

    async def put_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        async with self._client_ctx() as client:
            await client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    async def get_object(self, bucket: str, key: str) -> bytes:
        async with self._client_ctx() as client:
            response = await client.get_object(Bucket=bucket, Key=key)
            return await response["Body"].read()

    async def object_exists(self, bucket: str, key: str) -> bool:
        async with self._client_ctx() as client:
            try:
                await client.head_object(Bucket=bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response["Error"]["Code"] in {"404", "NoSuchKey"}:
                    return False
                raise

    async def ensure_bucket(self, bucket: str) -> None:
        async with self._client_ctx() as client:
            try:
                await client.head_bucket(Bucket=bucket)
            except ClientError:
                await client.create_bucket(Bucket=bucket)
