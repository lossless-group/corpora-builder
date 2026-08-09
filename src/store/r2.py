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

from typing import Any

from src.store.base import CorpusStore, ObjectStat


class R2Store(CorpusStore):
    """Keys become object keys in `bucket`."""

    def __init__(self, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self.client = client

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def write(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def stat(self, key: str) -> ObjectStat:
        raise NotImplementedError

    def list(self, prefix: str = "") -> list[str]:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError
