#!/usr/bin/env bash
set -euo pipefail
curl -fsS -X POST http://localhost:8001/internal/reconcile
