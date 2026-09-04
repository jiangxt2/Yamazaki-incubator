"""Create the read-only POC control-state schema.

Revision ID: 0001_control_state
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)

from alembic import op

revision: str = "0001_control_state"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clusters",
        Column("cluster_id", String(64), nullable=False),
        Column("engine", String(32), nullable=False),
        Column("payload", JSON(), nullable=False),
        PrimaryKeyConstraint("cluster_id"),
    )
    op.create_table(
        "investigations",
        Column("investigation_id", String(36), nullable=False),
        Column("state", String(32), nullable=False),
        Column("request_payload", JSON(), nullable=False),
        Column("result_payload", JSON(), nullable=True),
        Column("version", Integer(), nullable=False),
        PrimaryKeyConstraint("investigation_id"),
    )
    op.create_table(
        "capability_profiles",
        Column("capability_profile_id", String(36), nullable=False),
        Column("cluster_id", String(64), nullable=False),
        Column("captured_at", DateTime(timezone=True), nullable=False),
        Column("payload", JSON(), nullable=False),
        ForeignKeyConstraint(["cluster_id"], ["clusters.cluster_id"]),
        PrimaryKeyConstraint("capability_profile_id"),
    )
    op.create_index(
        "ix_capability_profiles_cluster_id",
        "capability_profiles",
        ["cluster_id"],
    )
    op.create_table(
        "query_runs",
        Column("query_run_id", String(36), nullable=False),
        Column("engine", String(32), nullable=False),
        Column("cluster_id", String(64), nullable=False),
        Column("engine_query_id", String(256), nullable=False),
        Column("native_fingerprint", String(256), nullable=False),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("payload", JSON(), nullable=False),
        ForeignKeyConstraint(["cluster_id"], ["clusters.cluster_id"]),
        PrimaryKeyConstraint("query_run_id"),
        UniqueConstraint(
            "engine",
            "cluster_id",
            "engine_query_id",
            "started_at",
            name="uq_query_execution_attempt",
        ),
    )
    op.create_index("ix_query_runs_cluster_id", "query_runs", ["cluster_id"])
    op.create_index(
        "ix_query_runs_native_fingerprint",
        "query_runs",
        ["native_fingerprint"],
    )
    op.create_index("ix_query_runs_started_at", "query_runs", ["started_at"])
    op.create_table(
        "evidence_refs",
        Column("evidence_id", String(36), nullable=False),
        Column("query_run_id", String(36), nullable=False),
        Column("source_kind", String(128), nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("payload", JSON(), nullable=False),
        ForeignKeyConstraint(["query_run_id"], ["query_runs.query_run_id"]),
        PrimaryKeyConstraint("evidence_id"),
        UniqueConstraint(
            "query_run_id",
            "source_kind",
            "content_hash",
            name="uq_query_evidence_content",
        ),
    )
    op.create_index(
        "ix_evidence_refs_query_run_id",
        "evidence_refs",
        ["query_run_id"],
    )
    op.create_table(
        "detections",
        Column("detection_id", String(36), nullable=False),
        Column("query_run_id", String(36), nullable=False),
        Column("payload", JSON(), nullable=False),
        ForeignKeyConstraint(["query_run_id"], ["query_runs.query_run_id"]),
        PrimaryKeyConstraint("detection_id"),
    )
    op.create_index("ix_detections_query_run_id", "detections", ["query_run_id"])
    op.create_table(
        "diagnoses",
        Column("diagnosis_id", String(36), nullable=False),
        Column("query_run_id", String(36), nullable=False),
        Column("source", String(32), nullable=False),
        Column("payload", JSON(), nullable=False),
        ForeignKeyConstraint(["query_run_id"], ["query_runs.query_run_id"]),
        PrimaryKeyConstraint("diagnosis_id"),
    )
    op.create_index("ix_diagnoses_query_run_id", "diagnoses", ["query_run_id"])
    op.create_table(
        "recommendations",
        Column("recommendation_id", String(36), nullable=False),
        Column("diagnosis_id", String(36), nullable=False),
        Column("payload", JSON(), nullable=False),
        ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.diagnosis_id"]),
        PrimaryKeyConstraint("recommendation_id"),
    )
    op.create_index(
        "ix_recommendations_diagnosis_id",
        "recommendations",
        ["diagnosis_id"],
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("diagnoses")
    op.drop_table("detections")
    op.drop_table("evidence_refs")
    op.drop_table("query_runs")
    op.drop_table("capability_profiles")
    op.drop_table("investigations")
    op.drop_table("clusters")
