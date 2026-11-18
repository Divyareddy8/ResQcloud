#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

docker compose -p resqcloud logs \
    --no-color \
    --no-log-prefix \
    --since "${LOG_SINCE:-10m}" \
    --follow \
    api coordinator matcher \
    shard0 shard1 shard2 \
    replica0 replica1 replica2 2>&1 |
python3 -u -c '
import sys
import json
import socket

with socket.create_connection(("127.0.0.1", 5000), timeout=30) as sock:
    sock.settimeout(None)
    for line in sys.stdin:
        try:
            event = json.loads(line.strip())
            if not isinstance(event, dict):
                continue
            if "event" not in event or "service" not in event:
                continue
            payload = json.dumps(event) + "\n"
            sock.sendall(payload.encode("utf-8"))
            print("SHIPPED:", event["service"], event["event"], flush=True)
        except (ValueError, TypeError):
            continue
'
