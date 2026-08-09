"""URL normalisation — the dedup key.

Rules carried from `memopop-orchestrator/src/curation/best_sources.py`'s
`canonical_url`. Deliberately NOT imported from there: the operator deferred
cross-app convergence, and a shared package across a Python orchestrator, a Node
service and a Tauri app is three bindings and a release cadence nobody wants.

The risk that buys is recorded as open question 1 of the spec: the day a second
writer exists, a normalisation mismatch is a silent dedup failure.

The tension the rules balance: collapse enough that the same article fetched
twice is one source, but not so much that two genuinely different pages become
one. Over-collapsing loses evidence; under-collapsing duplicates it.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

#: Params that identify a campaign, not a resource. Dropping them collapses the
#: same article shared five ways into one source.
_TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "ga_")
_TRACKING_EXACT = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "igshid",
        "mkt_tok",
        "ref",
        "referrer",
        "source",
        "s_cid",
        "cmp",
    }
)


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in _TRACKING_EXACT or lowered.startswith(_TRACKING_PREFIXES)


def normalize_url(raw: str) -> str:
    """Return a canonical form of `raw` suitable for cross-source dedup.

    Collapses what is cosmetic and keeps what addresses a different resource.
    Over-collapsing is the more expensive mistake: two genuinely different
    articles becoming one source loses evidence a memo may already cite.
    """
    text = (raw or "").strip()
    if not text:
        return ""

    if "//" not in text:
        text = f"https://{text}"

    try:
        parts = urlsplit(text)
    except ValueError:
        return text

    scheme = "https" if parts.scheme in ("", "http", "https") else parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    netloc = host
    if parts.port and not (
        (scheme == "https" and parts.port == 443) or (scheme == "http" and parts.port == 80)
    ):
        netloc = f"{host}:{parts.port}"

    path = parts.path.rstrip("/") or ""

    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)
    ]
    query = urlencode(sorted(kept))

    # Scheme and fragment are both dropped from the KEY: http and https address
    # the same resource, and a fragment addresses a position within one.
    return f"{netloc}{path}" + (f"?{query}" if query else "")
