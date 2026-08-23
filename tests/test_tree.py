"""Covers `context-v/specs/Corpus-Tree.md`.

Everything except TREE-08 runs against `build_tree` directly, because it is a
pure function over strings and needs no corpus. TREE-08 is the one promise that
is about I/O rather than shape — that painting the tree reads no file bodies —
and it uses a counting store to say so in the only terms that mean anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.server.app import create_app
from src.server.tree import build_tree
from src.store import LocalFsStore

# A real slice of reach-edu: the `live/` wrapper layout and the content-addressed
# `bin/` store side by side, which is what the corpus actually looks like.
KEYS = [
    "live/funders/ascendium-education/sources/2026-06-11_report.md",
    "live/funders/ascendium-education/sources/2026-06-12_note.md",
    "live/funders/ballmer-group/sources/2026-05-02_grant.md",
    "live/strategies/workforce-development/sources/2026-04-01_brief.md",
    "bin/00/0029ed06d59e49407980a51fe7c4110056c2a674f92636d709f1b867161355d5.pdf",
    "bin/a1/a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00.pdf",
    "README.md",
]


def find(nodes: list, path: str):
    """Depth-first lookup by path, so assertions can name a node directly."""
    for n in nodes:
        if n.path == path:
            return n
        hit = find(n.children, path)
        if hit is not None:
            return hit
    return None


# ---------------------------------------------------------------------------
# shape
# ---------------------------------------------------------------------------


@pytest.mark.spec("TREE-01")
def test_nesting_follows_the_key_structure() -> None:
    tree = build_tree(KEYS)

    assert [n.name for n in tree] == ["bin", "live", "README.md"]
    ascendium = find(tree, "live/funders/ascendium-education/")
    assert ascendium is not None and ascendium.is_dir
    assert [c.name for c in ascendium.children] == ["sources"]


@pytest.mark.spec("TREE-02")
def test_a_folder_counts_every_file_beneath_it_not_its_children() -> None:
    """`funders/` has two immediate children and three files under it.

    The count an operator wants is the second one. A tree that reports 2 for a
    folder holding 3 sources is a tree you expand hoping.
    """
    tree = build_tree(KEYS)

    funders = find(tree, "live/funders/")
    assert funders is not None
    assert len(funders.children) == 2  # ascendium-education, ballmer-group
    assert funders.count == 3  # but three files beneath

    assert find(tree, "live/").count == 4
    assert find(tree, "bin/").count == 2


@pytest.mark.spec("TREE-03")
def test_folders_sort_before_files_and_each_group_alphabetically() -> None:
    tree = build_tree(["z-dir/a.md", "a-file.md", "m-dir/b.md", "b-file.md"])

    assert [n.name for n in tree] == ["m-dir", "z-dir", "a-file.md", "b-file.md"]
    assert [n.is_dir for n in tree] == [True, True, False, False]


@pytest.mark.spec("TREE-04")
def test_a_files_path_is_its_key_and_a_folders_path_ends_in_a_slash() -> None:
    tree = build_tree(KEYS)

    leaf = find(tree, "live/funders/ballmer-group/sources/2026-05-02_grant.md")
    assert leaf is not None and not leaf.is_dir
    assert leaf.name == "2026-05-02_grant.md"

    folder = find(tree, "live/funders/")
    assert folder is not None and folder.is_dir
    assert folder.path.endswith("/")

    # Nothing anywhere in the tree is absolute or escapes the corpus.
    def walk(nodes):
        for n in nodes:
            yield n
            yield from walk(n.children)

    assert all(not n.path.startswith("/") and ".." not in n.path for n in walk(tree))


@pytest.mark.spec("TREE-05")
def test_a_key_with_no_slash_is_a_root_level_file() -> None:
    tree = build_tree(KEYS)

    readme = find(tree, "README.md")
    assert readme is not None
    assert not readme.is_dir and readme.children == []


@pytest.mark.spec("TREE-06")
def test_an_empty_corpus_yields_an_empty_tree() -> None:
    assert build_tree([]) == []
    assert build_tree(["", "/"]) == []


@pytest.mark.spec("TREE-07")
def test_the_content_addressed_store_is_shown_not_hidden() -> None:
    """`bin/` holds 92 PDFs under names no one can read.

    That is the reason to show it, not the reason to hide it: the operator moved
    those binaries out of the working tree, and a client asking where their PDFs
    went deserves an answer better than "trust us."
    """
    tree = build_tree(KEYS)

    bin_node = find(tree, "bin/")
    assert bin_node is not None
    assert bin_node.count == 2


# ---------------------------------------------------------------------------
# the I/O promise
# ---------------------------------------------------------------------------


class CountingStore(LocalFsStore):
    """A store that remembers how many file bodies were opened."""

    reads = 0

    def read(self, key: str) -> bytes:  # type: ignore[override]
        type(self).reads += 1
        return super().read(key)


@pytest.mark.spec("TREE-08")
def test_painting_the_tree_reads_no_file_bodies(tmp_path: Path) -> None:
    """The promise measured in the only terms that survive a faster laptop.

    Wall-clock would pass anywhere and rot quietly; a read count is what we
    actually mean. `/api/meta` once derived a count and a domain list by opening
    all 845 sources — 20.6 seconds, and a window that looked hung.
    """
    store = CountingStore(tmp_path / "corpus")
    for key in KEYS:
        store.write(key, b"---\ntitle: T\n---\n\nBody.\n")
    CountingStore.reads = 0

    body = TestClient(create_app(store, "test")).get("/api/tree").json()

    assert CountingStore.reads == 0
    assert body["total"] == len(KEYS)
    assert [n["name"] for n in body["tree"]] == ["bin", "live", "README.md"]


@pytest.mark.spec("TREE-09")
def test_the_content_addressed_fan_out_is_collapsed_but_the_key_is_not() -> None:
    """`bin/` shards by the first two hex characters so one directory never holds
    thousands of entries. Drawn literally that is 55 folders called `00`, `05`,
    `09` holding one file each — and since `bin` sorts before `live`, it is the
    first thing anyone sees. The level is a storage optimisation, not
    information.

    What must NOT be collapsed is the key. The tree flattens what it draws, never
    what it hands back, or clicking a binary would 404.
    """
    tree = build_tree(KEYS)

    assert find(tree, "bin/00/") is None
    assert find(tree, "bin/a1/") is None

    bin_node = find(tree, "bin/")
    assert bin_node is not None
    assert [c.is_dir for c in bin_node.children] == [False, False]

    leaf = bin_node.children[0]
    assert (
        leaf.path == "bin/00/0029ed06d59e49407980a51fe7c4110056c2a674f92636d709f1b867161355d5.pdf"
    )
    assert leaf.name.endswith(".pdf")

    # A non-fan-out folder under a flattened prefix is left alone.
    assert find(build_tree(["bin/notes/readme.md"]), "bin/notes/") is not None
