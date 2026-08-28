#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <base-commit> <head-commit>" >&2
  exit 2
fi

base_commit=$1
head_commit=$2

if ! git rev-parse --verify "${base_commit}^{commit}" >/dev/null 2>&1; then
  echo "DCO check failed: invalid base commit '${base_commit}'." >&2
  exit 2
fi

if ! git rev-parse --verify "${head_commit}^{commit}" >/dev/null 2>&1; then
  echo "DCO check failed: invalid head commit '${head_commit}'." >&2
  exit 2
fi

if ! git merge-base --is-ancestor "${base_commit}" "${head_commit}"; then
  echo "DCO check failed: base commit is not an ancestor of head commit." >&2
  exit 2
fi

checked=0
invalid_commits=()
signoff_pattern='^[^<>[:space:]].* <[^<>[:space:]@]+@[^<>[:space:]]+>$'

while IFS= read -r commit; do
  [[ -n "${commit}" ]] || continue
  checked=$((checked + 1))

  signoffs=$(git show -s --format='%(trailers:key=Signed-off-by,valueonly)' "${commit}")
  valid_signoff=0
  while IFS= read -r signoff; do
    if [[ ${signoff} =~ ${signoff_pattern} ]]; then
      valid_signoff=1
      break
    fi
  done <<< "${signoffs}"

  if [[ ${valid_signoff} -eq 0 ]]; then
    invalid_commits+=("${commit}")
  fi
done < <(git rev-list --reverse "${base_commit}..${head_commit}")

if [[ ${#invalid_commits[@]} -ne 0 ]]; then
  echo "DCO check failed: the following commits lack a valid Signed-off-by trailer:" >&2
  printf '  %s\n' "${invalid_commits[@]}" >&2
  exit 1
fi

printf 'DCO check passed for %d commit(s).\n' "${checked}"
