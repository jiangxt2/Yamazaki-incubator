"""Permission-restricted local evidence storage for development and POC use."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from yamazaki.contracts import content_digest


class LocalEvidenceStore:
    """Store opaque JSON files with owner-only permissions."""

    def __init__(self, root: Path) -> None:
        if root.exists() and root.is_symlink():
            raise ValueError("evidence root must not be a symbolic link")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        self._root = root.resolve()

    def write(self, evidence_id: UUID, payload: dict[str, Any]) -> tuple[str, str]:
        locator = f"{evidence_id}.json"
        target = self._resolve(locator, must_exist=False)
        digest = content_digest(payload)
        data = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        if target.exists():
            if target.is_symlink():
                raise ValueError("evidence target must not be a symbolic link")
            existing = json.loads(target.read_text(encoding="utf-8"))
            if content_digest(existing) != digest:
                raise ValueError("evidence identity collision")
            return locator, digest
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(target, 0o600)
        return locator, digest

    def read(self, locator: str) -> dict[str, Any]:
        target = self._resolve(locator, must_exist=True)
        value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("evidence payload must be an object")
        return value

    def _resolve(self, locator: str, *, must_exist: bool) -> Path:
        candidate = Path(locator)
        if (
            candidate.is_absolute()
            or len(candidate.parts) != 1
            or candidate.name != locator
        ):
            raise ValueError("evidence locator must be one relative opaque file name")
        target = self._root / candidate
        if target.is_symlink():
            raise ValueError("evidence locator must not be a symbolic link")
        if must_exist and not target.is_file():
            raise FileNotFoundError(locator)
        if target.parent.resolve() != self._root:
            raise ValueError("evidence locator escapes the configured root")
        return target
