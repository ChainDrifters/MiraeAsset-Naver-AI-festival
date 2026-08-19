#!/usr/bin/env bash
set -euo pipefail

excluded_path() {
  case "$1" in
    uv.lock|plugins/*.jar|tests/fixtures/*|docs/*) return 0 ;;
    *) return 1 ;;
  esac
}

scan_file() {
  local file="$1"
  local line_number=0
  local line
  local hex_regex='[[:xdigit:]]{32,}'
  local key_regex="(^|[^[:alnum:]_])([[:alnum:]_]*[Kk][Ee][Yy])[[:space:]]*=[[:space:]]*[\"']?([^[:space:]#\"']{20,})"

  [[ -f "$file" ]] || return 0
  excluded_path "$file" && return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_number=$((line_number + 1))

    if [[ "$line" =~ $hex_regex ]]; then
      printf '%s:%s %s\n' "$file" "$line_number" "hex32"
      return 1
    fi

    if [[ "$line" =~ $key_regex ]]; then
      local key_name="${BASH_REMATCH[2]}"
      local value="${BASH_REMATCH[3]}"
      case "${key_name}=${value}" in
        OPENDART_API_KEY=|MIRAE_RAW_REMOTE=user@host|MIRAE_RAW_ROOT=/srv/mirae-graph/raw) ;;
        *)
          printf '%s:%s %s\n' "$file" "$line_number" "key_assignment"
          return 1
          ;;
      esac
    fi
  done < "$file"
}

main() {
  local files=()
  local file

  while IFS= read -r file; do
    files+=("$file")
  done < <({ git ls-files; printf '%s\n' .env.example; } | sort -u)

  for file in "${files[@]}"; do
    scan_file "$file"
  done

  echo 'secret scan: OK'
}

main "$@"
