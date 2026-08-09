"""`CorpusStore` over Cloudflare R2, via the S3 API.

R2 speaks enough S3 for boto3 to work unmodified, but NOT all of it. The one
absence that shaped this whole project: **R2 has no object versioning.**
`PutBucketVersioning` / `GetBucketVersioning` are unimplemented,
`ListObjectVersions` is absent, and object lock is not implemented either. That
is why version history is application-level (Phase 4's content-addressed objects
plus checkpoint manifests) rather than delegated to the substrate.

The bucket is a required constructor argument with no default, deliberately: the
name is derived from the resolved workspace (`src.identity.bucket_for`), so no
call site anywhere carries a literal bucket string. That is what makes swapping
in a didi.sh-backed workspace resolver a swap rather than a search-and-replace.
"""

from __future__ import annotations

import hashlib
from typing import Any

from botocore.exceptions import ClientError

from src.store.base import CorpusStore, KeyNotFound, ObjectStat

#: sha256 is stashed as object metadata on write so `stat` costs one HEAD rather
#: than a full download. R2's ETag is an md5 of the upload, not of the content
#: for multipart, so it is not a substitute. Objects written by anything other
#: than corpora-builder will not carry it — hence the fallback in `stat`.
_SHA_KEY = "sha256"


class R2Store(CorpusStore):
    """Keys become object keys in `bucket`."""

    def __init__(self, bucket: str, client: Any, prefix: str = "") -> None:
        self.bucket = bucket
        self.client = client
        # Scoped transparently: callers pass "live/a.md", the object lands at
        # "<prefix>live/a.md", and list() hands back the unprefixed key. That is
        # what lets a corpus share a client's existing bucket without every
        # call site learning about it.
        self.prefix = prefix

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _head(self, key: str) -> dict[str, Any]:
        try:
            return dict(self.client.head_object(Bucket=self.bucket, Key=self._k(key)))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                raise KeyNotFound(key) from exc
            raise

    def read(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._k(key))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                raise KeyNotFound(key) from exc
            raise
        body: bytes = response["Body"].read()
        return body

    def write(self, key: str, data: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._k(key),
            Body=data,
            Metadata={_SHA_KEY: hashlib.sha256(data).hexdigest()},
        )

    def exists(self, key: str) -> bool:
        try:
            self._head(key)
        except KeyNotFound:
            return False
        return True

    def stat(self, key: str) -> ObjectStat:
        head = self._head(key)
        digest = head.get("Metadata", {}).get(_SHA_KEY)
        if not digest:
            digest = hashlib.sha256(self.read(key)).hexdigest()
        return ObjectStat(size=int(head["ContentLength"]), content_hash=digest)

    def list(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._k(prefix)):
            keys.extend(obj["Key"][len(self.prefix) :] for obj in page.get("Contents", []))
        return sorted(keys)

    def delete(self, key: str) -> None:
        # S3 delete is idempotent and reports success for absent keys, so the
        # existence check is ours to make — the interface promises KeyNotFound.
        self._head(key)
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))
