"""Wait for the exact PostgreSQL, ClickHouse, and Doris POC services."""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable

import clickhouse_connect
import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy import create_engine, text


def wait_until(name: str, check: Callable[[], None], *, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    last_error = "unavailable"
    while time.monotonic() < deadline:
        try:
            check()
        except Exception as exc:
            last_error = type(exc).__name__
            time.sleep(2)
        else:
            print(f"{name}: ready")
            return
    raise TimeoutError(f"{name} did not become ready: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    postgres_url = os.environ["YAMAZAKI_DATABASE_URL"]
    clickhouse_password = os.environ["YAMAZAKI_IT_CLICKHOUSE_ADMIN_PASSWORD"]

    def postgres() -> None:
        engine = create_engine(postgres_url)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()

    def clickhouse() -> None:
        client = clickhouse_connect.get_client(
            host="127.0.0.1",
            port=18124,
            username="admin",
            password=clickhouse_password,
        )
        try:
            client.query("SELECT 1")
        finally:
            client.close()

    def doris() -> None:
        connection = pymysql.connect(
            host="127.0.0.1",
            port=19031,
            user="root",
            password="",
            connect_timeout=5,
            read_timeout=5,
            cursorclass=DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW BACKENDS")
                rows = cursor.fetchall()
                if not rows or not any(
                    str(row.get("Alive")).lower() == "true" for row in rows
                ):
                    raise RuntimeError("Doris backend is not alive")
        finally:
            connection.close()

    wait_until("postgres", postgres, timeout=args.timeout)
    wait_until("clickhouse", clickhouse, timeout=args.timeout)
    wait_until("doris", doris, timeout=args.timeout)


if __name__ == "__main__":
    main()
