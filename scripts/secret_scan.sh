#!/usr/bin/env bash
set -euo pipefail

# Shared patterns for the repository scan and the self-test.
# hex32: any raw run of 32+ hexadecimal characters.
hex_regex='[[:xdigit:]]{32,}'
# key_assignment: uppercase ENV-style identifier (group 2) = value of 20+
# non-space chars (group 3). Lowercase names can never match; the sensitive
# suffix check happens in is_sensitive_name.
key_regex="(^|[^[:alnum:]_])([A-Z][A-Z0-9_]*)[[:space:]]*=[[:space:]]*[\"']?([^[:space:]#\"'=|]{20,})"

excluded_path() {
  case "$1" in
    uv.lock|plugins/*.jar|tests/fixtures/*|docs/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_sensitive_name() {
  case "$1" in
    API_KEY|*_API_KEY|SECRET|*_SECRET|TOKEN|*_TOKEN|PASSWORD|*_PASSWORD|PRIVATE_KEY|*_PRIVATE_KEY|ACCESS_KEY|*_ACCESS_KEY)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

line_finding() {
  # Print the pattern name and return 0 for a finding; silent return 1 when clean.
  local line="$1"

  if [[ "$line" =~ $hex_regex ]]; then
    printf '%s\n' 'hex32'
    return 0
  fi

  if [[ "$line" =~ $key_regex ]]; then
    local key_name="${BASH_REMATCH[2]}"
    local value="${BASH_REMATCH[3]}"
    case "${key_name}=${value}" in
      OPENDART_API_KEY=|MIRAE_RAW_REMOTE=user@host|MIRAE_RAW_ROOT=/srv/mirae-graph/raw)
        return 1
        ;;
    esac
    if is_sensitive_name "$key_name"; then
      printf '%s\n' 'key_assignment'
      return 0
    fi
  fi

  return 1
}

scan_file() {
  local file="$1"
  local line_number=0
  local line
  local finding

  [[ -f "$file" ]] || return 0
  excluded_path "$file" && return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_number=$((line_number + 1))
    if finding="$(line_finding "$line")"; then
      printf '%s:%s %s\n' "$file" "$line_number" "$finding"
      return 1
    fi
  done < "$file"
}

expect_clean() {
  local finding
  if finding="$(line_finding "$2")"; then
    printf 'self-test FAIL: expected no finding for %s, got %s\n' "$1" "$finding" >&2
    return 1
  fi
  return 0
}

expect_finding() {
  local finding
  if ! finding="$(line_finding "$2")"; then
    printf 'self-test FAIL: expected %s for %s, got no finding\n' "$3" "$1" >&2
    return 1
  fi
  if [[ "$finding" != "$3" ]]; then
    printf 'self-test FAIL: expected %s for %s, got %s\n' "$3" "$1" "$finding" >&2
    return 1
  fi
  return 0
}

self_test() {
  local failures=0
  # Detection fixtures are built from concatenated parts so this script's own
  # source contains no scannable secret-shaped literal.
  local alpha='abcdefghijklmnopqrstuvwxyz'
  local api_key_value="${alpha}1234567890"
  local password_value="${alpha}123456"
  local hex_run='0123456789abcdef'

  expect_clean 'lowercase python variable assignment' \
    'local_key = row.local_key.strip()' || failures=$((failures + 1))
  expect_clean 'empty example API key placeholder' \
    'OPENDART_API_KEY=' || failures=$((failures + 1))
  expect_clean 'ssh remote placeholder' \
    'MIRAE_RAW_REMOTE=user@host' || failures=$((failures + 1))
  expect_clean 'remote root placeholder' \
    'MIRAE_RAW_ROOT=/srv/mirae-graph/raw' || failures=$((failures + 1))
  expect_clean 'lowercase dictionary key with long value' \
    'payload = {"api_key": "'"${alpha}1234567890"'"}' || failures=$((failures + 1))
  expect_clean 'lowercase code expression' \
    'token = build_request_token(base_url)' || failures=$((failures + 1))

  expect_finding 'uppercase API key assignment' \
    "OPENDART_API_KEY=${api_key_value}" 'key_assignment' || failures=$((failures + 1))
  expect_finding 'uppercase password assignment' \
    "NEO4J_PASSWORD=${password_value}" 'key_assignment' || failures=$((failures + 1))
  expect_finding 'raw 32-character hex token' \
    "${hex_run}${hex_run}" 'hex32' || failures=$((failures + 1))

  if (( failures > 0 )); then
    printf 'secret scan self-test: FAILED with %s assertion failure(s)\n' "$failures" >&2
    return 1
  fi

  echo 'secret scan self-test: OK'
}

main() {
  if [[ "${1:-}" = '--self-test' ]]; then
    self_test
    return
  fi

  local files=()
  local file
  local tracked

  if ! tracked="$(git ls-files)"; then
    printf 'secret scan: cannot list tracked files\n' >&2
    return 1
  fi

  while IFS= read -r file; do
    files+=("$file")
  done < <({ printf '%s\n' "$tracked"; printf '%s\n' .env.example; } | sort -u)

  for file in "${files[@]}"; do
    scan_file "$file"
  done

  echo 'secret scan: OK'
}

main "$@"
