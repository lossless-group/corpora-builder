"""`corpora add <url>` — the first command that pays for itself.

Two rules shape everything here, both paid for elsewhere in this tree:

**Two-tier fetch.** A bare `add` writes metadata and a short excerpt, and sets
`content_pulled: false`. Full body only on `--fetch`. This is not a performance
tweak — augment-it exists *because* bulk AI enrichment went haywire. Gate every
enrichment step; spend grounding cost on survivors, never on candidates.

**A failure is a fact.** An unreachable URL still produces a file, with the
failure recorded in `machine_verdict`. A source that 404s is how you learn a
citation rotted, and deleting that information to keep the corpus tidy is how
you lose the ability to notice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.capture.binary import build_binary_asset, is_binary
from src.capture.fetch import Fetcher, prose_excerpt
from src.model import SourceFile, StrandedContent, normalize_url, source_filename
from src.store import CorpusStore

#: The cheap preview kept on a candidate. Arbitrary and still untested against
#: how an analyst actually triages — open question 2 of the spec, and open
#: question 4 of the blueprint before it.
EXCERPT_CHARS = 200

#: Where a source with no domain lands. Capture-first staging, and in practice
#: the richest bucket — reach-edu's inbox held more research than any funder
#: directory. Not a cleanup queue.
INBOX_PREFIX = "live/inbox/"


@dataclass
class AddResult:
    """What `add_source` did, including when it deliberately did nothing."""

    path: str
    created: bool
    source: SourceFile
    #: Set when `created` is False — the path that already held this URL.
    duplicate_of: str = ""


def domain_prefix(domain: str | None) -> str:
    """`thesis/consumer-immunology` -> `live/thesis/consumer-immunology/sources/`."""
    if not domain:
        return INBOX_PREFIX
    return f"live/{domain.strip('/')}/sources/"


def _existing_by_normalized_url(store: CorpusStore, prefix: str, key: str) -> str:
    """The path already holding `key`, or empty.

    Reads every markdown file under the prefix. Fine at corpus scale — the
    largest real corpus is 845 files and `CachedStore` makes a repeat scan free.
    A `normalized_url` index is a Phase 4 concern, once checkpoints exist to
    keep one honest.
    """
    for path in store.list(prefix):
        if not path.endswith(".md"):
            continue
        try:
            existing = SourceFile.parse(store.read(path).decode("utf-8", errors="replace"))
        except StrandedContent:
            # Damaged file. Not this command's job to fix, and not a reason to
            # refuse the write — but it must not be mistaken for a match.
            continue
        if existing.normalized_url and existing.normalized_url == key:
            return path
    return ""


def add_source(
    store: CorpusStore,
    url: str,
    fetcher: Fetcher,
    domain: str | None = None,
    full: bool = False,
    origin: str = "analyst-paste",
    now: str = "",
) -> AddResult:
    """Fetch `url`, build a source file, and write it unless it already exists."""
    stamp = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    fetched_date = stamp[:10]
    prefix = domain_prefix(domain)
    key = normalize_url(url)

    duplicate = _existing_by_normalized_url(store, prefix, key)
    if duplicate:
        existing = SourceFile.parse(store.read(duplicate).decode("utf-8", errors="replace"))
        return AddResult(path=duplicate, created=False, source=existing, duplicate_of=duplicate)

    result = fetcher.fetch(url, full)

    excerpt = ""
    body = ""
    if result.body:
        excerpt = prose_excerpt(result.body, EXCERPT_CHARS)
        if full:
            body = result.body

    source = SourceFile(
        url=url,
        normalized_url=key,
        title=result.title,
        publisher=result.publisher,
        fetched_at=stamp,
        published_at=result.published_at,
        status="candidate",
        content_pulled=bool(full and result.body),
        excerpt=excerpt,
        origin=origin,
        # A machine wrote this. `verdict` stays empty on every path, forever —
        # reachability is not approval.
        machine_verdict=result.status,
        body=body,
    )

    taken = {p.rsplit("/", 1)[-1] for p in store.list(prefix)}
    filename = source_filename(result.title, fetched_date, url=url, taken=taken)
    path = f"{prefix}{filename}"

    if is_binary(url, result.content_type):
        sibling_name = filename[: -len(".md")] + ".pdf"
        if result.ok and result.raw:
            store.write(f"{prefix}{sibling_name}", result.raw)
            source.binary_asset = build_binary_asset(sibling_name, result.raw, stamp, "ok")
        else:
            status = "http_error" if not result.ok else "fetch_failed"
            source.binary_asset = build_binary_asset(sibling_name, b"", stamp, status)

    store.write(path, source.render().encode("utf-8"))
    return AddResult(path=path, created=True, source=source)
