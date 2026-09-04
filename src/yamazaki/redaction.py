"""Fail-closed SQL structure redaction."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field
from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel, ParseError

from yamazaki.contracts import FrozenContract

_READ_ONLY_PREFIX = re.compile(r"^\s*(SELECT|WITH|SHOW|EXPLAIN)\b", re.IGNORECASE)


class RedactionResult(FrozenContract):
    """Safe SQL structure or an omission reason without the original text."""

    status: Literal["redacted", "omitted"]
    statement_type: str = Field(min_length=1, max_length=64)
    structure: str | None = Field(default=None, max_length=4_000)
    reason: str | None = Field(default=None, max_length=128)


def redact_sql(sql: str, *, dialect: str | None = None) -> RedactionResult:
    """Redact literals, identifiers, and comments from one read-only statement."""

    if not _READ_ONLY_PREFIX.match(sql):
        return RedactionResult(
            status="omitted",
            statement_type="unsupported",
            reason="non_read_only_prefix",
        )
    try:
        statements = parse(sql, read=dialect, error_level=ErrorLevel.RAISE)
    except (ParseError, ValueError):
        return RedactionResult(
            status="omitted",
            statement_type=_prefix(sql),
            reason="parse_failed",
        )
    if (
        len(statements) != 1
        or statements[0] is None
        or isinstance(statements[0], exp.Command)
    ):
        return RedactionResult(
            status="omitted",
            statement_type=_prefix(sql),
            reason="unsupported_statement_shape",
        )

    expression = statements[0]

    def replace(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Literal):
            return exp.Placeholder()
        if isinstance(node, exp.Identifier):
            return exp.Identifier(this="identifier", quoted=False)
        return node

    redacted = expression.transform(replace).sql(comments=False)
    return RedactionResult(
        status="redacted",
        statement_type=expression.key.upper(),
        structure=redacted[:4_000],
    )


def _prefix(sql: str) -> str:
    match = re.match(r"^\s*([A-Za-z]+)", sql)
    return match.group(1).upper()[:64] if match else "unknown"
