"""The PROVING-CORPUS round-trip — spec: context-v/specs/Storage-Seam.md.

Gated, not skipped-by-default-and-forgotten. The MVP plan's acceptance for
Phase 1 is that reach-edu's corpus (517 markdown files, 57 funder dirs, 156MB)
round-trips byte-identically. That corpus lives in a sibling repo, so this test
runs only when pointed at it:

    CORPORA_PROVING_CORPUS=../augment-it/clients/reach-edu/corpus uv run pytest -q

Why bother when STORE-01..10 already pass: synthetic fixtures test what you
thought of. 517 real files test what you didn't — accented funder slugs, PDFs
with null bytes, empty files, names with spaces and ampersands, paths deeper
than anyone designs for.

READ-ONLY against the corpus. `augment-it/clients/*/corpus/` is on the
Autonomy-Gates RED list; this test never writes there, only reads and then
writes elsewhere.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from src.store import CachedStore, LocalFsStore

CORPUS_ENV = "CORPORA_PROVING_CORPUS"
_corpus = os.environ.get(CORPUS_ENV)

pytestmark = pytest.mark.skipif(
    not _corpus or not Path(_corpus).is_dir(),
    reason=f"set {CORPUS_ENV} to the reach-edu corpus path to run",
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.spec("STORE-14")
def test_proving_corpus_round_trips_byte_identical(tmp_path: Path) -> None:
    """Every file in, every file out, same bytes, same count."""
    source = LocalFsStore(Path(_corpus or "."))
    target = CachedStore(LocalFsStore(tmp_path))

    keys = source.list()
    assert keys, "the proving corpus appears to be empty"

    for key in keys:
        target.write(key, source.read(key))

    assert target.list() == keys

    mismatched = [k for k in keys if _digest(target.read(k)) != _digest(source.read(k))]
    assert mismatched == [], f"{len(mismatched)} file(s) did not round-trip"
