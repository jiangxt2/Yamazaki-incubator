"""Tests for fail-closed SQL redaction."""

import pytest
from sqlglot.errors import ParseError

from yamazaki.redaction import redact_sql


def test_redaction_removes_literals_identifiers_and_comments() -> None:
    result = redact_sql(
        "SELECT secret_column FROM customer_table "
        "WHERE account = 'sensitive' /* note */"
    )
    assert result.status == "redacted"
    assert result.structure is not None
    assert "sensitive" not in result.structure
    assert "customer_table" not in result.structure
    assert "secret_column" not in result.structure
    assert "note" not in result.structure


def test_redaction_rejects_non_read_only_and_multiple_statements() -> None:
    assert redact_sql("DROP TABLE important").reason == "non_read_only_prefix"
    multiple = redact_sql("SELECT 1; DROP TABLE important")
    assert multiple.status == "omitted"
    assert multiple.reason == "unsupported_statement_shape"


def test_redaction_failure_does_not_echo_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "SELECT 'sensitive-value'"

    def fail_parse(*args: object, **kwargs: object) -> list[object]:
        raise ParseError("parser detail")

    monkeypatch.setattr("yamazaki.redaction.parse", fail_parse)
    result = redact_sql(secret)
    assert result.status == "omitted"
    assert "sensitive-value" not in result.model_dump_json()
    assert "sensitive-value" not in repr(result)
