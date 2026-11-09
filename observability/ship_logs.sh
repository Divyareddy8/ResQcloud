#!/usr/bin/env bash
# Streams JSON application logs to Logstash; requires netcat.
set -euo pipefail
docker compose logs --no-log-prefix --follow api coordinator matcher shard0 shard1 shard2 replica0 replica1 replica2 | while IFS= read -r line; do
  [[ "$line" == \{* ]] && printf '%s\n' "$line" || true
done | nc localhost 5000
