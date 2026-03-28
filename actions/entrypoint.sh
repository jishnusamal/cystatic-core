#!/usr/bin/env bash
set -euo pipefail

: "${CYSTATIC_API_URL:?Set CYSTATIC_API_URL (pass api_url to the action)}"
: "${GITHUB_REPOSITORY:?}"

REF="${CYSTATIC_REF:-${GITHUB_SHA}}"

# Placeholder: POST /v1/blast-radius with repo + PR context when wired to list of changed files.
curl -sS -X POST "${CYSTATIC_API_URL%/}/v1/blast-radius" \
  -H "Content-Type: application/json" \
  -d "{\"repo_url\":\"https://github.com/${GITHUB_REPOSITORY}\",\"ref\":\"${REF}\",\"changed_paths\":[]}" \
  || true

echo "Cystatic entrypoint finished (stub)."
