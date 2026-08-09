"""Parse every real markdown file in the PROVING-CORPUS — spec: Source-File-Model.md.

The test that matters most in Phase 2, and the reason it is gated rather than
mocked: 845 markdown files written by three generations of tooling over months
are a harsher parser test than anything hand-written. Hand-written fixtures
cover what the author thought of.

    CORPORA_PROVING_CORPUS=../augment-it/clients/reach-edu/corpus uv run pytest -q

READ-ONLY. `augment-it/clients/*/corpus/` is on the Autonomy-Gates RED list.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.model import SourceFile, StrandedContent
from src.store import LocalFsStore

CORPUS_ENV = "CORPORA_PROVING_CORPUS"
_corpus = os.environ.get(CORPUS_ENV)

pytestmark = pytest.mark.skipif(
    not _corpus or not Path(_corpus).is_dir(),
    reason=f"set {CORPUS_ENV} to the reach-edu corpus path to run",
)


@pytest.mark.spec("CORPUS-01")
def test_every_real_markdown_file_parses() -> None:
    """Every file, no exceptions swallowed, failures named rather than counted."""
    store = LocalFsStore(Path(_corpus or "."))
    keys = [k for k in store.list() if k.endswith(".md")]
    assert keys, "no markdown found in the proving corpus"

    stranded: list[str] = []
    failed: list[tuple[str, str]] = []

    for key in keys:
        text = store.read(key).decode("utf-8", errors="replace")
        try:
            SourceFile.parse(text)
        except StrandedContent as exc:
            # A real find, not a parser bug — the ImmuneCo failure mode, in the
            # wild. Reported separately so it reads as corpus damage rather than
            # as this module being wrong.
            stranded.append(f"{key}: {exc}")
        except Exception as exc:  # noqa: BLE001 - the point is to catch everything
            failed.append((key, f"{type(exc).__name__}: {exc}"))

    assert not failed, f"{len(failed)} of {len(keys)} failed to parse:\n" + "\n".join(
        f"  {k} — {e}" for k, e in failed[:10]
    )
    assert not stranded, (
        f"{len(stranded)} of {len(keys)} file(s) carry stranded frontmatter — "
        f"real corpus damage of the ImmuneCo kind:\n" + "\n".join(f"  {s}" for s in stranded[:10])
    )
