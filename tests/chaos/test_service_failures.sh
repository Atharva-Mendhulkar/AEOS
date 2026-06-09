#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
API_HEALTH_URL="${AEOS_HEALTH_URL:-http://localhost:8000/health}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$PROJECT_DIR"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

wait_for_gateway() {
  local deadline=$((SECONDS + 90))
  until curl -fsS "$API_HEALTH_URL" >/dev/null; do
    if (( SECONDS > deadline )); then
      echo "AEOS gateway did not recover before timeout: $API_HEALTH_URL" >&2
      return 1
    fi
    sleep 3
  done
}

assert_running() {
  local service="$1"
  if ! compose ps --status running "$service" | grep -q "$service"; then
    echo "Expected $service to be running" >&2
    compose ps
    return 1
  fi
}

echo "Starting AEOS stack for chaos tests..."
compose up -d
wait_for_gateway

echo "Chaos: kill Redis and verify stack recovers after restart..."
compose kill redis
sleep 5
compose up -d redis
wait_for_gateway
assert_running redis

echo "Chaos: kill PostgreSQL and verify stack recovers after restart..."
compose kill postgres
sleep 5
compose up -d postgres
wait_for_gateway
assert_running postgres

echo "Chaos: kill Workflow Engine mid-run and verify restart restores service..."
compose kill workflow-engine
sleep 5
compose up -d workflow-engine
wait_for_gateway
assert_running workflow-engine

echo "Chaos: kill Observability Service and verify restart restores event endpoint..."
compose kill observability-service
sleep 5
compose up -d observability-service
wait_for_gateway
assert_running observability-service

echo "Chaos tests completed successfully."
