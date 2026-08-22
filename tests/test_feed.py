"""Covers `context-v/specs/Corpus-Change-Feed.md` — the change record, the git
source, and the two renderers.

Every repository here is built under `tmp_path`, so the suite is hermetic and
says nothing about the real corpus. Proving it is *useful* against real history
is the deliberate run named in the spec, not something a fixture can assert.

`FEED-14` is the load-bearing one: the conformance block runs against both
`GitChangeSource` and an in-memory fake with no branching in the test bodies. It
is this spec's `STORE-11`, and it is what makes swapping in a Kopia-backed source
later cost an implementation rather than a rewrite.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.feed.change import Change, ChangePage, ChangeSource, Rename, parse_subject
from src.feed.git_source import GitChangeSource
from src.feed.render import has_reason, render_prose, to_json

# ---------------------------------------------------------------------------
# helpers — a throwaway repository we can commit into deterministically
# ---------------------------------------------------------------------------

_ENV = {
    "GIT_AUTHOR_NAME": "Test Operator",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test Operator",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _run(repo: Path, *args: str, when: str | None = None) -> None:
    import os

    env = {**os.environ, **_ENV}
    if when:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _run(repo, "init", "-q", "-b", "main")
    _run(repo, "config", "user.name", "Test Operator")
    _run(repo, "config", "user.email", "test@example.com")


def _write(repo: Path, rel: str, body: str = "hello") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _commit(repo: Path, subject: str, when: str | None = None) -> None:
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", subject, when=when)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "corpus-repo"
    _init(r)
    return r


class FakeChangeSource(ChangeSource):
    """An in-memory source, so `FEED-14` has a second implementation to run the
    same suite against without inventing a whole backend."""

    def __init__(self, changes: list[Change]) -> None:
        self._changes = sorted(changes, key=lambda c: c.when, reverse=True)

    def changes(self, prefix: str = "", limit: int = 20) -> ChangePage:
        clean = prefix.rstrip("/")

        def keep(p: str) -> bool:
            return not prefix or p == clean or p.startswith(clean + "/")

        def scoped(c: Change) -> Change:
            return Change(
                id=c.id,
                when=c.when,
                who=c.who,
                subject=c.subject,
                added=[p for p in c.added if keep(p)],
                changed=[p for p in c.changed if keep(p)],
                removed=[p for p in c.removed if keep(p)],
                renamed=[r for r in c.renamed if keep(r.new)],
                bytes_total=c.bytes_total,
            )

        hits = [s for s in (scoped(c) for c in self._changes) if s.n_paths > 0]
        return ChangePage(changes=hits[:limit], truncated=len(hits) > limit)


# ---------------------------------------------------------------------------
# the record — shape, derivation, header parsing
# ---------------------------------------------------------------------------


@pytest.mark.spec("FEED-01")
def test_a_change_carries_identity_authorship_and_four_path_lists(repo: Path) -> None:
    _write(repo, "corpus/funders/a.md")
    _commit(repo, "capture(a): the first source")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert change.id and len(change.id) == 40
    assert isinstance(change.when, datetime) and change.when.tzinfo is not None
    assert change.who == "Test Operator"
    assert change.subject == "capture(a): the first source"
    assert change.added == ["corpus/funders/a.md"]
    assert change.changed == [] and change.removed == [] and change.renamed == []


@pytest.mark.spec("FEED-02")
def test_counts_and_bytes_are_derived_from_the_path_lists(repo: Path) -> None:
    _write(repo, "corpus/a.md", "a")
    _write(repo, "corpus/b.md", "b")
    _write(repo, "corpus/gone.md", "g")
    _commit(repo, "capture: seed")
    (repo / "corpus/gone.md").unlink()
    _write(repo, "corpus/c.md", "c")
    _write(repo, "corpus/d.md", "d")
    _commit(repo, "triage: two in, one out")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert change.n_added == len(change.added) == 2
    assert change.n_removed == len(change.removed) == 1
    assert change.n_paths == len(change.paths)
    assert change.bytes_total > 0


@pytest.mark.spec("FEED-05")
@pytest.mark.parametrize(
    "subject,verb,scope,sentence",
    [
        ("capture(bloomberg): the annual report", "capture", "bloomberg", "the annual report"),
        (
            "triage(corpora, inbox): batches 5-6 close",
            "triage",
            "corpora, inbox",
            "batches 5-6 close",
        ),
        ("progress: no scope here", "progress", None, "no scope here"),
    ],
)
def test_the_lossless_header_splits_into_verb_scope_and_sentence(
    subject: str, verb: str, scope: str | None, sentence: str
) -> None:
    assert parse_subject(subject) == (verb, scope, sentence)
    assert Change(id="x", when=datetime.now(UTC), who="w", subject=subject).subject == subject


@pytest.mark.spec("FEED-06")
def test_a_subject_outside_the_convention_becomes_the_whole_sentence() -> None:
    subject = "Merge pull request #12 from somewhere"
    verb, scope, sentence = parse_subject(subject)
    assert verb is None and scope is None
    assert sentence == subject


# ---------------------------------------------------------------------------
# scoping
# ---------------------------------------------------------------------------


@pytest.mark.spec("FEED-03")
def test_a_commit_touching_nothing_under_the_prefix_is_absent_entirely(repo: Path) -> None:
    _write(repo, "corpus/a.md")
    _commit(repo, "capture: in scope")
    _write(repo, "docs/readme.md")
    _commit(repo, "docs: out of scope")

    page = GitChangeSource(repo).changes(prefix="corpus")

    assert [c.subject for c in page.changes] == ["capture: in scope"]


@pytest.mark.spec("FEED-04")
def test_a_straddling_commit_carries_only_the_paths_inside_the_prefix(repo: Path) -> None:
    _write(repo, "corpus/a.md")
    _write(repo, "docs/b.md")
    _commit(repo, "capture: both halves")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert change.added == ["corpus/a.md"]
    assert all(p.startswith("corpus/") for p in change.paths)


# ---------------------------------------------------------------------------
# time, ordering, file kinds, renames
# ---------------------------------------------------------------------------


@pytest.mark.spec("FEED-08")
def test_commits_authored_in_another_timezone_come_back_as_utc(repo: Path) -> None:
    _write(repo, "corpus/a.md")
    _commit(repo, "capture: tokyo o'clock", when="2026-03-01T12:00:00+09:00")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert change.when.utcoffset() == timedelta(0)
    assert change.when.hour == 3  # 12:00 +09:00 is 03:00 UTC


@pytest.mark.spec("FEED-09")
def test_changes_are_ordered_newest_first(repo: Path) -> None:
    _write(repo, "corpus/a.md")
    _commit(repo, "capture: older", when="2026-01-01T00:00:00+00:00")
    _write(repo, "corpus/b.md")
    _commit(repo, "capture: newer", when="2026-02-01T00:00:00+00:00")

    page = GitChangeSource(repo).changes(prefix="corpus")

    assert [c.sentence for c in page.changes] == ["newer", "older"]


@pytest.mark.spec("FEED-10")
def test_binaries_appear_alongside_markdown(repo: Path) -> None:
    _write(repo, "corpus/report.md")
    (repo / "corpus/report.pdf").write_bytes(b"%PDF-1.7\x00\x01binary\xff")
    _commit(repo, "capture: report and its wrapper")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert "corpus/report.pdf" in change.added
    assert "corpus/report.md" in change.added


@pytest.mark.spec("FEED-11")
def test_a_moved_file_is_a_rename_not_a_delete_plus_an_add(repo: Path) -> None:
    body = "a genuinely substantial body of text " * 20
    _write(repo, "corpus/old/carnegie.md", body)
    _commit(repo, "capture: carnegie")
    (repo / "corpus/new").mkdir(parents=True, exist_ok=True)
    _run(repo, "mv", "corpus/old/carnegie.md", "corpus/new/carnegie.md")
    _commit(repo, "triage(carnegie): folder folds into its successor")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert change.renamed == [Rename(old="corpus/old/carnegie.md", new="corpus/new/carnegie.md")]
    assert change.added == [] and change.removed == []


@pytest.mark.spec("FEED-16")
def test_a_modified_file_is_changed_and_neither_added_nor_removed(repo: Path) -> None:
    _write(repo, "corpus/a.md", "first")
    _commit(repo, "capture: first")
    _write(repo, "corpus/a.md", "second")
    _commit(repo, "progress: revised")

    change = GitChangeSource(repo).changes(prefix="corpus").changes[0]

    assert change.changed == ["corpus/a.md"]
    assert change.added == [] and change.removed == []


# ---------------------------------------------------------------------------
# truncation — never silent
# ---------------------------------------------------------------------------


@pytest.mark.spec("FEED-12")
def test_a_capped_page_returns_the_limit_and_says_it_was_capped(repo: Path) -> None:
    for i in range(5):
        _write(repo, f"corpus/{i}.md")
        _commit(repo, f"capture: source {i}")

    page = GitChangeSource(repo).changes(prefix="corpus", limit=3)

    assert len(page.changes) == 3
    assert page.truncated is True
    assert "there are more" in render_prose(page)


@pytest.mark.spec("FEED-13")
def test_a_long_path_list_states_how_many_it_omitted(repo: Path) -> None:
    for i in range(12):
        _write(repo, f"corpus/f{i:02d}.md")
    _commit(repo, "triage: a batch")

    page = GitChangeSource(repo).changes(prefix="corpus")
    prose = render_prose(page, max_paths=4)

    assert "+8 more" in prose
    assert prose.count("corpus/f") == 4


# ---------------------------------------------------------------------------
# rendering — the rule the whole feature turns on
# ---------------------------------------------------------------------------


@pytest.mark.spec("FEED-07")
def test_a_change_with_no_usable_reason_renders_without_one_and_invents_nothing(
    repo: Path,
) -> None:
    _write(repo, "corpus/a.md")
    _commit(repo, "wip")

    page = GitChangeSource(repo).changes(prefix="corpus")
    prose = render_prose(page)

    assert has_reason(page.changes[0]) is False
    assert "1 added" in prose  # the counts still appear
    assert "wip" not in prose  # ...and the placeholder is not dressed up as a reason
    # Nothing was generated to fill the gap: the only prose lines are the
    # timestamp/author line, the counts, and the paths.
    body = [ln for ln in prose.splitlines() if ln.strip()]
    assert len(body) == 3


@pytest.mark.spec("FEED-15")
def test_json_round_trips_the_record_and_rendering_writes_nothing(repo: Path) -> None:
    import json

    _write(repo, "corpus/a.md")
    _commit(repo, "capture(a): a real sentence")

    source = GitChangeSource(repo)
    page = source.changes(prefix="corpus")
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout

    payload = json.loads(to_json(page))
    render_prose(page)

    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout

    assert before == after  # no renderer touched the working tree
    entry = payload["changes"][0]
    assert entry["id"] == page.changes[0].id
    assert entry["verb"] == "capture" and entry["scope"] == "a"
    assert entry["sentence"] == "a real sentence"
    assert entry["counts"]["added"] == 1


# ---------------------------------------------------------------------------
# FEED-14 — one suite, every implementation, no branching in the bodies
# ---------------------------------------------------------------------------


def _git_backed(tmp_path: Path) -> ChangeSource:
    r = tmp_path / "conformance-git"
    _init(r)
    _write(r, "corpus/one.md", "one")
    _commit(r, "capture(one): the first", when="2026-01-01T00:00:00+00:00")
    _write(r, "corpus/two.md", "two")
    _write(r, "outside/x.md", "x")
    _commit(r, "capture(two): the second", when="2026-02-01T00:00:00+00:00")
    return GitChangeSource(r)


def _memory_backed(tmp_path: Path) -> ChangeSource:
    return FakeChangeSource(
        [
            Change(
                id="a" * 40,
                when=datetime(2026, 1, 1, tzinfo=UTC),
                who="Test Operator",
                subject="capture(one): the first",
                added=["corpus/one.md"],
            ),
            Change(
                id="b" * 40,
                when=datetime(2026, 2, 1, tzinfo=UTC),
                who="Test Operator",
                subject="capture(two): the second",
                added=["corpus/two.md", "outside/x.md"],
            ),
        ]
    )


@pytest.mark.spec("FEED-14")
@pytest.mark.parametrize("build", [_git_backed, _memory_backed], ids=["git", "memory"])
def test_every_change_source_satisfies_the_same_contract(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    source = build(tmp_path)

    page = source.changes(prefix="corpus")

    # newest first
    assert [c.sentence for c in page.changes] == ["the second", "the first"]
    # scoped: nothing outside the prefix survives
    assert all(p.startswith("corpus/") for c in page.changes for p in c.paths)
    # UTC at rest
    assert all(c.when.utcoffset() == timedelta(0) for c in page.changes)
    # the header parsed, the subject retained
    assert page.changes[0].verb == "capture"
    assert page.changes[0].subject.startswith("capture(two):")
    # counts derive from the lists
    assert all(c.n_paths == len(c.paths) for c in page.changes)
    # truncation is reported, not silent
    capped = source.changes(prefix="corpus", limit=1)
    assert len(capped.changes) == 1 and capped.truncated is True
    # both renderers work over whatever produced the record
    assert "the second" in render_prose(page)
    assert '"verb": "capture"' in to_json(page)
