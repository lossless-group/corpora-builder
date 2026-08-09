"""Tests for capture from the screen — spec: context-v/specs/Capture-From-The-Screen.md.

Through FastAPI's TestClient, with a fake fetcher patched in so no test touches
the network. The behaviour under protection is the *gate*: a server that was not
started writable must refuse, and must say so in `/api/meta` so the page never
offers an action that will fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.capture.fetch import FetchResult
from src.server.app import create_app
from src.store import LocalFsStore


class FakeFetcher:
    def __init__(self, result: FetchResult) -> None:
        self.result = result

    def fetch(self, url: str, full: bool = False) -> FetchResult:
        return self.result


OK = FetchResult(
    ok=True,
    status="HTTP 200 (body verified)",
    title="Ocean Energy Report",
    publisher="IEA-OES",
    published_at="2025-03-01",
    body="Real prose about ocean energy that is long enough to be an excerpt here.",
    content_type="text/html",
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing in this module may reach the internet."""
    monkeypatch.setattr("src.server.app.JinaFetcher", lambda *a, **k: FakeFetcher(OK))


def client(tmp_path: Path, writable: bool) -> TestClient:
    return TestClient(create_app(LocalFsStore(tmp_path), "test", writable=writable))


@pytest.mark.spec("WRITE-01")
def test_posting_a_url_creates_a_source(tmp_path: Path) -> None:
    api = client(tmp_path, writable=True)

    response = api.post("/api/capture", json={"url": "https://example.org/a", "domain": "topic/x"})

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["title"] == "Ocean Energy Report"
    assert body["status"] == "candidate"
    assert LocalFsStore(tmp_path).exists(body["path"])


@pytest.mark.spec("WRITE-02")
def test_a_read_only_server_refuses_and_writes_nothing(tmp_path: Path) -> None:
    """The first target this surface ever had was a client corpus."""
    api = client(tmp_path, writable=False)

    response = api.post("/api/capture", json={"url": "https://example.org/a"})

    assert response.status_code == 403
    assert LocalFsStore(tmp_path).list() == []


@pytest.mark.spec("WRITE-03")
def test_a_duplicate_reports_the_existing_path(tmp_path: Path) -> None:
    api = client(tmp_path, writable=True)
    first = api.post("/api/capture", json={"url": "https://www.example.org/a/"}).json()

    second = api.post("/api/capture", json={"url": "http://example.org/a?utm_source=x"}).json()

    assert second["created"] is False
    assert second["duplicate_of"] == first["path"]
    assert len([k for k in LocalFsStore(tmp_path).list() if k.endswith(".md")]) == 1


@pytest.mark.spec("WRITE-04")
def test_meta_reports_whether_capture_is_enabled(tmp_path: Path) -> None:
    """So the page never offers an action that will fail."""
    assert client(tmp_path, writable=True).get("/api/meta").json()["writable"] is True
    assert client(tmp_path, writable=False).get("/api/meta").json()["writable"] is False


@pytest.mark.spec("WRITE-05")
def test_a_failed_fetch_still_creates_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = FetchResult(ok=False, status="HTTP 404 (not found)")
    monkeypatch.setattr("src.server.app.JinaFetcher", lambda *a, **k: FakeFetcher(failed))
    api = client(tmp_path, writable=True)

    body = api.post("/api/capture", json={"url": "https://example.org/gone"}).json()

    assert body["created"] is True
    assert body["machine_verdict"] == "HTTP 404 (not found)"
    assert body["content_pulled"] is False


@pytest.mark.spec("WRITE-06")
def test_filing_into_a_new_domain_is_not_an_error(tmp_path: Path) -> None:
    api = client(tmp_path, writable=True)

    body = api.post(
        "/api/capture", json={"url": "https://example.org/a", "domain": "thesis/brand-new"}
    ).json()

    assert body["created"] is True
    assert body["path"].startswith("live/thesis/brand-new/sources/")
