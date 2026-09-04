"""Minimal CLI for validation, probing, investigation, and local serving."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from yamazaki.api import create_app
from yamazaki.config import load_config, resolve_credential, resolve_database_url
from yamazaki.runtime import build_runtime
from yamazaki.service import recent_request


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="yamazaki")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("validate", "probe", "run", "serve"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        if name == "run":
            command.add_argument("--minutes", type=int, default=15)
        if name == "serve":
            command.add_argument("--port", type=int, default=8080)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "validate":
        resolve_database_url(config)
        for cluster in config.clusters:
            resolve_credential(cluster)
        if not os.environ.get(config.api_token_env):
            raise ValueError(
                "required API token environment variable is unset: "
                f"{config.api_token_env}"
            )
        print(json.dumps({"status": "valid", "clusters": len(config.clusters)}))
        return 0

    runtime = build_runtime(config)
    try:
        if args.command == "probe":
            profiles = [
                adapter.probe_capabilities().model_dump(mode="json")
                for adapter in runtime.adapters
            ]
            print(json.dumps(profiles, default=str, sort_keys=True))
            return 0
        if args.command == "run":
            request = recent_request(
                tuple(cluster.cluster_id for cluster in config.clusters),
                minutes=args.minutes,
            )
            result = runtime.coordinator.investigate(request)
            print(result.model_dump_json())
            return 0 if result.state.value in {"succeeded", "degraded"} else 1
        token = os.environ.get(config.api_token_env)
        if not token:
            raise ValueError(
                "required API token environment variable is unset: "
                f"{config.api_token_env}"
            )
        try:
            import uvicorn
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install the service extra to use serve") from exc
        uvicorn.run(
            create_app(runtime.repository, api_token=token),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )
        return 0
    except KeyboardInterrupt:
        runtime.coordinator.cancellation.cancel()
        return 130
    finally:
        runtime.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
