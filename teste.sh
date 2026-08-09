#!/usr/bin/env bash

set -Eeuo pipefail

BASE_URL="${BASE_URL:-https://reporter-shiftwise-ai.apps-crc.testing}"
REPORT_FILE="${REPORT_FILE:-default-local.md}"
TEMP_DIR="$(mktemp -d)"
BODY_FILE="${TEMP_DIR}/body"
HEADERS_FILE="${TEMP_DIR}/headers"

trap 'rm -rf "$TEMP_DIR"' EXIT

fail() {
    printf '[FAIL] %s\n' "$*" >&2
    exit 1
}

request() {
    local description="$1"
    local path="$2"
    local expected_status="$3"
    local status

    status="$(curl --silent --show-error --insecure \
        --dump-header "$HEADERS_FILE" \
        --output "$BODY_FILE" \
        --write-out '%{http_code}' \
        "${BASE_URL}${path}")" || fail "${description}: request failed"

    [[ "$status" == "$expected_status" ]] \
        || fail "${description}: expected HTTP ${expected_status}, received ${status}: $(cat "$BODY_FILE")"

    printf '[PASS] %s (HTTP %s)\n' "$description" "$status"
}

assert_body_contains() {
    local description="$1"
    local expected="$2"

    grep --fixed-strings --quiet "$expected" "$BODY_FILE" \
        || fail "${description}: response body does not contain '${expected}': $(cat "$BODY_FILE")"
}

assert_header_contains() {
    local description="$1"
    local expected="$2"

    grep --ignore-case --fixed-strings --quiet "$expected" "$HEADERS_FILE" \
        || fail "${description}: response headers do not contain '${expected}'"
}

request "Health endpoint" "/health" "200"
assert_body_contains "Health endpoint" '"status":"ok"'

request "Existing Markdown report" "/report/${REPORT_FILE}" "200"
[[ -s "$BODY_FILE" ]] || fail "Existing Markdown report: response body is empty"
assert_header_contains "Existing Markdown report" "content-type: text/markdown"
assert_header_contains "Existing Markdown report" "content-disposition: inline;"

request "Invalid report extension" "/report/teste.txt" "400"
assert_body_contains "Invalid report extension" '"detail":"Informe somente o nome de um arquivo com extensão .md"'

request "Nested report path" "/report/subdir/default-local.md" "404"
assert_body_contains "Nested report path" '"detail":"Not Found"'

request "Missing Markdown report" "/report/inexistente.md" "404"
assert_body_contains "Missing Markdown report" '"detail":"Arquivo não encontrado: inexistente.md"'

request "OpenAPI specification" "/openapi.json" "200"
assert_body_contains "OpenAPI specification" '"title":"Assessment API"'
assert_body_contains "OpenAPI specification" '"version":"1.0.0"'

printf '\nAll API tests passed. Documentation: %s/docs\n' "$BASE_URL"
