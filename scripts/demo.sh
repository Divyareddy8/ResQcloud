#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
echo 'Registering water resource'
curl -fsS -X POST "$BASE/resources" -H 'Content-Type: application/json' -d '{"type":"water","location":"Bengaluru","availability":true,"provider":"Rescue NGO"}';echo
echo 'Creating emergency request'
curl -fsS -X POST "$BASE/requests" -H 'Content-Type: application/json' -d '{"type":"water","location":"Bengaluru","details":"Flood relief drinking water","priority":5}';echo
sleep 4
curl -fsS "$BASE/requests";echo
curl -fsS "$BASE/stats";echo
