"""Getting bytes and metadata from a URL.

Behind an interface on purpose. The test suite performs no network I/O — a live
fetch is a gated, deliberate run, the same discipline as the proving-corpus and
live-R2 tests. Mocked HTTP proves the code shape and says nothing about what a
real page returns, so pretending otherwise would be the comfortable lie this
project keeps refusing.

`ok=False` is not an exception. A URL that 404s is *information* — it is how you
learn a citation rotted — so a failed fetch still produces a `FetchResult` and
still produces a file. See `CAPTURE-03`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

# Re-exported: `prose_excerpt` moved down to `src/model/text.py` so the manifest
# can compute the same excerpt without importing the capture package — which
# eagerly imports `add`, which imports the manifest. Call sites are unchanged.
from src.model.text import prose_excerpt as prose_excerpt


@dataclass
class FetchResult:
    """What came back, including when nothing did."""

    ok: bool
    #: Human-readable outcome, destined for `machine_verdict`. Never `verdict`.
    status: str
    title: str = ""
    publisher: str = ""
    published_at: str = ""
    body: str = ""
    content_type: str = ""
    #: Raw bytes, when the resource is a binary rather than a page.
    raw: bytes = b""


class Fetcher(Protocol):
    """Anything that can turn a URL into a `FetchResult`."""

    def fetch(self, url: str, full: bool = False) -> FetchResult:
        """Retrieve `url`. When `full` is False, metadata and a short excerpt."""
        ...


class JinaFetcher:
    """Fetch through `r.jina.ai`, as augment-it and memopop both do.

    Jina returns a small preamble (Title, URL Source, Published Time) ahead of
    the markdown body, which is where `title` and `published_at` come from.
    """

    def __init__(self, endpoint: str = "https://r.jina.ai/", timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def fetch(self, url: str, full: bool = False) -> FetchResult:
        try:
            response = httpx.get(
                f"{self.endpoint}{url}",
                timeout=self.timeout,
                follow_redirects=True,
                headers={"X-Return-Format": "markdown"},
            )
        except httpx.HTTPError as exc:
            # Not raised: a fetch failure is a fact about the source, and the
            # caller writes a file recording it.
            return FetchResult(ok=False, status=f"fetch_failed ({type(exc).__name__})")

        content_type = response.headers.get("content-type", "")
        if response.status_code != 200:
            return FetchResult(
                ok=False,
                status=f"HTTP {response.status_code}",
                content_type=content_type,
            )

        if "application/pdf" in content_type:
            return FetchResult(
                ok=True,
                status="HTTP 200 (binary)",
                content_type=content_type,
                raw=response.content,
            )

        preamble, body = parse_jina_preamble(response.text)
        return FetchResult(
            ok=True,
            status="HTTP 200 (body verified)",
            title=preamble.get("Title", ""),
            publisher=preamble.get("Published Source", ""),
            published_at=preamble.get("Published Time", ""),
            body=body,
            content_type=content_type,
        )


_PREAMBLE_LINE = re.compile(r"^([A-Z][A-Za-z ]{2,30}):\s*(.*)$")
#: Jina's marker for "everything after this is the page". The preamble above it
#: is blank-line separated, so scanning to the first blank line finds only the
#: title — which is exactly the bug that put "URL Source: … Markdown Content:"
#: into the first excerpt this tool ever wrote.
_BODY_MARKER = "Markdown Content"


def parse_jina_preamble(text: str) -> tuple[dict[str, str], str]:
    """Split Jina's `Key: value` preamble from the markdown body.

    `published_at` is lifted out of the preamble to the top level because sort
    and filter surfaces read it as first-class — augment-it's `liftPublishedAt`
    does exactly this, and the blueprint makes it a ruling.
    """
    lines = text.splitlines()
    preamble: dict[str, str] = {}
    start = 0

    for index, line in enumerate(lines):
        if not line.strip():
            continue
        match = _PREAMBLE_LINE.match(line)
        if not match:
            start = index
            break
        key, value = match.group(1), match.group(2).strip()
        if key == _BODY_MARKER:
            start = index + 1
            break
        preamble[key] = value
    else:
        start = len(lines)

    return preamble, "\n".join(lines[start:]).lstrip("\n")
