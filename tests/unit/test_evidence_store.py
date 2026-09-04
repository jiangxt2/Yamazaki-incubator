"""Tests for owner-only and traversal-safe evidence storage."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from yamazaki.evidence_store import LocalEvidenceStore


def test_store_writes_owner_only_and_is_idempotent(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    identifier = uuid4()
    first = store.write(identifier, {"metric": 1})
    second = store.write(identifier, {"metric": 1})
    assert first == second
    assert (tmp_path / "evidence").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "evidence" / first[0]).stat().st_mode & 0o777 == 0o600


def test_store_rejects_collision_traversal_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = LocalEvidenceStore(root)
    identifier = uuid4()
    store.write(identifier, {"metric": 1})
    with pytest.raises(ValueError, match="collision"):
        store.write(identifier, {"metric": 2})
    with pytest.raises(ValueError, match="relative"):
        store.read("../outside.json")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = root / "link.json"
    os.symlink(outside, link)
    with pytest.raises(ValueError, match="symbolic"):
        store.read("link.json")
