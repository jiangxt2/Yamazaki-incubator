#!/usr/bin/env bash

set -euo pipefail

umask 077

project_name="yamazaki-it-read-only"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
compose_file="${project_root}/tests/integration/docker-compose.yml"
temporary_dir="$(mktemp -d /tmp/yamazaki-it.XXXXXX)"
environment_file="${temporary_dir}/environment"
before_images="${temporary_dir}/dangling-before"
after_images="${temporary_dir}/dangling-after"
log_file="${project_root}/.local/test-logs/dual-engine-it.log"
owned_resources=false

mkdir -p "${project_root}/.local/test-logs"
chmod 700 "${project_root}/.local" "${project_root}/.local/test-logs"

docker_cli() {
  env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy docker "$@"
}

compose() {
  docker_cli compose --project-name "${project_name}" \
    --env-file "${environment_file}" --file "${compose_file}" "$@"
}

cleanup() {
  original_status=$?
  set +e
  if [[ "${owned_resources}" != true ]]; then
    if command -v trash >/dev/null 2>&1; then
      trash "${temporary_dir}"
    else
      chmod -R 000 "${temporary_dir}"
    fi
    exit "${original_status}"
  fi
  if [[ "${original_status}" -ne 0 ]]; then
    compose ps --all >"${project_root}/.local/test-logs/compose-state.log" 2>&1
    compose logs --no-color |
      sed -E \
        -e "s/(IDENTIFIED( WITH [^ ]+)? BY ')[^']*'/\1[REDACTED]'/Ig" \
        -e 's/[0-9a-f]{48}/[REDACTED]/g' \
        >"${project_root}/.local/test-logs/compose.log"
    chmod 600 "${project_root}/.local/test-logs/compose-state.log" \
      "${project_root}/.local/test-logs/compose.log"
  fi
  compose down --volumes --remove-orphans >/dev/null 2>&1
  docker_cli image ls --filter dangling=true --quiet | sort >"${after_images}"
  if ! cmp -s "${before_images}" "${after_images}"; then
    echo "Docker IT changed the pre-existing dangling image baseline" >&2
    cleanup_status=1
  else
    cleanup_status="${original_status}"
  fi
  if docker_cli ps --all --quiet \
    --filter "label=com.docker.compose.project=${project_name}" | grep -q .; then
    echo "Docker IT left project containers behind" >&2
    cleanup_status=1
  fi
  if docker_cli network ls --quiet \
    --filter "label=com.docker.compose.project=${project_name}" | grep -q .; then
    echo "Docker IT left project networks behind" >&2
    cleanup_status=1
  fi
  if docker_cli volume ls --quiet \
    --filter "label=com.docker.compose.project=${project_name}" | grep -q .; then
    echo "Docker IT left project volumes behind" >&2
    cleanup_status=1
  fi
  if command -v trash >/dev/null 2>&1; then
    trash "${temporary_dir}"
  else
    chmod -R 000 "${temporary_dir}"
    echo "Temporary credentials remain unreadable at ${temporary_dir}" >&2
  fi
  exit "${cleanup_status}"
}

trap cleanup EXIT INT TERM

for port in 15433 18124 18031 19031; do
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN | grep -q .; then
    echo "Required localhost port is already in use: ${port}" >&2
    exit 1
  fi
done

if docker_cli ps --all --quiet \
  --filter "label=com.docker.compose.project=${project_name}" | grep -q .; then
  echo "Compose project already has containers: ${project_name}" >&2
  exit 1
fi
if docker_cli network ls --quiet \
  --filter "label=com.docker.compose.project=${project_name}" | grep -q .; then
  echo "Compose project already has networks: ${project_name}" >&2
  exit 1
fi
if docker_cli volume ls --quiet \
  --filter "label=com.docker.compose.project=${project_name}" | grep -q .; then
  echo "Compose project already has volumes: ${project_name}" >&2
  exit 1
fi

for image in \
  "postgres:16.14@sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b" \
  "clickhouse/clickhouse-server:25.3.2.39@sha256:8745843b17f92db1765025009772ec1d87dfdcaa95deabca6b802a66cb669d30" \
  "apache/doris:fe-4.0.6@sha256:830863e9ff8af4b354df5303b1235c11b2f822fa3125b83a1627e498c5c251cf" \
  "apache/doris:be-4.0.6@sha256:72e58021c2fa110350269e587d6c74a28579d3c1ed563023cb784a3824f4ad87"; do
  docker_cli image inspect "${image}" >/dev/null
done

postgres_password="$(openssl rand -hex 24)"
clickhouse_admin_password="$(openssl rand -hex 24)"
clickhouse_reader_password="$(openssl rand -hex 24)"
doris_reader_password="$(openssl rand -hex 24)"

{
  echo "YAMAZAKI_IT_POSTGRES_PASSWORD=${postgres_password}"
  echo "YAMAZAKI_IT_CLICKHOUSE_ADMIN_PASSWORD=${clickhouse_admin_password}"
} >"${environment_file}"
chmod 600 "${environment_file}"

export YAMAZAKI_DATABASE_URL="postgresql+psycopg://yamazaki:${postgres_password}@127.0.0.1:15433/yamazaki"
export YAMAZAKI_IT_CLICKHOUSE_ADMIN_PASSWORD="${clickhouse_admin_password}"
export YAMAZAKI_IT_CLICKHOUSE_READER_PASSWORD="${clickhouse_reader_password}"
export YAMAZAKI_IT_DORIS_READER_PASSWORD="${doris_reader_password}"
export YAMAZAKI_IT_EVIDENCE_DIR="${temporary_dir}/evidence"

docker_cli image ls --filter dangling=true --quiet | sort >"${before_images}"
compose config --quiet
owned_resources=true
compose up --detach --no-build --pull never

cd "${project_root}"
uv run python scripts/wait_for_services.py --timeout 300
uv run alembic upgrade head
uv run pytest tests/integration/test_dual_engine.py -m integration -v \
  2>&1 | tee "${log_file}"
chmod 600 "${log_file}"
