"""Optional localhost-only read API."""

from __future__ import annotations

import hmac
from typing import Any

from yamazaki.ports import ControlStateRepositoryPort


def create_app(
    repository: ControlStateRepositoryPort,
    *,
    api_token: str,
) -> Any:
    """Create the five read-only endpoints defined by the POC plan."""

    if not api_token:
        raise ValueError("api_token must be configured")
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Query
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install the service extra to use the API") from exc

    application = FastAPI(title="Yamazaki", version="0.1.0a0")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {api_token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/clusters", dependencies=[Depends(require_token)])
    def clusters() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in repository.list_clusters()]

    @application.get("/query-runs", dependencies=[Depends(require_token)])
    def query_runs(
        limit: int = Query(default=100, ge=1, le=1_000),
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in repository.list_query_runs(limit=limit)
        ]

    @application.get("/detections", dependencies=[Depends(require_token)])
    def detections(
        limit: int = Query(default=100, ge=1, le=1_000),
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in repository.list_detections(limit=limit)
        ]

    @application.get("/diagnoses", dependencies=[Depends(require_token)])
    def diagnoses(
        limit: int = Query(default=100, ge=1, le=1_000),
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in repository.list_diagnoses(limit=limit)
        ]

    return application
